# coding=utf-8

from __future__ import print_function

import os
import sys
import json
import time
from six import b as bytes

import test
from test import DaemonTestCase

from elasticsearch.client import Elasticsearch


class ElasticsearchClientMock(object):
    """ Mock multiprocessing calls into file - no better idea """
    el_responses = None

    result_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '.mock_calls')

    def __init__(self, *args, **kwargs):
        pass

    def write_call(self, method, kwargs):
        with open(self.result_file, 'a') as f:
            f.write(
                json.dumps(
                    {"method": method, "kwargs": kwargs},
                    sort_keys=True))
            f.write("\n")
            f.flush()

    def bulk(self, **kwargs):
        self.write_call('bulk', kwargs)

        nb_requests = int((kwargs['body'].count('\n') + 1) / 2)

        # Forge return value / timestamp strictly > now
        timestamp = int(time.time()) * 1000 + 1
        item = {'update': {'get': {'fields': {'timestamp': [timestamp]}}}}
        return {
            'errors': False,
            'items': [item for i in range(nb_requests)]}

    def get_response(self):
        return json.loads(self.fixture.pop())

    def search(self, **kwargs):
        self.write_call('msearch', kwargs)
        return self.get_response()

    def msearch(self, **kwargs):
        self.write_call('msearch', kwargs)
        return self.get_response()

    def update(self, **kwargs):
        self.write_call('update', kwargs)
        return self.get_response()

    @classmethod
    def get_calls(cls):
        res = []
        try:
            with open(cls.result_file, 'r') as f:
                for line in f.readlines():
                    res.append(json.loads(line))
        except:
            pass

        if os.path.isfile(cls.result_file):
            os.unlink(cls.result_file)

        return res


class ElasticsearchBaseTestCase(object):
    def mocking(self):
        # Clean result file from previous run
        if os.path.isfile(ElasticsearchClientMock.result_file):
            os.unlink(ElasticsearchClientMock.result_file)

        # Gather elastic responses fixture
        responses = []
        for line in self.getFixture('el_responses').split('\n'):
            if not line.startswith('#') and line != '':
                responses.append(line)
        el_responses = responses
        el_responses.reverse()

        # Mock elasticsearch client with sys.modules trick
        self.elastic_mod = sys.modules['elasticsearch.client']
        test.Elasticsearch = ElasticsearchClientMock
        test.Elasticsearch.fixture = el_responses
        sys.modules['elasticsearch.client'] = test

    def unmocking(self):
        sys.modules['elasticsearch.client'] = self.elastic_mod


class ElasticsearchFailTestCase(DaemonTestCase):
    """ Mainly test errors on catching """
    def mocking(self):
        # Mock elasticsearch client with sys.modules trick
        self.elastic_mod = sys.modules['elasticsearch.client']

        def none(*args, **kwargs):
            raise Exception('Mock fail')
            return None
        test.Elasticsearch = none
        sys.modules['elasticsearch.client'] = test

    def unmocking(self):
        sys.modules['elasticsearch.client'] = self.elastic_mod

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
