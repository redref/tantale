#!/usr/bin/env python
# coding=utf-8

import os
import sys
import imp
import optparse
import logging
import unittest
import inspect

# DaemonTestCase Deps
try:
    from tantale.server import Server
    import signal
    from multiprocessing import Process, Queue, active_children
except:
    pass

try:
    from mock import ANY, call, MagicMock, Mock, mock_open, patch
except ImportError:
    from unittest.mock import ANY, call, MagicMock, Mock, mock_open, patch

try:
    from setproctitle import setproctitle
except ImportError:
    setproctitle = None


###############################################################################
def getTests(mod_name, src=None, class_prefix="internal_"):
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
                if not issubclass(c, unittest.TestCase):
                    continue
                tests.append(c)

        # Recurse
        if os.path.isdir(pathname):
            for f in os.listdir(pathname):
                if len(f) > 3 and f[-3:] == '.py':
                    tests.extend(getTests(f[:-3], mod.__path__, class_prefix))
                elif (
                    not f.startswith('_') and
                    os.path.isdir(os.path.join(pathname, f))
                ):
                    tests.extend(getTests(f, mod.__path__, class_prefix))
    except:
        import traceback
        print("Failed to import module: %s\n %s" % (
            mod_name, traceback.format_exc()))

    return tests


###############################################################################
class DaemonTestCase(unittest.TestCase):
    def setUp(self):
        ready_queue = Queue(maxsize=10)
        self.mock_queue = Queue()
        self.daemon_p = Process(
            target=self.launch, args=(ready_queue, self.mock_queue))
        self.daemon_p.start()
        while True:
            r = ready_queue.get()
            if r == 'input':
                break

    def launch(self, ready_queue, mock_queue):
        # Initialize Server
        server = Server(
            configfile=os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'conf/tantale.conf.example'))

        def sig_handler(signum, frame):
            for child in active_children():
                child.terminate()

        # Set the signal handlers
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        server.run(ready_queue, mock_queue)

    def tearDown(self):
        self.daemon_p.terminate()

###############################################################################
if __name__ == "__main__":
    if setproctitle:
        setproctitle('test.py')

    # Fix path
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'src')
    sys.path.append(path)

    # disable normal logging
    log = logging.getLogger("tantale")
    log.addHandler(logging.StreamHandler(sys.stderr))
    log.disabled = True

    # Initialize Options
    parser = optparse.OptionParser()
    parser.add_option("-v",
                      "--verbose",
                      dest="verbose",
                      default=1,
                      action="count",
                      help="verbose")

    # Parse Command Line Args
    (options, args) = parser.parse_args()

    # Load
    tests = getTests('tantale')

    # Init test
    loaded_tests = []
    loader = unittest.TestLoader()
    for test in tests:
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
