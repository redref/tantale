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
        'timestamp', 'hostname', 'check', 'status', 'description', 'tags',
    ]

    def __init__(self, timestamp=None, hostname=None, check=None,
                 status=None, description=None, **tags):
        """
        Create new instance
        """
        # If the timestamp isn't an int, then make it one
        if not isinstance(timestamp, integer_types):
            try:
                timestamp = int(timestamp)
            except ValueError as e:
                raise Exception("Invalid timestamp when "
                                "creating new Check "
                                "%s-%s: %s" % (hostname, check, e))

        # If the status isn't known, then make it one
        if not isinstance(status, integer_types):
            try:
                status = int(status)
                if status < 0 or status > 3:
                    raise Exception("Unknown status when "
                                    "creating new Check "
                                    "%s-%s: %s" % (hostname, check, e))
            except ValueError as e:
                raise Exception("Invalid status when "
                                "creating new Check "
                                "%s-%s: %s" % (hostname, check, e))

        self.timestamp = timestamp
        self.hostname = hostname
        self.check = check
        self.status = int(status)
        self.description = description
        if tags:
            self.tags = tags
        else:
            self.tags = {}

    @classmethod
    def parse(cls, string, log):
        """
        Parse a string and create a check
        """
        match = re.match(r'^'
                         '(?P<timestamp>[0-9]+)\s+'
                         '(?P<hostname>\w+)\s+'
                         '(?P<check>\w+)\s+'
                         '(?P<status>[0-3])\s+'
                         '(?P<description>.*)'
                         '.*(\n?)$',
                         string)
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
