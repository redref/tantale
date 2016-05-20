# coding=utf-8

from __future__ import print_function

import json
import copy
import time
import logging

from tantale.backends.elasticsearch.base import ElasticsearchBaseBackend
from tantale.livestatus.backend import Backend


class ElasticsearchBackend(ElasticsearchBaseBackend, Backend):
    def __init__(self, config=None):
        self.log = logging.getLogger('tantale.livestatus')
        super(ElasticsearchBackend, self).__init__(config)

    def _convert_expr(self, field, operator, value=None):
        """ Convert tantale expression to elasticsearch filter """
        # Handle booleans (and/or/not)
        if value is None:
            if field in ('and', 'or'):
                l = []
                for expr in operator:
                    l.append(self._convert_expr(*expr))
                return {field: l}
            if field in ('not',):
                # Elasticsearch does not support NAND / NOR
                # Convert it to OR (NOT) and AND (NOT)
                expr = self._convert_expr(*operator[0])
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
                    return {field: self._convert_expr(*operator[0])}
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

    def command(self, command):
        if command.function == 'acknowledge':
            if command.action == 'add':
                value = 1
            else:
                value = None

            self._update_query(
                body=json.dumps({"doc": {"ack": value}}),
                doc_type=command.type,
                id=command.doc_id,
                parent=command.parent
            )

        elif command.function == 'downtime':
            query = {'doc': {}}

            if command.action == 'add':
                # Generate unique id
                res = self.elasticclient.search(
                    index=self.status_index, size=0,
                    body=json.dumps({
                        "aggs": {"uid": {"max": {"field": "downtime_id"}}}
                    })
                )
                uid = res['aggregations']['uid']['value']

                if uid:
                    uid = int(uid) + 1
                else:
                    uid = 1

                query['doc']['downtime_id'] = uid
                query['doc']['downtime'] = 1

            else:
                # Get document by downtime_id
                id_search = {
                    'filter': {'term': {'downtime_id': command.doc_id}}}
                kwargs = {
                    'index': self.status_index,
                    'size': 1,
                    'body': json.dumps(id_search),
                }
                res = self.elasticclient.search(
                    index=self.status_index,
                    body=json.dumps({
                        'filter': {'term': {'downtime_id': command.doc_id}}})
                )

                if len(res['hits']['hits']) <= 0:
                    return

                command.doc_id = res['hits']['hits'][0]['_id']
                command.type = res['hits']['hits'][0]['_type']
                if '_parent' in res['hits']['hits'][0]:
                    command.parent = res['hits']['hits'][0]['_parent']

                query['doc']['downtime_id'] = None
                query['doc']['downtime'] = None

            self._update_query(
                body=json.dumps(query),
                doc_type=command.type,
                id=command.doc_id,
                parent=command.parent
            )

        elif command.function == 'drop':
            pass

    def _update_query(self, **kwargs):
        self.log.debug('Elasticsearch update request : %s' % str(kwargs))

        if 'parent' in kwargs and kwargs['parent'] is None:
            del kwargs['parent']

        response = self.elasticclient.update(index=self.status_index, **kwargs)

        self.log.debug('Elasticsearch update response : %s' % response)

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

        if query.table == 'downtimes':
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
        es_meta = {"index": "%s-*" % self.log_index, '_type': 'event'}
        sort = [{"timestamp": "desc"}]
        return self._search_query(query, es_meta, sort)

    def _search_query(self, query, es_meta, sort=None):
        """ Internally process GET queries """
        es_query = {}

        # Add filters
        if query.filters:
            es_query = {'filter': {'and': []}}
            for filt in query.filters:
                es_query['filter']['and'].append(self._convert_expr(*filt))

        # Stats / COUNT query
        if query.stats:
            if 'filter' not in es_query:
                es_query = {'filter': {'and': []}}
            es_meta['search_type'] = 'count'
            body = ""
            for stat in query.stats:
                body += json.dumps(es_meta) + "\n"
                stat_query = copy.deepcopy(es_query)
                stat_query['filter']['and'].append(self._convert_expr(*stat))
                self.log.debug(
                    'Elasticsearch search request : %s' % stat_query)
                body += json.dumps(stat_query) + "\n"

            result = []
            for response in self.elasticclient.msearch(body=body)['responses']:
                if 'error' in response:
                    self.log.debug(
                        'Elasticsearch error response: %s' % response)
                else:
                    result.append(response['hits']['total'])
            count = 1
            query.append(result)

        # Normal query / return lines
        else:
            if sort:
                es_query['sort'] = sort
            if query.limit:
                es_query['size'] = query.limit

            self.log.debug('Elasticsearch count request : %s' % es_query)

            body = json.dumps(es_meta) + "\n"
            body += json.dumps(es_query) + "\n"

            response = self.elasticclient.msearch(body=body)['responses'][0]

            if 'error' in response:
                # No index or empty query
                self.log.debug(
                    'Elasticsearch error response: %s' % response)
                return 0

            count = response['hits']['total']
            for hit in response['hits']['hits']:
                line = hit['_source']
                if 'last_check' not in line:
                    line['last_check'] = line['timestamp']
                query.append(line)

        return count
