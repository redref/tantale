# coding=utf-8

from __future__ import print_function

import os
import stat
import signal
import traceback
import logging
import re

import socket
import select
from six import b as bytes

try:
    from setproctitle import setproctitle, getproctitle
except ImportError:
    setproctitle = None

try:
    BlockingIOError
except:
    BlockingIOError = None


class Client(object):
    """
    Tantale client
    Read one FIFO in Nagios format
    Read one FIFO in Diamond/Graphite format
    Send to Tantale Input
    """
    def __init__(self, config):
        # Initialize Logging
        self.log = logging.getLogger('tantale')

        # Process signal
        self.running = True

        # Save our config
        self.config = config['modules']['Client']
        self.my_hostname = socket.getfqdn()

        # Output config
        self.host = self.config['server_host']
        self.port = int(self.config['server_port'])
        self.sock = None

        # Contacts
        if self.config['contacts']:
            self.contacts = ','.join(self.config['contacts'])
        else:
            self.contacts = None

        # Diamond input config
        self.diamond_fifo = self.config['diamond_fifo']
        self.create_fifo(self.diamond_fifo)

        # Nagios input config
        self.nagios_fifo = self.config['nagios_fifo']
        self.create_fifo(self.nagios_fifo)

        # Nagios regexp (drop perfdata)
        self.pattern = re.compile(
            r'\[(?P<timestamp>\d+)\] PROCESS_SERVICE_CHECK_RESULT;'
            '(?P<hostname>[^;]+);'
            '(?P<check>[^;]+);'
            '(?P<status>[^;]+);'
            '(?P<output>.*)(|\|.*$)'
        )

        # Pre-provide checks
        self.checks = {"diamond": []}
        self.metric_stash = {}

    def __del__(self):
        self.close()

    def run(self, init_done=None):
        if setproctitle:
            setproctitle('%s - Client' % getproctitle())

        self.parse_config_checks()

        # Gentle out
        pipe = os.pipe()

        def sig_handler(signum, frame):
            self.log.debug("%s received" % signum)
            self.running = False
            os.write(pipe[1], bytes("END\n"))
        signal.signal(signal.SIGTERM, sig_handler)

        diamond_fd = None
        nagios_fd = None

        if init_done:
            init_done.set()

        self.connect()

        while self.running:
            # Open diamond
            if self.diamond_fifo and not diamond_fd:
                diamond_fd = self.open_fifo(self.diamond_fifo)

            # Open nagios
            if self.nagios_fifo and not nagios_fd:
                nagios_fd = self.open_fifo(self.nagios_fifo)

            # Wait IO
            fds = [pipe[0]]
            for fd in (diamond_fd, nagios_fd):
                if fd:
                    fds.append(fd)

            try:
                r, o, e = select.select(fds, [], [], 60)
            except:
                # Gentle exit on signal
                break

            # Process
            result = ""
            for fd in r:
                if fd == diamond_fd:
                    try:
                        result += self.process_diamond(
                            self.read_fifo(diamond_fd))
                    except:
                        self.log.debug(
                            'Diamond error:\n%s' % traceback.format_exc())
                        self.diamond_fd = None

                elif fd == nagios_fd:
                    try:
                        res = self.read_fifo(nagios_fd)
                        if res:
                            result += self.process_nagios(res)
                    except:
                        self.log.debug(
                            'Nagios error:\n%s' % traceback.format_exc())
                        self.nagios_fd = self.open_fifo(self.nagios_fifo)

            # Send
            if result != "":
                self.send(result)

        self.log.info("Exit")

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
            pass
        except Exception as exc:
            # Python 2 BlockingIOError
            if isinstance(exc, OSError) and exc.errno == 11:
                return False
            self.log.debug('Trace: %s' % traceback.format_exc())
            os.close(fifo_fd)
            raise

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(True)
        self.sock.connect((self.host, self.port))

    def close(self):
        if self.sock:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()

    def send(self, result):
        if not self.sock:
            self.connect()

        if not self.sock:
            self.log.debug(
                'Reconnect to %s:%s failed' % (self.host, self.port))

        try:
            self.sock.send(bytes(result))
        except:
            pass

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

        self.log.debug("Sending: %s" % result)
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

    def process_nagios(self, lines):
        result = ""
        for line in lines.strip().split('\n'):
            match = re.match(self.pattern, line)

            groups = match.groupdict()
            result += ' '.join([
                groups['timestamp'],
                groups['hostname'],
                groups['check'],
                groups['status'],
                groups['output'],
            ])

            if self.contacts:
                result += "|%s\n" % self.contacts
            else:
                result += "\n"

        return result

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
