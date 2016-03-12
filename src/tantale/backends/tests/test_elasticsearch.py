# coding=utf-8

from __future__ import print_function
import os
import sys
import test
import six
import time
import sys
import json

import test
from test import DaemonTestCase
from test import unittest, ANY, call, MagicMock, Mock, mock_open, patch


class ElasticclientMock(Mock):
    """ Mock multiprocessing into file - no better idea """
    def bulk(self, *args, **kwargs):
        result_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '.test_tmp')
        kwargs['args'] = args
        with open(result_file, 'a') as f:
            f.write(json.dumps(kwargs))
            f.write('\n')
            f.flush()
        return {}

    @classmethod
    def get_results(cls):
        result_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '.test_tmp')
        res = []
        with open(result_file, 'r') as f:
            for line in f.readlines():
                res.append(json.loads(line))
        os.unlink(result_file)
        return res


class ElasticsearchTestCase(DaemonTestCase):
    def setUp(self):
        # Improve default config
        self.config = {'backends': {
            'ElasticsearchBackend': {'batch': 1}
        }}

        # Mock elasticsearch client
        self.elastic_mod = sys.modules['elasticsearch.client']
        test.Elasticsearch = ElasticclientMock
        sys.modules['elasticsearch.client'] = test

        super(ElasticsearchTestCase, self).setUp()

    def test_sendOneCheck(self):
        sock = self.connect()

        timestamp = int(time.time())
        check = "%s localhost test_check 0 test on some special chars" \
                " ><&(){}[],;:!\n" % timestamp
        check = six.b(check)
        sock.send(check)

        sock.close()
        self.flush()

        bulk_calls = ElasticclientMock.get_results()
        self.assertTrue(len(bulk_calls) == 1)

    def tearDown(self):
        # Unmock
        sys.modules['elasticsearch.client'] = self.elastic_mod


class BenchElasticsearchTestCase(DaemonTestCase):
    def setUp(self):
        # Improve default config
        self.batch_size = 1000
        self.config = {
            'backends': {
                'ElasticsearchBackend': {
                    'batch': self.batch_size,
                    'backlog_size': self.batch_size * 10,
                }
            },
            'server': {'queue_size': 100000},
        }

        # Mock elasticsearch client
        self.elastic_mod = sys.modules['elasticsearch.client']
        test.Elasticsearch = ElasticclientMock
        sys.modules['elasticsearch.client'] = test

        super(BenchElasticsearchTestCase, self).setUp()

    def test_sendFromOne(self):
        expected_time = float(5)
        how_many = 50000

        start = time.time()

        sock = self.connect()
        for a in range(how_many):
            timestamp = int(time.time())
            check = "%s localhost test_check 0 test on some special chars" \
                    " ><&(){}[],;:!\n" % timestamp
            check = six.b(check)
            sock.send(check)
        sock.close()
        self.flush()

        stop = time.time()

        # Check call_count
        bulk_calls = ElasticclientMock.get_results()
        print(len(bulk_calls))
        self.assertTrue(len(bulk_calls) == int(how_many / self.batch_size))

        # Check time
        print(repr(stop - start))
        self.assertTrue(
            (stop - start) < expected_time,
            "Runtime too long (more than %s) - %s secs" %
            (expected_time, (stop - start)))

    def tearDown(self):
        # Unmock
        sys.modules['elasticsearch.client'] = self.elastic_mod
