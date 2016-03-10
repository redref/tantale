# coding=utf-8

from six import integer_types


class Check(object):
    # This saves a significant amount of memory per object. This only matters
    # due to the queue system that moves objects between processes and can end
    # up storing a large number of objects in the queue waiting for the
    # handlers to flush.
    __slots__ = [
        'timestamp', 'hostname', 'check', 'status', 'description'
    ]

    def __init__(self, timestamp, hostname, check,
                 status, description, **tags):
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
        self.status = status
        self.description = description
        self.tags = tags

    @classmethod
    def parse(cls, string):
        """
        Parse a string and create a check
        """
        match = re.match(r'^(?P<name>[A-Za-z0-9\.\-_]+)\s+' +
                         '(?P<value>[0-9\.]+)\s+' +
                         '(?P<timestamp>[0-9\.]+)(\n?)$',
                         string)
        try:
            groups = match.groupdict()
            # TODO: get precision from value string
            return Metric(groups['name'],
                          groups['value'],
                          float(groups['timestamp']))
        except:
            raise DiamondException(
                "Metric could not be parsed from string: %s." % string)

    def __getstate__(self):
        return dict(
            (slot, getattr(self, slot))
            for slot in self.__slots__
            if hasattr(self, slot)
        )

    def __setstate__(self, state):
        for slot, value in state.items():
            setattr(self, slot, value)

    def __repr__(self):
        """
        Return the Metric as a string
        """
        # Return formated string
        return (
            "%s %s %i\n"
            % (self.path, self.get_formatted_value(), self.timestamp)
        )

    def get_formatted_value(self):
        """
        Return the Metric value as string
        """
        if not isinstance(self.precision, integer_types):
            log = logging.getLogger('tantale')
            log.warn('Metric %s does not have a valid precision', self.path)
            self.precision = 0

        # Set the format string
        fstring = "%%0.%if" % self.precision

        # Return formated string
        return fstring % self.value
