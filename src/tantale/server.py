# coding=utf-8

import time
import configobj
import os
import signal
import logging
import traceback
import socket
import select
from multiprocessing import Manager, Process, Queue

from tantale.utils import load_backend

try:
    from Queue import Full
except:
    from queue import Full

try:
    from setproctitle import setproctitle, getproctitle
except ImportError:
    setproctitle = None


class Server(object):
    """
    Loads and start configured functions
    """
    def __init__(self, configfile):
        # Initialize Logging
        self.log = logging.getLogger('tantale')
        # Process signal
        self.ready_queue = None
        self.run_server = True
        # Initialize Members
        self.configfile = configfile
        self.config = None
        #
        self.backends = []
        self.backend_queue = []
        self.check_queue = []
        #
        self.manager = Manager()

        # Set proctitle of main thread
        if setproctitle:
            setproctitle('tantale')

    def load_config(self, configfile):
        """
        Load the full config / merge splitted configs if configured
        """
        configfile = os.path.abspath(configfile)
        config = configobj.ConfigObj(configfile)
        config_extension = '.conf'

        # Load up other config files
        if 'configs' in config:
            config_extension = config['configs'].get(
                'extension', config_extension)

        # Check sanity
        if 'server' not in config:
            raise Exception('Failed to load config file %s!' % configfile)

        # Load up backends config
        if 'backends' not in config:
            config['backends'] = configobj.ConfigObj()

        return config

    def handler(self, sig, stack):
        self.run_server = False

    def input(self, ready_queue, mock_queue):
        if setproctitle:
            setproctitle('%s - input' % getproctitle())
        signal.signal(signal.SIGINT, self.handler)
        signal.signal(signal.SIGTERM, self.handler)

        # Queue : Input
        if not mock_queue:
            queue_size = int(self.config['server'].get(
                'queue_size', 16384))
            self.check_queue = self.manager.Queue(maxsize=queue_size)
            self.log.debug('queue_size: %d', queue_size)
        else:
            self.check_queue = mock_queue

        # Load backends
        backends = []
        if 'backend' not in self.config:
            for backend in self.config['backends']:
                try:
                    load_backend(backend)
                except:
                    self.log.error('Error loading backend %s' % backend)
                    self.log.debug(traceback.format_exc())

        # Open listener
        connections = []
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(('', 2003))
        except socket.error as msg:
            self.log.critical('INPUT: Socket bind failed.')
            self.log.debug(traceback.format_exc())

        s.listen(50)
        self.log.info("INPUT: listen")
        connections.append(s)

        if ready_queue:
            ready_queue.put('input', block=False)

        # Logic
        while self.run_server:
            try:
                r, w, e = select.select(connections, [], [])
            except:
                # Handle "Interrupted system call"
                break

            for sock in r:
                if sock == s:
                    # New clients
                    sockfd, addr = s.accept()
                    connections.append(sockfd)
                else:
                    try:
                        data = sock.recv(4096)
                        if data:
                            try:
                                self.check_queue.put(data, block=False)
                            except Full:
                                self.log.warning('INPUT: Queue full')
                    except:
                        self.log.debug(traceback.format_exc())
                        sock.close()
                        connections.remove(sock)

        self.log.info("INPUT: exit")
        s.close()

    def run(self, ready_queue=None, mock_queue=None):
        self.config = self.load_config(self.configfile)

        processes = {}

        threads = self.config.get('threads', {})
        for thread in threads:
            if thread == 'Input':
                processes[thread] = Process(
                    name="Input",
                    target=self.input,
                    args=(ready_queue, mock_queue),
                )
                processes[thread].start()
            else:
                self.log.error(
                    'Unknown thread %s found in configuration' % thread)

        for process in processes:
            processes[process].join()
