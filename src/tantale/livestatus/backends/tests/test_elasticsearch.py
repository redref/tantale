# coding=utf-8

from __future__ import print_function

import os
import sys
import test
import time
import sys
import json
from six import b as bytes

import test
from test import DaemonTestCase
from test import Mock


class ElasticclientMock(Mock):
    """ Mock multiprocessing into file - no better idea """
    fixture = None

    def msearch(self, body, **kwargs):
        line = self.fixture[:self.fixture.index('\n')]
        self.fixture[self.fixture.index('\n') + 1:]
        return json.loads(line)


class ElasticsearchBaseTestCase(object):
    def mocking(self):
        # Mock elasticsearch client
        self.elastic_mod = sys.modules['elasticsearch.client']
        test.Elasticsearch = ElasticclientMock
        test.Elasticsearch.fixture = self.getFixture('elasticsearch/search')
        sys.modules['elasticsearch.client'] = test

    def unmocking(self):
        # Unmock
        sys.modules['elasticsearch.client'] = self.elastic_mod


class ElasticsearchTestCase(DaemonTestCase, ElasticsearchBaseTestCase):
    def setUp(self):
        # Daemon config
        self.config = {}
        super(ElasticsearchTestCase, self).setUp()

    def test_Queries(self):
        sock = self.get_socket(6557)

        res = ""
        requests = self.getFixture('elasticsearch/requests')
        for line in requests.split('\n'):
            sock.send(bytes(line + '\n'))
            if line == '':
                res += sock.recv(4096)

        sock.close()
        self.flush()

        self.assertEqual(res, self.getFixture('elasticsearch/responses'))


class BenchElasticsearchTestCase(DaemonTestCase, ElasticsearchBaseTestCase):
    def setUp(self):
        # Improve default config in setup (before daemon start)
        self.config = {}
        super(BenchElasticsearchTestCase, self).setUp()

    def test_sendFromOne(self):
        expected_time = float(6)
        how_many = 20000

        start = time.time()

        # TODO
        sock.close()
        self.flush()

        stop = time.time()
