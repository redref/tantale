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

    def process(self, check):
        """
        Process a check by storing it in memory
        Trigger sending is batch size reached
        """
        # Append the data to the array as a string
        self.checks.append(check)
        if len(self.checks) >= self.batch_size:
            self._send()

    def flush(self):
        """
        Flush queue
        """
        if len(self.checks) != 0:
            self._send()

    def _send_data(self):
        """
        Try to send all data in buffer.
        """
        requests = []
        for check in self.checks:
            head = {"_type": check.type, "_id": check.id}
            if check.type == 'service':
                head['parent'] = check.hostname
            requests.append(json.dumps({"update": head}))

            obj = {}
            for slot in check.__slots__:
                if slot not in ('type', 'id'):
                    obj[slot] = getattr(check, slot, None)
            obj['timestamp'] = obj['timestamp'] * 1000
            requests.append(json.dumps({
                "fields": ["timestamp"], 'upsert': obj,
                "script": {"file": "tantale", "params": obj}}))

        if len(requests) > 0:
            res = self.elasticclient.bulk(
                "\n".join(requests), index=self.status_index)

            if res:
                if 'errors' in res and res['errors'] != 0:
                    for idx, item in enumerate(res['items']):
                        if 'error' in item['update']:
                            self.log.debug(
                                "ElasticsearchBackend: %s" % repr(item))
                            self.log.debug(
                                "ElasticsearchBackend: "
                                "Failed source : %s" % repr(self.checks[idx]))
                    self.log.error("ElasticsearchBackend: Errors sending data")
                    raise Exception("Elasticsearch Cluster returned problem")

                if 'items' in res:
                    return res['items']

        return None

    def _send_logs(self, res):
        requests = []
        for idx, check in enumerate(self.checks):
            # Logs / Events
            if self.log_index_rotation == 'daily':
                index = "%s-%s" % (
                    self.log_index,
                    datetime.fromtimestamp(
                        check.timestamp).strftime('%Y.%m.%d')
                )
            elif self.log_index_rotation == 'hourly':
                index = "%s-%s" % (
                    self.log_index,
                    datetime.fromtimestamp(
                        check.timestamp).strftime('%Y.%m.%d.%H')
                )
            else:
                index = self.log_index

            if (
                'update' in res[idx] and 'get' in res[idx]['update'] and
                (check.timestamp * 1000) !=
                res[idx]['update']['get']['fields']['timestamp'][0]
            ):
                head = {"_type": "event", "_id": check.id, "_index": index}
                requests.append(json.dumps({"index": head}))

                obj = {}
                for slot in check.__slots__:
                    if slot not in ('type', 'id'):
                        obj[slot] = getattr(check, slot, None)
                obj['timestamp'] = obj['timestamp'] * 1000
                requests.append(json.dumps(obj))

        if len(requests) > 0:
            res = self.elasticclient.bulk("\n".join(requests))

            if 'errors' in res and res['errors'] != 0:
                for idx, item in enumerate(res['items']):
                    if 'error' in item['update']:
                        self.log.debug(
                            "ElasticsearchBackend: %s" % repr(item))
                        self.log.debug(
                            "ElasticsearchBackend: "
                            "Failed source : %s" % repr(self.checks[idx]))
                self.log.error("ElasticsearchBackend: Errors sending logs")
                raise Exception("Elasticsearch Cluster returned problem")

    def _send(self):
        """
        Send data. Queue on error
        """
        # Check to see if we have a valid connection. If not, try to connect.
        try:
            if self.elasticclient is None:
                self.log.debug("ElasticsearchBackend: not connected. "
                               "Reconnecting")
                self._connect()

            if self.elasticclient is None:
                self.log.debug("ElasticsearchBackend: Reconnect failed")
            else:
                try:
                    # Send data
                    res = self._send_data()
                    if res:
                        self._send_logs(res)
                    else:
                        self.log.info(
                            'ElasticsearchBackend: no events to send')
                    self.checks = []
                except Exception:
                    import traceback
                    self._throttle_error("ElasticsearchBackend: "
                                         "Error sending checks %s" %
                                         traceback.format_exc())
        finally:
            # self.log.debug("%d checks in queue" % len(self.checks))
            if len(self.checks) > self.backlog_size:
                trim_offset = (self.backlog_size * -1 + self.batch_size)
                self.log.warn('ElasticsearchBackend: Trimming backlog. '
                              'Removing oldest %d and '
                              'keeping newest %d checks',
                              len(self.checks) - abs(trim_offset),
                              abs(trim_offset))
                self.checks = self.checks[trim_offset:]

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
