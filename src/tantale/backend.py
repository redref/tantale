# coding=utf-8

from __future__ import print_function

import logging
import threading
from configobj import ConfigObj
import time


class BaseBackend(object):
    """
    Base class to all backends
    """

    def __init__(self, config=None):
        self.enabled = True

        #
        self.config = ConfigObj()
        self.config.merge(self.get_default_config())
        if config:
            self.config.merge(config)

        # error logging throttling
        self.server_error_interval = float(
            self.config['server_error_interval'])
        self._errors = {}

        # Initialize Lock
        self.lock = threading.Lock()

    def get_default_config_help(self):
        """
        Returns the help text for the configuration options
        """
        return {
            'server_error_interval': ('How frequently to send repeated server '
                                      'errors'),
        }

    def get_default_config(self):
        """
        Return the default config
        """
        return {
            'server_error_interval': 120,
        }

    def _throttle_error(self, logger, msg, *args, **kwargs):
        """
        Wrapper around log.error
        Avoids sending errors repeatedly. Waits at least
        `self.server_error_interval` seconds before sending the same error
        string to the error logging facility. If not enough time has passed,
        it calls `log.debug` instead

        :returns: the return value of `Logger.debug` or `Logger.error`
        """
        now = time.time()
        if msg in self._errors:
            if ((now - self._errors[msg]) >=
                    self.server_error_interval):
                fn = logger.error
                self._errors[msg] = now
            else:
                fn = logger.debug
        else:
            self._errors[msg] = now
            fn = logger.error

        return fn(msg, *args, **kwargs)

    def _reset_errors(self, msg=None):
        """
        Resets the logging throttle cache, so the next error is emitted
        regardless of the value in `self.server_error_interval`

        :param msg: if present, only this key is reset. Otherwise, the whole
            cache is cleaned.
        """
        if msg is not None and msg in self._errors:
            del self._errors[msg]
        else:
            self._errors = {}
