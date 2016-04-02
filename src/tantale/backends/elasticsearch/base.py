# coding=utf-8
"""
Use [Elasticsearch] cluster (https://www.elastic.co/products/elasticsearch)
using bulk / msearch / update API.

Require python Elastic client 'python-elasticsearch'

### Setup

Elasticsearch templates :

  * STATUS INDEX : in status.template file

  * LOGS INDEX : in status_logs.template

  * UPDATE SCRIPT (Groovy) :

Path may be /etc/elasticsearch/scripts/tantale.groovy

```
ctx._source.last_check = timestamp
ctx._source.output = output
ctx._source.contacts = contacts

if (ctx._source.status != status) {
    ctx._source.status = status
    ctx._source.timestamp = timestamp
    ctx._source.output = output
    if (ctx._source.ack == 1) {
        ctx._source.ack = 0
    }
}

### Description

Post check to "status" index with id unicity (<hostname>-<check_name>)
using "update/upsert" API, script maintain correct timestamp/last_check values.

Timestamp returned in update query ()

"""

from __future__ import print_function

from six import string_types

from tantale.backend import BaseBackend
from tantale.utils import str_to_bool

from elasticsearch.client import Elasticsearch


class ElasticsearchBaseBackend(BaseBackend):
    def __init__(self, config=None):
        BaseBackend.__init__(self, config)

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
        config = super(
            ElasticsearchBaseBackend, self).get_default_config_help()

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
        config = super(ElasticsearchBaseBackend, self).get_default_config()

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
