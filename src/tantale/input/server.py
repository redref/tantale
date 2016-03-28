# coding=utf-8

from __future__ import print_function

import os
import signal
import traceback
import logging

import socket
import select
from six import b as bytes

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
        self.log = logging.getLogger('tantale')

        # Process signal
        self.running = True

        # Initialize Members
        self.config = config

    def run(self, check_queue, init_done):
        if setproctitle:
            setproctitle('%s - Input' % getproctitle())

        # Open listener
        connections = []
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            port = int(self.config['modules']['Input']['port'])
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
            os.write(pipe[1], bytes('END'))
        signal.signal(signal.SIGTERM, sig_handler)

        # Logic
        queue_state = True
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
                    try:
                        if isinstance(sock, int):
                            raise Exception('Select call returned int')

                        f = sock.makefile()
                        for line in f.readlines():
                            if line == 'END':
                                break
                            try:
                                check_queue.put(line, block=False)
                            except Full:
                                self.log.error('Queue full, dropping')
                            except (EOFError, IOError):
                                # Queue died
                                self.running = False
                                queue_state = False
                                break
                    except:
                        self.log.debug(traceback.format_exc())
                        connections.remove(sock)

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

        # Ignore signals
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

        # Logic
        while self.running:
            try:
                check = check_queue.get(block=True, timeout=None)
            except EOFError:
                break
            if check is not None:
                # self.log.debug('Check: %s' % check.strip())
                for backend in backends:
                    backend._process(Check.parse(check, self.log))
                check_queue.task_done()
            else:
                # Call on terminate to flush cache
                self.running = False
                for backend in backends:
                    backend._flush()
                self.log.debug('Backends flushed')

        self.log.info("Exit")
