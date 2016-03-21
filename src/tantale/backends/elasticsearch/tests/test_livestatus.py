# coding=utf-8

from __future__ import print_function

import time
from six import b as bytes

from tantale.backends.elasticsearch.tests.tools \
    import ElasticsearchBaseTestCase, ElasticclientMock


class ElasticsearchTestCase(ElasticsearchBaseTestCase):
    def setUp(self):
        # Daemon config
        self.config = {}
        super(ElasticsearchTestCase, self).setUp()

    def test_Queries(self):
        sock = self.get_socket(6557)

        res = ""
        requests = self.getFixture('requests')
        for line in requests.split('\n'):
            if line == 'RECV':
                res += sock.recv(4096).decode("utf-8")
            else:
                sock.send(bytes(line + '\n'))

        sock.close()
        self.flush()

        self.maxDiff = None
        self.assertEqual(res, self.getFixture('responses'))


class BenchElasticsearchTestCase(ElasticsearchBaseTestCase):
    def setUp(self):
        # Improve default config in setup (before daemon start)
        self.config = {}
        super(BenchElasticsearchTestCase, self).setUp()

    def test_sendFromOne(self):
        expected_time = float(6)
        how_many = 20000

        start = time.time()

        # TODO
        # sock.close()
        # self.flush()

        stop = time.time()
