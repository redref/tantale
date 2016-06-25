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


class DiamondSource(object):
    def __init__(self, config, checks):
        self.log = logging.getLogger('tantale.client')

        self.interval = config['interval']
        self.fifo_path = config['diamond_fifo']
        self.create_fifo(self.fifo_path)

        # Parse checks
        self.metrics = {}

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
            else:
                if self.metrics[metric]['retention'] < keep:
                    self.metrics[metric]['retention'] = keep
                if check not in self.metrics[metric]['checks']:
                    self.metrics[metric]['checks'].append(check)

        return {"metrics": metrics, 'formula': formula}

    def run(self, event, results):
        self.retention = {}

        fifo = None

        while True:
            # Keep fifo open
            if not fifo:
                fifo = self.open_fifo(self.fifo_path)
            if not fifo:
                self.log.warn('Diamond : failed to open FIFO')
                time.sleep(self.interval)
                continue

            res = self.read_fifo(fifo)
            if res:
                for name, out in self.process_diamond(res):
                    if out['status'] != results[name]['status']:
                        results[name].update(out)
                        event.set()
                    else:
                        results[name].update(out)

    def gather_values(self, check, metrics):
        lower_ts = None
        vals = []

        for metric, when in metrics:

            if metric not in self.retention:
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
                # Take old metric
                vals.append(self.retention[metric][0][0])

        return vals, lower_ts

    def process_diamond(self, lines):
        result = ""
        for line in lines.strip().split('\n'):
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

            if name not in self.retention:
                self.retention[name] = []
            self.retention[name].append((value, ts))

            # Compute check
            for check in self.metrics[name]['checks']:
                name = check
                check = self.checks[check]

                if 'condition' in check:
                    try:
                        c_vals, ts = self.gather_values(
                            name, check['condition']['metrics'])
                        self.log.debug(c_vals)
                        if not c_vals:
                            continue

                        formula = check['condition']['formula'].format(*c_vals)
                        if not eval(formula):
                            yield name, {
                                "status": 0,
                                "output": "Condition not met",
                                "timestamp": ts,
                            }
                            continue
                    except:
                        self.log.info('Diamond : %s condition failed' % name)
                        self.log.debug(
                            'Diamond : trace - %s' % traceback.format_exc())
                        continue

                try:
                    vals, ts = self.gather_values(
                            name, check['expression']['metrics'])
                    if not vals:
                        continue

                    formula = check['expression']['formula'].format(*vals)
                    computed = float(eval(formula))
                except:
                    self.log.info('Diamond : %s expression failed' % name)
                    self.log.debug(
                        'Diamond : trace - %s' % traceback.format_exc())
                    continue

                status, output = self.range_check(
                    computed, **check['thresholds'])

                yield name, {
                    "status": status,
                    "output": output,
                    "timestamp": ts,
                }

        # Retention cleanup loop
        for metric in self.metrics:
            if metric not in self.retention:
                continue

            while (
                len(self.retention[metric]) > 1 and
                self.retention[metric][0][1] <
                (time.time() - self.metrics[metric]['retention'])
            ):
                self.retention[metric].pop(0)

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
                return os.open(fifo_path, os.O_RDONLY)
        except:
            self.log.error('Diamond : failed to open %s' % fifo_path)
            self.log.debug('Diamond : trace - %s' % traceback.format_exc())
            return None
        return None

    def read_fifo(self, fifo_fd):
        try:
            res = os.read(fifo_fd, 4096).decode('utf-8')
            if res != "":
                return res
            else:
                return None
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
