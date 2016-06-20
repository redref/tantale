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

from tantale.client.diamond import DiamondSource
from tantale.client.ps import PsSource
from tantale.client.external import ExternalSource

try:
    from setproctitle import setproctitle, getproctitle
except ImportError:
    setproctitle = None

SOURCES = ('ps', 'diamond', 'external')


class Client(object):
    """
    Tantale client :
        - Spawn "diamond" metrics marsing thread
        - Spawn "ps" thread
        - Spawn "external" scheduler thread
        - Spawn "timer" interval thread
    Push all checks on :
        - Event
        - Interval time
    """

    def __init__(self, config):
        self.log = logging.getLogger('tantale.client')
        self.config = config['modules']['Client']
        self.config['interval'] = int(self.config['interval'])

        # Result hash
        self.results = {}

        # Tantale input target
        self.host = self.config['server_host']
        self.port = int(self.config['server_port'])
        self.sock = None

        # Global config
        self.contacts = self.config['contacts']

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setblocking(True)
            self.sock.connect((self.host, self.port))
        except:
            self.sock = None

    def send(self, results):
        """ Send data with exception handling """
        if not self.sock:
            self.connect()

        if not self.sock:
            self.log.info(
                'Reconnect to %s:%s failed' % (self.host, self.port))

        for key in results:
            self.log.debug("Sending: %s -> %s" % (key, results[key]))

        try:
            self.sock.send(bytes(json.dumps(results) + '\n'))
        except:
            pass

    def close(self):
        if self.sock:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()

    def __del__(self):
        self.close()

    def timer_thread(self, event, interval):
        while True:
            event.wait(interval)
            if not event.is_set():
                event.set()
            else:
                time.sleep(1)

    def loop_thread(self, event):
        self.connect()

        # Wait at least one interval
        # Avoid sending while running all a first time
        time.sleep(self.config['interval'])

        while True:
            event.wait()
            event.clear()

            # Add contacts to results
            for result in self.results:
                self.results[result]['contacts'] = self.contacts

            # Renew ok timestamps
            for check in self.checks['ok']:
                self.results[check]['timestamp'] = int(time.time())

            self.send(self.results)

    def run(self, init_done=None):
        """ Launch threads, then wait for signal """
        if setproctitle:
            setproctitle('%s - Client' % getproctitle())

        # Parse checks configs to dispatch
        default_host = socket.getfqdn()
        self.checks = {}
        for key in self.config:
            if isinstance(self.config[key], dict):
                # If name specified, overwrite dict name
                name = self.config[key].get('name', key)

                check = self.config[key]
                check_type = check.get('type', None)
                hostname = check.get('hostname', default_host)

                if check_type in SOURCES + ("ok",):
                    if check_type not in self.checks:
                        self.checks[check_type] = {}

                    self.log.debug('Found check : %s -> %s' % (key, check))
                    self.checks[check_type][key] = check

                    # Pre-provision results
                    if check_type == "ok":
                        self.results[key] = {
                            "check": name,
                            "timestamp": int(time.time()),
                            "hostname": hostname,
                            "status": 0,
                            "output": "Ok check",
                        }
                    else:
                        # Send Ok default result
                        self.results[key] = {
                            "check": name,
                            "timestamp": int(time.time()),
                            "hostname": hostname,
                            "status": 3,
                            "output": "OUTDATED - No result yet",
                        }

                else:
                    self.log.error('Check type %s unknown.')

                # Remove check from config
                del self.config[key]

        def sig_handler(signum, frame):
            self.log.debug("%s received" % signum)
        signal.signal(signal.SIGTERM, sig_handler)

        event = Event()

        # Loop
        t = Thread(target=self.loop_thread, args=(event,))
        t.daemon = True
        t.start()

        # Timer
        t = Thread(
            target=self.timer_thread, args=(event, self.config['interval']))
        t.daemon = True
        t.start()

        # Launch source threads
        for source in SOURCES:
            if source not in self.checks:
                continue
            try:
                cls = load_class(
                    'tantale.client.%s.%sSource' % (source, source.title()))
                src = cls(self.config, self.checks[source])
                t = Thread(target=src.run, args=(event, self.results))
                t.daemon = True
                t.start()
            except:
                self.log.error('Failed to initialize %s source' % source)
                self.log.debug(traceback.format_exc())

        if init_done:
            init_done.set()

        signal.pause()

        self.log.info("Exit")
