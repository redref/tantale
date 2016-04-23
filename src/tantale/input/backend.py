# coding=utf-8

from __future__ import print_function

import traceback

from tantale.backend import BaseBackend


class Backend(BaseBackend):
    def __init__(self, config=None):
        super(Backend, self).__init__(config)

        self.ttl_thread = None
        self.checks = []
        self.logs = []

    def get_default_config_help(self):
        return super(Backend, self).get_default_config_help()

    def get_default_config(self):
        return super(Backend, self).get_default_config()

    def _process(self, check):
        """
        Decorator for processing with a lock, catching exceptions
        """
        if not self.enabled:
            return
        try:
            try:
                self.lock.acquire()
                self.process(check)
            except Exception:
                self.log.error(traceback.format_exc())
        finally:
            if self.lock.locked():
                self.lock.release()

    def process(self, check):
        """
        Process (add check to stack)
        """
        raise NotImplementedError

    def process(self, check):
        """
        Process stack to backend
        """
        raise NotImplementedError

    def _flush(self):
        """
        Decorator for flushing with a lock, catching exceptions
        """
        if not self.enabled:
            return
        try:
            try:
                self.lock.acquire()
                self.flush()
            except Exception:
                self.log.error(traceback.format_exc())
        finally:
            if self.lock.locked():
                self.lock.release()

    def flush(self):
        """
        Flush
        """
        pass
