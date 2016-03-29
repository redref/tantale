# coding=utf-8

from __future__ import print_function

import os
import stat
import signal
import traceback
import logging

import socket
import select
from six import b as bytes

try:
    from setproctitle import setproctitle, getproctitle
except ImportError:
    setproctitle = None


class Client(object):
    """
    Tantale client
    Read one FIFO in Nagios format
    Read one FIFO in Diamond/Graphite format
    Send to Tantale Input
    """
    def __init__(self, config):
        # Initialize Logging
        self.log = logging.getLogger('tantale')

        # Process signal
        self.running = True

        # Save our config
        self.config = config['modules']['Client']
        self.my_hostname = socket.getfqdn()

        # Output config
        self.host = self.config['server_host']
        self.port = int(self.config['server_port'])
        self.sock = None
        if self.config['contact_groups']:
            self.contact_groups = ','.join(self.config['contact_groups'])
        else:
            self.contact_groups = None

        # Diamond input config
        self.diamond_fifo = self.config['diamond']['fifo_file']
        self.diamond_fd = None
        self.diamond_checks = self.config['diamond'].get('checks', None)
        self.diamond_stack = ""

        # Nagios input config
        self.nagios_fifo = self.config['nagios']['fifo_file']
        self.nagios_fd = None
        self.nagios_stack = ""

    def __del__(self):
        self.close()

    def run(self, init_done):
        if setproctitle:
            setproctitle('%s - Client' % getproctitle())

        init_done.set()

        while self.running:
            # Open diamond
            if not self.diamond_fd:
                self.diamond_fd = self.open_fifo(self.diamond_fifo)

            # Open nagios
            if not self.nagios_fd:
                self.nagios_fd = self.open_fifo(self.nagios_fifo)

            # Wait IO
            fds = []
            for fd in (self.diamond_fd, self.nagios_fd):
                if fd:
                    fds.append(fd)
            r, o, e = select.select(fds, [], [], 60)

            # Process
            result = ""
            for fd in r:
                if fd == self.diamond_fd:
                    try:
                        result += self.process_diamond(
                            self.read_fifo(self.diamond_fd))
                    except:
                        self.diamond_fd = None

                elif fd == self.nagios_fd:
                    try:
                        result += self.process_nagios(
                            self.read_fifo(self.nagios_fd))
                    except:
                        self.nagios_fd = None

            # Send
            if result != "":
                self.send(result)

        self.log.info("Exit")

    def open_fifo(self, fifo_path):
        try:
            if fifo_path:
                return os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        except:
            self.log.error('Failed to open %s' % fifo_path)
            self.log.debug('Trace: %s' % traceback.format_exc())
            return None

    def read_fifo(self, fifo_fd):
        try:
            return os.read(fifo_fd, 4096)
        except:
            self.log.debug('Trace: %s' % traceback.format_exc())
            os.close(fifo_fd)
            raise

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(True)
        self.sock.connect((self.host, self.port))

    def close(self):
        if self.sock:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()

    def send(self, result):
        if not self.sock:
            self.connect()

        if not self.sock:
            self.log.debug(
                'Reconnect to %s:%s failed' % (self.host, self.port))

        if self.contact_groups:
            result += "|%s\n" % self.contact_groups
        else:
            result += "\n"

        try:
            self.sock.send(bytes(result))
        except:
            pass

    def process_diamond(self, lines):
        result = ""
        for line in lines.strip().split('\n'):
            line_list = line.split(' ')

            for check in self.diamond_checks:
                if line_list[0].endswith(check):
                    thresholds = self.diamond_checks[check]
                    status, output = self.range_check(
                        check,
                        thresholds.get('lower_critical', None),
                        thresholds.get('lower_warning', None),
                        thresholds.get('upper_warning', None),
                        thresholds.get('upper_critical', None),
                        line_list[1],
                    )

                    result += "%s %s %s %s %s" \
                        % (
                            line_list[2], self.my_hostname,
                            thresholds.get('name', check), status, output)

        return result

    def range_check(self, metric, lc, lw, uw, uc, value):
        """ Do the comparing maths """
        message = "%s value %%s than %s" % (metric, value)
        if lc and float(value) < float(lc):
            return 2, message % 'lower'
        elif lw and float(value) < float(lw):
            return 1, message % 'lower'
        elif uw and float(value) > float(uw):
            return 1, message % 'upper'
        elif uc and float(value) > float(uc):
            return 2, message % 'upper'

    def process_nagios(self, input):
        pass
