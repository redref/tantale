# coding=utf-8

from __future__ import print_function

import traceback

from tantale.backend import BaseBackend


class Backend(BaseBackend):
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
        Process
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
