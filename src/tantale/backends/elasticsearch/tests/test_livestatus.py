# coding=utf-8

from __future__ import print_function

import time
import threading
from six import b as bytes

from test import LivestatusTestCase
from tantale.backends.elasticsearch.tests.mixins \
    import ElasticsearchOk, ElasticsearchConnectFail


class ElasticsearchLivestatusTestCase(ElasticsearchOk, LivestatusTestCase):
    def setUp(self):
        # Daemon config
        self.config = {}
        super(ElasticsearchLivestatusTestCase, self).setUp()

    def Queries(self, assertion=True):
        sock = self.get_socket()
        self.maxDiff = None

        responses = []
        response = ""
        # Gather up responses
        for line in self.getFixture('responses').split('\n'):
            if line.startswith('#'):
                continue
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
                if assertion:
                    self.assertEqual(res, responses.pop())

            elif line[0] != '#':
                request += line + '\n'

        sock.close()

    def test_Queries(self):
        self.Queries()
        self.flush()


class BenchElasticsearchLivestatusTestCase(ElasticsearchLivestatusTestCase):
    def setUp(self):
        # Improve default config in setup (before daemon start)
        self.config = {}
        super(BenchElasticsearchLivestatusTestCase, self).setUp()

    def test_simultaneousRequests(self):
        expected_time = float(1)
        how_many = 80

        start = time.time()

        threads = []
        for i in range(how_many):
            threads.append(threading.Thread(
                target=self.Queries, args=(False,)))
            threads[-1].start()

        for t in threads:
            t.join()

        stop = time.time()

        print("\nLivestatus bench time %f" % (stop - start))

        # Check time
        self.assertTrue(
            (stop - start) < expected_time,
            "Runtime too long (more than %s) - %s secs" %
            (expected_time, (stop - start)))
