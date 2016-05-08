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
servers.domain.my_fqdn.diskspace.root.byte_free 109989548032.00
servers.domain.my_fqdn.diskspace.root.byte_avail 103819173888.00
servers.domain.my_fqdn.diskspace.root.inodes_percentfree 95
servers.domain.my_fqdn.diskspace.root.inodes_used 340616
servers.domain.my_fqdn.diskspace.root.inodes_free 7171448
servers.domain.my_fqdn.diskspace.root.inodes_avail 7171448
servers.domain.my_fqdn.cpu.total.system 1
servers.domain.my_fqdn.cpu.total.user 3
servers.domain.my_fqdn.cpu.total.softirq 0
servers.domain.my_fqdn.cpu.total.nice 0
servers.domain.my_fqdn.cpu.total.steal 0
servers.domain.my_fqdn.cpu.total.iowait 0
servers.domain.my_fqdn.cpu.total.guest 0
servers.domain.my_fqdn.cpu.total.guest_nice 0
servers.domain.my_fqdn.cpu.total.idle 396
servers.domain.my_fqdn.cpu.total.irq 0"""


class ClientTC(TantaleTC):
    def setUp(self):
        super(ClientTC, self).setUp()

        # Daemon config
        config = {
            'modules': {
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
            "Value 103819173888.000000 (10.0, 20.0, None, None)", res)
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
