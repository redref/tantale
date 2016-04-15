#!/usr/bin/env python
# coding=utf-8

import sys
import os

from setuptools import setup, find_packages
from setuptools.command.install import install


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

data_files = []
if not running_under_virtualenv():
    data_files = [
        ('/etc/tantale', ['conf/tantale.conf.example']),
    ]
    if os.path.isdir('/usr/lib/systemd'):
        # Systemd script
        data_files.append((
            '/usr/lib/systemd/system', ['service/systemd/tantale.service']))
    else:
        # Init script
        data_files.append((
            '/etc/init.d', ['service/init/tantale']))

install_requires = ['configobj', ]

setup(
    name='tantale',
    version=get_version(),
    url='https://github.com/redref/tantale',
    author='redref',
    author_email='https://github.com/redref/tantale',
    license='Apache 2.0',
    description='Monitoring system over NoSQL (mainly Elasticsearch)',
    package_dir={'': 'src'},
    packages=find_packages('src', exclude=["tests"]),
    package_data={'': ['*.*']},
    scripts=['bin/tantale'],
    data_files=data_files,
    install_requires=install_requires,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Topic :: System :: Monitoring",
    ],
    ** setup_kwargs
)
