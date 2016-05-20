# coding=utf-8

import traceback
import logging
from six import b as bytes

from tantale.livestatus.query import Query
from tantale.livestatus.command import Command
from tantale.livestatus.mapping import *


class Parser(object):
    def __init__(self):
        self.log = logging.getLogger('tantale.livestatus')

    def field_map(self, field, table):
        """ Map query field to tantale known field """
        if field.startswith("%s_" % table[:-1]):
            field = field[len(table):]
        # Log got no final 's'
        if field.startswith("log_"):
            field = field[4:]

        # Map parent on service
        if table == 'services' and field.startswith('host_'):
            mapped = self.field_map(field[5:], 'hosts')
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

    def parse_expr(self, arg_list, table):
        """ Convert filters to expression list """
        # TOFIX exclude custom_variable_names / not relevant
        # TOFIX for now assume right operand is constant
        if arg_list[0].endswith("custom_variable_names"):
            return None

        arg_list[0] = self.field_map(arg_list[0], table)

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

    def combine_expr(self, operator, expr_list):
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

    def parse_command(self, command):
        """
        Parse data from :
            SCHEDULE_HOST_DOWNTIME / SCHEDULE_SVC_DOWNTIME
            ACKNOWLEDGE_HOST_PROBLEM / ACKNOWLEDGE_SVC_PROBLEM
            REMOVE_HOST_ACKNOWLEDGEMENT / REMOVE_SVC_ACKNOWLEDGEMENT
            DEL_HOST_DOWNTIME / DEL_SVC_DOWNTIME
            DISABLE_PASSIVE_HOST_CHECKS /
            DISABLE_PASSIVE_SVC_CHECKS (wired to delete from backend method)
        """
        args = command.split(';')
        command = args.pop(0)

        if command in ('DEL_HOST_DOWNTIME', 'DEL_SVC_DOWNTIME'):
            # remove downtime is a special case (id)
            return True, Command(
                function='downtime',
                action='remove',
                doc_id=int(args.pop(0)))

        else:
            kwargs = {}

            command = command.split('_')

            if command[1] == 'HOST' or command[2] == 'HOST':
                kwargs['host'] = args[0]
            elif command[1] == 'SVC' or command[2] == 'SVC':
                kwargs['host'] = args[0]
                kwargs['service'] = args[1]
            else:
                raise Exception('Unknown command %s' % command)

            # parse action
            if command[0] in ('REMOVE', 'DISABLE'):
                kwargs['action'] = 'remove'
            else:
                kwargs['action'] = 'add'

            # parse function
            if command[2] == 'PASSIVE':
                kwargs['function'] = 'drop'

            elif command[2] == 'DOWNTIME':
                kwargs['function'] = 'downtime'

            elif (command[2] == 'ACKNOWLEDGEMENT' or
                  command[0] == 'ACKNOWLEDGE'):
                kwargs['function'] = 'acknowledge'

            else:
                raise Exception('Unknown command %s' % command)

        # Always keepalived
        return True, Command(**kwargs)

    def parse(self, string):
        """
        Parse a string and create a livestatus query object
        """
        method = None
        table = None
        options = {}
        keepalive = False

        try:
            for line in string.split('\n'):
                self.log.debug("Livestatus query : %s" % line)

                members = line.split(' ')
                # Empty line
                if members[0] == '':
                    pass

                # Stats
                elif members[0] == 'Stats:':
                    options['stats'] = options.get('stats', [])
                    options['stats'].append(
                        self.parse_expr(members[1:], table))
                elif members[0] == 'StatsAnd:':
                    nb = int(members[1])
                    options['stats'][-nb] = self.combine_expr(
                        'and', options['stats'][-nb:])
                    options['stats'] = options['stats'][:-nb + 1]
                elif members[0] == 'StatsOr:':
                    nb = int(members[1])
                    options['stats'][-nb] = self.combine_expr(
                        'or', options['stats'][-nb:])
                    options['stats'] = options['stats'][:-nb + 1]
                elif members[0] == 'StatsNegate:':
                    options['stats'][1] = self.combine_expr(
                        'not', options['stats'][-1])

                # Filters
                elif members[0] == 'Filter:':
                    options['filters'] = options.get('filters', [])
                    options['filters'].append(
                        self.parse_expr(members[1:], table))
                elif members[0] == 'And:':
                    nb = int(members[1])
                    options['filters'][-nb] = self.combine_expr(
                        'and', options['filters'][-nb:])
                    options['filters'] = options['filters'][:-nb + 1]
                elif members[0] == 'Or:':
                    nb = int(members[1])
                    options['filters'][-nb] = self.combine_expr(
                        'or', options['filters'][-nb:])
                    options['filters'] = options['filters'][:-nb + 1]
                elif members[0] == 'Negate:':
                    options['filters'][-1] = self.combine_expr(
                        'not', options['filters'][-1])

                # Method
                elif members[0] == 'GET':
                    method = 'GET'
                    table = members[1]
                elif members[0] == 'COMMAND':
                    return self.parse_command(members[2])

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
                        keepalive = True
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

            return keepalive, Query(method, table, **options)
        except:
            raise Exception(
                'Error %s\nparsing line "%s" on query "%s"'
                % (traceback.format_exc(), line, repr(string)))
