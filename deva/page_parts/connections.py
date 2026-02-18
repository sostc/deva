import datetime
import json

from pymaybe import maybe
from sockjs.tornado import SockJSConnection
from tornado import gen

from deva.bus import log
from deva.core import Stream


class StreamsConnection(SockJSConnection):
    def __init__(self, *args, **kwargs):
        self._out_stream = Stream()
        self.link1 = self._out_stream.sink(self.send)
        self._in_stream = Stream()
        self.link2 = self._in_stream.sink(self.process_msg)
        super(StreamsConnection, self).__init__(*args, **kwargs)

    def on_open(self, request):
        self.out_stream = Stream()
        self.connection = self.out_stream >> self._out_stream
        json.dumps({"id": "default", "html": "welcome"}) >> self.out_stream
        self.request = request
        self.request.ip = maybe(self.request.headers)["x-forward-for"].or_else(self.request.ip)
        f"open:{self.request.ip}:{datetime.datetime.now()}" >> log

    @gen.coroutine
    def on_message(self, msg):
        json.loads(msg) >> self._in_stream

    def process_msg(self, msg):
        stream_ids = msg["stream_ids"]
        "view:%s:%s:%s" % (stream_ids, self.request.ip, datetime.datetime.now()) >> log

        self.out_streams = [stream for stream in Stream.instances() if str(hash(stream)) in stream_ids]

        def _(sid):
            return lambda x: json.dumps({"id": sid, "html": x})

        self.connections = set()
        for s in self.out_streams:
            sid = str(hash(s))
            f = _(sid)
            self.connections.add(s.map(repr).map(f) >> self._out_stream)
            html = maybe(s).recent(1)[0].or_else("流内暂无数据")
            json.dumps({"id": sid, "html": html}) >> self._out_stream

    def on_close(self):
        f"close:{self.request.ip}:{datetime.datetime.now()}" >> log
        for connection in self.connections:
            connection.destroy()
        self.connections = set()
        self.connection.destroy()
        self.link1.destroy()
        self.link2.destroy()
        self.out_stream.destroy()
