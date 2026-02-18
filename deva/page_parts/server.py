import os
from collections import defaultdict

import tornado.web
from sockjs.tornado import SockJSRouter

from .connections import StreamsConnection


class PageServer(object):
    def __init__(self, name="default", host="127.0.0.1", port=9999, start=False, **kwargs):
        self.name = name
        self.port = port
        self.host = host
        self.streams = defaultdict(list)
        self.StreamRouter = SockJSRouter(StreamsConnection, r"")
        self.application = tornado.web.Application(self.StreamRouter.urls, **kwargs)
        if start:
            self.start()

    def add_page(self, page):
        self.application.add_handlers(".*$", page.get_routes())

    def start(self):
        self.server = self.application.listen(self.port)
        os.system(f"open http://{self.host}:{self.port}/")

    def stop(self):
        self.server.stop()
