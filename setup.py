#!/usr/bin/env python
# coding=utf-8

import sys
import os
from glob import glob
import platform
from setuptools import setup


def running_under_virtualenv():
    if hasattr(sys, 'real_prefix'):
        return True
    elif sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return True
    if os.getenv('VIRTUAL_ENV', False):
        return True
    return False


def get_version():
    """
        Get version from version.py
    """
    sys.path.append(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
    from tantale import VERSION
    return VERSION

setup_kwargs = dict(zip_safe=0)

distro = platform.dist()[0]
distro_major_version = platform.dist()[1].split('.')[0]

data_files = []

# Are we in a virtenv?
if running_under_virtualenv():
    # PIP requires
    install_requires = ['configobj', ]
elif distro == ['debian', 'ubuntu']:
    # Package requires
    install_requires = ['python-configobj', ]
else:
    # PIP requires
    install_requires = ['configobj', ]

setup(
    name='tantale',
    version=get_version(),
    url='https://github.com/redref/tantale',
    author='redref',
    author_email='https://github.com/redref/tantale',
    license='Apache 2.0',
    description='Monitoring API / Backend interfaces',
    package_dir={'': 'src'},
    packages=['tantale'],
    scripts=[],
    data_files=data_files,
    install_requires=install_requires,
    ** setup_kwargs
)
