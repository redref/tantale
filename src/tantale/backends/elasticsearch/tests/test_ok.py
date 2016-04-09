# coding=utf-8

from __future__ import print_function

import time
import json
import random
from six import b as bytes

import configobj
from test import TantaleTC


class ElasticsearchTC(TantaleTC):
    def randStatus(self):
        # Push some failed checks
        state = random.randrange(0, 29)
        if state < 27:
            state = 0
        elif state == 27:
            state = 1
        elif state == 28:
            state = 2
        elif state == 29:
            state = 3
        return state

    def test_Workflow(self):
        if self.bench:
            config = {'backends': {
                'ElasticsearchBackend': {
                    'batch': 1000, 'recreate_index_for_test': True}
            }}
            hosts_nb = 4000
            services_per_host = 3
        else:
            config = {'backends': {
                'ElasticsearchBackend': {
                    'batch': 4, 'recreate_index_for_test': True}
            }}
            hosts_nb = 1
            services_per_host = 3

        # Merge config addins and start
        self.server.config.merge(configobj.ConfigObj(config))
        self.start()

        #
        # Input
        #
        input_s = self.getSocket('Input')
        # Generate some checks
        checks = []
        for host in range(hosts_nb):
            checks.append((int(time.time()), host, self.randStatus()))
            input_s.send(
                "%d host_%d Host %d output ><&(){}[],;:!\\"
                "|user_1,user_2\n" % checks[-1])

            for service in range(services_per_host):
                checks.append((
                    int(time.time()), host, service, self.randStatus()))
                input_s.send(
                    "%d host_%d Service_%d %d output %%|user_1,user_2\n" %
                    checks[-1])
        input_s.close()

        #
        # Livestatus
        #
        live_s = self.getSocket('Livestatus')
        requests = self.getParsedFixture('requests')

        # Status table
        live_s.send("%s\n" % requests.get('status'))
        res = live_s.recv()
        self.assertEqual(
            res, "200          32 [['tantale', '1.0', 0, '', '']]\n")

        self.stop()
