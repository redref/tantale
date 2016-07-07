#!/usr/bin/env python
# coding=utf-8

import sys
import os
import subprocess
import re

from setuptools import setup, find_packages
from setuptools.command.install import install

my_dir = os.path.dirname(os.path.abspath(__file__))


#
# TOOLS
#
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
    sys.path.append(os.path.join(my_dir, 'src'))

    p = subprocess.Popen(
        "git --work-tree='%s' describe --tags" % my_dir,
        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()

    if p.returncode == 0 and stdout:
        version = '.'.join(stdout.decode('utf-8').strip().split('-')[0:-1])
        # Rewrite version
        v_file = os.path.join(my_dir, 'src/tantale/__init__.py')
        with open(v_file, 'r') as f:
            content = f.read()
        content = re.sub(
            r'\nVERSION\s*=.*\n', '\nVERSION = "%s"\n' % version, content)
        with open(v_file, 'w') as f:
            f.write(content)
        return version

    else:
        from tantale import VERSION
        return VERSION

#
# Setup options
#
setup_kwargs = dict(zip_safe=0)

init_file = None
data_files = []

if not running_under_virtualenv():
    data_files = [
        ('/etc/tantale', ['conf/tantale.conf.example']),
    ]
    if os.path.isdir('/usr/lib/systemd/user'):
        # Systemd script
        data_files.append((
            '/usr/lib/systemd/system', ['service/systemd/tantale.service']))
        init_file = os.path.join(my_dir, 'service/systemd/tantale.service')
    else:
        # Init script
        data_files.append((
            '/etc/init.d', ['service/init/tantale']))
        init_file = os.path.join(my_dir, 'service/init/tantale')

requirements = os.path.join(my_dir, 'requirements.txt')
with open(requirements, 'r') as f:
    install_requires = f.read().split('\n')


class TantaleInstallClass(install):
    def run(self):
        if init_file:
            # Rewrite tantale path with distrib path
            with open(init_file, 'r') as f:
                content = f.read()
            content = content.replace(
                '{{{SCRIPT_PATH}}}', self.install_scripts)
            with open(init_file, 'w') as f:
                f.write(content)

        install.run(self)

        if os.path.isfile('/etc/init.d/tantale'):
            os.chmod('/etc/init.d/tantale', 755)

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
    cmdclass={"install": TantaleInstallClass},
    ** setup_kwargs
)
