# coding=utf-8

import sys
import imp
import inspect
from six import string_types


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


def load_backend(class_name):
    if not class_name.endswith('Backend'):
        raise Exception(
            "%s is not a valid backend. "
            "Class name don't finish by Backend." % class_name)
    file = class_name[:-len('Backend')].lower()
    fqcn = 'tantale.backends.%s.%s' % (file, class_name)
    return load_class(fqcn)
