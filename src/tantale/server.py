# coding=utf-8

from __future__ import print_function
import time
import configobj
import os
import signal
import logging
import traceback
import socket
import select
from multiprocessing import Manager, Process, Queue, active_children
from six import b as bytes

from tantale.utils import load_backend
from tantale.check import Check

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
    def __init__(self, configfile, config_adds=None):
        # Initialize Logging
        self.log = logging.getLogger('tantale')
        # Process signal
        self.running = True
        # Initialize Members
        self.configfile = configfile
        self.config_adds = config_adds
        self.config = None

    def load_config(self, configfile):
        """
        Load the full config / merge splitted configs if configured
        """
        configfile = os.path.abspath(configfile)
        config = configobj.ConfigObj(configfile)
        if self.config_adds:
            config.merge(configobj.ConfigObj(self.config_adds))
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

    def input(self, check_queue):
        if setproctitle:
            setproctitle('%s - input' % getproctitle())

        # Open listener
        connections = []
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('', 2003))
        except socket.error as msg:
            self.log.critical('INPUT: Socket bind failed.')
            self.log.debug(traceback.format_exc())
            return

        s.listen(1024)
        self.log.info("INPUT: listen")
        connections.append(s)

        # Signals
        pipe = os.pipe()
        connections.append(pipe[0])

        def sig_handler(signum, frame):
            self.log.info("INPUT: %s received" % signum)
            self.running = False
            os.write(pipe[1], bytes('END'))
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        # Logic
        queue_state = True
        while self.running:
            r = None
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
                        if isinstance(sock, int):
                            raise

                        f = sock.makefile()
                        for line in f.readlines():
                            if line == 'END':
                                break
                            try:
                                check_queue.put(line, block=False)
                            except Full:
                                self.log.error('INPUT: Queue full, dropping')
                            except (EOFError, IOError):
                                # Queue died
                                self.running = False
                                queue_state = False
                                break
                    except:
                        traceback.print_exc()
                        connections.remove(sock)

        # Stop backend
        if queue_state:
            try:
                check_queue.put(None, block=False)
            except:
                pass

        s.close()
        self.log.info("INPUT: exit")

    def input_backend(self, check_queue):
        if setproctitle:
            setproctitle('%s - input backend' % getproctitle())

        # Ignore signals
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

        # Load backends
        backends = []
        if 'backend' not in self.config:
            for backend in self.config['backends']:
                try:
                    cls = load_backend(backend)
                    backends.append(
                        cls(self.config['backends'].get(backend, None)))
                except:
                    self.log.error('Error loading backend %s' % backend)
                    self.log.debug(traceback.format_exc())
        if len(backends) == 0:
            self.log.critical('INPUT BACKEND: No available backends')
            return

        # Logic
        while self.running:
            try:
                check = check_queue.get(block=True, timeout=None)
            except EOFError:
                break
            if check is not None:
                # self.log.debug('Check: %s' % check.strip())
                for backend in backends:
                    backend._process(Check.parse(check, self.log))
                check_queue.task_done()
            else:
                # Call on terminate to flush cache
                self.running = False
                for backend in backends:
                    backend._flush()
                self.log.debug('Backends flushed')

        self.log.info("INPUT BACKEND: exit")

    def spawn(self, process):
        # Signals (get then ignore)
        l_SIGINT_default_handler = signal.getsignal(signal.SIGINT)
        l_SIGTERM_default_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        # Start
        process.daemon = True
        process.start()

        # Restore signals
        signal.signal(signal.SIGINT, l_SIGINT_default_handler)
        signal.signal(signal.SIGTERM, l_SIGTERM_default_handler)

    def run(self, _onInitDone):
        # Fix Manager title
        if setproctitle:
            setproctitle('tantale - Manager')
        l_manager = Manager()

        # Set proctitle of main thread
        if setproctitle:
            setproctitle('tantale')

        self.config = self.load_config(self.configfile)

        processes = []

        # Set the signal handlers
        def sig_handler(signum, frame):
            for child in processes:
                child.terminate()
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        # Spawn processes
        modules = self.config.get('modules', {})
        for module in modules:
            if module == 'Input':
                # Input check Queue
                queue_size = int(self.config['server'].get(
                    'queue_size', 16384))
                check_queue = l_manager.Queue(maxsize=queue_size)
                self.log.debug('queue_size: %d', queue_size)

                # Backends
                processes.append(Process(
                    name="input_backend",
                    target=self.input_backend,
                    args=(check_queue,),
                ))
                self.spawn(processes[-1])

                # Listener
                processes.append(Process(
                    name="input",
                    target=self.input,
                    args=(check_queue,),
                ))
                self.spawn(processes[-1])
            else:
                self.log.error(
                    'Unknown module %s found in configuration' % thread)

        # We are ready
        _onInitDone()

        # Wait
        for process in processes:
            process.join()

        self.log.info('Shutdown manager')
        l_manager.shutdown()

        self.log.info('Exit')
