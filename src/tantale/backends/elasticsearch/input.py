# coding=utf-8

from __future__ import print_function

import json
import time
import logging
import traceback
from datetime import datetime

from tantale.backends.elasticsearch.base import ElasticsearchBaseBackend
from tantale.input.backend import Backend
from tantale.input.check import Check


class ElasticsearchBackend(ElasticsearchBaseBackend, Backend):
    def __init__(self, config=None):
        self.log = logging.getLogger('tantale.input')
        super(ElasticsearchBackend, self).__init__(config)

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
        Flush queue (called on exit)
        Avoid dropping checks
        """
        while len(self.checks) > 0:
            before = len(self.checks)
            self._send()
            if before == len(self.checks):
                break

    def freshness_update(self, timeout, outdated_status, prefix):
        """
        Fetch then Update to enforce freshness_timeout
        timeout : validity time for checks
        outdated_status : status to be applied on outdated
        prefix : output prefix to apply on outdated
        """
        try:
            min_ts = (int(time.time()) - timeout) * 1000
            search_body = json.dumps({
                'size': self.batch_size, 'version': True,
                'filter': {"and": [
                    {'or': [
                        {'range': {'last_check': {'lt': min_ts}}},
                        {'and': [
                            {'not': {'exists': {'field': 'last_check'}}},
                            {'range': {'timestamp': {'lt': min_ts}}},
                        ]},
                    ]},
                    {"not": {"prefix": {"output": prefix}}},
                ]}
            })

            while True:
                try:
                    # Refresh (before redo request)
                    self.elasticclient.indices.refresh(index=self.status_index)

                    # GET
                    result = self.elasticclient.search(
                        index=self.status_index, body=search_body)

                    if 'hits' not in result:
                        raise Exception("No hits")
                except Exception as e:
                    self.log.debug(
                        "ElasticsearchBackend: failed to get outdated"
                        "\n%s" % e)
                    break

                if result['hits']['total'] == 0:
                    # Normal end here
                    break

                # Generate bulk update
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

                    # If changed, construct request
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

                        # Update fields (and retrieve doc)
                        body += json.dumps({
                            "refresh": True, "fields": Check.log_fields,
                            "doc": {
                                "output": output,
                                "status": status,
                                "last_check": int(time.time()) * 1000}})
                        body += "\n"

                # Do bulk
                if body != "":
                    bulk_result = self.elasticclient.bulk(body=body)

                    if not bulk_result or 'items' not in bulk_result:
                        raise Exception(bulk_result)

                    for item in bulk_result['items']:
                        # Log errors
                        if 'error' in item["update"]:
                            self.log.debug(
                                "ElasticsearchBackend: failed to update "
                                "outdated with error %s" % bulk_result)
                        # Forward update to _send_to_logs
                        try:
                            fields = item['update']['get']['fields']
                            log = {}
                            for field in fields:
                                if field == 'last_check':
                                    log['timestamp'] = fields['last_check'][0]
                                else:
                                    log[field] = fields[field][0]
                            self.logs.append(log)
                        except:
                            self.log.warn(
                                "ElasticsearchBackend: log_outdated error")
                            self.log.debug(
                                "Trace :\n%s" % traceback.format_exc())

                    self._send_to_logs()

        except SystemExit:
            # Handle process exit
            raise
        except:
            self.log.info("ElasticsearchBackend: failed to update outdated")
            self.log.debug("Trace:\n%s" % traceback.format_exc())

    def _send_to_status(self):
        """
        Send batch_size checks to status index
        """
        body = ""
        sources = []
        while len(sources) <= self.batch_size:
            if len(self.checks) == 0:
                break

            check = self.checks.pop(0)

            # Request metadata
            es_meta = {"_type": check.type, "_id": check.id}
            if check.type == 'service':
                es_meta['parent'] = check.hostname
            body += json.dumps({"update": es_meta})
            body += "\n"

            # Request document
            obj = {}
            for slot in check.fields:
                obj[slot] = getattr(check, slot, None)

            # Timestamp in milliseconds
            obj['timestamp'] = obj['timestamp'] * 1000

            # Call tantale groovy script (maintain statuses)
            sources.append(obj)
            body += json.dumps({
                "fields": ["timestamp"], 'upsert': obj,
                "script": {"file": "tantale", "params": obj}})
            body += "\n"

        # Do it and handle
        if body != "":
            res = self.elasticclient.bulk(body=body, index=self.status_index)
            if res:
                # Handle errors
                if 'errors' in res and res['errors'] != 0:
                    status = False

                    # On errors, search errored items, log it, drop it
                    idx = 0
                    while len(res['items']) > idx:
                        item = res['items'][idx]
                        if 'error' in item['update']:
                            self.log.debug(
                                "ElasticsearchBackend: send error - %s" % item)
                            self.log.debug(
                                "ElasticsearchBackend: send error source - "
                                "%s" % sources[idx])
                            res['items'].pop(idx)
                        else:
                            idx += 1

                    self.log.warn("ElasticsearchBackend: send error found")

                # Construct logs list (if timestamp changed)
                if 'items' in res:
                    for idx, item in enumerate(res['items']):
                        try:
                            ts = item['update']['get']['fields']['timestamp']
                            if sources[idx]['timestamp'] <= ts[0]:
                                self.logs.append(sources[idx])
                        except:
                            self.log.warn(
                                "ElasticsearchBackend: send_res parse error")
                            self.log.debug(
                                "Trace :\n%s" % traceback.format_exc())

    def _send_to_logs(self):
        body = ""
        while len(self.logs) > 0:
            log = self.logs.pop(0)

            index = self.get_log_index(int(log['timestamp'] / 1000))

            # Request metadata
            body += json.dumps({
                "index": {"_type": "event", "_index": index}})
            body += "\n"

            # Request document
            body += json.dumps(log)
            body += "\n"

        if body != "":
            res = self.elasticclient.bulk(body=body)

            if 'errors' in res and res['errors'] != 0:
                self.log.warn("ElasticsearchBackend: log_send error found")

    def _send(self):
        """
        Send data. Queue on error
        """
        if not self._connect():
            self._throttle_error(
                self.log, "ElasticsearchBackend: not connected, queuing")
            return

        try:
            # Send to status
            self._send_to_status()
            # Send to logs
            if len(self.logs) > 0:
                self._send_to_logs()
            else:
                self.log.debug('ElasticsearchBackend: no events to send')

        except Exception:
            self._throttle_error(
                self.log,
                "ElasticsearchBackend: uncatched error sending checks")
            self.log.debug("Trace :\n%s" % traceback.format_exc())

        finally:
            # Trim
            if len(self.checks) > self.backlog_size:
                trim_offset = (self.backlog_size * -1 + self.batch_size)
                self.log.warn(
                    "ElasticsearchBackend: trimming backlog (keep %d on %d)" %
                    len(self.checks) - abs(trim_offset), abs(trim_offset))
                self.checks = self.checks[trim_offset:]
