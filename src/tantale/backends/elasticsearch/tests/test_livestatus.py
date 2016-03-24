# coding=utf-8

from __future__ import print_function

import time
from six import b as bytes

from test import DaemonTestCase
from tantale.backends.elasticsearch.tests.test_basics \
    import ElasticsearchBaseTestCase, ElasticsearchClientMock


class ElasticsearchTestCase(ElasticsearchBaseTestCase, DaemonTestCase):
    def setUp(self):
        # Daemon config
        self.config = {}
        super(ElasticsearchTestCase, self).setUp()

    def test_Queries(self):
        sock = self.get_socket(6557)
        self.maxDiff = None

        responses = []
        response = ""
        # Gather up responses
        for line in self.getFixture('responses').split('\n'):
            if line == '':
                responses.append(response)
                response = ""
            else:
                response += line + '\n'
        responses.reverse()

        # Gather up requests (RECV mean response needed)
        request = ""
        sent = False
        for line in self.getFixture('requests').split('\n'):
            if sent and line != "RECV":
                request = ""
                sent = False

            if line == '':
                # Got request
                sock.send(bytes(request + '\n'))
                sent = True

            elif line == '#RECV':
                # Response parse
                res = sock.recv(4096).decode("utf-8")
                self.assertEqual(res, responses.pop())

            elif line[0] != '#':
                request += line + '\n'

        sock.close()
        self.flush()


class BenchElasticsearchTestCase(ElasticsearchBaseTestCase, DaemonTestCase):
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
