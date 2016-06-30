# coding=utf-8

from __future__ import print_function

import time
import logging
import traceback


class BaseSource(object):
    def __init__(self, config, checks, res_q):
        self.log = logging.getLogger('tantale.client')

        self.config = config
        self.checks = checks
        self.res_q = res_q

        now = time.time()
        for name in self.checks:
            # Give one interval of grace time
            self.checks[name]['next'] = now + self.checks[name]['interval']

        self.process_config()

    def process_config(self):
        pass

    def run(self):
        """
        Source run catching errors and managing loop against exec_check
        Args :
          event : Threading.Event called to trigger sending
          results : results stash (to feed)
        """
        while True:
            check = self.get_and_wait_next_check()

            try:
                self.execute_check(check)
            except:
                self.log.warning(
                    "Check %s failed to execute on source %s" %
                    (check, self.checks[check]['source']))
                self.log.debug(traceback.format_exc())

    def send(self, check_name, status, message, timestamp=None):
        """
        Format results to be sent
        """
        if not timestamp:
            timestamp = int(time.time())

        self.send_raw({
            "check": self.checks[check_name]['name'],
            "timestamp": timestamp,
            "hostname": self.checks[check_name]['hostname'],
            "status": status,
            "output": message,
            "interval": self.checks[check_name]['interval'],
            "contacts": self.checks[check_name]['contacts'],
        })

    def send_raw(self, check_dict):
        self.res_q.put_nowait(check_dict)

    def get_and_wait_next_check(self):
        """
        Determine next check to be executed/computed (with interval)
        """
        sched = None
        check = None
        for name in self.checks:
            if sched is None or sched > self.checks[name]['next']:
                sched = self.checks[name]['next']
                check = name

        # Wait next
        now = time.time()
        if sched > now:
            time.sleep(sched - now)

        # Reschedule
        now = time.time()
        self.checks[check]['next'] = now + self.checks[check]['interval']

        return check
