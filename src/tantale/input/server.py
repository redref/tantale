# coding=utf-8

from __future__ import print_function

import os
import sys
import signal
import traceback
import logging
import time

import socket
import select
from six import b as bytes
from threading import Thread, Lock

from tantale.utils import load_backend
from tantale.input.check import Check

try:
    from Queue import Full
except:
    from queue import Full

try:
    from setproctitle import setproctitle, getproctitle
except ImportError:
    setproctitle = None


class InputServer(object):
    """
    Listening thread for Input function
    """
    def __init__(self, config):
        # Initialize Logging
        self.log = logging.getLogger('tantale.input')

        # Process signal
        self.running = True

        # Initialize Members
        self.config = config

        self.port = int(self.config['modules']['Input']['port'])

        self.ttl = None
        if self.config['modules']['Input']['ttl']:
            self.ttl = int(self.config['modules']['Input']['ttl'])

        self.freshness_timeout = None
        if self.config['modules']['Input']['freshness_timeout']:
            self.freshness_timeout = int(
                self.config['modules']['Input']['freshness_timeout'])

    def run(self, check_queue, init_done):
        if setproctitle:
            setproctitle('%s - Input' % getproctitle())

        # Open listener
        connections = []
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            port = self.port
            s.bind(('', port))
        except socket.error as msg:
            self.log.critical('Socket bind failed.')
            self.log.debug(traceback.format_exc())
            return

        s.listen(1024)
        self.log.info("Listening on %s" % port)
        init_done.set()
        connections.append(s)

        # Signals
        pipe = os.pipe()
        connections.append(pipe[0])

        def sig_handler(signum, frame):
            self.log.debug("%s received" % signum)
            self.running = False
            os.write(pipe[1], bytes("END\n"))
        signal.signal(signal.SIGTERM, sig_handler)

        # Logic
        queue_state = True
        stack = ""
        while self.running:
            r = None
            try:
                r, w, e = select.select(connections, [], [])
            except:
                # Handle "Interrupted system call"
                break

            for sock in r:
                if sock == s:
                    # New clients
                    sockfd, addr = s.accept()
                    connections.append(sockfd)
                else:
                    if isinstance(sock, int):
                        data = os.read(sock, 4096)
                    else:
                        data = sock.recv(4096)

                    if data == bytes(''):
                        # Disconnect
                        connections.remove(sock)

                    data = stack + data.decode('utf-8')

                    while True:
                        idx = data.find('\n')
                        if idx == -1:
                            stack = data
                            break
                        line = data[:idx]
                        data = data[idx + 1:]

                        if line == "END":
                            break
                        else:
                            try:
                                check_queue.put(line, block=False)
                            except Full:
                                self.log.error('Queue full, dropping')
                            except (EOFError, IOError):
                                # Queue died
                                self.running = False
                                queue_state = False
                                break

        # Stop backend
        if queue_state:
            try:
                check_queue.put(None, block=False)
            except:
                pass

        s.close()
        self.log.info("Exit")

    def input_backend(self, check_queue):
        if setproctitle:
            setproctitle('%s - Input_Backend' % getproctitle())

        # Ignore signals / stop triggered by Input main thread
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

        # Load backends
        backends = []
        for backend in self.config['backends']:
            try:
                cls = load_backend('input', backend)
                backends.append(
                    cls(self.config['backends'].get(backend, None)))
            except:
                self.log.error('Error loading backend %s' % backend)
                self.log.debug(traceback.format_exc())
        if len(backends) == 0:
            self.log.critical('No available backends')
            return

        send_lock = Lock()

        def ttl_thread(ttl, backend):
            time.sleep(ttl)
            # Force send it ttl reached
            if (len(backend.checks) > 0 and
               (time.time() - backend.checks[0].parsing_ts) >= ttl):
                send_lock.acquire()
                backend.send()
                send_lock.release()

        # Logic
        while self.running:
            try:
                string = check_queue.get(block=True, timeout=None)
            except EOFError:
                break

            if string is not None:

                for check in Check.parse(string, self.log):

                    for backend in backends:
                        send_lock.acquire()
                        backend._process(check)
                        send_lock.release()

                        if (self.ttl and len(backend.checks) > 0 and
                           (not backend.ttl_thread or
                           not backend.ttl_thread.isAlive())):
                            backend.ttl_thread = Thread(
                                target=ttl_thread, args=(self.ttl, backend))
                            backend.ttl_thread.daemon = True
                            backend.ttl_thread.start()

                check_queue.task_done()

            else:
                # Terminate branch
                self.running = False
                for backend in backends:
                    backend._flush()
                self.log.debug('Backends flushed')

        self.log.info("Exit")

    def input_freshness(self):
        if setproctitle:
            setproctitle('%s - Input_Freshness' % getproctitle())

        # Signals
        def sig_handler(signum, frame):
            self.log.debug("%s received" % signum)
            self.running = False
        signal.signal(signal.SIGTERM, sig_handler)

        # Load backends
        backends = []
        for backend in self.config['backends']:
            try:
                cls = load_backend('input', backend)
                backends.append(
                    cls(self.config['backends'].get(backend, None)))
            except:
                self.log.error('Error loading backend %s' % backend)
                self.log.debug(traceback.format_exc())
        if len(backends) == 0:
            self.log.critical('No available backends')
            return

        # Grace time of one timeout
        time.sleep(self.freshness_timeout)

        # Logic
        while self.running:
            self.log.debug('Run update')

            start = int(time.time())

            for backend in backends:
                backend.freshness(self.freshness_timeout, 2, 'OUTDATED - ')

            exec_time = int(time.time()) - start

            # If faster then freshness_timeout / 2, sleep a bit
            if exec_time < (self.freshness_timeout / 2):
                time.sleep(self.freshness_timeout / 2 - exec_time)

            self.log.debug('End update')

        self.log.info("Exit")
