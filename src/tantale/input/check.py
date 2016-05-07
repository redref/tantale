# coding=utf-8

from __future__ import print_function
from six import integer_types
import json
import time
import traceback


class Check(object):
    # This saves a significant amount of memory per object. This only matters
    # due to the queue system that moves objects between processes and can end
    # up storing a large number of objects in the queue waiting for the
    # handlers to flush.
    __slots__ = [
        'type', 'tags', 'id', 'parsing_ts',
        'timestamp', 'hostname', 'check', 'status', 'output',
        'contacts',
    ]
    # Relevant attributes (backend POV)
    fields = [
        'timestamp', 'hostname', 'check', 'status', 'output',
        'contacts']
    # Relevant attributes (backend logs POV)
    log_fields = [
        'last_check', 'hostname', 'check', 'status', 'output']

    def __init__(self, check, timestamp=None, hostname=None,
                 status=None, output=None, contacts=None, **tags):
        """
        Create new instance
        """
        self.status = int(status)
        self.parsing_ts = time.time()
        self.timestamp = int(timestamp)
        self.contacts = contacts

        self.hostname = hostname
        if check == 'Host':
            self.type = 'host'
            self.id = hostname
        else:
            self.type = 'service'
            self.id = "%s-%s" % (hostname, check)

        self.check = check
        self.output = output

        if tags:
            self.tags = tags
        else:
            self.tags = {}

    @classmethod
    def parse(cls, string, log):
        """
        Generate Checks object on JSON hash
        """
        try:
            checks_hash = json.loads(string)
        except:
            log.warn('Error loading client JSON')
            log.debug(traceback.format_exc())
            log.debug(string)
            return

        for name in checks_hash:
            try:
                yield Check(name, **checks_hash[name])
            except:
                log.info('CHECK: Error on %s - %s' % (name, checks_hash[name]))
                log.debug(traceback.format_exc())

    def __getstate__(self):
        return dict(
            (slot, getattr(self, slot))
            for slot in self.__slots__
            if hasattr(self, slot)
        )

    def __setstate__(self, state):
        for slot, value in state.items():
            setattr(self, slot, value)
