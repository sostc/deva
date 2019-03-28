from glob import glob
import os

import time
import tornado.ioloop
from tornado import gen

from .core import Stream, convert_interval
from .pipe import *


def PeriodicCallback(callback, callback_time, asynchronous=False, **kwargs):
    source = Stream(asynchronous=asynchronous)

    def _():
        result = callback()
        source._emit(result)

    pc = tornado.ioloop.PeriodicCallback(_, callback_time, **kwargs)
    pc.start()
    return source


def sink_to_file(filename, upstream, mode='w', prefix='', suffix='\n', flush=False):
    file = open(filename, mode=mode)

    def write(text):
        file.write(prefix + text + suffix)
        if flush:
            file.flush()

    upstream.sink(write)
    return file


class Source(Stream):
    _graphviz_shape = 'doubleoctagon'


@Stream.register_api(staticmethod)
class from_textfile(Source):
    """ Stream data from a text file

    Parameters
    ----------
    f: file or string
    poll_interval: Number
        Interval to poll file for new data in seconds
    delimiter: str ("\n")
        Character(s) to use to split the data into parts
    start: bool (False)
        Whether to start running immediately; otherwise call stream.start()
        explicitly.

    Example
    -------
    >>> source = Stream.from_textfile('myfile.json')  # doctest: +SKIP
    >>> js.map(json.loads).pluck('value').sum().sink(print)  # doctest: +SKIP

    >>> source.start()  # doctest: +SKIP

    Returns
    -------
    Stream
    """
    def __init__(self, f, poll_interval=0.100, delimiter='\n', start=False,
                 **kwargs):
        if isinstance(f, str):
            f = open(f)
        self.file = f
        self.delimiter = delimiter

        self.poll_interval = poll_interval
        super(from_textfile, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def start(self):
        self.stopped = False
        self.loop.add_callback(self.do_poll)

    @gen.coroutine
    def do_poll(self):
        buffer = ''
        while True:
            line = self.file.read()
            if line:
                buffer = buffer + line
                if self.delimiter in buffer:
                    parts = buffer.split(self.delimiter)
                    buffer = parts.pop(-1)
                    for part in parts:
                        yield self._emit(part + self.delimiter)
            else:
                yield gen.sleep(self.poll_interval)
            if self.stopped:
                break


@Stream.register_api(staticmethod)
class filenames(Source):
    """ Stream over filenames in a directory

    Parameters
    ----------
    path: string
        Directory path or globstring over which to search for files
    poll_interval: Number
        Seconds between checking path
    start: bool (False)
        Whether to start running immediately; otherwise call stream.start()
        explicitly.

    Examples
    --------
    >>> source = Stream.filenames('path/to/dir')  # doctest: +SKIP
    >>> source = Stream.filenames('path/to/*.csv', poll_interval=0.500)  # doctest: +SKIP
    """
    def __init__(self, path, poll_interval=0.100, start=False, **kwargs):
        if '*' not in path:
            if os.path.isdir(path):
                if not path.endswith(os.path.sep):
                    path = path + '/'
                path = path + '*'
        self.path = path
        self.seen = set()
        self.poll_interval = poll_interval
        self.stopped = True
        super(filenames, self).__init__(ensure_io_loop=True)
        if start:
            self.start()

    def start(self):
        self.stopped = False
        self.loop.add_callback(self.do_poll)

    @gen.coroutine
    def do_poll(self):
        while True:
            filenames = set(glob(self.path))
            new = filenames - self.seen
            for fn in sorted(new):
                self.seen.add(fn)
                yield self._emit(fn)
            yield gen.sleep(self.poll_interval)  # TODO: remove poll if delayed
            if self.stopped:
                break


@Stream.register_api(staticmethod)
class from_tcp(Source):
    """
    Creates events by reading from a socket using tornado TCPServer

    The stream of incoming bytes is split on a given delimiter, and the parts
    become the emitted events.

    Parameters
    ----------
    port : int
        The port to open and listen on. It only gets opened when the source
        is started, and closed upon ``stop()``
    delimiter : bytes
        The incoming data will be split on this value. The resulting events
        will still have the delimiter at the end.
    start : bool
        Whether to immediately initiate the source. You probably want to
        set up downstream nodes first.
    server_kwargs : dict or None
        If given, additional arguments to pass to TCPServer

    Example
    -------

    >>> source = Source.from_tcp(4567)  # doctest: +SKIP
    """
    def __init__(self, port, delimiter=b'\n', start=False,
                 server_kwargs=None):
        super(from_tcp, self).__init__(ensure_io_loop=True)
        self.stopped = True
        self.server_kwargs = server_kwargs or {}
        self.port = port
        self.server = None
        self.delimiter = delimiter
        if start:  # pragma: no cover
            self.start()

    @gen.coroutine
    def _start_server(self):
        from tornado.tcpserver import TCPServer
        from tornado.iostream import StreamClosedError

        class EmitServer(TCPServer):
            source = self

            @gen.coroutine
            def handle_stream(self, stream, address):
                while True:
                    try:
                        data = yield stream.read_until(self.source.delimiter)
                        yield self.source._emit(data)
                    except StreamClosedError:
                        break

        self.server = EmitServer(**self.server_kwargs)
        self.server.listen(self.port)

    def start(self):
        if self.stopped:
            self.loop.add_callback(self._start_server)
            self.stopped = False

    def stop(self):
        if not self.stopped:
            self.server.stop()
            self.server = None
            self.stopped = True


@Stream.register_api(staticmethod)
class from_http_server(Source):
    """Listen for HTTP POSTs on given port

    Each connection will emit one event, containing the body data of
    the request

    Parameters
    ----------
    port : int
        The port to listen on
    path : str
        Specific path to listen on. Can be regex, but content is not used.
    start : bool
        Whether to immediately startup the server. Usually you want to connect
        downstream nodes first, and then call ``.start()``.
    server_kwargs : dict or None
        If given, set of further parameters to pass on to HTTPServer

    Example
    -------
    >>> source = Source.from_http_server(4567)  # doctest: +SKIP
    """

    def __init__(self, port, path='/.*', start=False, server_kwargs=None):
        self.port = port
        self.path = path
        self.server_kwargs = server_kwargs or {}
        super(from_http_server, self).__init__(ensure_io_loop=True)
        self.stopped = True
        self.server = None
        if start:  # pragma: no cover
            self.start()

    def _start_server(self):
        from tornado.web import Application, RequestHandler
        from tornado.httpserver import HTTPServer

        class Handler(RequestHandler):
            source = self

            @gen.coroutine
            def post(self):
                yield self.source._emit(self.request.body)
                self.write('OK')

        application = Application([
            (self.path, Handler),
        ])
        self.server = HTTPServer(application, **self.server_kwargs)
        self.server.listen(self.port)

    def start(self):
        """Start HTTP server and listen"""
        if self.stopped:
            self.loop.add_callback(self._start_server)
            self.stopped = False

    def stop(self):
        """Shutdown HTTP server"""
        if not self.stopped:
            self.server.stop()
            self.server = None
            self.stopped = True


@Stream.register_api(staticmethod)
class from_kafka(Source):
    """ Accepts messages from Kafka

    Uses the confluent-kafka library,
    https://docs.confluent.io/current/clients/confluent-kafka-python/


    Parameters
    ----------
    topics: list of str
        Labels of Kafka topics to consume from
    consumer_params: dict
        Settings to set up the stream, see
        https://docs.confluent.io/current/clients/confluent-kafka-python/#configuration
        https://github.com/edenhill/librdkafka/blob/master/CONFIGURATION.md
        Examples:
        bootstrap.servers: Connection string(s) (host:port) by which to reach Kafka
        group.id: Identity of the consumer. If multiple sources share the same
            group, each message will be passed to only one of them.
    poll_interval: number
        Seconds that elapse between polling Kafka for new messages
    start: bool (False)
        Whether to start polling upon instantiation

    Example
    -------

    >>> source = Stream.from_kafka(['mytopic'],
    ...           {'bootstrap.servers': 'localhost:9092',
    ...            'group.id': 'streamz'})  # doctest: +SKIP
    """
    def __init__(self, topics, consumer_params, poll_interval=0.1, start=False, **kwargs):
        self.cpars = consumer_params
        self.consumer = None
        self.topics = topics
        self.poll_interval = poll_interval
        super(from_kafka, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def do_poll(self):
        if self.consumer is not None:
            msg = self.consumer.poll(0)
            if msg and msg.value() and msg.error() is None:
                return msg.value()

    @gen.coroutine
    def poll_kafka(self):
        while True:
            val = self.do_poll()
            if val:
                yield self._emit(val)
            else:
                yield gen.sleep(self.poll_interval)
            if self.stopped:
                break
        self._close_consumer()

    def start(self):
        import confluent_kafka as ck
        if self.stopped:
            self.stopped = False
            self.consumer = ck.Consumer(self.cpars)
            self.consumer.subscribe(self.topics)
            tp = ck.TopicPartition(self.topics[0], 0, 0)

            # blocks for consumer thread to come up
            self.consumer.get_watermark_offsets(tp)
            self.loop.add_callback(self.poll_kafka)

    def _close_consumer(self):
        if self.consumer is not None:
            consumer = self.consumer
            self.consumer = None
            consumer.unsubscribe()
            consumer.close()
        self.stopped = True


class FromKafkaBatched(Stream):
    """Base class for both local and cluster-based batched kafka processing"""
    def __init__(self, topic, consumer_params, poll_interval='1s',
                 npartitions=1, **kwargs):
        self.consumer_params = consumer_params
        self.topic = topic
        self.npartitions = npartitions
        self.positions = [0] * npartitions
        self.poll_interval = convert_interval(poll_interval)
        self.stopped = True

        super(FromKafkaBatched, self).__init__(ensure_io_loop=True, **kwargs)

    @gen.coroutine
    def poll_kafka(self):
        import confluent_kafka as ck

        try:
            while not self.stopped:
                out = []
                for partition in range(self.npartitions):
                    tp = ck.TopicPartition(self.topic, partition, 0)
                    try:
                        low, high = self.consumer.get_watermark_offsets(
                            tp, timeout=0.1)
                    except (RuntimeError, ck.KafkaException):
                        continue
                    current_position = self.positions[partition]
                    lowest = max(current_position, low)
                    if high > lowest:
                        out.append((self.consumer_params, self.topic, partition,
                                    lowest, high - 1))
                        self.positions[partition] = high

                for part in out:
                    yield self._emit(part)

                else:
                    yield gen.sleep(self.poll_interval)
        finally:
            self.consumer.unsubscribe()
            self.consumer.close()

    def start(self):
        import confluent_kafka as ck
        if self.stopped:
            self.consumer = ck.Consumer(self.consumer_params)
            self.stopped = False
            tp = ck.TopicPartition(self.topic, 0, 0)

            # blocks for consumer thread to come up
            self.consumer.get_watermark_offsets(tp)
            self.loop.add_callback(self.poll_kafka)


@Stream.register_api(staticmethod)
def from_kafka_batched(topic, consumer_params, poll_interval='1s',
                       npartitions=1, start=False, dask=False, **kwargs):
    """ Get messages from Kafka in batches

    Uses the confluent-kafka library,
    https://docs.confluent.io/current/clients/confluent-kafka-python/

    This source will emit lists of messages for each partition of a single given
    topic per time interval, if there is new data. If using dask, one future
    will be produced per partition per time-step, if there is data.

    Parameters
    ----------
    topic: str
        Kafka topic to consume from
    consumer_params: dict
        Settings to set up the stream, see
        https://docs.confluent.io/current/clients/confluent-kafka-python/#configuration
        https://github.com/edenhill/librdkafka/blob/master/CONFIGURATION.md
        Examples:
        bootstrap.servers: Connection string(s) (host:port) by which to reach Kafka
        group.id: Identity of the consumer. If multiple sources share the same
            group, each message will be passed to only one of them.
    poll_interval: number
        Seconds that elapse between polling Kafka for new messages
    npartitions: int
        Number of partitions in the topic
    start: bool (False)
        Whether to start polling upon instantiation

    Example
    -------

    >>> source = Stream.from_kafka_batched('mytopic',
    ...           {'bootstrap.servers': 'localhost:9092',
    ...            'group.id': 'streamz'}, npartitions=4)  # doctest: +SKIP
    """
    if dask:
        from distributed.client import default_client
        kwargs['loop'] = default_client().loop
    source = FromKafkaBatched(topic, consumer_params,
                              poll_interval=poll_interval,
                              npartitions=npartitions, **kwargs)
    if dask:
        source = source.scatter()

    if start:
        source.start()

    return source.starmap(get_message_batch)


def get_message_batch(kafka_params, topic, partition, low, high, timeout=None):
    """Fetch a batch of kafka messages in given topic/partition

    This will block until messages are available, or timeout is reached.
    """
    import confluent_kafka as ck
    t0 = time.time()
    consumer = ck.Consumer(kafka_params)
    tp = ck.TopicPartition(topic, partition, low)
    consumer.assign([tp])
    out = []
    try:
        while True:
            msg = consumer.poll(0)
            if msg and msg.value() and msg.error() is None:
                if high >= msg.offset():
                    out.append(msg.value())
                if high <= msg.offset():
                    break
            else:
                time.sleep(0.1)
                if timeout is not None and time.time() - t0 > timeout:
                    break
    finally:
        consumer.close()
    return out

@Stream.register_api(staticmethod)
class engine(Source):
    """
    ::func:: func to gen data
    ::interval:: func to run interval time
    ::asyncflag:: func execute in threadpool
    ::threadcount:: if asyncflag ,this is threadpool count
    """

    def __init__(self,
                 interval=1,
                 cache_max_len=1,
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
class from_redis(Source):

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
                    msg_body = (msg_body.values() >> head(1) >> to_list)[
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

def dumps(body):
    if not isinstance(body,bytes):
        try:
            import json
            body = json.dumps(body)
        except:
            import dill
            body = dill.dumps(body)
    return body
    
    
def loads(body):
    try:
        import json
        body = json.loads(body)
    except TypeError:
        import dill
        body = dill.loads(body)
    except ValueError:
        try:
            body = body.decode('utf-8')
        except:
            import dill
            body = dill.loads(body)
    
    return body



@Stream.register_api(staticmethod)
class from_http_request(Source):
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
        from tornado.web import Application, RequestHandler
        from tornado.httpserver import HTTPServer
        class HTTPStreamHandler(RequestHandler):
            output = self
            def post(self, *args, **kwargs):
                self.request.body = loads(self.request.body)   
                self.request >> HTTPStreamHandler.output
                self.write(str({'status': 'ok', 'ip': self.request.remote_ip}))   
        
        app = Application([(r'/', HTTPStreamHandler)])
        self.http_server = HTTPServer(app)  # ,xheaders=True
        self.http_server.bind(self.port)
        self.http_server.start()

    def stop(self):
        if self.http_server is not None:
            self.http_server.stop()
            self.stopped = True


@Stream.register_api(staticmethod)
class from_web_stream(Source):
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



@Stream.register_api(staticmethod)
class from_command(Source):
    """ receive command eval result data from subprocess,emit  data into stream"""

    def __init__(self, poll_interval=0.1):
        self.poll_interval = poll_interval
        super(from_command, self).__init__(ensure_io_loop=True)
        self.stopped = True
        from concurrent.futures import ThreadPoolExecutor
        self.thread_pool = ThreadPoolExecutor(2)

    @gen.coroutine
    def poll_out(self):
        for out in self.subp.stdout:
            out = out.decode('utf-8').strip()
            if out:
                self._emit(out)

    @gen.coroutine
    def poll_err(self):
        for err in self.subp.stderr:
            err = err.decode('utf-8').strip()
            if err:
                self._emit(err)

    def run(self,command):
        self.subp = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,bufsize=1,stdin=subprocess.PIPE)
        self.thread_pool.submit(self.poll_err)
        self.thread_pool.submit(self.poll_out)
