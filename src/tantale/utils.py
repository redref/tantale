# coding=utf-8

from __future__ import print_function

import os
import sys
import imp
import inspect
import logging
import logging.config
import configobj
from six import string_types


def set_logging_config(config=None):
    if not config:
        config_min_f = os.path.join(
            os.path.dirname(__file__), 'config_min.conf')
        config_min = configobj.ConfigObj(config_min_f)
        config = config_min['logging']

    # Adapt config to logging format
    config['version'] = 1

    for logger in config['loggers']:
        if 'propagate' in config['loggers'][logger]:
            config['loggers'][logger]['propagate'] = \
                str_to_bool(config['loggers'][logger]['propagate'])

    for handler in config['handlers']:
        for field in config['handlers'][handler]:
            try:
                config['handlers'][handler][field] = \
                    int(config['handlers'][handler][field])
            except ValueError:
                pass

    # Apply it
    logging.config.dictConfig(config)


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


def load_backend(caller, class_name):
    if not class_name.endswith('Backend'):
        raise Exception(
            "%s is not a valid backend. "
            "Class name don't finish by Backend." % class_name)
    file = class_name[:-len('Backend')].lower()
    fqcn = 'tantale.backends.%s.%s.%s' % (file, caller, class_name)
    return load_class(fqcn)
