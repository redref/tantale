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
import traceback
from multiprocessing import Process, Event
from six import binary_type
from six import b as bytes

# Fix path
path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'src')
sys.path.insert(0, path)

try:
    from setproctitle import setproctitle
except ImportError:
    setproctitle = None


###############################################################################
def getTests(mod_name, src=None, class_prefix=""):
    if src is None:
        src = sys.path

    tests = []

    try:
        # Import the module
        custom_name = '%s_%s' % (class_prefix, mod_name)
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
            len(pathname) > 4 and
            basename[-3:] == '.py' and
            basename[0:4] == 'test'
        ):
            for name, c in inspect.getmembers(mod, inspect.isclass):
                if not issubclass(c, unittest.TestCase):
                    continue
                tests.append(c)

        # Recurse on directoy
        if os.path.isdir(pathname):
            for f in os.listdir(pathname):

                # File only if test*.py
                if len(f) > 4 and f[:3] == 'tes' and f[-3:] == '.py':
                    tests.extend(getTests(
                        f[:-3], mod.__path__,
                        "%s_%s" % (class_prefix, mod_name)))

                # Recurse on python module folders
                elif (
                    not f.startswith('_') and
                    os.path.isdir(os.path.join(pathname, f)) and
                    os.path.isfile(os.path.join(pathname, f, '__init__.py'))
                ):
                    tests.extend(getTests(
                        f, mod.__path__,
                        "%s_%s" % (class_prefix, mod_name)))

    except:
        print("Failed to import module: %s\n %s" % (
            mod_name, traceback.format_exc()))
        return

    return tests


###############################################################################
class SocketClient(object):
    def __init__(self, dst):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(True)
        self.sock.settimeout(5)
        self.sock.connect(dst)

    def send(self, msg):
        if not isinstance(msg, binary_type):
            msg = bytes(msg)

        totalsent = 0
        MSGLEN = len(msg)
        while totalsent < MSGLEN:
            sent = self.sock.send(msg[totalsent:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            totalsent = totalsent + sent

    def recv(self, size=4096):
        return self.sock.recv(size).decode('utf-8')

    def close(self):
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()


class TantaleTC(unittest.TestCase):
    bench = False
    config_file = 'conf/tantale.conf.example'

    def setUp(self):
        from tantale.server import Server
        self.server = Server(
            configfile=os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                self.config_file))

        # Daemon handle
        self.ready = Event()
        self.daemon_p = Process(target=self._launch)

    def tearDown(self):
        """ Stop anyway """
        self.stop()

    def start(self):
        """ Start the daemon """
        self.daemon_p.start()

        # Wait daemon ready
        self.ready.wait(10)

    def stop(self):
        """
        Terminate daemon
        Need to be called explicitely in test in order to get
        coverage data
        """
        if self.daemon_p and self.daemon_p.is_alive():
            self.daemon_p.terminate()
            self.daemon_p.join()

        self.ready = Event()
        self.daemon_p = Process(target=self._launch)

    def _launch(self):
        """ Internally launch tantale daemon """
        def __onInitDone():
            self.ready.set()

        self.server.run(__onInitDone)

    def getSocket(self, module):
        port = self.server.config['modules'][module]['port']
        return SocketClient(('127.0.0.1', int(port)))

    def getLivestatusRequest(self, request_name):
        my_dir = os.path.dirname(os.path.abspath(__file__))
        fix_file = os.path.join(
            my_dir, 'src', 'tantale', 'livestatus', 'fixtures', 'requests')

        request = ""
        with open(fix_file, 'r') as f:
            for line in f.read().split("\n"):
                if line.startswith('#'):
                    name = line[2:]
                    continue

                if line == '' and request != "":
                    if name == request_name:
                        return request
                    else:
                        request = ""
                else:
                    request += "%s\n" % line
        return False


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
    parser.add_option("-d",
                      "--debug",
                      dest="debug",
                      default=False,
                      action="store_true",
                      help="set log level to DEBUG (instead INFO)")
    parser.add_option("-t",
                      "--test",
                      dest="test",
                      default="",
                      help="Run a single test class (by ClassName")

    # Parse Command Line Args
    (options, args) = parser.parse_args()

    # Disable normal logging
    from tantale.utils import DebugFormatter
    root = logging.getLogger()
    root.addHandler(logging.NullHandler())
    log = logging.getLogger("tantale")
    handler = logging.StreamHandler(sys.stderr)
    log.addHandler(handler)
    if options.log:
        if options.debug:
            log.setLevel(logging.DEBUG)
        else:
            log.setLevel(logging.INFO)
        handler.setFormatter(DebugFormatter())
        handler.setLevel(logging.DEBUG)
    else:
        log.disabled = True

    # Load
    tests = getTests('tantale')
    loaded_tests = []
    loader = unittest.TestLoader()
    for test in tests:

        # Supply bench mode
        if options.bench:
            test.bench = True

        # Keep only selected test
        if options.test and test.__name__ != options.test:
            continue
        loaded_tests.append(loader.loadTestsFromTestCase(test))

    # Run tests
    suite = unittest.TestSuite(loaded_tests)
    results = unittest.TextTestRunner(verbosity=options.verbose).run(suite)

    # Manage status output
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
