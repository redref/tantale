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

    def freshness_iterator(
        self, query, outdated_status, prefix, start_time, timeout
    ):
        """
        Make a scan query then manipulate hits
        Yield on all modified hits
        """
        self.elasticclient.indices.refresh(
            index=self.status_index, ignore_unavailable=True)

        start_time = start_time * 1000
        now = int(time.time()) * 1000

        for hit in helpers.scan(
            self.elasticclient,
            index=self.status_index,
            size=self.batch_size,
            query=query,
            scroll="%ss" % timeout,
        ):
            # Startup grace_time handle
            if 'last_check' not in hit['_source']:
                hit['_source']['last_check'] = hit['_source']['timestamp']

            if (
                hit['_source']['last_check'] < start_time and
                now < (
                    start_time + hit['_source']['last_check'] -
                    hit['_source']['freshness'])
            ):
                continue

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

    def freshness(self, outdated_status, prefix, start_time, timeout):
        """
        Get scroll on outdated, then bulk update it with values
            factor : number of intervals to loose
            outdated_status : status to be applied on outdated
            prefix : output prefix to apply on outdated
        """
        try:
            now = int(time.time()) * 1000
            search_body = json.dumps({
                'size': self.batch_size, 'version': True,
                'filter': {"and": [
                    {'range': {'freshness': {'lt': now}}},
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
                    search_body, outdated_status, prefix, start_time, timeout),
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

    def status_iterator(self):
        """
        Iterate over input checks, yielding to update it
        """
        body = []
        checks = []
        while len(body) <= self.batch_size:
            if len(self.checks) == 0:
                break

            check = self.checks.pop(0)

            metadata = {"_type": check.type, "_id": check.id}
            if check.type == 'service':
                metadata['_parent'] = check.hostname

            body.append(metadata)
            checks.append(check)

        # Get previous status and ack to make decisions
        self.elasticclient.indices.refresh(
            index=self.status_index, ignore_unavailable=True)

        res = self.elasticclient.mget(
            body=json.dumps({"docs": body}),
            index=self.status_index,
            _source_include=('status', 'ack'),
            refresh=True,
        )

        for doc in res['docs']:
            check = checks.pop(0)

            if 'found' in doc and doc['found'] is True:
                doc['doc'] = {}
                doc['_op_type'] = 'update'
                doc['doc']['output'] = check.output
                doc['doc']['contacts'] = check.contacts

                if check.status != doc['_source']['status']:
                    doc['doc']['status'] = check.status
                    doc['doc']['timestamp'] = check.timestamp * 1000

                    # Add a log entry of this change (no ack / last_check)
                    self.logs.append(doc['doc'])

                    doc['doc']['ack'] = 0

                del doc['_source']
                del doc['_version']
                doc['doc']['last_check'] = check.timestamp * 1000
                doc['doc']['freshness'] = check.freshness * 1000

            else:
                doc['_source'] = {}
                doc['_op_type'] = 'create'

                if check.type == 'service':
                    doc['_parent'] = check.hostname

                for slot in check.fields:
                    if slot in ("timestamp", "freshness"):
                        doc['_source'][slot] = getattr(
                            check, slot, None) * 1000
                    else:
                        doc['_source'][slot] = getattr(check, slot, None)

            yield doc

    def _send_to_status(self):
        """
        Send batch_size checks to status index
        """
        for res in helpers.streaming_bulk(
            self.elasticclient,
            self.status_iterator(),
            chunk_size=self.batch_size,
        ):
            # Errors are already raised by bulk
            pass

        # Trigger logs update
        self._send_to_logs()

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
