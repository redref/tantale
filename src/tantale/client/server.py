# coding=utf-8

from __future__ import print_function

import os
import signal
import traceback
import logging
import time
import json

import socket
from threading import Thread, Event
from six import b as bytes

from tantale.utils import load_class
from tantale import sources

try:
    from Queue import Queue
except:
    from queue import Queue

try:
    from setproctitle import setproctitle, getproctitle
except ImportError:
    setproctitle = None


class Client(object):
    """
    Tantale client
    """

    def __init__(self, config):
        self.log = logging.getLogger('tantale.client')

        self.config = config['modules']['Client']
        self.config['interval'] = int(self.config['interval'])

        # Result stash
        self.res_q = Queue(maxsize=2048)

        # Tantale input target
        self.host = self.config['server_host']
        self.port = int(self.config['server_port'])
        self.sock = None

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setblocking(True)
            self.sock.connect((self.host, self.port))
        except:
            self.sock = None

    def sending_thread(self, res_q):
        """
        Send results from queue
        """
        self.connect()

        while True:
            try:
                result = res_q.get(True)
                # Not keeping data in memory
                res_q.task_done()

                if not self.sock:
                    self.connect()

                if not self.sock:
                    self.log.info(
                        'Reconnect to %s:%s failed' % (self.host, self.port))
                    continue

                self.log.debug("Sending: %s" % result)

                try:
                    self.sock.send(bytes(json.dumps(result) + '\n'))
                except:
                    self.log.info("Connection reset")
                    self.log.debug(traceback.format_exc())
                    self.sock = None
            except:
                self.log.error("Unknown error sending checks")

    def run(self, init_done=None):
        """
        Parse checsk
        Spawn sources
        Spawn sender thread
        """
        if setproctitle:
            setproctitle('%s - Client' % getproctitle())

        # Parse checks configs to dispatch
        default_host = socket.getfqdn()
        self.checks = {}
        for key in self.config:
            if isinstance(self.config[key], dict):
                check = self.config[key]

                # If name specified, overwrite dict name
                check['name'] = check.get('name', key)

                check['source'] = check.get('source', None)

                # Default hostname
                check['hostname'] = check.get('hostname', default_host)

                # Default contacts
                check['contacts'] = check.get(
                    'contacts', self.config['contacts'])

                # Defualt interval
                check['interval'] = int(check.get(
                    'interval', self.config['interval']))

                if check['source'] and hasattr(sources, check['source']):

                    self.log.debug('Found check : %s -> %s' % (key, check))

                    # Make a source checks hash
                    if check['source'] not in self.checks:
                        self.checks[check['source']] = {}
                    self.checks[check['source']][key] = check

                else:
                    self.log.error(
                        "Check '%s' source '%s' unknown" %
                        (check, check['source']))

                # Clean config from checks
                del self.config[key]

        def sig_handler(signum, frame):
            self.log.debug("%s received" % signum)
        signal.signal(signal.SIGTERM, sig_handler)

        # Loop
        t = Thread(target=self.sending_thread, args=(self.res_q,))
        t.daemon = True
        t.start()

        # Launch source threads
        for source in self.checks:
            try:
                cls = load_class(
                    'tantale.sources.%s.%sSource' % (source, source.title()))
                src = cls(self.config, self.checks[source], self.res_q)
                t = Thread(target=src.run)
                t.daemon = True
                t.start()
            except:
                self.log.error("Failed to initialize '%s' source" % source)
                self.log.debug(traceback.format_exc())

        if init_done:
            init_done.set()

        signal.pause()

        self.log.info("Exit")
