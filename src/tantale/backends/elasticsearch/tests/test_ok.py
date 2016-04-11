# coding=utf-8

from __future__ import print_function

import re
import time
import random

import configobj
from test import TantaleTC


class ElasticsearchTC(TantaleTC):
    def randStatus(self):
        # Push some failed checks
        state = random.randrange(0, 29)
        if state < 27:
            state = 0
        elif state == 27:
            state = 1
        elif state == 28:
            state = 2
        elif state == 29:
            state = 3
        return state

    def push_checks(self, hosts_nb, services_per_host):
        """ Input """
        input_s = self.getSocket('Input')
        # Generate some checks
        checks = []
        for host in range(hosts_nb):
            checks.append((int(time.time()), host, self.randStatus(), host))
            input_s.send(
                "%d host_%d Host %d out ><&(){}[],;:!\\|user_1,user_%d\n" %
                checks[-1])

            for service in range(services_per_host):
                checks.append((
                    int(time.time()), host, service, self.randStatus(), host))
                input_s.send(
                    "%d host_%d Service_%d %d output %%|user_1,user_%d\n" %
                    checks[-1])
        input_s.close()

    def test_Status(self):
        self.start()
        live_s = self.getSocket('Livestatus')

        # Status table
        live_s.send("%s\n" % self.getLivestatusRequest('status'))
        res = live_s.recv()
        self.assertEqual(
            res, "200          32 [['tantale', '1.0', 0, '', '']]\n")

        live_s.close()
        self.stop()

    def test_Workflow(self):
        if self.bench:
            config = {'backends': {
                'ElasticsearchBackend': {
                    'batch': 1000, 'recreate_index_for_test': True}
            }}
            hosts_nb = 2000
            services_per_host = 3
        else:
            config = {'backends': {
                'ElasticsearchBackend': {
                    'batch': 25, 'recreate_index_for_test': True}
            }}
            hosts_nb = 50
            services_per_host = 3

        # Merge config addins and start
        self.server.config.merge(configobj.ConfigObj(config))
        self.start()

        # Input (create)
        start = time.time()
        self.push_checks(hosts_nb, services_per_host)

        live_s = self.getSocket('Livestatus')

        # Hosts stats (wait every input done)
        regexp = r'200\s+\d+ \[\[' + str(hosts_nb) + ', \d+, \d+\]\]\n'
        tries = 0
        while True:
            time.sleep(1)
            tries += 1
            if tries > 10:
                break
            live_s.send("%s\n" % self.getLivestatusRequest('hosts_stats'))
            res = live_s.recv()
            if re.search(regexp, res):
                break
        self.assertRegexpMatches(
            res, regexp, "Input longer than 10s, quitting")

        stop = time.time()
        if self.bench:
            print("")
            print(
                "Created %d checks in %f seconds." %
                ((hosts_nb * (services_per_host + 1)), (stop - start)))

        # Check limit enforced on hosts
        live_s.send("%s\n" % self.getLivestatusRequest('hosts_get'))
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(len(res), 1, "Check limit failed")

        # Check user fitler against hosts
        live_s.send("%s\n" % self.getLivestatusRequest('hosts_get_user_2'))
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(len(res), 1, "Auth User filter failed")

        # Get logs
        live_s.send("%s\n" % self.getLivestatusRequest('hosts_get'))
        res = live_s.recv()

        self.stop()
