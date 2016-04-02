# coding=utf-8

from __future__ import print_function
from six import integer_types
import re


class Check(object):
    # This saves a significant amount of memory per object. This only matters
    # due to the queue system that moves objects between processes and can end
    # up storing a large number of objects in the queue waiting for the
    # handlers to flush.
    __slots__ = [
        'type', 'tags', 'id',
        'timestamp', 'hostname', 'check', 'status', 'output',
        'contacts',
    ]

    pattern = re.compile(
        r'^'
        '(?P<timestamp>[0-9]+)\s+'
        '(?P<hostname>\w+)\s+'
        '(?P<check>\w+)\s+'
        '(?P<status>[0-3])\s+'
        '(?P<output>.*?)'
        '(|\|(?P<contacts>[^|]+))'
        '$')

    def __init__(self, timestamp=None, hostname=None, check=None,
                 status=None, output=None, contacts=None, **tags):
        """
        Create new instance
        """
        # No Value error here (regexp verify it)
        self.status = int(status)
        self.timestamp = int(timestamp)

        self.hostname = hostname
        if check == 'Host':
            self.type = 'host'
            self.id = hostname
        else:
            self.type = 'service'
            self.id = "%s-%s" % (hostname, check)

        self.check = check
        self.output = output

        self.contacts = []
        if contacts:
            self.contacts = contacts.split(',')

        if tags:
            self.tags = tags
        else:
            self.tags = {}

    @classmethod
    def parse(cls, string, log):
        """
        Parse a string and create a check
        """
        match = re.match(cls.pattern, string)
        try:
            groups = match.groupdict()
            return Check(**groups)
        except:
            import traceback
            log.info('CHECK: Error parsing check %s' % string.strip())
            log.debug('CHECK: %s' % traceback.format_exc())

    def __getstate__(self):
        return dict(
            (slot, getattr(self, slot))
            for slot in self.__slots__
            if hasattr(self, slot)
        )

    def __setstate__(self, state):
        for slot, value in state.items():
            setattr(self, slot, value)
