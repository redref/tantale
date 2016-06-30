# coding=utf-8

from __future__ import print_function

import time
import shlex
import logging
import traceback
from threading import Thread
from subprocess import Popen, CalledProcessError, PIPE, STDOUT

try:
    from Queue import Queue, Empty, Full
except:
    from queue import Queue, Empty, Full

from tantale.client.source import BaseSource


class ExternalSource(BaseSource):
    def process_config(self):
        self.nb_workers = int(self.config['external_workers'])

        for check in self.checks:
            self.checks[check]['command'] = shlex.split(
                self.checks[check]['command'])

        cmd_q = Queue(maxsize=self.nb_workers)
        res_q = Queue()
        self.threads = []

        for i in range(self.nb_workers):
            t = Thread(target=self.worker, args=(cmd_q, res_q))
            t.daemon = True
            self.threads.append(t)
            t.start()

        t = Thread(target=self.sender, args=(res_q,))
        t.daemon = True
        t.start()

        self.cmd_q = cmd_q

    def execute_check(self, check):
        try:
            self.cmd_q.put_nowait((check, self.checks[check]['command']))
        except Full:
            self.send(check, 3, 'OUTDATED - No result yet')

    def sender(self, res_q):
        """
        Wait for results, then forward it
        """
        while True:
            self.send(*res_q.get(True))
            res_q.task_done()

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

            res_q.put_nowait(
                (name, proc.returncode, output, int(time.time())))
            cmd_q.task_done()
