# coding=utf-8

from __future__ import print_function
import os
import sys
import test
import time
import sys
import json
import random
from six import b as bytes

import test
from test import DaemonTestCase
from test import unittest, ANY, call, MagicMock, Mock, mock_open, patch


class ElasticclientMock(Mock):
    """ Mock multiprocessing into file - no better idea """
    result_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '.test_tmp')

    def bulk(self, body, **kwargs):
        lines = int(body.count('\n')) + 1
        kwargs['body'] = body
        with open(self.result_file, 'a') as f:
            f.write(json.dumps(kwargs))
            f.write('\n')
            f.flush()

        # At least correct return on _send_data routine / all refreshed
        timestamp = int(time.time()) * 1000 + 1
        item = {'update': {'get': {'fields': {'timestamp': [timestamp]}}}}
        return {
            'errors': False,
            'items': [item for i in range(int(lines / 2))]}

    @classmethod
    def get_results(cls):
        res = []
        try:
            with open(cls.result_file, 'r') as f:
                for line in f.readlines():
                    res.append(json.loads(line))
        except:
            pass
        try:
            os.unlink(cls.result_file)
        except:
            pass
        return res


class ElasticsearchBaseTestCase(object):
    def mocking(self):
        # Mock elasticsearch client
        self.elastic_mod = sys.modules['elasticsearch.client']
        test.Elasticsearch = ElasticclientMock
        sys.modules['elasticsearch.client'] = test

    def unmocking(self):
        # Unmock
        sys.modules['elasticsearch.client'] = self.elastic_mod


class ElasticsearchTestCase(DaemonTestCase, ElasticsearchBaseTestCase):
    def setUp(self):
        # Daemon config
        self.config = {'backends': {
            'ElasticsearchBackend': {'batch': 1}
        }}
        super(ElasticsearchTestCase, self).setUp()

    def test_sendOne(self):
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

        bulk_calls = ElasticclientMock.get_results()
        wait = 4
        self.assertEqual(
            len(bulk_calls), wait,
            "Calls (%s not %s): %s" % (
                len(bulk_calls), wait,
                '\n' + '\n'.join([str(call) for call in bulk_calls])))

        # TOFIX further test on those results


class BenchElasticsearchTestCase(DaemonTestCase, ElasticsearchBaseTestCase):
    def setUp(self):
        # Improve default config in setup (before daemon start)
        self.batch_size = 200
        self.config = {
            'backends': {
                'ElasticsearchBackend': {
                    'batch': self.batch_size,
                    'backlog_size': self.batch_size * 10,
                }
            },
            'server': {'queue_size': 100000},
        }
        super(BenchElasticsearchTestCase, self).setUp()

    def test_sendFromOne(self):
        expected_time = float(6)
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
                state = random.randrange(0, 3)
                sock.send(bytes(check % (timestamp, a, state)))
        sock.close()
        self.flush()

        stop = time.time()

        # Check call_count
        bulk_calls = ElasticclientMock.get_results()
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
