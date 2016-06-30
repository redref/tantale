# coding=utf-8

from __future__ import print_function

import time
import logging

from tantale.client.source import BaseSource


class OkSource(BaseSource):
    def execute_check(self, check):
        self.send(check, 0, "Ok check")
