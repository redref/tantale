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

from elasticsearch import helpers


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
            self.send()

    def flush(self):
        """
        Flush queue (called on exit)
        Avoid dropping checks
        """
        while len(self.checks) > 0:
            before = len(self.checks)
            self.send()
            if before == len(self.checks):
                break

    def freshness_iterator(self, query, timeout, outdated_status, prefix):
        """
        Make a scan query then manipulate hits
        Yield on all modified hits
        """
        for hit in helpers.scan(
            self.elasticclient,
            index=self.status_index,
            size=self.batch_size,
            query=query,
            scroll="%ss" % timeout,
        ):
            hit['_op_type'] = 'update'
            hit['doc'] = {}

            # Update status only if OK before
            if hit['_source']['status'] == 0:
                hit['doc']['status'] = outdated_status
            else:
                hit['doc']['status'] = hit['_source']['status']

            hit['doc']['timestamp'] = int(time.time()) * 1000

            hit['doc']['output'] = prefix + hit['_source']['output']

            # Build a log entry
            log = {}
            for field in Check.log_fields:
                if field in ('timestamp', 'status', 'output'):
                    log[field] = hit['doc'][field]
                else:
                    log[field] = hit['_source'][field]

            del hit['_source']

            yield hit

            # Update OK
            # Forward update to _send_to_logs
            self.logs.append(log)

    def freshness(self, timeout, outdated_status, prefix):
        """
        Get scroll on outdated, then bulk update it with values
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
        except:
            self.log.error(
                'ElasticsearchBackend: failed to build freshness request')
            self.log.debug("Trace:\n%s" % traceback.format_exc())
            return

        if self.elasticclient is None:
            self.log.debug("ElasticsearchBackend: not connected. "
                           "Reconnecting")
            self._connect()
        if self.elasticclient is None:
            self.log.info("ElasticsearchBackend: Reconnect failed")
            return

        try:
            for res in helpers.streaming_bulk(
                self.elasticclient,
                self.freshness_iterator(
                    search_body, timeout, outdated_status, prefix),
                chunk_size=self.batch_size,
            ):
                pass
        except SystemExit:
            # Handle process exit
            raise
        except:
            self.log.info("ElasticsearchBackend: failed to update outdated")
            self.log.debug("Trace:\n%s" % traceback.format_exc())

        self._send_to_logs()

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

    def send(self):
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
