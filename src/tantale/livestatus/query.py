# coding=utf-8

import traceback
import logging
from six import b as bytes

try:
    unicode
except:
    unicode = None

from tantale.livestatus.mapping import *


class Query(object):
    __slots__ = [
        'log',
        'output_sock', 'method', 'table',
        'columns', 'filters', 'stats', 'limit',
        'rheader', 'oformat', 'headers',
        'separators', 'results',
    ]

    def __init__(
        self, method, table,
        columns=None, filters=None, stats=None, limit=None,
        rheader=None, oformat='csv', headers=False,
        separators=['\n', ';', ',', '|']
    ):
        self.log = logging.getLogger('tantale.livestatus')

        self.output_sock = None
        self.method = method
        self.table = table
        self.columns = columns
        self.limit = limit
        self.rheader = rheader
        self.oformat = oformat
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

    def execute(self, backends):
        """
        Do query on backends
        """
        try:
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

            # downtimes table / add filter
            elif self.table == 'downtimes':
                if self.filters:
                    self.filters.append(['downtime', '!=', 0])
                else:
                    self.filters = [['downtime', '!=', 0]]

            # Request backend
            for backend in backends:
                length = backend._query(self)

                if length and self.limit:
                    if length > self.limit:
                        return
                    self.limit -= length
        finally:
            self.flush()

    def append(self, result):
        """ Map back tantale results columns to queried columns """
        if self.columns:
            mapped_res = []
            for req_field in self.columns:
                # Remove object related prefix
                if req_field.startswith("host_"):
                    field = req_field[5:]
                elif req_field.startswith("service_"):
                    field = req_field[8:]
                elif req_field.startswith("log_"):
                    field = req_field[4:]
                else:
                    field = req_field

                # Search for columns
                map_name = False

                if self.table == 'services' and req_field == 'host_state':
                    mapped_res.append(0)
                    continue

                # Host state from a service log
                elif self.table == 'downtimes' and req_field == "host_state":
                    mapped_res.append(0)
                    continue

                elif field in result:
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
                elif self.table == 'log':
                    if field == 'type':
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
                'Tantale result (first line): %s', str(self.results))

        # Handle line by line printing
        if self.oformat == 'csv' and not self.rheader:
            self._output_line()

    def _output_line(self):
        """
        Write a result line
        Used in csv format
        """
        raise NotImplementedError

    def flush(self):
        """
        Dump results to network
        """
        if self.rheader == 'fixed16':
            string = str(self.results)
            self.output_sock.send(
                bytes('%3d %11d %s\n' % (200, len(string) + 1, string)))
        else:
            if len(self.results) > 0:
                raise NotImplementedError
                # for result in self.results:
                #     self.output_fd.write(bytes('%s\n' % ';'.join(result)))
