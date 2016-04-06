# coding=utf-8

from __future__ import print_function

import json
import time
import traceback
from datetime import datetime

from tantale.backends.elasticsearch.base import ElasticsearchBaseBackend
from tantale.input.backend import Backend


class ElasticsearchBackend(ElasticsearchBaseBackend, Backend):
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
                body="\n".join(requests), index=self.status_index)
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
            res = self.elasticclient.bulk(body="\n".join(requests))

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

    def update_outdated(self, timeout, outdated_status, prefix):
        try:
            max_time = (int(time.time()) - timeout) * 1000
            es_query = {
                'size': self.batch_size,
                'version': True,
                'filter': {"and": [
                    {'or': [
                        {'range': {'last_check': {'lt': max_time}}},
                        {'and': [
                            {'not': {'exists': {'field': 'last_check'}}},
                            {'range': {'timestamp': {'lt': max_time}}},
                        ]},
                    ]},
                    {"not": {"prefix": {"output": prefix}}},
                ]}
            }
            sbody = json.dumps(es_query)

            while True:
                # Refresh before redo request
                self.elasticclient.indices.refresh(index=self.status_index)
                result = self.elasticclient.search(
                    index=self.status_index, body=sbody)

                if 'hits' not in result:
                    self.log.debug(
                        "ElasticsearchBackend: Failed to get outdated checks"
                        "\n%s" % result)
                    break

                if result['hits']['total'] == 0:
                    # Normal end here
                    break

                # Generate bulk update body
                body = ""
                for hit in result['hits']['hits']:
                    # Change status to 1 and output prefix
                    changed = False
                    if hit['_source']['status'] == 0:
                        status = outdated_status
                        changed = True
                    else:
                        status = hit['_source']['status']
                    if not hit['_source']['output'].startswith(prefix):
                        output = "%s%s" % (prefix, hit['_source']['output'])
                        changed = True
                    else:
                        output = hit['_source']['output']

                    if changed:
                        # Metadata for an update
                        metadata = {"update": {
                            "_index": self.status_index,
                            "_version": hit['_version'],
                            "_id": hit['_id'],
                            "_type": hit['_type'],
                        }}
                        if '_parent' in hit:
                            metadata['update']['_parent'] = hit['_parent']
                        body += json.dumps(metadata)
                        body += "\n"

                        # Update fields
                        body += json.dumps({"refresh": True, "doc": {
                            "output": output,
                            "status": status,
                            "last_check": int(time.time()) * 1000,
                        }})
                        body += "\n"

                # Do bulk
                if body != "":
                    bulk_result = self.elasticclient.bulk(body=body)

                    if 'items' not in bulk_result:
                        raise Exception(
                            'Failed to send bulk request %s' % bulk_result)

                    # TOFIX : some update problem with version and cache
                    for item in bulk_result['items']:
                        if 'error' in item["update"]:
                            raise Exception(
                                'Failed to update with error %s' % bulk_result)

        except SystemExit:
            raise
        except:
            self.log.info("ElasticsearchBackend: unable to update outdated")
            self.log.debug("Trace:\n%s" % traceback.format_exc())
