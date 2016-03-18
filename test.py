#!/usr/bin/env python
# coding=utf-8

from __future__ import print_function
import os
import sys
import imp
import optparse
import logging
import unittest
import inspect
import socket
import time
import signal
from multiprocessing import Process, Manager, Event, active_children

# Fix path
path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'src')
sys.path.insert(0, path)

# DaemonTestCase Deps
from tantale.utils import DebugFormatter
from tantale.server import Server

try:
    from mock import ANY, call, MagicMock, Mock, mock_open, patch
except ImportError:
    from unittest.mock import ANY, call, MagicMock, Mock, mock_open, patch

try:
    from setproctitle import setproctitle
except ImportError:
    setproctitle = None


###############################################################################
def getTests(mod_name, src=None, class_prefix="", bench=False):
    if src is None:
        src = sys.path

    tests = []

    try:
        # Import the module
        custom_name = '%s%s' % (class_prefix, mod_name)
        f, pathname, desc = imp.find_module(
            mod_name, src)
        mod = imp.load_module(
            custom_name, f, pathname, desc)
        if f is not None:
            f.close()

        # Save if it's a test
        basename = os.path.basename(pathname)
        if (
            os.path.isfile(pathname) and
            len(pathname) > 3 and
            basename[-3:] == '.py' and
            basename[0:4] == 'test'
        ):
            for name, c in inspect.getmembers(mod, inspect.isclass):
                if name.startswith('Bench'):
                    if not bench:
                        continue
                else:
                    if bench:
                        continue
                if not issubclass(c, unittest.TestCase):
                    continue
                tests.append(c)

        # Recurse
        if os.path.isdir(pathname):
            for f in os.listdir(pathname):
                if len(f) > 3 and f[-3:] == '.py':
                    tests.extend(getTests(
                        f[:-3], mod.__path__,
                        "%s_%s" % (class_prefix, mod_name), bench))
                elif (
                    not f.startswith('_') and
                    os.path.isdir(os.path.join(pathname, f))
                ):
                    tests.extend(getTests(
                        f, mod.__path__,
                        "%s_%s" % (class_prefix, mod_name), bench))
    except:
        import traceback
        print("Failed to import module: %s\n %s" % (
            mod_name, traceback.format_exc()))

    return tests


###############################################################################
class SocketClient(object):
    def __init__(self, dst):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(True)
        self.sock.connect(dst)

    def send(self, msg):
        totalsent = 0
        MSGLEN = len(msg)
        while totalsent < MSGLEN:
            sent = self.sock.send(msg[totalsent:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            totalsent = totalsent + sent

    def close(self):
        # TOFIX - closing too fast after send (test error)
        time.sleep(0.5)
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()


class DaemonTestCase(unittest.TestCase):
    mock = True

    def setUp(self):
        if self.mock and hasattr(self, 'mocking'):
            self.mocking()

        # Daemon handle
        self.ready = Event()
        self.daemon_p = Process(target=self.launch)
        self.daemon_p.start()
        for i in range(100):
            if self.ready.is_set():
                break
            time.sleep(0.1)

    def launch(self):
        # Initialize Server
        server = Server(
            configfile=os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'conf/tantale.conf.example'),
            config_adds=getattr(self, 'config', None))

        # Run handle
        def __onInitDone():
            self.ready.set()

        server.run(__onInitDone)

    def flush(self):
        self.daemon_p.terminate()
        self.daemon_p.join()

    def get_socket(self):
        return SocketClient(('127.0.0.1', 2003))

    def tearDown(self):
        if self.mock and hasattr(self, 'unmocking'):
            self.unmocking()

###############################################################################
if __name__ == "__main__":
    if setproctitle:
        setproctitle('test.py')

    # Initialize Options
    parser = optparse.OptionParser()
    parser.add_option("-v",
                      "--verbose",
                      dest="verbose",
                      default=1,
                      action="count",
                      help="verbose")
    parser.add_option("-b",
                      "--bench",
                      dest="bench",
                      default=False,
                      action="store_true",
                      help="bench tests (only)")
    parser.add_option("-l",
                      "--log",
                      dest="log",
                      default=False,
                      action="store_true",
                      help="log daemon to stdout (messy with verbose)")
    parser.add_option("-n",
                      "--no-mock",
                      dest="nomock",
                      default=False,
                      action="store_true",
                      help="log daemon to stdout (messy with verbose)")

    # Parse Command Line Args
    (options, args) = parser.parse_args()

    # disable normal logging
    log = logging.getLogger("tantale")
    handler = logging.StreamHandler(sys.stderr)
    log.addHandler(handler)
    if options.log:
        log.setLevel(logging.DEBUG)
        handler.setFormatter(DebugFormatter())
        handler.setLevel(logging.DEBUG)
    else:
        log.disabled = True

    # Load
    tests = getTests('tantale', bench=options.bench)

    # Init test
    loaded_tests = []
    loader = unittest.TestLoader()
    for test in tests:
        if options.nomock:
            test.mock = False
        loaded_tests.append(loader.loadTestsFromTestCase(test))
    suite = unittest.TestSuite(loaded_tests)
    results = unittest.TextTestRunner(verbosity=options.verbose).run(suite)

    results = str(results)
    results = results.replace('>', '').split()[1:]
    resobj = {}
    for result in results:
        result = result.split('=')
        resobj[result[0]] = int(result[1])

    if resobj['failures'] > 0:
        sys.exit(1)
    if resobj['errors'] > 0:
        sys.exit(2)

    sys.exit(0)
