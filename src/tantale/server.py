# coding=utf-8

from __future__ import print_function

import os
import signal
import traceback
import logging

import configobj
from multiprocessing import Manager, Process, Queue, active_children

from tantale import config_min
from tantale.utils import str_to_bool

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
        Load the full config
        """
        config = configobj.ConfigObj(config_min)
        config.merge(configobj.ConfigObj(os.path.abspath(configfile)))
        if self.config_adds:
            config.merge(configobj.ConfigObj(self.config_adds))

        return config

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
                if str_to_bool(modules[module]['enabled']):
                    from tantale.input.server import InputServer
                    inputserver = InputServer(self.config)

                    # Input check Queue
                    queue_size = int(self.config['server'].get(
                        'queue_size', 16384))
                    check_queue = l_manager.Queue(maxsize=queue_size)
                    self.log.debug('input_queue_size: %d', queue_size)

                    # Backends
                    processes.append(Process(
                        name="Input Backend",
                        target=inputserver.input_backend,
                        args=(check_queue,),
                    ))
                    self.spawn(processes[-1])

                    # Socket Listener
                    processes.append(Process(
                        name="Input",
                        target=inputserver.input,
                        args=(check_queue,),
                    ))
                    self.spawn(processes[-1])

            elif module == 'Livestatus':
                if str_to_bool(modules[module]['enabled']):
                    from tantale.livestatus.server import LivestatusServer
                    livestatusserver = LivestatusServer(self.config)

                    # Livestatus
                    processes.append(Process(
                        name="Livestatus",
                        target=livestatusserver.livestatus,
                        args=(),
                    ))
                    self.spawn(processes[-1])

            else:
                self.log.error(
                    'Unknown module %s found in configuration' % module)

        if len(processes) == 0:
            self.log.critical('No modules enabled. Quitting')

        # We are ready
        _onInitDone()

        # Wait
        for process in processes:
            process.join()

        self.log.info('Shutdown manager')
        l_manager.shutdown()

        self.log.info('Exit')
