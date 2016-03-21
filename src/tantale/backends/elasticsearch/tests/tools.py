# coding=utf-8

from __future__ import print_function

import os
import sys
import json
import time

import test
from test import DaemonTestCase

from elasticsearch.client import Elasticsearch


class ElasticclientMock(object):
    """ Mock multiprocessing calls into file - no better idea """
    fixture = None
    result_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '.test_tmp')

    def __init__(self, *args, **kwargs):
        pass

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

    def msearch(self, body, **kwargs):
        line = self.fixture[:self.fixture.index('\n')]
        self.fixture[self.fixture.index('\n') + 1:]
        return json.loads(line)

    def update(self, **kwargs):
        self.msearch(**kwargs)


class ElasticsearchBaseTestCase(DaemonTestCase):
    def mocking(self):
        # Mock elasticsearch client
        self.elastic_mod = sys.modules['elasticsearch.client']
        test.Elasticsearch = ElasticclientMock
        test.Elasticsearch.fixture = self.getFixture('searches')
        sys.modules['elasticsearch.client'] = test

    def unmocking(self):
        # Unmock
        sys.modules['elasticsearch.client'] = self.elastic_mod
