# coding=utf-8

from __future__ import print_function

import os
import signal
import traceback
import logging
from six import b as bytes

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

    def handle_client(self, client_socket):
        run = True
        request = ""
        stack = ""
        while not self.stop.is_set() and run:
            try:
                r = None
                r, w, e = select.select([client_socket], [], [], 300)
            except:
                # Handle "Interrupted system call"
                break

            if r is not None:
                sock = r[0]
                data = sock.recv(4096)
                if data == bytes(''):
                    # Closing thread
                    run = False
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                        sock.close()
                    except:
                        pass
                    break

                data = stack + data.decode('utf-8')

                for line in data.split("\n"):
                    if line == "":
                        # Empty line - process query
                        if request != "":
                            keep = self.handle_livestatus_query(sock, request)
                            if not keep:
                                run = False
                                break
                            else:
                                request = ""
                    else:
                        # Append to query
                        if data.endswith("\n"):
                            request += line + '\n'
                        else:
                            stack = line
            else:
                # Timeout waiting
                run = False
                break
        print('DROP')

    def livestatus(self, init_done):
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
        init_done.set()
        connections.append(s)

        # Signals
        pipe = os.pipe()
        connections.append(pipe[0])

        def sig_handler(signum, frame):
            self.log.debug("%s received" % signum)
            self.stop.set()
            os.write(pipe[1], bytes('END'))
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
                    t.daemon = False
                    t.start()
                else:
                    # Pipe receive something - exit
                    break

        s.close()
        self.log.info("Exit")
