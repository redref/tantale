# coding=utf-8

"""
Tantale diamond handler
Pass metrics to FIFO file
"""

from __future__ import print_function

from diamond.handler.Handler import Handler

import stat
import os


class FifoHandler(Handler):
    """
    Implements the Handler abstract class, archiving data to a log file
    """

    def __init__(self, config):
        """
        Create a new instance
        """
        # Initialize Handler
        Handler.__init__(self, config)

        self.fifo_path = self.config['fifo_path']

        if not os.path.exists(self.fifo_path):
            os.mkfifo(
                self.fifo_path, int(self.config['creation_mode'], base=8))
        elif not stat.S_ISFIFO(os.stat(self.fifo_path).st_mode):
            self.log.error('FifoHandler: %s is not FIFO file' % self.fifo_path)
            self.enabled = False

        self.open()

    def get_default_config_help(self):
        """
        Returns the help text for the configuration options for this handler
        """
        config = super(FifoHandler, self).get_default_config_help()

        config.update({
            'fifo_path': 'FIFO file path (created if needed)',
            'creation_mode': 'rights to apply when create FIFO',
        })

        return config

    def get_default_config(self):
        """
        Return the default config for the handler
        """
        config = super(FifoHandler, self).get_default_config()

        config.update({
            'fifo_path': '/dev/shm/diamond_to_fifo',
            'creation_mode': 0600,
        })

        return config

    def process(self, metric):
        """
        Send a Metric to FIFO
        """
        if not self.fifo:
            # Try to reopen
            self.open()

        if not self.fifo:
            self._throttle_error('FifoHandler: failed to open FIFO')

        if self.fifo:
            try:
                os.write(self.fifo, str(metric))
            except:
                self.close()

    def open(self):
        try:
            self.fifo = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
        except:
            self.fifo = None

    def close(self):
        os.close(self.fifo)
        self.fifo = None
