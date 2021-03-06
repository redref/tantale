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
        self.ttl = int(self.config['modules']['Input']['ttl'])
        self.freshness_factor = int(
            self.config['modules']['Input']['freshness_factor'])
        self.freshness_interval = int(
            self.config['modules']['Input']['freshness_interval'])

    def run(self, check_queue, init_done):
        if setproctitle:
            setproctitle('%s - Input' % getproctitle())

        # Open listener
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

        # Create a poller object
        connections = select.poll()
        poll_map = select.POLLIN | select.POLLPRI | select.POLLHUP
        fd_to_socket = {s.fileno(): s}
        connections.register(s, poll_map)

        def sig_handler(signum, frame):
            self.log.debug("%s received" % signum)
            self.running = False
            s.close()
        signal.signal(signal.SIGTERM, sig_handler)

        # Logic
        queue_state = True
        stack = {}

        try:
            while self.running:
                r = None
                try:
                    poll_array = connections.poll()
                except:
                    # Handle "Interrupted system call"
                    break

                for fd, event in poll_array:
                    sock = fd_to_socket[fd]

                    if sock is s:
                        if event & select.POLLNVAL:
                            # Stop server
                            break
                        else:
                            # New clients
                            sockfd, addr = s.accept()
                            sockfd.setblocking(0)
                            fd_to_socket[sockfd.fileno()] = sockfd
                            connections.register(sockfd, poll_map)

                    elif event & (select.POLLIN | select.POLLPRI):
                        data = sock.recv(4096).decode('utf-8')
                        key = sock.getpeername()

                        if data == '':
                            # Disconnect
                            del stack[key]
                            connections.unregister(fd)
                            continue

                        if (
                            data[0] != '{' and
                            key in stack and stack[key] != ""
                        ):
                            data = stack[key] + data.decode('utf-8')

                        while True:
                            idx = data.find('\n')
                            if idx == -1:
                                stack[key] = data
                                break
                            line = data[:idx]
                            data = data[idx + 1:]

                            try:
                                check_queue.put(line, block=False)
                            except Full:
                                self.log.error('Queue full, dropping')

                    elif event & select.POLLHUP:
                        # Hung up clients
                        sock.close()
                        connections.unregister(fd)
        except:
            self.log.critical("Fatal Input error")
            self.log.debug(traceback.format_exc())
        finally:
            self.log.info("Exit")
            check_queue.put(None, block=False)

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

                for check in Check.parse(
                    string, self.freshness_factor, self.log
                ):

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

    def freshness_worker(self):
        # Save current time (startup grace)
        start_time = time.time()

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

        while True:
            self.log.debug('Run update')

            start = int(time.time())

            for backend in backends:
                backend.freshness(
                    2, 'OUTDATED - ', start_time, self.freshness_interval)

            self.log.debug('End update')

            exec_time = int(time.time()) - start

            if exec_time < self.freshness_interval:
                time.sleep(self.freshness_interval - exec_time)

    def input_freshness(self):
        if setproctitle:
            setproctitle('%s - Input_Freshness' % getproctitle())

        # Signals
        def sig_handler(signum, frame):
            self.log.debug("%s received" % signum)
        signal.signal(signal.SIGTERM, sig_handler)

        # Making a daemon thread to handle instant stop
        t = Thread(target=self.freshness_worker)
        t.daemon = True
        t.start()

        signal.pause()
        self.log.info("Exit")
