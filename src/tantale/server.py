# coding=utf-8

import time

try:
    from setproctitle import setproctitle
except ImportError:
    setproctitle = None


class Server(object):
    def __init__(self, configfile):
        pass

    def run(self):
        # Set proctitle of main thread
        if setproctitle:
            setproctitle('tantale')

        while True:
            time.sleep(1)
