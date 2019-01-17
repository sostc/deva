import json
import time
from tornado import gen

from streamz.core import Stream as Streamz
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornadose.handlers import EventSource
from tornadose.stores import DataStore
from tornado.httpserver import HTTPServer

from tornado.web import Application, RequestHandler
from .pipe import *


class StreamData(object):
    """流数据 数据机构，数据自身的信息"""

    def __init__(self, source_id=None, source_name=None,
                 content_type=None, headers=None,
                 data=None, use_gzip=None):

        # Note that some of these attributes go through property setters
        # defined below.
        """
        :source_id source_name :描述数据来源
        :content_type:object|json|dataframe|dict|list，描述数据类型
        :headers:其他扩展描述字符
        :use_zip:数据是否压缩
        :data:数据本身
        """
        if content_type:
            self.content_type = content_type
        else:
            self.content_type = data.__class__.__name__
        self.headers = headers
        self.source_id = source_id
        self.source_name = source_name
        self.data = data
        self.create_time = time.time()

    def __repr__(self):
        return '<%s|%s|%s|%s>' % (self.source_id, self.source_name, self.content_type, self.data)


class Stream(Streamz):
    _graphviz_shape = "doubleoctagon"

    def __ror__(self, value):  # |
        """emit value to stream ,end,return emit result"""
        self.emit(value)
        return value

    def __rrshift__(self, value):  # >>
        """emit value to stream ,end,return emit result"""
        self.emit(value)
        return value

    def write(self, value):  # |
        """emit value to stream ,end,return emit result"""
        self.emit(value)

    def send(self, value):  # |
        """emit value to stream ,end,return emit result"""
        self.emit(value)

    def to_redis_stream(self, topic, db=None):
        """
        push stream to redis stream

        ::topic:: redis stream topic
        ::db:: walrus redis databse object ,default :from walrus import Database,db=Database()
        """
        import dill
        if not db:
            import walrus
            self.db = walrus.Database()
        producer = self.db.Stream(topic)
        self.map(lambda x: {"data": dill.dumps(x)}).sink(
            producer.add)  # producer only accept non-empty dict dict
        return producer

    def to_web_stream(self, port=9999):
        store = DataStore()

        app = Application(
            [(r'/', EventSource, {'store': store})],
            debug=True)

        http_server = HTTPServer(app, xheaders=True)
        # 最原始的方式
        http_server.bind(port)
        # http_server.start(1)
        self.map(lambda x: {"data": x}).map(json.dumps).sink(store.submit)
        return http_server


class JsonStream(Stream):
    pass


@Stream.register_api(staticmethod)
class engine(Stream):
    """
    ::func:: func to gen data
    ::interval:: func to run interval time
    ::asyncflag:: func execute in threadpool
    ::threadcount:: if asyncflag ,this is threadpool count
    """

    def __init__(self,
                 interval=1,
                 start=False,
                 func=None,
                 asyncflag=False,
                 threadcount=5,
                 **kwargs):

        self.interval = interval
        if func == None:
            import moment

            def func(): return moment.now().seconds
        self.func = func
        self.asyncflag = asyncflag
        if self.asyncflag:
            from concurrent.futures import ThreadPoolExecutor
            self.thread_pool = ThreadPoolExecutor(threadcount)

        super(engine, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def do_gen(self):
        msg = self._emit(self.func())
        if msg:
            return msg

    @gen.coroutine
    def push_downstream(self):
        while True:
            if self.asyncflag:
                val = self.thread_pool.submit(self.do_gen)
            else:
                val = self.do_gen()
            yield gen.sleep(self.interval)
            if self.stopped:
                break

    def start(self):
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.push_downstream)

    def stop(self):
        self.stopped = True


class RedisMsg(object):
    def __init__(self, topic, msg_id, msg_body):
        import dill

        self.topic = topic
        self.msg_id = msg_id
        try:
            self.msg_body = dill.loads(msg_body)
        except:
            self.msg_body = msg_body

    def __repr__(self,):
        return '<%s %s>' % (self.topic, self.msg_body)


@Stream.register_api(staticmethod)
class from_redis(Stream):

    def __init__(self, topics, poll_interval=0.1, start=False, group="test",
                 **kwargs):

        from walrus import Database
        self.consumer = None
        self.topics = topics
        self.group = group
        self.poll_interval = poll_interval
        self.db = Database()
        self.consumer = self.db.consumer_group(self.group, self.topics)
        self.consumer.create()  # Create the consumer group.
        self.consumer.set_id('$')  # 不会从头读

        super(from_redis, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def do_poll(self):
        if self.consumer is not None:
            meta_msgs = self.consumer.read(count=1)

            # Returns:
            [('stream-a', [(b'1539023088125-0', {b'message': b'new a'})]),
             ('stream-b', [(b'1539023088125-0', {b'message': b'new for b'})]),
             ('stream-c', [(b'1539023088126-0', {b'message': b'c-0'})])]

            if meta_msgs:
                meta_msgs >> debug
                l = []
                for meta_msg in meta_msgs:
                    topic, msg = meta_msg[0], meta_msg[1][0]
                    msg_id, msg_body = msg
                    msg_body = (msg_body.values() >> take(1) >> to_list)[
                        0]  # {'data':'dills'}
                    l.append(RedisMsg(topic, msg_id, msg_body))
                return l
            else:
                return None

    @gen.coroutine
    def poll_redis(self):
        while True:
            vals = self.do_poll()
            if vals:
                for val in vals:
                    self._emit(val)

            yield gen.sleep(self.poll_interval)
            if self.stopped:
                break

    def start(self):
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.poll_redis)

    def stop(self):
        if self.consumer is not None:
            self.consumer.destroy()
            self.consumer = None
            self.stopped = True


class HTTPStreamHandler(RequestHandler):
    output = None

    def post(self, *args, **kwargs):
        self.request >> HTTPStreamHandler.output
        self.write(str({'status': 'ok', 'ip': self.request.remote_ip}))


@Stream.register_api(staticmethod)
class from_http_request(Stream):
    """ receive data from http request,emit httprequest data to stream"""

    def __init__(self, port=9999, start=False, httpcount=3):
        self.port = port
        self.httpcount = httpcount
        self.http_server = None
        super(from_http_request, self).__init__(ensure_io_loop=True)
        self.stopped = True
        if start:
            self.start()

    def start(self):
        if self.stopped:
            self.stopped = False
            HTTPStreamHandler.output = self
            app = Application([(r'/', HTTPStreamHandler)])
            self.http_server = HTTPServer(app)  # ,xheaders=True
            self.http_server.bind(self.port)
            self.http_server.start()

    def stop(self):
        if self.http_server is not None:
            self.http_server.stop()
            self.stopped = True


@Stream.register_api(staticmethod)
class from_web_stream(Stream):
    def __init__(self, url='http://127.0.0.1:9999', read_timeout=60*60*24, start=True,
                 **kwargs):
        self.url = url
        self.request_timeout = read_timeout
        self.http_client = AsyncHTTPClient()
        super(from_web_stream, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    @gen.coroutine
    def get(self):
        # if self.read_timeout is None:
            # HTTPRequest._DEFAULTS['request_timeout']=None
            # defaultset none  is 20s,hack源代码也无法解决的，这部分代码不管用
        requests = HTTPRequest(
            url=self.url, streaming_callback=self.on_chunk, request_timeout=self.request_timeout)
        yield self.http_client.fetch(requests)

    @gen.coroutine
    def on_chunk(self, chunk):
        chunk >> self

    def start(self):
        if self.stopped:
            self.stopped = False
        if self.http_client is None:
            self.http_client = AsyncHTTPClient()
        self.get()

    def stop(self):
        if self.http_client is not None:
            self.http_client.close()  # this  not imple
            self.http_client = None
            self.stopped = True


import subprocess


@Stream.register_api(staticmethod)
class from_command(Stream):
    """ receive command eval result data from subprocess,emit  data into stream"""

    def __init__(self, command, start=True, poll_interval=0.1):
        self.command = command
        self.poll_interval = poll_interval
        super(from_command, self).__init__(ensure_io_loop=True)
        self.stopped = True
        from concurrent.futures import ThreadPoolExecutor
        self.thread_pool = ThreadPoolExecutor(2)
        
        if start:
            self.start()


    @gen.coroutine
    def poll_out(self):
        for out in self.subp.stdout:
            out = out.decode('utf-8')
            if out:
                self._emit(out)

    @gen.coroutine
    def poll_err(self):
        for err in self.subp.stderr:
            err = err.decode('utf-8')
            if err:
                self._emit(err)
            
       

    def start(self):
        if self.stopped:
            self.stopped = False
            self.subp = subprocess.Popen(
                self.command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,bufsize=1)
            
            self.thread_pool.submit(self.poll_err)
            self.thread_pool.submit(self.poll_out)
                

    def stop(self):
        self.stoped = True


class NamedStream(Stream):
    """A named generic notification emitter."""

    def __init__(self, name):
        Stream.__init__(self,)

        #: The name of this stream.
        self.name = name

    def __repr__(self):
        base = Stream.__repr__(self)
        return "%s; %r>" % (base[:-1], self.name)


class Namespace(dict):
    """A mapping of signal names to signals."""

    def stream(self, name, doc=None):
        """Return the :class:`NamedSignal` *name*, creating it if required.
        Repeated calls to this function will return the same signal object.
        """
        try:
            return self[name]
        except KeyError:
            return self.setdefault(name, NamedStream(name))


namedstream = Namespace().stream

debug = namedstream('debug')
warn = namedstream('warn')
error = namedstream('error')


def write_to_file(fn):
    def write(x):
        with open(fn, 'a+') as f:
            f.write(x >> to_str)
        return x
    return write


def gen_quant():
    import pandas as pd
    import easyquotation
    quotation_engine = easyquotation.use("sina")
    q1 = quotation_engine.all
    df = pd.DataFrame(q1).T
    return df


def gen_test():
    import moment as mm
    return mm.now().seconds


def gen_block_test():
    import moment as mm
    import time
    time.sleep(6)
    return mm.now().seconds
