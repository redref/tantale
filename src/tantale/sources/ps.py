# coding=utf-8

from __future__ import print_function

import time
import re
import psutil
import logging

from tantale.client.source import BaseSource


class PsSource(BaseSource):
    def process_config(self):
        checks = self.checks

        for check in self.checks:
            checks[check]['pattern'] = re.compile(checks[check]['regexp'])
            checks[check]['user'] = checks[check].get('user', None)

            # Thresholds
            thresholds = checks[check].get('thresholds', None)
            if not thresholds:
                self.log.info(
                    "Ps : dropping check '%s', "
                    "no thresholds defined" % check)

            if len(thresholds) != 4:
                self.log.info(
                    "Ps : dropping check '%s', thresholds must contain "
                    "4 elements (lc, lw, uw, uc)" % check)

            explicit_thresholds = {}
            for idx, name in enumerate(
                ['lower_crit', 'lower_warn',
                 'upper_warn', 'upper_crit']
            ):
                try:
                    explicit_thresholds[name] = int(thresholds[idx])
                except ValueError:
                    explicit_thresholds[name] = None

            checks[check]['thresholds'] = explicit_thresholds

        self.checks = checks

    def run(self):
        while True:
            self.get_and_wait_next_check()

            res = {}

            # Get timestamp before process enumeration
            now = int(time.time())

            for process in psutil.process_iter():
                user = process.username()
                command = ' '.join(process.cmdline())

                for check in self.checks:
                    if (
                        user and self.checks[check]['user'] and
                        user != self.checks[check]['user']
                    ):
                        continue

                    if re.search(self.checks[check]['pattern'], command):
                        res[check] = res.get(check, 0) + 1

            for check in self.checks:
                status, output = self.range_check(
                    res.get(check, 0),
                    self.checks[check]['regexp'],
                    self.checks[check]['user'],
                    **self.checks[check]['thresholds']
                )
                self.send(check, status, output, now)

    def range_check(
        self, value, regexp, user,
        lower_crit=None, lower_warn=None, upper_warn=None, upper_crit=None
    ):
        """ Compare with thresholds """
        message = "Found %d processes matching %s " \
            "for user %s (%s, %s, %s, %s)" % \
            (value, regexp, user, lower_crit, lower_warn,
             upper_warn, upper_crit)

        if lower_crit and float(value) < float(lower_crit):
            return 2, message

        elif lower_warn and float(value) < float(lower_warn):
            return 1, message

        elif upper_crit and float(value) > float(upper_crit):
            return 2, message

        elif upper_warn and float(value) > float(upper_warn):
            return 1, message

        else:
            return 0, message
