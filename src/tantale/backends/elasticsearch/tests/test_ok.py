# coding=utf-8

from __future__ import print_function

import re
import time
import random

import configobj
from test import TantaleTC


class ElasticsearchTC(TantaleTC):
    def randStatus(self, seed):
        if seed == 0:
            # 0 has status warning
            return 1
        elif seed == 1:
            # 1 has status crit
            return 2
        elif seed == 2:
            # 2 has status unknown
            return 3
        else:
            return 0

    def push_checks(self, hosts_nb, services_per_host, delay=0):
        """ Input """
        input_s = self.getSocket('Input')
        # Generate some checks
        checks = []
        for host in range(hosts_nb):
            checks.append(
                (int(time.time()) - delay, host, self.randStatus(host), host))
            input_s.send(
                "%d host_%d Host %d out ><&(){}[],;:!\\|user_1,user_%d\n" %
                checks[-1])

            for service in range(services_per_host):
                checks.append((
                    int(time.time()) - delay,
                    host, service, self.randStatus(service), host))
                input_s.send(
                    "%d host_%d service_%d %d output %%|user_1,user_%d\n" %
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
                    'batch': 5, 'recreate_index_for_test': True}
            }}
            hosts_nb = 10
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
            live_s.send(self.getLivestatusRequest('hosts_stats'))
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
        live_s.send(self.getLivestatusRequest('get_hosts_limit_1'))
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(len(res), 1, "Check limit failed")

        # Check user filter against hosts
        live_s.send(
            self.getLivestatusRequest('get_hosts_filtered_by_user') % "user_2")
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(len(res), 1, "AuthUser filter failed")

        # Get logs / check order
        live_s.send("%s\n" % self.getLivestatusRequest('get_logs'))
        res = live_s.recv()
        res = eval(res[16:])
        self.assertTrue(len(res) > 0, "Logs empty")

        # Check downtimes logic on host
        live_s.send(self.getLivestatusRequest('push_host_downtime') % 'host_1')
        for nb in range(5):
            time.sleep(1)
            live_s.send(self.getLivestatusRequest('get_downtimes'))
            res = live_s.recv()
            res = eval(res[16:])
            if len(res) > 0:
                break
        self.assertEqual(len(res), 1, "Downtime push failed")
        self.assertEqual(res[0][-5], 'host_1', "Downtime push incorrect")
        # Check not more reported as problem
        live_s.send(
            self.getLivestatusRequest('get_host_is_problem') % 'host_1')
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(len(res), 0, "Downtimed host still in problem")

        # Check downtimes logic on service
        live_s.send(self.getLivestatusRequest(
            'push_service_downtime') % ('host_1', 'service_0'))
        for nb in range(5):
            time.sleep(1)
            live_s.send(self.getLivestatusRequest('get_downtimes'))
            res = live_s.recv()
            res = eval(res[16:])
            if len(res) > 1:
                break
        self.assertEqual(len(res), 2, "Downtime push failed")

        self.stop()

    def test_Freshness(self):
        # Low freshness timeout to bypass loop time
        config = {
            "modules": {"Input": {"freshness_timeout": 3}}
        }
        if self.bench:
            config['backends'] = {
                'ElasticsearchBackend': {
                    'batch': 1000, 'recreate_index_for_test': True}
            }
            hosts_nb = 2000
            services_per_host = 3
        else:
            config['backends'] = {
                'ElasticsearchBackend': {
                    'batch': 5, 'recreate_index_for_test': True}
            }
            hosts_nb = 10
            services_per_host = 3

        # Merge config addins and start
        self.server.config.merge(configobj.ConfigObj(config))
        self.start()

        # Input (create)
        start = time.time()
        self.push_checks(hosts_nb, services_per_host, delay=60)

        live_s = self.getSocket('Livestatus')

        # Hosts stats (wait every input done)
        regexp = r'200\s+\d+ \[\[\d+, ' + str(hosts_nb) + ', \d+\]\]\n'
        tries = 0
        while True:
            time.sleep(1)
            tries += 1
            if tries > 20:
                break
            live_s.send(self.getLivestatusRequest('hosts_stats'))
            res = live_s.recv()
            if re.search(regexp, res):
                break
        self.assertRegexpMatches(
            res, regexp, "Input longer than 10s, quitting")

        stop = time.time()
        if self.bench:
            print("")
            print(
                "Update %d checks to outdated in %f seconds." %
                ((hosts_nb * (services_per_host + 1)), (stop - start)))
