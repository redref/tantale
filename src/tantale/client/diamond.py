# coding=utf-8

from __future__ import print_function

import os
import stat
import time

try:
    BlockingIOError
except:
    BlockingIOError = None


class DiamondSource(object):
    def __init__(self, config, checks):
        self.config = config

    def run(self, event, results):
        while True:
            time.sleep(10)

    def process_diamond(self, lines):
        result = ""
        for line in lines.strip().split('\n'):
            llist = line.split(' ')
            value = float(llist[1])
            ts = llist[2]

            for check in self.checks['diamond']:
                # Parse metric and enqueue value
                if check['metric_prefix'] and llist[0].startswith(
                    check['metric_prefix']
                ):
                    name = llist[0][len(check['metric_prefix']) + 1:]
                else:
                    name = llist[0]

                if name in check['metrics']:
                    self.metric_stash[name] = value
                else:
                    continue

                # Compute a value on this check
                vals = []
                for metric in check['metrics']:
                    if metric in self.metric_stash:
                        vals.append(self.metric_stash[metric])
                    else:
                        self.log.warn(
                            "Check '%s': missing metric %s" %
                            (check['name'], metric))
                        vals = None
                        continue

                if vals:
                    try:
                        computed = eval(check['formula'].format(*vals))
                        computed = float(computed)
                    except:
                        self.log.debug(traceback.format_exc())

                    status, output = self.range_check(
                        value, **check['thresholds'])

                    result += "%s %s %s %s %s" % (
                        ts, check['hostname'], check['name'], status, output)

                    if self.contacts:
                        result += "|%s\n" % self.contacts
                    else:
                        result += "\n"

        return result

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

    def parse_config_checks(self):
        for key in self.config:
            if isinstance(self.config[key], dict):
                check = self.config[key]
                check_type = check.get('type', None)

                if check_type == "diamond":

                    # WORK ON THRESHOLDS
                    thresholds = check.get('thresholds', None)
                    if not thresholds:
                        self.log.info(
                            "Dropping check '%s', no thresholds defined" % key)

                    if len(thresholds) != 4:
                        self.log.info(
                            "Dropping check '%s', thresholds must contain"
                            " 4 elements (lc, lw, uw, uc)" % key)

                    explicit_thresholds = {}
                    for idx, name in enumerate(
                        ['lower_crit', 'lower_warn',
                         'upper_warn', 'upper_crit']
                    ):
                        try:
                            explicit_thresholds[name] = float(thresholds[idx])
                        except ValueError:
                            explicit_thresholds[name] = None

                    # WORK ON EXPRESSION
                    expression = check.get('expression', None)
                    if not expression:
                        self.log.info(
                            "Dropping check '%s', no expression defined" % key)

                    metrics = re.findall(r'\{([^\}]+)\}', expression)
                    formula = re.sub(r'\{[^\}]+\}', '{}', expression)

                    self.checks[check_type].append({
                        "name": key,
                        "hostname": check.get('hostname', socket.getfqdn()),
                        "metric_prefix": check.get('metric_prefix', ''),
                        "thresholds": explicit_thresholds,
                        "metrics": metrics,
                        "formula": formula,
                    })

                    self.log.info(
                        "Found check %s" % self.checks[check_type][-1])

    def create_fifo(self, fifo_path):
        if fifo_path and not os.path.exists(fifo_path):
            os.mkfifo(fifo_path, 0o0660)
        elif not stat.S_ISFIFO(os.stat(fifo_path).st_mode):
            raise Exception("%s not a fifo file")

    def open_fifo(self, fifo_path):
        try:
            if fifo_path:
                return os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        except:
            self.log.error('Failed to open %s' % fifo_path)
            self.log.debug('Trace: %s' % traceback.format_exc())
            return None

    def read_fifo(self, fifo_fd):
        try:
            res = os.read(fifo_fd, 4096).decode('utf-8')
            if res != "":
                return res
            else:
                return False
        except BlockingIOError:
            return False
        except Exception as exc:
            # Python 2 BlockingIOError
            if isinstance(exc, OSError) and exc.errno == 11:
                return False
            self.log.debug('Trace: %s' % traceback.format_exc())
            os.close(fifo_fd)
            raise
