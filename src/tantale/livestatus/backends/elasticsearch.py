# coding=utf-8
"""
Use [Elasticsearch] cluster
(https://www.elastic.co/products/elasticsearch) using search API.

Require python Elastic client 'python-elasticsearch'

### Setup

You may look setup in tantale.input.backends.elasticsearch.
"""

from __future__ import print_function

import json
import copy
from six import string_types
from datetime import datetime

from tantale.livestatus.backend import Backend
from tantale.utils import str_to_bool

from elasticsearch.client import Elasticsearch


class ElasticsearchBackend(Backend):
    def __init__(self, config=None):
        Backend.__init__(self, config)

        # Initialize collector options
        self.batch_size = int(self.config['batch'])
        self.backlog_size = int(self.config['backlog_size'])

        # Initialize Elasticsearch client Options
        if isinstance(self.config['hosts'], string_types):
            self.hosts = [self.config['hosts']]
        else:
            self.hosts = self.config['hosts']

        self.use_ssl = str_to_bool(self.config['use_ssl'])
        self.verify_certs = str_to_bool(self.config['verify_certs'])
        self.ca_certs = self.config['ca_certs']

        self.sniffer_timeout = int(self.config['sniffer_timeout'])
        self.sniff_on_start = str_to_bool(self.config['sniff_on_start'])
        self.sniff_on_connection_fail = str_to_bool(
            self.config['sniff_on_connection_fail'])

        self.status_index = self.config['status_index']
        self.log_index = self.config['log_index']
        self.log_index_rotation = self.config['log_index_rotation']
        self.request_timeout = int(self.config['request_timeout'])

        # Connect
        self.elasticclient = None
        self._connect()

    def get_default_config_help(self):
        """
        Returns the help text for the configuration options
        """
        config = super(ElasticsearchBackend, self).get_default_config_help()

        config.update({
            'hosts': "Elasticsearch cluster front HTTP URL's "
                     "(comma separated)",
            'use_ssl': 'Elasticsearch client option :'
                       ' use SSL on HTTP connections',
            'verify_certs': 'Elasticsearch client option :'
                            ' verify certificates.',
            'ca_certs': 'Elasticsearch client option :'
                        ' path to ca_certs on disk',
            'sniffer_timeout': 'Elasticsearch client option',
            'sniff_on_start': 'Elasticsearch client option',
            'sniff_on_connection_fail': 'Elasticsearch client option',
            'status_index': 'Elasticsearch index to use',
            'log_index': 'Elasticsearch index to use',
            'log_index_rotation': 'Determine index name time suffix'
                              ' (None|"daily"|"hourly")',
            'request_timeout': 'Elasticsearch client option',
            'batch': 'How many checks to store before sending',
            'backlog_size': 'How many checks to keep before trimming',
        })

        return config

    def get_default_config(self):
        """
        Return the default config
        """
        config = super(ElasticsearchBackend, self).get_default_config()

        config.update({
            'hosts': "http://127.0.0.1:9200",
            'use_ssl': False,
            'verify_certs': False,
            'ca_certs': '',
            'sniffer_timeout': 10,
            'sniff_on_start': True,
            'sniff_on_connection_fail': True,
            'status_index': 'status',
            'log_index': 'status_logs',
            'log_index_rotation': 'daily',
            'request_timeout': 30,
            'batch': 1,
            'backlog_size': 50,
        })

        return config

    def __del__(self):
        """
        Destroy instance
        """
        self._close()

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

        # Special cases - null values - not posted in input
        filt = {}
        if field in ('downtime', 'ack') and value == 0 and operator == '=':
            filt = {'or': [
                {'not': {'exists': {'field': field}}},
                {'term': {field: value}}
            ]}
        else:
            # Compare
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
            else:
                raise Exception("Unknown operator %s" % operator)

        # Map back into parent filter
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
        elif query.table == 'services':
            return self.query_status(query, 'service')
        elif query.table == 'hosts':
            return self.query_status(query, 'host')
        elif query.table == 'log':
            return self.query_logs(query)
        else:
            raise NotImplementedError

    def query_status(self, query, qtype):
        es_meta = {"index": self.status_index, 'type': qtype}
        return self.search_query(query, es_meta)

    def query_logs(self, query):
        es_meta = {"index": "%s-*" % self.log_index, '_type': 'event'}
        return self.search_query(query, es_meta)

    def search_query(self, query, es_meta):
        es_query = {'filter': {'and': []}}

        if query.filters:
            for filt in query.filters:
                es_query['filter']['and'].append(self.convert_expr(*filt))

        if query.stats:
            es_meta['search_type'] = 'count'
            body = ""
            for stat in query.stats:
                body += json.dumps(es_meta) + "\n"
                stat_query = es_query.copy()
                es_query['filter']['and'].append(self.convert_expr(*stat))
                body += json.dumps(stat_query) + "\n"
            self.log.debug('Elasticsearch requests :\n%s' % body)

            result = []
            for response in self.elasticclient.msearch(body)['responses']:
                # DEBUG : usefull lines
                # self.log.debug(
                #     'Elasticsearch response 1rst line :\n%s' % response)
                result.append(response['hits']['total'])
            count = 1
            query.append(result)
        else:
            # DEBUG : comment both next lines to limit results to 5
            # if query.limit:
            #     es_query['size'] = query.limit
            body = json.dumps(es_meta) + "\n"
            body += json.dumps(es_query) + "\n"
            self.log.debug('Elasticsearch requests :\n%s' % body)

            response = self.elasticclient.msearch(body)['responses'][0]
            # self.log.debug('Elasticsearch response :\n%s' % response)
            if 'error' in response:
                # Handle empty result
                return 0
            count = response['hits']['total']
            for hit in response['hits']['hits']:
                query.append(hit['_source'])

        return count

    def update_query(self, query):
        command = {"doc": {query.method: 1}}
        kwargs = {
            'index': self.status_index,
            'body': json.dumps(command),
            'doc_type': query.table,
            'id': query.columns[0],
        }
        if query.table == 'service':
            kwargs['parent'] = query.columns[1]
        response = self.elasticclient.update(**kwargs)
        self.log.debug('Elasticsearch response :\n%s' % response)

    def _connect(self):
        """
        Connect to the server
        """
        # Connect to server
        try:
            self.elasticclient = Elasticsearch(
                self.hosts,
                use_ssl=self.use_ssl,
                verify_certs=self.verify_certs,
                ca_certs=self.ca_certs,
                sniffer_timeout=self.sniffer_timeout,
                sniff_on_start=self.sniff_on_start,
                sniff_on_connection_fail=self.sniff_on_connection_fail,
            )
            # Log
            self.log.info(
                "ElasticsearchBackend: Established connection to "
                "Elasticsearch cluster %s" % repr(self.hosts))
        except:
            # Log Error
            self._throttle_error("ElasticsearchBackend: Failed to connect")
            import traceback
            self.log.debug(
                "Connection error stack :\n%s" % traceback.format_exc())
            # Close Socket
            self._close()
            return

    def _close(self):
        """
        Close / Free
        """
        self.elasticclient = None
