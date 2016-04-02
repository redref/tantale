# coding=utf-8

from __future__ import print_function

import os
import socket
import sys
from six import b as bytes

from test import ClientTestCase

from tantale.client import Client

my_folder = os.path.dirname(os.path.abspath(__file__))
diamond_fifo = os.path.join(my_folder, '.test_diamond_fifo')
nagios_fifo = os.path.join(my_folder, '.test_nagios_fifo')


def getfqdn():
    return 'mock_fqdn'


class ClientRealTestCase(ClientTestCase):
    def setUp(self):
        # Mock this
        socket.getfqdn = getfqdn

        # Daemon config
        self.config = {
            'modules': {
                'Client': {
                    'diamond': {'fifo_file': diamond_fifo},
                    'nagios': {'fifo_file': nagios_fifo},
                }
            }
        }

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

        # Prepare receiving sock
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.bind(('', 2003))
        self.s.listen(1024)

        super(ClientRealTestCase, self).setUp()

        self.diamond_fd = os.open(diamond_fifo, os.O_WRONLY | os.O_NONBLOCK)
        self.nagios_fd = os.open(nagios_fifo, os.O_WRONLY | os.O_NONBLOCK)

    def tearDown(self):
        self.s.close()
        super(ClientRealTestCase, self).tearDown()

    def test_Diamond(self):
        sock, addr = self.s.accept()

        metrics = [
            'servers.test.diskspace.root.byte_percentfree 90 1459589281',
            'servers.test.diskspace.root.byte_percentfree 50 1459589281',
        ]

        results = \
            "1459589281 mock_fqdn fs_root 1 diskspace.root.byte_percentfree"\
            " value upper than 90|user_1,user_2\n" \
            "1459589281 mock_fqdn fs_root 0 diskspace.root.byte_percentfree"\
            ": 50|user_1,user_2\n"

        for metric in metrics:
            os.write(self.diamond_fd, bytes("%s\n" % metric))

        res = sock.recv(4096)

        self.flush()
        self.assertEqual(res, bytes(results))

    def test_Nagios(self):
        sock, addr = self.s.accept()

        metrics = [
            '[1459610979] PROCESS_SERVICE_CHECK_RESULT;mock_fqdn;echo;0;toto',
            '[1459610979] PROCESS_SERVICE_CHECK_RESULT;mock_fqdn;echo;2;error',
        ]

        results = \
            "1459610979 mock_fqdn echo 0 |user_1,user_2\n" \
            "1459610979 mock_fqdn echo 2 |user_1,user_2\n"

        for metric in metrics:
            os.write(self.nagios_fd, bytes("%s\n" % metric))

        res = sock.recv(4096)
        self.flush()
        self.assertEqual(res, bytes(results))
