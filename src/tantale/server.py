# coding=utf-8

from __future__ import print_function

import os
import signal
import traceback
import logging

import configobj
from multiprocessing import Process, Event, active_children
from multiprocessing import JoinableQueue as Queue

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
    def __init__(self, configfile):
        # Initialize Logging
        self.log = logging.getLogger()
        # Process signal
        self.running = True
        # Initialize Members
        self.configfile = configfile
        self.config = self.load_config(self.configfile)

    def load_config(self, configfile):
        """
        Load the full config
        """
        config = configobj.ConfigObj(config_min)
        config.merge(configobj.ConfigObj(os.path.abspath(configfile)))
        return config

    def spawn(self, process):
        # Signals (get then ignore)
        l_SIGINT_default_handler = signal.getsignal(signal.SIGINT)
        l_SIGTERM_default_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        # Start
        process.daemon = True
        process.start()

        # Restore signals
        signal.signal(signal.SIGINT, l_SIGINT_default_handler)
        signal.signal(signal.SIGTERM, l_SIGTERM_default_handler)

    def run(self, _onInitDone):
        # Set proctitle of main thread
        if setproctitle:
            setproctitle('tantale')

        processes = []
        init_events = []
        got_signal = False

        # Set the signal handlers
        def sig_handler(signum, frame):
            got_signal = True
            self.log.debug("%s received" % signum)
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
                    queue_size = int(self.config['modules']['Input'].get(
                        'queue_size', 16384))
                    check_queue = Queue(maxsize=queue_size)
                    self.log.debug('input_queue_size: %d', queue_size)

                    # Backends
                    processes.append(Process(
                        name="Input_Backend",
                        target=inputserver.input_backend,
                        args=(check_queue,),
                    ))
                    self.spawn(processes[-1])

                    # Socket Listener
                    init_events.append(Event())
                    processes.append(Process(
                        name="Input",
                        target=inputserver.run,
                        args=(check_queue, init_events[-1],),
                    ))
                    self.spawn(processes[-1])

                    # Freshness check
                    if modules[module]['freshness_timeout']:
                        processes.append(Process(
                            name="Input_Freshness",
                            target=inputserver.input_freshness,
                            args=(),
                        ))
                        self.spawn(processes[-1])

            elif module == 'Livestatus':
                if str_to_bool(modules[module]['enabled']):
                    from tantale.livestatus.server import LivestatusServer
                    livestatusserver = LivestatusServer(self.config)

                    # Livestatus
                    init_events.append(Event())
                    processes.append(Process(
                        name="Livestatus",
                        target=livestatusserver.run,
                        args=(init_events[-1],),
                    ))
                    self.spawn(processes[-1])

            elif module == 'Client':
                if str_to_bool(modules[module]['enabled']):
                    from tantale.client.server import Client
                    client = Client(self.config)

                    # Livestatus
                    init_events.append(Event())
                    processes.append(Process(
                        name="Client",
                        target=client.run,
                        args=(init_events[-1],),
                    ))
                    self.spawn(processes[-1])

            else:
                self.log.error(
                    'Unknown module %s found in configuration' % module)

        if len(processes) == 0:
            self.log.critical('No modules enabled. Quitting')

        # Check our sub-processes are ready
        for event in init_events:
            # Maximum time starting
            event.wait(15)
        _onInitDone()

        if not got_signal:
            signal.pause()

        for child in processes:
            self.log.debug('Terminate %s process' % child.name)
            child.terminate()

        for child in processes:
            child.join()

        self.log.info('Exit')
