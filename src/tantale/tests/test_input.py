# coding=utf-8

from test import DaemonTestCase
from test import unittest, ANY, call, MagicMock, Mock, mock_open, patch
import six
import socket
import time


class InputThreadTestCase(DaemonTestCase):
    def setUp(self):
        super(InputThreadTestCase, self).setUp()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def socketConnect(self):
        self.sock.connect(('127.0.0.1', 2003))

    def tearDown(self):
        self.sock.close()
        super(InputThreadTestCase, self).tearDown()

    def test_sendOneCheck(self):
        self.socketConnect()

        timestamp = int(time.time())
        check = "%s localhost test_check 0 test on some special chars" \
                " ><&(){}[],;:!"
        check = six.b(check)
        self.sock.send(check)

        self.assertEqual(self.mock_queue.get(), check)
