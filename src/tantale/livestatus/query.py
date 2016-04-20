# coding=utf-8

import traceback
import logging
from six import b as bytes

try:
    unicode
except:
    unicode = None

# Fields known by tantale
KNOWN_FIELDS = (
    'type',
    'timestamp', 'hostname', 'check', 'status', 'output',
)

# Static mapping (without object names)
FIELDS_MAPPING = {
    "state": "status",
    "name": "hostname",
    "host_name": "hostname",
    "service_description": "output",
    # No address here, only hostnames
    "address": "hostname",
    "last_state_change": "timestamp",
    "plugin_output": "output",
    "description": "check",
    "acknowledged": "ack",
    "scheduled_downtime_depth": "downtime",
    "last_check": "last_check",
    "time": "timestamp",
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
    "class": 1,
    "state_type": '',
    "downtime_start_time": 0,
    "downtime_end_time": 0,
    "downtime_entry_time": 0,
    "downtime_duration": 0,
}

# Data in status_table / Livestatus visible configuration
STATUS_TABLE = {
    "livestatus_version": "tantale",
    "program_version": "1.0",
    "program_start": 0,
    "num_hosts": "",
    "num_services": "",
    "enable_notifications": 0,
    "execute_service_checks": 1,
    "execute_host_checks": 1,
    "enable_flap_detection": 0,
    "enable_event_handlers": 0,
    "process_performance_data": 0,
}


class Query(object):
    __slots__ = [
        'log',
        'output_sock', 'method', 'table',
        'columns', 'filters', 'stats', 'limit',
        'rheader', 'oformat', 'keepalive', 'headers',
        'separators', 'results',
    ]

    def __init__(
        self, output_sock, method, table,
        columns=None, filters=None, stats=None, limit=None,
        rheader=None, oformat='csv', keepalive=None, headers=False,
        separators=['\n', ';', ',', '|']
    ):
        self.log = logging.getLogger('tantale.livestatus')

        self.output_sock = output_sock
        self.method = method
        self.table = table
        self.columns = columns
        self.limit = limit
        self.rheader = rheader
        self.oformat = oformat
        self.keepalive = keepalive
        self.headers = headers
        self.separators = separators

        self.results = []

        # Remove None from filters
        self.filters = []
        if filters:
            for filt in filters:
                if filt:
                    self.filters.append(filt)
        if len(self.filters) == 0:
            self.filters = None

        # Remove None from stats
        self.stats = []
        if stats:
            for stat in stats:
                if stat:
                    self.stats.append(stat)
        if len(self.stats) == 0:
            self.stats = None

    def __repr__(self):
        result = ""
        for slot in self.__slots__:
            if slot not in ('log', 'output_sock'):
                result += "%s: %s" % (slot, getattr(self, slot, None))
        return result

    def _query(self, backends):
        """ Do query on backends """
        # status table / no backend query
        if self.table == "status":
            self.append(STATUS_TABLE)
            return

        # commands table / no logic
        elif self.table == "commands":
            self.append({'name': 'tantale'})
            return

        # hostgroups table / no logic
        elif self.table == "hostgroups":
            self.append({'name': 'tantale', 'alias': 'tantale'})
            return

        # contactgroups table / no logic
        elif self.table == "contactgroups":
            self.append({'name': 'tantale', 'alias': 'tantale'})
            return

        # servicegroups tables / no logic
        elif self.table == "servicegroups":
            self.append({'name': 'tantale', 'alias': 'tantale'})
            return

        # downtimes table / converted to services+hosts query
        elif self.table == 'downtimes':
            self.table = 'services_and_hosts'
            if self.filters:
                self.filters.append(['downtime', '!=', 0])
            else:
                self.filters = [['downtime', '!=', 0]]

        # DO IT
        for backend in backends:
            length = backend._query(self)

            if length and self.limit:
                if length > self.limit:
                    break
                self.limit -= length

    def append(self, result):
        """ Map back tantale results columns to queried columns """
        if self.columns:
            mapped_res = []
            for field in self.columns:
                # Remove object related prefix
                if field.startswith("host_"):
                    field = field[5:]
                if field.startswith("service_"):
                    field = field[8:]
                if field.startswith("log_"):
                    field = field[4:]

                # Search for columns
                map_name = False
                if field in result:
                    map_name = field
                elif field in FIELDS_MAPPING:
                    map_name = FIELDS_MAPPING[field]
                elif field in FIELDS_DUMMY:
                    mapped_res.append(FIELDS_DUMMY[field])
                    continue

                # downtimes table specific
                elif field == 'downtime_is_service':
                    if result.get('check') == 'Host':
                        mapped_res.append(0)
                    else:
                        mapped_res.append(1)
                    continue

                # log table specific
                elif self.table == 'log' and field == 'type':
                    if result['check'] == 'Host':
                        mapped_res.append('HOST ALERT')
                    else:
                        mapped_res.append('SERVICE ALERT')
                    continue

                # Append
                if map_name:
                    res = result.get(map_name, None)

                    # Python2 specific
                    if unicode and isinstance(res, unicode):
                        res = res.encode('ascii', 'ignore')

                    if res is None:
                        if map_name in ('downtime', 'ack'):
                            res = 0
                        else:
                            res = ''
                    else:
                        if map_name in ('timestamp', 'last_check'):
                            # TOFIX : this is part of elasticsearch
                            res = int(res / 1000)
                    mapped_res.append(res)
                else:
                    mapped_res.append('')

            self.results.append(mapped_res)

        else:
            # No columns header / forward results
            self.results.append(result)

        # Debug : print first line of results
        if len(self.results) == 1:
            self.log.debug(
                'Tantale result (first line):\n%s', str(self.results))

        # Handle line by line printing
        if self.oformat == 'csv' and not self.rheader:
            self._output_line()

    def _output_line(self):
        """ Write result line by line is possible """
        raise NotImplementedError

    def _flush(self):
        """ Dump results to network """
        if self.rheader == 'fixed16':
            string = str(self.results)
            # print('%3d %11d %s\n' % (200, len(string) + 1, string))
            self.output_sock.send(
                bytes('%3d %11d %s\n' % (200, len(string) + 1, string)))
        else:
            if len(self.results) > 0:
                raise NotImplementedError
                # for result in self.results:
                #     self.output_fd.write(bytes('%s\n' % ';'.join(result)))

    @classmethod
    def field_map(cls, field, table):
        """ Map query field to tantale known field """
        if field.startswith("%s_" % table[:-1]):
            field = field[len(table):]
        # Log got no final 's'
        if field.startswith("log_"):
            field = field[4:]

        # Map parent on service
        if table == 'services' and field.startswith('host_'):
            mapped = cls.field_map(field[5:], 'hosts')
            if mapped:
                return 'host.%s' % mapped
            else:
                return None

        if field in FIELDS_MAPPING:
            return FIELDS_MAPPING[field]
        elif field in FIELDS_DUMMY:
            # Handle not wired fields
            return None
        else:
            raise Exception('Unknown field %s' % field)

    @classmethod
    def parse_expr(cls, arg_list, table):
        """ Convert filters to expression list """
        # TOFIX exclude custom_variable_names / not relevant
        # TOFIX for now assume right operand is constant
        if arg_list[0].endswith("custom_variable_names"):
            return None

        arg_list[0] = cls.field_map(arg_list[0], table)

        # Not wired filters
        if arg_list[0] is None:
            return None

        if len(arg_list) == 3:
            try:
                arg_list[2] = int(arg_list[2])
            except ValueError:
                pass
            return arg_list
        else:
            raise Exception(
                "Error parsing expression %s", ' '.join(arg_list))

    @classmethod
    def combine_expr(cls, operator, expr_list):
        """ Combine expressions with and/or - filter not defined ones """
        if None in expr_list:
            res = []
            for expr in expr_list:
                if expr is not None:
                    res.append(expr)
            if len(res) == 1:
                return res
            if len(res) == 0:
                return None
            expr_list = res
        return [operator, expr_list]

    @classmethod
    def parse_command(cls, command):
        """ Parse ACK / DOWNTIME commands """
        args = command.split(';')
        cargs = args[0].split('_')
        query_args = []

        # Command parse
        if cargs[0] in ('REMOVE', 'DEL'):
            query_args.append(False)
        else:
            query_args.append(True)

        if cargs[2] == 'ACKNOWLEDGEMENT' or cargs[0] == 'ACKNOWLEDGE':
            command = 'ack'
        elif cargs[2] == 'DOWNTIME':
            command = 'downtime'
        else:
            raise NotImplementedError

        # Table parse
        query_args.append(args[1])
        table = None
        if not query_args[0] and command == 'downtime':
            # Remove downtime done only by id
            pass
        elif cargs[1] == 'HOST':
            table = 'host'
        elif cargs[1] == 'SVC':
            table = 'service'
            query_args.append(args[2])

        return cls(None, command, table, keepalive=True, columns=query_args)

    @classmethod
    def parse(cls, sock, string):
        """
        Parse a string and create a livestatus query object
        """
        method = None
        table = None
        options = {}

        log = logging.getLogger('tantale.livestatus')
        log.debug("Livestatus query :\n%s" % string)

        try:
            for line in string.split('\n'):
                members = line.split(' ')
                # Empty line
                if members[0] == '':
                    pass

                # Stats
                elif members[0] == 'Stats:':
                    options['stats'] = options.get('stats', [])
                    options['stats'].append(cls.parse_expr(members[1:], table))
                elif members[0] == 'StatsAnd:':
                    nb = int(members[1])
                    options['stats'][-nb] = cls.combine_expr(
                        'and', options['stats'][-nb:])
                    options['stats'] = options['stats'][:-nb + 1]
                elif members[0] == 'StatsOr:':
                    nb = int(members[1])
                    options['stats'][-nb] = cls.combine_expr(
                        'or', options['stats'][-nb:])
                    options['stats'] = options['stats'][:-nb + 1]
                elif members[0] == 'StatsNegate:':
                    options['stats'][1] = cls.combine_expr(
                        'not', options['stats'][-1])

                # Filters
                elif members[0] == 'Filter:':
                    options['filters'] = options.get('filters', [])
                    options['filters'].append(
                        cls.parse_expr(members[1:], table))
                elif members[0] == 'And:':
                    nb = int(members[1])
                    options['filters'][-nb] = cls.combine_expr(
                        'and', options['filters'][-nb:])
                    options['filters'] = options['filters'][:-nb + 1]
                elif members[0] == 'Or:':
                    nb = int(members[1])
                    options['filters'][-nb] = cls.combine_expr(
                        'or', options['filters'][-nb:])
                    options['filters'] = options['filters'][:-nb + 1]
                elif members[0] == 'Negate:':
                    options['filters'][-1] = cls.combine_expr(
                        'not', options['filters'][-1])

                # Method
                elif members[0] == 'GET':
                    method = 'GET'
                    table = members[1]
                elif members[0] == 'COMMAND':
                    return cls.parse_command(members[2])

                # Optional lines / Headers
                elif members[0] == 'AuthUser:':
                    options['filters'] = options.get('filters', [])
                    options['filters'].append(['contacts', '>=', members[1]])
                elif members[0] == 'Columns:':
                    options['columns'] = members[1:]
                elif members[0] == 'ColumnHeaders:':
                    options['headers'] = members[1:]
                elif members[0] == 'ResponseHeader:':
                    options['rheader'] = members[1]
                elif members[0] == 'KeepAlive:':
                    if members[1] == 'on':
                        options['keepalive'] = True
                elif members[0] == 'OutputFormat:':
                    options['oformat'] = members[1]
                elif members[0] == 'Limit:':
                    options['limit'] = int(members[1])
                elif members[0] == 'Localtime:':
                    # TOFIX no time handling
                    pass

                # Raise error is something not understood
                else:
                    raise Exception('Unknown command %s' % members[0])

            return cls(sock, method, table, **options)
        except:
            raise Exception(
                'Error %s\nparsing line "%s" on query "%s"'
                % (traceback.format_exc(), line, repr(string)))
