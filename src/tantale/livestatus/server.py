# coding=utf-8

from __future__ import print_function

import os
import signal
import traceback
import logging

import select
import socket
import errno

from tantale.utils import load_class
from tantale.livestatus.query import Query

try:
    import SocketServer as socketserver
except:
    import socketserver

try:
    ConnectionResetError
except:
    ConnectionResetError = None

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
        self.running = True

        # Initialize Members
        self.config = config

    def load_backend(caller, class_name):
        if not class_name.endswith('Backend'):
            raise Exception(
                "%s is not a valid backend. "
                "Class name don't finish by Backend." % class_name)
        file = class_name[:-len('Backend')].lower()
        fqcn = 'tantale.livestatus.backends.%s.%s' % (file, class_name)
        return load_class(fqcn)

    def livestatus(self):
        if setproctitle:
            setproctitle('%s - Livestatus' % getproctitle())

        # Load backends
        backends = []
        for backend in self.config['backends']:
            try:
                cls = self.load_backend(backend)
                backends.append(
                    cls(self.config['backends'].get(backend, None)))
            except:
                self.log.error('Error loading backend %s' % backend)
                self.log.debug(traceback.format_exc())
        if len(backends) == 0:
            self.log.critical('No available backends')
            return

        from tantale.livestatus.query import Query

        class RequestHandler(socketserver.StreamRequestHandler):
            def handle(self):
                run = True
                while run:
                    try:
                        r, w, e = select.select([self.connection], [], [], 300)
                        if r is not None:
                            request = ""
                            while True:
                                data = self.rfile.readline().decode("utf-8")
                                if data is None or data == '':
                                    # Abnormal - closing thread
                                    run = False
                                    try:
                                        self.connection.shutdown(
                                            socket.SHUT_RDWR)
                                        self.connection.close()
                                    except:
                                        pass
                                    break
                                elif data.strip() == '':
                                    # Empty line - query END - process
                                    keep = self.handle_query(request)
                                    if not keep:
                                        break
                                    else:
                                        request = ""
                                else:
                                    # Append to query
                                    request += str(data)
                        else:
                            # Timeout waiting query
                            break

                    except ConnectionResetError:
                        break
                    except socket.error as e:
                        if e.errno != errno.ECONNRESET:
                            log = logging.getLogger('tantale')
                            log.debug(
                                "Client got : %s" % traceback.format_exc())
                        break

            def handle_query(self, request):
                try:
                    queryobj = Query.parse(self.wfile, request)
                    queryobj._query(backends)
                    queryobj._flush()
                    return queryobj.keepalive
                except Exception as e:
                    log = logging.getLogger('tantale')
                    log.warn(e)
                    log.debug(traceback.format_exc())

            def finish(self, *args, **kwargs):
                try:
                    super(RequestHandler, self).finish(*args, **kwargs)
                except:
                    pass

        class MyThreadingTCPServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            timeout = 10
            request_queue_size = 10000

        port = int(self.config['modules']['Livestatus']['port'])
        server = MyThreadingTCPServer(('', port), RequestHandler)

        self.log.info('Listening on %s' % port)
        try:
            server.serve_forever()
        except:
            self.log.error('Error trying to listen')

        self.log.info("Exit")
