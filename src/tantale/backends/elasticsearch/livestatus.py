# coding=utf-8

from __future__ import print_function

import json
import copy

from tantale.backends.elasticsearch.base import ElasticsearchBaseBackend
from tantale.livestatus.backend import Backend


class ElasticsearchBackend(ElasticsearchBaseBackend, Backend):
    def convert_expr(self, field, operator, value=None):
        # Bool
        if value is None:
            if field in ('and', 'or'):
                l = []
                for expr in operator:
                    l.append(self.convert_expr(*expr))
                return {field: l}
            if field in ('not',):
                return {field: self.convert_expr(*operator[0])}
            else:
                raise Exception('Unknown boolean operator %s' % field)

        # Special case - parent field
        related = False
        if field.startswith('host.'):
            related = 'host'
            field = field[5:]

        # Special cases - handle null values
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

        # Map back parent fields filter into parent
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
        if qtype is not None:
            es_meta = {"index": self.status_index, 'type': qtype}
        else:
            es_meta = {"index": self.status_index}
        return self.search_query(query, es_meta)

    def logs_query(self, query):
        es_meta = {"index": "%s-*" % self.log_index, '_type': 'event'}
        return self.search_query(query, es_meta)

    def search_query(self, query, es_meta):
        es_query = {}

        if query.filters:
            es_query = {'filter': {'and': []}}
            for filt in query.filters:
                es_query['filter']['and'].append(self.convert_expr(*filt))

        if query.stats:
            if 'filter' not in es_query:
                es_query = {'filter': {'and': []}}
            es_meta['search_type'] = 'count'
            body = ""
            for stat in query.stats:
                body += json.dumps(es_meta) + "\n"
                stat_query = es_query.copy()
                es_query['filter']['and'].append(self.convert_expr(*stat))
                body += json.dumps(stat_query) + "\n"
            self.log.debug('Elasticsearch requests :\n%s' % body)

            result = []
            for response in self.elasticclient.msearch(body=body)['responses']:
                # DEBUG : usefull lines
                # self.log.debug(
                #     'Elasticsearch response 1rst line :\n%s' % response)
                result.append(response['hits']['total'])
            count = 1
            query.append(result)
        else:
            # DEBUG : comment both next lines to limit results to 5
            if query.limit:
                es_query['size'] = query.limit
            body = json.dumps(es_meta) + "\n"
            body += json.dumps(es_query) + "\n"
            self.log.debug('Elasticsearch requests :\n%s' % body)

            response = self.elasticclient.msearch(body=body)['responses'][0]
            # self.log.debug('Elasticsearch response :\n%s' % response)
            if 'error' in response:
                # Handle empty result
                return 0
            count = response['hits']['total']
            for hit in response['hits']['hits']:
                query.append(hit['_source'])

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
            kwargs['parent'] = query.columns[1]

        self.log.debug('Elasticsearch update request :\n%s' % str(kwargs))
        response = self.elasticclient.update(**kwargs)
        # self.log.debug('Elasticsearch response :\n%s' % response)
