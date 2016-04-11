# coding=utf-8

from __future__ import print_function

import re
import os
import time
from six import b as bytes

import configobj
from test import TantaleTC

my_folder = os.path.dirname(os.path.abspath(__file__))
diamond_fifo = os.path.join(my_folder, '.test_diamond_fifo')
nagios_fifo = os.path.join(my_folder, '.test_nagios_fifo')

diamond_input = """servers.my_fqdn.diskspace.root.byte_percentfree 90.90
servers.my_fqdn.diskspace.root.byte_used 11017080832.00
servers.my_fqdn.diskspace.root.byte_free 109989548032.00
servers.my_fqdn.diskspace.root.byte_avail 103819173888.00
servers.my_fqdn.diskspace.root.inodes_percentfree 95
servers.my_fqdn.diskspace.root.inodes_used 340616
servers.my_fqdn.diskspace.root.inodes_free 7171448
servers.my_fqdn.diskspace.root.inodes_avail 7171448
servers.my_fqdn.cpu.total.system 1
servers.my_fqdn.cpu.total.user 3
servers.my_fqdn.cpu.total.softirq 0
servers.my_fqdn.cpu.total.nice 0
servers.my_fqdn.cpu.total.steal 0
servers.my_fqdn.cpu.total.iowait 0
servers.my_fqdn.cpu.total.guest 0
servers.my_fqdn.cpu.total.guest_nice 0
servers.my_fqdn.cpu.total.idle 396
servers.my_fqdn.cpu.total.irq 0"""


class ClientTC(TantaleTC):
    def setUp(self):
        super(ClientTC, self).setUp()

        # Daemon config
        config = {
            'modules': {
                'Client': {
                    'enabled': True,
                    'diamond_fifo': diamond_fifo,
                    'nagios_fifo': nagios_fifo,
                }
            },
            'backends':
                {'ElasticsearchBackend':
                    {'batch': 1, 'recreate_index_for_test': True}}
        }
        # Merge config addins
        self.server.config.merge(configobj.ConfigObj(config))

        # Prepare fifos
        try:
            os.unlink(diamond_fifo)
        except:
            pass
        os.mkfifo(diamond_fifo)

        try:
            os.unlink(nagios_fifo)
        except:
            pass
        os.mkfifo(nagios_fifo)

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
                self.getLivestatusRequest('get_service') % ("fqdn", "root"))
            res = live_s.recv()
            res = eval(res[16:])
            if len(res) > 0:
                break

        self.assertEqual(
            res[0][-3], "Value 103819173888.000000 (10.0, 20.0, None, None)")

        self.stop()

    def test_Nagios(self):
        self.start()

        fd = os.open(nagios_fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.write(
            fd,
            bytes(
                "[%d] PROCESS_SERVICE_CHECK_RESULT;%s;%s;%d;%s\n" %
                (int(time.time()), "fqdn", "Host", 0, "test_output")))
        os.close(fd)

        # Check result from livestatus
        live_s = self.getSocket('Livestatus')
        for nb in range(10):
            time.sleep(1)
            live_s.send(self.getLivestatusRequest('get_host') % ("fqdn"))
            res = live_s.recv()
            res = eval(res[16:])
            if len(res) > 0:
                break

        self.assertEqual(res[0][-3], "fqdn")
        self.assertEqual(res[0][4], "test_output")
        self.assertEqual(res[0][13], 0)

        self.stop()
