# coding=utf-8

from __future__ import print_function

import time
import json
import random
from six import b as bytes

from test import InputTestCase
from tantale.backends.elasticsearch.tests.mixins \
    import ElasticsearchOk, ElasticsearchConnectFail


class ElasticsearchInputTestCase(ElasticsearchConnectFail, InputTestCase):
    def test_FailedConnection(self):
        sock = self.get_socket()

        timestamp = int(time.time())
        checks = [
            "%s localhost Host 0 test funkychars ><&(){}[],;:!\n",
            "%s localhost Service 0 test funkychars ><&(){}[],;:!\n",
        ]
        for check in checks:
            sock.send(bytes(check % timestamp))

        sock.close()
        self.flush()

        # TODO tests (logging, handle, ...)


class ElasticsearchTestCase(ElasticsearchOk, InputTestCase):
    def setUp(self):
        # Daemon config
        self.config = {'backends': {
            'ElasticsearchBackend': {'batch': 1}
        }}
        super(ElasticsearchTestCase, self).setUp()

    def test_One(self):
        sock = self.get_socket()

        timestamp = int(time.time())
        checks = [
            "%s localhost Host 0 test funkychars ><&(){}[],;:!\n",
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

        # TOFIX further test on those results


class BenchElasticsearchTestCase(ElasticsearchOk, InputTestCase):
    def setUp(self):
        # Improve default config in setup (before daemon start)
        self.batch_size = 4000
        self.config = {
            'backends': {
                'ElasticsearchBackend': {
                    'batch': self.batch_size,
                    'backlog_size': self.batch_size * 10,
                }
            },
            'modules': {'Input': {'queue_size': 100000}},
        }
        super(BenchElasticsearchTestCase, self).setUp()

    def test_Mono(self):
        expected_time = float(9)
        how_many = 20000

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
