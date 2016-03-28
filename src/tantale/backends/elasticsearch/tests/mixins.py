# coding=utf-8

from __future__ import print_function

import os
import sys

import tantale.backends.elasticsearch.tests.mock as mock
from elasticsearch.client import Elasticsearch


class ElasticsearchOk(object):
    def mocking(self):
        # Clean result file from previous run
        if os.path.isfile(mock.Elasticsearch.result_file):
            os.unlink(mock.Elasticsearch.result_file)

        # Gather elastic responses fixture
        responses = []
        for line in self.getFixture('el_responses').split('\n'):
            if not line.startswith('#') and line != '':
                responses.append(line)
        el_responses = responses
        el_responses.reverse()

        # Mock elasticsearch client with sys.modules trick
        self.original_mod = sys.modules['elasticsearch.client']
        mock.Elasticsearch.el_responses = el_responses
        sys.modules['elasticsearch.client'] = mock

        self.mock_class = mock.Elasticsearch

    def unmocking(self):
        sys.modules['elasticsearch.client'] = self.original_mod


class ElasticsearchConnectFail(object):
    """ Mainly test errors on catching """
    def mocking(self):
        # Mock elasticsearch client with sys.modules trick
        self.original_mod = sys.modules['elasticsearch.client']

        def NoneClient(*args, **kwargs):
            return None
        self.original_mock = mock.Elasticsearch
        mock.Elasticsearch = NoneClient
        sys.modules['elasticsearch.client'] = mock

    def unmocking(self):
        sys.modules['elasticsearch.client'] = self.original_mod
        mock.Elasticsearch = self.original_mock
