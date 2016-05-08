# coding=utf-8

from __future__ import print_function

import os
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
                self.log.info(
                    "Diamond : dropping check '%s', "
                    "no thresholds defined" % check)

            if len(thresholds) != 4:
                self.log.info(
                    "Diamond : dropping check '%s', thresholds must contain "
                    "4 elements (lc, lw, uw, uc)" % check)

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

            # Expression
            expression = checks[check].get('expression', None)
            if not expression:
                self.log.info(
                    "Diamond : dropping check '%s', "
                    "no expression defined" % key)

            metrics = re.findall(r'\{([^\}]+)\}', expression)
            checks[check]['formula'] = re.sub(r'\{[^\}]+\}', '{}', expression)

            # Save full metrics name
            checks[check]['metrics'] = []
            for metric in metrics:
                if checks[check]['prefix'] != "":
                    metric = checks[check]['prefix'] + metric
                # To check
                checks[check]['metrics'].append(metric)
                # To global
                self.metrics[metric] = self.metrics.get(metric, [])
                self.metrics[metric].append(check)

        self.checks = checks

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

            self.retention[name] = (value, ts)

            # Compute check
            for check in self.metrics[name]:

                lower_ts = None
                vals = []

                for metric in self.checks[check]['metrics']:

                    if metric not in self.retention:
                        self.log.info(
                            "Diamond : %s missing metric %s" %
                            (check, metric))
                        vals = None
                        break

                    if (
                        lower_ts is None or
                        self.retention[metric][1] < lower_ts
                    ):
                        lower_ts = self.retention[metric][1]

                    vals.append(self.retention[metric][0])

                if vals is None:
                    continue

                try:
                    formula = self.checks[check]['formula'].format(*vals)
                    computed = float(eval(formula))
                except:
                    self.log.info('Diamond : %s expression failed' % check)
                    self.log.debug(
                        'Diamond : trace - %s' % traceback.format_exc())
                    continue

                status, output = self.range_check(
                    value, **self.checks[check]['thresholds'])

                yield check, {
                    "status": status,
                    "output": output,
                    "timestamp": lower_ts,
                }

    def range_check(
        self, value,
        lower_crit=None, lower_warn=None, upper_warn=None, upper_crit=None
    ):
        """ Compare with thresholds """
        message = "Value %f %%s than %%f" % value

        if lower_crit and float(value) < float(lower_crit):
            return 2, message % ('lower', lower_crit)

        elif lower_warn and float(value) < float(lower_warn):
            return 1, message % ('lower', lower_warn)

        elif upper_warn and float(value) > float(upper_warn):
            return 1, message % ('upper', upper_warn)

        elif upper_crit and float(value) > float(upper_crit):
            return 2, message % ('upper', upper_crit)

        else:
            return 0, "Value %f (%s, %s, %s, %s)" % \
                (value, lower_crit, lower_warn, upper_warn, upper_crit)

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
