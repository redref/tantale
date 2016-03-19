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
            if field in ('and', 'or', 'not'):
                l = []
                for expr in operator:
                    l.append(self.convert_expr(*expr))
                return {field: l}
            else:
                raise Exception('Unknown boolean operator %s' % field)

        # Special cases - null values - not posted in input
        filt = {}
        if field in ('downtime', 'ack') and value == 0 and operator == '=':
            filt = {'or': [
                {'not': {'exists': {'field': field}}},
                {'term': {field: value}}
            ]}
            return filt

        # Special case - parent field
        related = False
        if field.startswith('host.'):
            related = 'host'
            field = field[7:]

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
        if query.table == 'services':
            return self.query_status(query, 'service')
        elif query.table == 'hosts':
            return self.query_status(query, 'host')
        else:
            raise NotImplementedError

    def query_status(self, query, qtype):
        es_meta = {"index": self.status_index}
        es_query = {'filter': {'and': [{'type': {'value': qtype}}]}}

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
                self.log.debug('Elasticsearch response :\n%s' % response)
                result.append(response['hits']['total'])
            count = 1
            query.append(result)
        else:
            body = json.dumps(es_meta) + "\n"
            body += json.dumps(es_query) + "\n"
            self.log.debug('Elasticsearch requests :\n%s' % body)

            count = 0
            for response in self.elasticclient.msearch(body)['responses']:
                self.log.debug('Elasticsearch response :\n%s' % response)
                if 'error' not in response:
                    query.append(response)
                    count += 1

        return count

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
            self.log.debug("ElasticsearchBackend: Established connection to "
                           "Elasticsearch cluster %s",
                           repr(self.hosts))
        except Exception as ex:
            import traceback
            self.log.debug(traceback.format_exc())
            # Log Error
            self._throttle_error("ElasticsearchBackend: Failed to connect to "
                                 "%s.", ex)
            # Close Socket
            self._close()
            return

    def _close(self):
        """
        Close / Free
        """
        self.elasticclient = None
