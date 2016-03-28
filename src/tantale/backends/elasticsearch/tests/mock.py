# coding=utf-8

from __future__ import print_function

import os
import json
import time


class Elasticsearch(object):
    """
    Mock object for Elasticsearch
    Trace multiprocessing calls into file
    """
    el_responses = None

    result_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '.mock_calls')

    def __init__(self, *args, **kwargs):
        pass

    def write_call(self, method, kwargs):
        with open(self.result_file, 'a') as f:
            f.write(
                json.dumps(
                    {"method": method, "kwargs": kwargs},
                    sort_keys=True))
            f.write("\n")
            f.flush()

    def bulk(self, **kwargs):
        self.write_call('bulk', kwargs)

        nb_requests = int((kwargs['body'].count('\n') + 1) / 2)

        # Forge return value / timestamp strictly > now
        timestamp = int(time.time()) * 1000 + 1
        item = {'update': {'get': {'fields': {'timestamp': [timestamp]}}}}
        return {
            'errors': False,
            'items': [item for i in range(nb_requests)]}

    def get_response(self):
        return json.loads(self.el_responses.pop())

    def search(self, **kwargs):
        self.write_call('msearch', kwargs)
        return self.get_response()

    def msearch(self, **kwargs):
        self.write_call('msearch', kwargs)
        return self.get_response()

    def update(self, **kwargs):
        self.write_call('update', kwargs)
        return self.get_response()

    @classmethod
    def get_calls(cls):
        res = []
        try:
            with open(cls.result_file, 'r') as f:
                for line in f.readlines():
                    res.append(json.loads(line))
        except:
            pass

        if os.path.isfile(cls.result_file):
            os.unlink(cls.result_file)

        return res
