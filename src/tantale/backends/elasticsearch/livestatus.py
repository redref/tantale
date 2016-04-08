# coding=utf-8

from __future__ import print_function

import json
import copy
import time

from tantale.backends.elasticsearch.base import ElasticsearchBaseBackend
from tantale.livestatus.backend import Backend


class ElasticsearchBackend(ElasticsearchBaseBackend, Backend):
    def convert_expr(self, field, operator, value=None):
        """ Convert tantale expression to elasticsearch filter """
        # Handle booleans (and/or/not)
        if value is None:
            if field in ('and', 'or'):
                l = []
                for expr in operator:
                    l.append(self.convert_expr(*expr))
                return {field: l}
            if field in ('not',):
                # Elasticsearch does not support NAND / NOR
                # Convert it to OR (NOT) and AND (NOT)
                expr = self.convert_expr(*operator[0])
                if 'and' in expr or 'or' in expr:
                    if 'and' in expr:
                        old = 'and'
                        new = 'or'
                    else:
                        old = 'or'
                        new = 'and'
                    filt = {new: []}
                    for nest_filt in expr[old]:
                        filt[new].append({"not": nest_filt})
                    return filt
                else:
                    return {field: self.convert_expr(*operator[0])}
            else:
                raise Exception('Unknown boolean operator %s' % field)

        # JOIN - wrap into
        related = False
        if field.startswith('host.'):
            related = 'host'
            field = field[5:]

        # Handle columns that are lists to contain filter
        if field == 'contacts' and operator == '>=':
            operator = "="

        # Handle columns that can be null
        filt = {}
        if field in ('downtime', 'ack'):
            if value == 0 and operator in ('=', '>'):
                filt = {'or': [
                    {'not': {'exists': {'field': field}}},
                    {'term': {field: value}}
                ]}
            elif value == 0 and operator == '!=':
                filt = {'term': {field: 1}}
            else:
                raise NotImplementedError

        # Normal
        else:
            # Operators
            filt = {}
            if operator == "=":
                filt['term'] = {field: value}
            elif operator == "!=":
                filt['not'] = {'term': {field: value}}
            elif operator == ">":
                filt['range'] = {field: {"gt": value}}
            elif operator == ">=":
                filt['range'] = {field: {"gte": value}}
            elif operator == "<":
                filt['range'] = {field: {"gt": value}}
            elif operator == "<=":
                filt['range'] = {field: {"gte": value}}
            elif operator == "~~":
                # Not case insensitive
                filt['regexp'] = {field: value + ".*"}
            else:
                raise Exception("Unknown operator %s" % operator)

        # JOIN - map back in a has_parent filter
        if related:
            filt = {
                "has_parent": {
                    "type": related,
                    "filter": filt
                }
            }

        return filt

    def query(self, query):
        """
        Process a query
        """
        if self.elasticclient is None:
                self.log.debug("ElasticsearchBackend: not connected. "
                               "Reconnecting")
                self._connect()
        if self.elasticclient is None:
            self.log.info("ElasticsearchBackend: Reconnect failed")
            return 0

        if query.method in ('ack', 'downtime'):
            self.update_query(query)
        elif query.table == 'services_and_hosts':
            return self.status_query(query, None)
        elif query.table == 'services':
            return self.status_query(query, 'service')
        elif query.table == 'hosts':
            return self.status_query(query, 'host')
        elif query.table == 'log':
            return self.logs_query(query)
        else:
            raise NotImplementedError

    def status_query(self, query, qtype):
        """ Process GET query over status index """
        if qtype is not None:
            es_meta = {"index": self.status_index, 'type': qtype}
        else:
            es_meta = {"index": self.status_index}
        return self._search_query(query, es_meta)

    def logs_query(self, query):
        """ Process GET query over log indexes (with sort) """
        es_meta = {"index": "%s-*" % self.log_index, '_type': 'event',
                   'sort': [{"timestamp": "desc"}]}
        return self._search_query(query, es_meta)

    def _search_query(self, query, es_meta):
        """ Internally process GET queries """
        es_query = {}

        # Add filters
        if query.filters:
            es_query = {'filter': {'and': []}}
            for filt in query.filters:
                es_query['filter']['and'].append(self.convert_expr(*filt))

        # Stats / COUNT query
        if query.stats:
            if 'filter' not in es_query:
                es_query = {'filter': {'and': []}}
            es_meta['search_type'] = 'count'
            body = ""
            for stat in query.stats:
                body += json.dumps(es_meta) + "\n"
                stat_query = copy.deepcopy(es_query)
                stat_query['filter']['and'].append(self.convert_expr(*stat))
                body += json.dumps(stat_query) + "\n"
            self.log.debug('Elasticsearch requests :\n%s' % body)

            result = []
            for response in self.elasticclient.msearch(body=body)['responses']:
                if 'error' in response:
                    self.log.debug(
                        'Elasticsearch error response:\n%s' % response)
                else:
                    result.append(response['hits']['total'])
            count = 1
            query.append(result)

        # Normal query / return lines
        else:
            if query.limit:
                es_query['size'] = query.limit

            body = json.dumps(es_meta) + "\n"
            body += json.dumps(es_query) + "\n"
            self.log.debug('Elasticsearch requests :\n%s' % body)

            response = self.elasticclient.msearch(body=body)['responses'][0]

            if 'error' in response:
                # No index or empty query
                self.log.debug(
                    'Elasticsearch error response:\n%s' % response)
                return 0

            count = response['hits']['total']
            for hit in response['hits']['hits']:
                line = hit['_source']
                if 'last_check' not in line:
                    line['last_check'] = line['timestamp']
                query.append(line)

        return count

    def update_query(self, query):
        # Parse set/unset bool
        value = int(query.columns[0])
        if value == 0:
            value = None
        # Document id
        did = "-".join(query.columns[1:])
        # Type
        el_type = query.table

        # Update to do
        command = {"doc": {query.method: value}}

        # Downtime creation need an unique id
        if query.method == "downtime":
            if value == 1:
                # Generate unique id
                id_search = {
                    "aggs": {"uid": {"max": {"field": "downtime_id"}}}}
                kwargs = {
                    'index': self.status_index,
                    'size': 0,
                    'body': json.dumps(id_search),
                }
                res = self.elasticclient.search(**kwargs)
                # print(res)
                uid = res['aggregations']['uid']['value']
                if uid:
                    uid = int(uid) + 1
                else:
                    uid = 1
                command['doc']['downtime_id'] = uid
            else:
                # Get ID by downtime id
                id_search = {'filter': {'term': {'downtime_id': did}}}
                kwargs = {
                    'index': self.status_index,
                    'size': 1,
                    'body': json.dumps(id_search),
                }
                res = self.elasticclient.search(**kwargs)
                # print(res)
                if len(res['hits']['hits']) > 0:
                    did = res['hits']['hits'][0]['_id']
                    el_type = res['hits']['hits'][0]['_type']
                    command['doc']['downtime_id'] = None
                else:
                    return

        # Update
        kwargs = {
            'index': self.status_index,
            'body': json.dumps(command),
            'doc_type': el_type,
            'id': did,
        }
        if el_type == 'service':
            kwargs['parent'] = did.split('-')[0]

        self.log.debug('Elasticsearch update request :\n%s' % str(kwargs))
        response = self.elasticclient.update(**kwargs)
        # self.log.debug('Elasticsearch response :\n%s' % response)
