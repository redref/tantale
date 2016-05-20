# coding=utf-8

from __future__ import print_function

import re
import time
import random
import json

import configobj
from test import TantaleTC


class ElasticsearchTC(TantaleTC):
    def randStatus(self, seed):
        """
        Provide some failed examples to play with
        """
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

    def push_checks(self, hosts_nb, services_per_host, delay=60):
        """
        Simulate X Hosts pushing hash
        """
        for host in range(hosts_nb):

            input_s = self.getSocket('Input')

            checks = {}

            checks['Host'] = {
                "status": self.randStatus(host),
                "timestamp": (int(time.time()) - delay),
                "contacts": ["user_1", "user_%d" % host],
                "hostname": "host_%d" % host,
                "output": "Check %d" % host,
            }

            for service in range(services_per_host):
                checks['service_%d' % service] = {
                    "status": self.randStatus(service),
                    "timestamp": (int(time.time()) - delay),
                    "contacts": ["user_1", "user_%d" % host],
                    "hostname": "host_%d" % host,
                    "output": "Service %d" % service,
                }

            input_s.send(json.dumps(checks) + "\n")
            input_s.close()

    def test_Status(self):
        """
        Test status API
        """
        self.start()
        live_s = self.getSocket('Livestatus')

        # Status table
        live_s.send("%s\n" % self.getLivestatusRequest('status'))
        res = live_s.recv()
        self.assertEqual(
            res, "200          32 [['tantale', '1.0', 0, '', '']]\n")

        live_s.close()
        self.stop()

    def InputAndDisplay(self, bench=False, add_config=None):
        """
        Push some checks, then check they got stored
        """
        if bench:
            hosts_nb = 2000
            services_per_host = 3
        else:
            hosts_nb = 10
            services_per_host = 3

        config = {
            'modules': {'Input': {'ttl': 1}},
            'backends': {
                'ElasticsearchBackend': {'recreate_index_for_test': True}
            }
        }

        # Merge config addins and start
        self.server.config.merge(configobj.ConfigObj(config))
        if add_config:
            self.server.config.merge(configobj.ConfigObj(add_config))
        self.start()

        # Input (create)
        start = time.time()
        self.push_checks(hosts_nb, services_per_host)

        live_s = self.getSocket('Livestatus')

        # Hosts stats (loop till everything done)
        regexp = r'200\s+\d+ \[\[' + str(hosts_nb) + ', \d+, \d+\]\]\n'
        for nb in range(20):
            time.sleep(0.5)
            live_s.send(self.getLivestatusRequest('hosts_stats'))
            res = live_s.recv()
            if re.search(regexp, res):
                break

        stop = time.time()

        self.assertRegexpMatches(
            res, regexp, "Input longer than 10s, quitting")

        if bench:
            print("")
            print(
                "Created %d checks in %f seconds." %
                ((hosts_nb * (services_per_host + 1)), (stop - start)))

    def test_InputAndDisplay(self):
        """
        Wrapper to get bench on this test
        """
        self.InputAndDisplay(self.bench)

    def test_LivestatusLimit(self):
        self.InputAndDisplay()

        live_s = self.getSocket('Livestatus')
        live_s.send(self.getLivestatusRequest('get_hosts_limit_1'))
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(len(res), 1, "Check limit failed")

    def test_LivestatusAuthUser(self):
        self.InputAndDisplay()

        live_s = self.getSocket('Livestatus')
        live_s.send(
            self.getLivestatusRequest('get_hosts_filtered_by_user') % "user_2")
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(len(res), 1, "AuthUser filter failed")

    def test_LivestatusCommandKeepalive(self):
        self.InputAndDisplay()
        live_s = self.getSocket('Livestatus')

        live_s.send(self.getLivestatusRequest('push_host_downtime') % 'host_1')
        live_s.send(self.getLivestatusRequest('push_host_downtime') % 'host_2')

        for nb in range(20):
            time.sleep(0.5)
            live_s.send(self.getLivestatusRequest('get_downtimes'))
            res = live_s.recv()
            res = eval(res[16:])
            if len(res) == 2:
                break

        self.assertEqual(len(res), 2, "Downtime push failed")

    def test_LivestatusHostDowntime(self):
        self.InputAndDisplay()
        live_s = self.getSocket('Livestatus')

        live_s.send(self.getLivestatusRequest('push_host_downtime') % 'host_1')
        # Update not synced - sleep a bit
        time.sleep(1)

        live_s.send(self.getLivestatusRequest('get_downtimes'))
        downs = live_s.recv()
        downs = eval(downs[16:])
        self.assertEqual(len(downs), 1, "Downtime push failed")
        self.assertEqual(downs[0][-5], 'host_1', "Downtime push incorrect")

        # Check not more reported as problem
        live_s.send(
            self.getLivestatusRequest('get_host_is_problem') % 'host_1')
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(len(res), 0, "Downtimed host still in problem")

        # Remove it now
        live_s.send(
            self.getLivestatusRequest('host_remove_downtime') % downs[0][0])
        time.sleep(1)

        # Check host is back
        live_s.send(
            self.getLivestatusRequest('get_host_is_problem') % 'host_1')
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(
            len(res), 1, "Host not a problem after removing downtime")

    def test_LivestatusServiceDowntime(self):
        self.InputAndDisplay()
        live_s = self.getSocket('Livestatus')

        live_s.send(self.getLivestatusRequest(
            'push_service_downtime') % ('host_1', 'service_0'))
        time.sleep(1)

        live_s.send(self.getLivestatusRequest('get_downtimes'))
        res = live_s.recv()
        res = eval(res[16:])
        self.assertEqual(len(res), 1, "Downtime push failed")

    def test_InputFreshnessWork(self):
        """
        Check freshness update works by checking logs
        Tests checks are push from the past by default
        they all trigger freshness
        """
        add_config = {"modules": {"Input": {"freshness_timeout": 1}}}
        start = time.time()
        self.InputAndDisplay(bench=self.bench, add_config=add_config)
        live_s = self.getSocket('Livestatus')

        # Hosts stats (loop till down hosts == total hosts)
        for nb in range(20):
            time.sleep(0.5)
            live_s.send(self.getLivestatusRequest('hosts_stats'))
            res = live_s.recv()
            res = eval(res[16:])
            if res[0][0] == res[0][1]:
                break

        stop = time.time()

        time.sleep(1)

        # Check freshness changes were logged
        live_s.send(self.getLivestatusRequest('get_logs'))
        res = live_s.recv()
        res = eval(res[16:])
        self.assertTrue(len(res) > 0, "Logs empty")

        if self.bench:
            print("")
            print(
                "Created then outdated those checks in %f seconds." %
                (stop - start))
