# coding=utf-8

from __future__ import print_function
import sys
import imp
import inspect
import logging
import logging.config
from six import string_types


class DebugFormatter(logging.Formatter):

    def __init__(self, fmt=None):
        if fmt is None:
            fmt = ('%(created)10s\t' +
                   '%(processName)15s\t%(process)d\t%(levelname)8s\t' +
                   '%(message)s')
        self.fmt_default = fmt
        self.fmt_prefix = fmt.replace('%(message)s', '')
        logging.Formatter.__init__(self, fmt)

    def format(self, record):
        self._fmt = self.fmt_default

        if record.levelno in [logging.ERROR, logging.CRITICAL]:
            self._fmt = ''
            self._fmt += self.fmt_prefix
            self._fmt += '%(message)s'
            self._fmt += '\n'
            self._fmt += self.fmt_prefix
            self._fmt += '%(pathname)s:%(lineno)d'

        return logging.Formatter.format(self, record)


def str_to_bool(value):
    """
    Converts string truthy/falsey strings to a bool
    Empty strings are false
    """
    if isinstance(value, string_types):
        value = value.strip().lower()
        if value in ['true', 't', 'yes', 'y']:
            return True
        elif value in ['false', 'f', 'no', 'n', '']:
            return False
        else:
            raise NotImplementedError("Unknown bool %s" % value)

    return value


def load_class(fqcn, module_prefix='internal_'):
    # Break apart fqcn to get module and classname
    paths = fqcn.split('.')
    classname = paths[-1]
    if module_prefix:
        modulename = "%s%s" % (module_prefix, paths[0])
    else:
        modulename = paths[0]

    # Import the module
    f, filename, desc = imp.find_module(paths[0])
    mod = imp.load_module(modulename, f, filename, desc)
    if len(paths) > 2:
        for path in paths[1:-1]:
            if module_prefix:
                modulename = "%s%s" % (module_prefix, path)
            else:
                modulename = path
            f, filename, desc = imp.find_module(path, mod.__path__)
            mod = imp.load_module(modulename, f, filename, desc)

    cls = getattr(sys.modules[modulename], classname)
    # Check cls
    if not inspect.isclass(cls):
        raise TypeError("%s is not a class" % fqcn)
    # Return class
    return cls
