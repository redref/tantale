# coding=utf-8

from __future__ import print_function

import time
import shlex
import logging
import traceback
from threading import Thread
from subprocess import Popen, CalledProcessError, PIPE, STDOUT

try:
    from Queue import Queue, Empty
except:
    from queue import Queue, Empty


class ExternalSource(object):
    def __init__(self, config, checks):
        self.log = logging.getLogger('tantale.client')
        self.nb_workers = int(config['external_workers'])

        for check in checks:
            checks[check]['command'] = shlex.split(checks[check]['command'])
            checks[check]['interval'] = checks[check].get(
                'interval', config['interval'])
            checks[check]['next'] = time.time()

        self.checks = checks

    def run(self, event, results):
        """
        Thread class enter point
            event - threading.Event - trigger checks push
            results - reference to global results hash
        """
        # Spawn workers
        cmd_q = Queue()
        res_q = Queue()
        threads = []
        for i in range(self.nb_workers):
            t = Thread(target=self.worker, args=(cmd_q, res_q))
            t.daemon = True
            threads.append(t)
            t.start()

        t = Thread(target=self.scheduler, args=(cmd_q,))
        t.daemon = True
        t.start()

        # Wait results
        while True:
            check, ts, code, out = res_q.get(True)

            results[check]['output'] = out
            results[check]['timestamp'] = ts
            if results[check]['status'] != code:
                results[check]['status'] = code
                event.set()

            res_q.task_done()

    def scheduler(self, cmd_q):
        while True:
            # Determine next check to be execute
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

            # Pass to worker
            cmd_q.put((check, self.checks[check]['command']))

    def worker(self, cmd_q, res_q):
        while True:
            name, cmd = cmd_q.get(True)

            self.log.debug("External : launch %s" % cmd)

            try:
                proc = Popen(
                    cmd,
                    stdin=None, stdout=PIPE, stderr=STDOUT, close_fds=True)

                output = ""
                while True:
                    out, err = proc.communicate()
                    proc.poll()
                    output += out.decode('utf-8')
                    if proc.returncode is not None:
                        break

            except:
                self.log.debug(traceback.format_exc())

            # Truncate multi-line output
            try:
                output = output[:output.index("\n")]
            except:
                pass

            res_q.put((name, int(time.time()), proc.returncode, output))
            cmd_q.task_done()
