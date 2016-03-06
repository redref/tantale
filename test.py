#!/usr/bin/env python
# coding=utf-8

import os
import sys
import imp
import optparse
import logging

try:
    # python 2.6
    import unittest2 as unittest
except ImportError:
    import unittest

try:
    from mock import ANY, call, MagicMock, Mock, mock_open, patch
except ImportError:
    from unittest.mock import ANY, call, MagicMock, Mock, mock_open, patch

try:
    # py2
    import builtins
    BUILTIN_OPEN = "builtins.open"
except ImportError:
    # py3
    BUILTIN_OPEN = "__builtin__.open"

###############################################################################
if __name__ == "__main__":
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

    loader = unittest.TestLoader()
    tests = []
    suite = unittest.TestSuite(tests)
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
