# coding=utf-8

from __future__ import print_function

import os
import sys
import re
import stat
import time
import logging
import traceback

try:
    BlockingIOError
except:
    BlockingIOError = None

from tantale.client.source import BaseSource


class DiamondSource(BaseSource):
    def process_config(self):
        self.fifo_path = self.config['diamond_fifo']
        self.create_fifo(self.fifo_path)

        # Parse checks
        self.metrics = {}
        self.retention = {}
        self.fifo = None

        checks = self.checks

        for check in checks:

            # Prefix
            checks[check]['prefix'] = checks[check].get(
                'prefix', '')
            if (
                checks[check]['prefix'] != '' and
                not checks[check]['prefix'].endswith('.')
            ):
                checks[check]['prefix'] += '.'

            # Thresholds
            thresholds = checks[check].get('thresholds', None)
            if not thresholds:
                self.log.warning(
                    "Diamond : dropping check '%s', "
                    "no thresholds defined" % check)
                continue

            if len(thresholds) != 4:
                self.log.warning(
                    "Diamond : dropping check '%s', thresholds must contain "
                    "4 elements (lc, lw, uw, uc)" % check)
                continue

            explicit_thresholds = {}
            for idx, name in enumerate(
                ['lower_crit', 'lower_warn',
                 'upper_warn', 'upper_crit']
            ):
                try:
                    explicit_thresholds[name] = float(thresholds[idx])
                except ValueError:
                    explicit_thresholds[name] = None

            checks[check]['thresholds'] = explicit_thresholds

            # Condition
            condition = checks[check].get('condition', None)
            if condition:
                checks[check]['condition'] = self._parse_expression(
                    condition, check, checks[check]['prefix'])

            # Expression
            expression = checks[check].get('expression', None)
            if not expression:
                self.log.warning(
                    "Diamond : dropping check '%s', "
                    "no expression defined" % key)
                continue
            checks[check]['expression'] = self._parse_expression(
                expression, check, checks[check]['prefix'])

            self.log.debug('Diamond : parsed %s' % checks[check])

        self.checks = checks

        # Open FIFO early to begin receiving metrics
        self.fifo = self.open_fifo(self.fifo_path)

        self.log.debug('Diamond : global metrics %s' % self.metrics)

    def _parse_expression(self, expression, check, prefix):
        metrics = []

        # Python 2.6 compat
        if sys.version_info < (2, 7):
            formula = expression
            re_idx = 0
            while True:
                formula, nb = re.subn(
                    r'\{[^\}]+\}', '__%s__' % re_idx, formula, count=1)
                if nb == 0:
                    break
                re_idx += 1
            formula = re.sub(r'__(\d+)__', r'{\1}', formula)
        else:
            formula = re.sub(r'\{[^\}]+\}', '{}', expression)

        # Work with metrics (name, retention)
        for metric in re.findall(r'\{([^\}]+)\}', expression):
            # Trend metric (with time slot)
            split = metric.split('|')
            if len(split) > 1:
                metric = split[1]
                keep = int(split[0])
            else:
                keep = 0

            if prefix != "":
                metric = prefix + metric

            # Keep information check wide
            metrics.append((metric, keep))

            # Make a global retention hash
            if metric not in self.metrics:
                self.metrics[metric] = {
                    'checks': [check], 'retention': keep}
                self.retention[metric] = []
            else:
                if self.metrics[metric]['retention'] < keep:
                    self.metrics[metric]['retention'] = keep
                if check not in self.metrics[metric]['checks']:
                    self.metrics[metric]['checks'].append(check)

        return {"metrics": metrics, 'formula': formula}

    def execute_check(self, name):
        """
        Read FIFO, save interesting values
        Check the one we got
        """
        self.get_and_save_metrics_from_fifo()

        check = self.checks[name]

        # Check about condition
        if 'condition' in check:
            try:
                c_vals, ts = self.gather_values(
                    name, check['condition']['metrics'])
                if not c_vals:
                    self.send(name, 3, 'OUTDATED - No result yet')
                    return

                formula = check['condition']['formula'].format(*c_vals)

                if not eval(formula):
                    self.send(
                        name, 0,
                        "Diamond trend : Condition not met", ts)
                    return
            except:
                self.log.info('Diamond : %s condition failed' % name)
                self.log.debug(
                    'Diamond : trace - %s' % traceback.format_exc())
                self.send(name, 3, 'OUTDATED - No result yet')
                return

        # Appky formula
        try:
            vals, ts = self.gather_values(
                    name, check['expression']['metrics'])
            if not vals:
                self.send(name, 3, 'OUTDATED - No result yet')
                return

            formula = check['expression']['formula'].format(*vals)
            computed = float(eval(formula))
        except:
            self.log.info('Diamond : %s expression failed' % name)
            self.log.debug(
                'Diamond : trace - %s' % traceback.format_exc())
            self.send(name, 3, 'OUTDATED - No result yet')
            return

        status, output = self.range_check(
            computed, **check['thresholds'])

        self.send(name, status, output, ts)

    def get_and_save_metrics_from_fifo(self):
        if not self.fifo:
            self.fifo = self.open_fifo(self.fifo_path)
        if not self.fifo:
            self.log.warn('Diamond : failed to open FIFO')
            return

        try:
            res = self.read_fifo(self.fifo)
            if not res:
                return
        except:
            self.fifo = None

        for line in res.strip().split('\n'):
            try:
                name, value, ts = line.split(' ')
                value = float(value)
                ts = int(ts)
            except:
                # No log here
                continue

            # If we don't known, zap it
            if name not in self.metrics:
                continue

            self.retention[name].append((value, ts))

        # Retention cleanup loop
        for metric in self.metrics:
            while (
                len(self.retention[metric]) > 1 and
                self.retention[metric][0][1] <
                (time.time() - self.metrics[metric]['retention'])
            ):
                self.retention[metric].pop(0)

    def gather_values(self, check, metrics):
        lower_ts = None
        vals = []

        for metric, when in metrics:

            if len(self.retention[metric]) == 0:
                self.log.info(
                    "Diamond : %s missing metric %s" %
                    (check, metric))
                return None, None

            if when == 0:
                if (
                    lower_ts is None or
                    self.retention[metric][-1][1] < lower_ts
                ):
                    lower_ts = self.retention[metric][-1][1]
                vals.append(self.retention[metric][-1][0])
            else:
                # Take oldest metric available
                vals.append(self.retention[metric][0][0])

        return vals, lower_ts

    def range_check(
        self, value,
        lower_crit=None, lower_warn=None, upper_warn=None, upper_crit=None
    ):
        """ Compare with thresholds """
        message = "%.2f (%s, %s, %s, %s)" % (
            value, lower_crit, lower_warn, upper_warn, upper_crit)

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

    def create_fifo(self, fifo_path):
        if fifo_path and not os.path.exists(fifo_path):
            os.mkfifo(fifo_path, 0o0660)
        elif not stat.S_ISFIFO(os.stat(fifo_path).st_mode):
            raise Exception("Diamond : %s not a fifo file")

    def open_fifo(self, fifo_path):
        try:
            if fifo_path:
                return os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        except:
            self.log.error('Diamond : failed to open %s' % fifo_path)
            self.log.debug('Diamond : trace - %s' % traceback.format_exc())
            return None
        return None

    def read_fifo(self, fifo_fd):
        try:
            res = ""
            while True:
                read = os.read(fifo_fd, 4096).decode('utf-8')
                if read == "":
                    if res == "":
                        return None
                    else:
                        return res

                res += read

                if len(read) != 4096:
                    return res
        except BlockingIOError:
            return None
        except Exception as exc:
            # Python 2 BlockingIOError
            if isinstance(exc, OSError) and exc.errno == 11:
                return None
            self.log.debug(
                'Diamond : read fifo error: %s' % traceback.format_exc())
            os.close(fifo_fd)
            raise
