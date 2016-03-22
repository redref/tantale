# coding=utf-8

from __future__ import print_function

import os
import signal
import traceback
import logging

import select
import socket
from threading import Thread, Event

from tantale.utils import load_backend
from tantale.livestatus.query import Query

try:
    from setproctitle import setproctitle, getproctitle
except ImportError:
    setproctitle = None


class LivestatusServer(object):
    """
    Listening thread for Input function
    """
    def __init__(self, config):
        # Initialize Logging
        self.log = logging.getLogger('tantale')

        # Process signal
        self.stop = Event()

        # Initialize Members
        self.config = config

        # Load backends
        self.backends = []
        for backend in self.config['backends']:
            try:
                cls = load_backend('livestatus', backend)
                self.backends.append(
                    cls(self.config['backends'].get(backend, None)))
            except:
                self.log.error('Error loading backend %s' % backend)
                self.log.debug(traceback.format_exc())
        if len(self.backends) == 0:
            self.log.critical('No available backends')
            return

    def handle_livestatus_query(self, sock, request):
        queryobj = Query.parse(sock, request)
        queryobj._query(self.backends)
        queryobj._flush()
        return queryobj.keepalive

    def handle_client(self, socket):
        run = True
        request = ""
        while not self.stop.is_set() and run:
            try:
                r = None
                r, w, e = select.select([socket], [], [], 300)
            except:
                # Handle "Interrupted system call"
                break

            if r is not None:
                sock = r[0]
                f = sock.makefile()

                while True:
                    data = f.readline()
                    if data is None or data == '':
                        # Abnormal - closing thread
                        run = False
                        try:
                            sock.shutdown(socket.SHUT_RDWR)
                            sock.close()
                        except:
                            pass
                        break
                    elif data.strip() == '':
                        # Empty line - process query
                        if request != "":
                            keep = self.handle_livestatus_query(sock, request)
                            if not keep:
                                break
                            else:
                                request = ""
                        break
                    else:
                        # Append to query
                        request += str(data)
            else:
                # Timeout waiting
                run = False
                break

    def livestatus(self):
        if setproctitle:
            setproctitle('%s - Livestatus' % getproctitle())

        # Open listener
        connections = []
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            port = int(self.config['modules']['Livestatus']['port'])
            s.bind(('', port))
        except socket.error as msg:
            self.log.critical('Socket bind failed.')
            self.log.debug(traceback.format_exc())
            return

        s.listen(1024)
        self.log.info("Listening on %s" % port)
        connections.append(s)

        # Signals
        pipe = os.pipe()
        connections.append(pipe[0])

        def sig_handler(signum, frame):
            self.log.debug("%s received" % signum)
            self.stop.set()
            os.write(pipe[1], bytes('END'))
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        # Logic
        queue_state = True
        while not self.stop.is_set():
            try:
                r = None
                r, w, e = select.select(connections, [], [])
            except:
                # Handle "Interrupted system call"
                break

            for sock in r:
                if sock == s:
                    # New clients
                    sockfd, addr = s.accept()
                    t = Thread(target=self.handle_client, args=(sockfd,))
                    t.daemon = True
                    t.start()
                else:
                    # Pipe receive something - exit
                    break

        s.close()
        self.log.info("Exit")
