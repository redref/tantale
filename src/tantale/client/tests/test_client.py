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

diamond_input = """
servers.azibox.diskspace.root.byte_percentfree 90.90 1460281153
servers.azibox.diskspace.root.byte_used 11017080832.00 1460281153
servers.azibox.diskspace.root.byte_free 109989548032.00 1460281153
servers.azibox.diskspace.root.byte_avail 103819173888.00 1460281153
servers.azibox.diskspace.root.inodes_percentfree 95 1460281153
servers.azibox.diskspace.root.inodes_used 340616 1460281153
servers.azibox.diskspace.root.inodes_free 7171448 1460281153
servers.azibox.diskspace.root.inodes_avail 7171448 1460281153
servers.azibox.cpu.total.system 1 1460281156
servers.azibox.cpu.total.user 3 1460281156
servers.azibox.cpu.total.softirq 0 1460281156
servers.azibox.cpu.total.nice 0 1460281156
servers.azibox.cpu.total.steal 0 1460281156
servers.azibox.cpu.total.iowait 0 1460281156
servers.azibox.cpu.total.guest 0 1460281156
servers.azibox.cpu.total.guest_nice 0 1460281156
servers.azibox.cpu.total.idle 396 1460281156
servers.azibox.cpu.total.irq 0 1460281156
"""


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
            os.write(diamond_fd, bytes("%s\n" % metric))

        # Check result from livestatus
        live_s = self.getSocket('Livestatus')
        request = \
            "GET services\n" \
            "Columns: host_scheduled_downtime_depth service_last_check " \
            "service_check_command service_host_name service_plugin_output " \
            "service_last_state_change service_description host_address " \
            "service_service_description host_name service_state\n" \
            "OutputFormat: python\n" \
            "ResponseHeader: fixed16\n\n"
        live_s.send(request)
        res = live_s.recv()
        res = eval(res[16:])
        print(res)
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

        # TODO : test results

        self.stop()
