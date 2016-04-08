# coding=utf-8

from __future__ import print_function

import time
import json
import random
from six import b as bytes

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

    def test_Workflow(self):
        if self.bench:
            config = {'backends': {
                'ElasticsearchBackend': {'batch': 1000}
            }}
            hosts_nb = 4000
            services_per_host = 3
        else:
            config = {}
            hosts_nb = 1
            services_per_host = 3

        # Start the daemon (merging config addins)
        self.server.config.merge(configobj.ConfigObj(config))
        self.start()

        #
        # Input
        #
        input_s = self.getSocket('Input')
        # Generate some checks
        checks = []
        for host in range(hosts_nb):
            checks.append((int(time.time()), host, self.randStatus()))
            input_s.send(
                "%d host_%d Host %d output ><&(){}[],;:!\\"
                "|user_1,user_2\n" % checks[-1])

            for service in range(services_per_host):
                checks.append((int(time.time()), host, self.randStatus()))
                input_s.send(
                    "%d host_%d Host %d output %%|user_1,user_2\n" %
                    checks[-1])
        input_s.close()

        #
        # Livestatus get
        #
        live_s = self.getSocket('Livestatus')
        requests = self.getParsedFixture('requests')

        live_s.send(requests[0] + "\n")
        a = live_s.recv()
        print(a)
        print(requests)

        # Stop the daemon
        self.stop()


"""
class ElasticsearchInputFailTestCase(ElasticsearchConnectFail, InputTestCase):
    def test_FailedConnection(self):
        sock = self.get_socket()

        
        checks = [
            
            "%s localhost Service 0 test funkychars ><&(){}[],;:!\n",
        ]
        for check in checks:
            sock.send(bytes(check % timestamp))

        sock.close()
        self.flush()

        # TODO tests (logging, handle, ...)


class ElasticsearchInputTestCase(ElasticsearchOk, InputTestCase):
    def setUp(self):
        # Daemon config
        self.config = {'backends': {
            'ElasticsearchBackend': {'batch': 1}
        }}
        super(ElasticsearchInputTestCase, self).setUp()

    def test_One(self):
        sock = self.get_socket()

        timestamp = int(time.time())
        checks = [
            "%s localhost Host 0 test funkychars ><&(){}[],;:!"
            "|user_1,user_2\n",
            "%s localhost Service 0 test funkychars ><&(){}[],;:!\n",
        ]

        for check in checks:
            sock.send(bytes(check % timestamp))

        sock.close()
        self.flush()

        bulk_calls = self.mock_class.get_calls()
        wait = 4
        self.assertEqual(
            len(bulk_calls), wait,
            "Calls (%s not %s): %s" % (
                len(bulk_calls), wait,
                '\n' + '\n'.join([str(call) for call in bulk_calls])))


class BenchElasticsearchInputTestCase(ElasticsearchOk, InputTestCase):
    def setUp(self):
        # Improve default config in setup (before daemon start)
        self.batch_size = 1000
        self.config = {
            'backends': {
                'ElasticsearchBackend': {
                    'batch': self.batch_size,
                    'backlog_size': self.batch_size * 10,
                }
            },
            'modules': {'Input': {'queue_size': 100000}},
        }
        super(BenchElasticsearchInputTestCase, self).setUp()

    def test_Mono(self):
        if self.mock:
            expected_time = float(9)
            how_many = 20000
        else:
            # Provide initial data
            expected_time = float(2)
            how_many = 1000

        start = time.time()

        sock = self.get_socket()
        for a in range(how_many):
            timestamp = int(time.time())
            checks = [
                "%s local%d Host %d test funkychars ><&(){}[],;:!\n",
                "%s local%d Service %d test funkychars ><&(){}[],;:!\n",
            ]
            for check in checks:
                # Push 10% some random to test send_logs
                state = random.randrange(0, 29)
                if state < 27:
                    state = 0
                elif state == 27:
                    state = 1
                elif state == 28:
                    state = 2
                elif state == 29:
                    state = 3
                sock.send(bytes(check % (timestamp, a, state)))
        sock.close()
        self.flush()

        stop = time.time()

        print("\nInput bench time %f" % (stop - start))

        # Test if mock
        if getattr(self, 'mock_class', None):
            # Check call_count
            bulk_calls = self.mock_class.get_calls()
            # 4 times how_many - Host/Service + both events
            wait = int(how_many / self.batch_size * 4)
            self.assertEqual(
                len(bulk_calls), wait,
                "Calls (%d not %d)" % (len(bulk_calls), wait))

        # Check time
        self.assertTrue(
            (stop - start) < expected_time,
            "Runtime too long (more than %s) - %s secs" %
            (expected_time, (stop - start)))
"""
