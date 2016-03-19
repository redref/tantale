# coding=utf-8

from __future__ import print_function

import traceback

from tantale.backend import BaseBackend


class Backend(BaseBackend):
    def _query(self, query):
        """
        Decorator for processing with a lock, catching exceptions
        """
        if not self.enabled:
            return
        try:
            try:
                self.lock.acquire()
                return self.query(query)
            except Exception:
                self.log.error(traceback.format_exc())
        finally:
            if self.lock.locked():
                self.lock.release()

    def query(self, query, limit=None):
        raise NotImplementedError
