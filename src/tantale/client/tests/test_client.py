# coding=utf-8

from __future__ import print_function

import re
import os
import time
from six import b as bytes

import configobj
import socket

from test import TantaleTC

my_folder = os.path.dirname(os.path.abspath(__file__))
diamond_fifo = os.path.join(my_folder, '.test_diamond_fifo')

diamond_input = """servers.domain.my_fqdn.diskspace.root.byte_percentfree 90.90
servers.domain.my_fqdn.diskspace.root.byte_used 11017080832.00
servers.domain.my_fqdn.diskspace.root.byte_free 30989548032.00
servers.domain.my_fqdn.diskspace.root.byte_avail 103819173888.00
"""


class ClientTC(TantaleTC):
    def setUp(self):
        super(ClientTC, self).setUp()

        # Daemon config
        config = {
            'modules': {
                'Input': {
                    'ttl': 1,
                },
                'Client': {
                    'enabled': True,
                    'diamond_fifo': diamond_fifo,
                    'interval': 2,
                }
            },
            'backends':
                {'ElasticsearchBackend':
                    {'recreate_index_for_test': True}}
        }
        # Merge config addins
        self.server.config.merge(configobj.ConfigObj(config))

        # Prepare fifos
        try:
            os.unlink(diamond_fifo)
        except:
            pass
        os.mkfifo(diamond_fifo)

    def tearDown(self):
        try:
            os.unlink(diamond_fifo)
        except:
            pass
        super(ClientTC, self).tearDown()

    def test_Diamond(self):
        self.start()

        diamond_fd = os.open(diamond_fifo, os.O_WRONLY | os.O_NONBLOCK)

        for metric in diamond_input.split("\n"):
            os.write(diamond_fd, bytes("%s %d\n" % (metric, int(time.time()))))

        # Check result from livestatus
        live_s = self.getSocket('Livestatus')
        for nb in range(10):
            time.sleep(1)
            live_s.send(
                self.getLivestatusRequest('get_service') %
                ("fqdn.domain", "fs_root"))
            res = live_s.recv()
            res = eval(res[16:])
            if len(res) > 0:
                break

        self.assertEqual(res[0][3], "fqdn.domain", res)
        self.assertEqual(
            res[0][4],
            "29.85 (10.0, 20.0, None, None)", res)
        self.assertEqual(res[0][-1], 0, res)

        self.stop()

    def test_Ps(self):
        self.start()

        # Check result from livestatus
        live_s = self.getSocket('Livestatus')
        fqdn = socket.getfqdn()
        for nb in range(10):
            time.sleep(1)
            live_s.send(
                self.getLivestatusRequest('get_service') %
                (fqdn, "ps_example"))
            res = live_s.recv()
            res = eval(res[16:])
            if len(res) > 0:
                break

        self.assertEqual(res[0][3], fqdn, res)
        self.assertEqual(
            res[0][4],
            "Found 1 processes matching in[ia]t for user root "
            "(1, 1, None, None)", res)
        self.assertEqual(res[0][-1], 0, res)

        self.stop()

    def test_External(self):
        self.start()

        # Check result from livestatus
        live_s = self.getSocket('Livestatus')
        fqdn = socket.getfqdn()
        for nb in range(20):
            time.sleep(1)
            live_s.send(
                self.getLivestatusRequest('get_host') % (fqdn))
            res = live_s.recv()
            res = eval(res[16:])
            if len(res) > 0:
                break

        self.assertEqual(res[0][-3], fqdn)
        self.assertEqual(res[0][4], "Ok check")
        self.assertEqual(res[0][13], 0)

        # Check result from livestatus
        live_s = self.getSocket('Livestatus')
        for nb in range(10):
            time.sleep(1)
            live_s.send(
                self.getLivestatusRequest(
                    'get_service') % (fqdn, "external_example"))
            res = live_s.recv()
            res = eval(res[16:])
            if len(res) > 0:
                break

        self.assertEqual(res[0][3], fqdn, res)
        self.assertEqual(res[0][4], 'fail', res)
        self.assertEqual(res[0][-1], 1, res)

        self.stop()
