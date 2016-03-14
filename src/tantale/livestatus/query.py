# coding=utf-8

# Fields known by tantale
KNOWN_FIELDS = ('status', 'timestamp', 'host', 'description', 'service', 'ack')

# Static mapping (without object names)
FIELDS_MAPPING = {
    "state": "status",
    "name": "host",
    "address": "host",
    "last_state_change": "timestamp",
    "plugin_output": "description",
    "description": "service",
    "acknowledged": "ack",
    "last_check": "last_check",
}

# Default values / Unwired logics
FIELDS_DUMMY = {
    "current_attempt": 1,
    "max_check_attempts": 1,
    "staleness": 0,
    "has_been_checked": 1,
    "scheduled_downtime_depth": 0,
    "check_command": 'elk',
    "notifications_enabled": 1,
    "accept_passive_checks": 1,
    "downtimes": [],
    "in_notification_period": 1,
    "active_checks_enabled": 0,
    "pnpgraph_present": 0,
    "retry_interval": 60,
    "check_interval": 60,
    "last_time_ok": 0,
    "next_check": 0,
    "next_notification": 0,
    "latency": 0,
    "execution_time": 0,
    "custom_variables": {},
}

STATUS_TABLE = {
    "livestatus_version": "tantale",
    "program_version": "1.0",
    "program_start": 0,
    "num_hosts": "",
    "num_services": "",
    "enable_notifications": 0,
    "execute_service_checks": 1,
    "execute_host_checks": 1,
    "enable_flap_detection": 1,
    "enable_event_handlers": 1,
    "process_performance_data": 1,
}


class Query(object):
    __slots__ = [
        'output_fd', 'method', 'table',
        'columns', 'filters', 'stats', 'limit',
        'rheader', 'oformat', 'keepalive', 'headers',
        'separators', 'results',
    ]

    def __init__(
        self, output_fd, method, table,
        columns=None, filters=None, stats=None, limit=None,
        rheader=None, oformat='csv', keepalive=None, headers=False,
        separators=['\n', ';', ',', '|']
    ):
        self.output_fd = output_fd
        self.method = method
        self.table = table
        self.columns = columns
        self.filters = filters
        self.stats = stats
        self.limit = limit
        self.rheader = rheader
        self.oformat = oformat
        self.keepalive = keepalive
        self.headers = headers
        self.separators = separators

        self.results = []

        if self.table == "status":
            self.append(STATUS_TABLE)
            self.flush()

    def __getstate__(self):
        return dict(
            (slot, getattr(self, slot))
            for slot in self.__slots__
            if hasattr(self, slot)
        )

    def __setstate__(self, state):
        for slot, value in state.items():
            setattr(self, slot, value)

    def append(self, result):
        # Mapping fields
        print(self.columns)
        mapped_res = []
        for field in self.columns:
            mapped_res.append(result.get(field, None))

        print(mapped_res)
        self.results.append(mapped_res)

        if self.oformat == 'csv':
            self.output_line()

    def output_line(self):
        pass

    def flush(self):
        if self.rheader == 'fixed16':
            string = str(self.results)
            print('%3d %11d %s\n' % (200, len(string), string))
            self.output_fd.write(
                '%3d %11d %s\n' % (200, len(string), string))
        else:
            for result in self.results:
                self.output_fd.write('%s\n' % ';'.join(result))

    @classmethod
    def parse(cls, fd, string):
        """
        Parse a string and create a livestatus query
        """
        method = None
        table = None
        optionals = {}

        try:
            for line in string.split('\n'):
                members = line.split(' ')
                if members[0] == '':
                    pass
                elif members[0] == 'GET':
                    method = 'GET'
                    table = members[1]
                elif members[0] == 'Columns:':
                    optionals['columns'] = members[1:]
                elif members[0] == 'ResponseHeader:':
                    optionals['rheader'] = members[1]
                elif members[0] == 'KeepAlive:':
                    if members[1] == 'on':
                        optionals['keepalive'] = True
                elif members[0] == 'OutputFormat:':
                    optionals['oformat'] = members[1]
                elif members[0] == 'Localtime:':
                    pass
                else:
                    raise Exception(
                        'Error parsing line '
                        '"%s" on query "%s"' % (line, repr(string)))
            return cls(
                fd, method, table, **optionals), optionals.get('limit', None)
        except:
            raise
