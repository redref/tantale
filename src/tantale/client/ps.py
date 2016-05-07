# coding=utf-8

from __future__ import print_function

import time


class PsSource(object):
    def __init__(self, config, checks):
        self.config = config

    def run(self, event, results):
        while True:
            # results['Host']['status'] = 3
            time.sleep(10)
