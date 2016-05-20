# coding=utf-8


class Command(object):
    """
    Simple object to handle livestatus commands
    """

    __slots__ = ['function', 'action', 'doc_id', 'parent', 'type']

    def __init__(
        self, function, action, doc_id=None, host=None, service=None
    ):
        self.function = function
        self.action = action
        self.parent = None

        if doc_id:
            self.doc_id = doc_id
        elif service:
            self.doc_id = '-'.join([host, service])
            self.type = 'service'
            self.parent = host
        else:
            self.doc_id = host
            self.type = 'host'

    def execute(self, backends):
        """
        Execute command on backends
        """
        # Request backend
        for backend in backends:
            backend._command(self)
