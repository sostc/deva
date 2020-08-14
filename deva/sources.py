import subprocess
import json
from tornado.web import RequestHandler, Application
from tornado.httpserver import HTTPServer
from tornado import gen
from tornado.tcpserver import TCPServer
from tornado.tcpclient import TCPClient
from tornado.iostream import StreamClosedError
import dill
from glob import glob
import os
import tornado.ioloop

from .topic import RedisStream
from .core import Stream

import logging


logger = logging.getLogger(__name__)


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

    def __init__(self, **kwargs):
        self.stopped = True
        super(Source, self).__init__(**kwargs)

    def stop(self):  # pragma: no cover
        # fallback stop method - for poll functions with while not self.stopped
        if not self.stopped:
            self.stopped = True


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
    >>> source = Stream.filenames('path/to/*.csv', poll_interval=0.500)
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
class from_tcp_port(Source):
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

    >>> source = Source.from_tcp_port(4567)  # doctest: +SKIP
    """

    def __init__(self, port, delimiter=b'\n', start=False,
                 server_kwargs=None):
        super(from_tcp_port, self).__init__(ensure_io_loop=True)
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
class from_command(Stream):
    """Messages from a running external process.

    This doesn't work on Windows

    Parameters
    ----------
    cmd : list of str or str
        Command to run: program name, followed by arguments
    open_kwargs : dict
        To pass on the the process open function, see ``subprocess.Popen``.
    with_stderr : bool
        Whether to include the process STDERR in the stream
    start : bool
        Whether to immediately startup the process. Usually you want to connect
        downstream nodes first, and then call ``.start()``.

    Example
    -------
    >>> source = Source.from_process(['ping localhost'])  # doctest: +SKIP

    """

    def __init__(self, interval=0.1, command=None, **kwargs):
        self.interval = interval
        super(from_command, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        from concurrent.futures import ThreadPoolExecutor
        self.thread_pool = ThreadPoolExecutor(2)
        self.command = command
        if self.command:
            self.run(self.command)

    def poll_out(self):
        for out in self.subp.stdout:
            out = out.decode('utf-8').strip()
            if out:
                self._emit(out)

    def poll_err(self):
        for err in self.subp.stderr:
            err = err.decode('utf-8').strip()
            if err:
                self._emit(err)

    def emit(self, command, asynchronous=False):
        self.subp = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=1,
            stdin=subprocess.PIPE)
        self.thread_pool.submit(self.poll_err)
        self.thread_pool.submit(self.poll_out)
        # self.loop.add_callback(self.poll_err)
        # self.loop.add_callback(self.poll_out)


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


@Stream.register_api(staticmethod)
class from_redis(Stream):
    def __init__(self, topic, group=None, max_len=100, **kwargs):
        Stream.__init__(self, ensure_io_loop=True)
        self.source = RedisStream(topic=topic, group=group, max_len=max_len)
        self.source >> self


@Stream.register_api(staticmethod)
class from_http_request(Stream):
    """Receive data from http request,emit httprequest data to stream."""

    def __init__(self, port, path='/.*', start=False, server_kwargs=None):
        self.port = port
        self.path = path
        self.server_kwargs = server_kwargs or {}
        super(from_http_request, self).__init__(ensure_io_loop=True)
        self.stopped = True
        self.server = None
        if start:  # pragma: no cover
            self.start()

    def _start_server(self):
        class Handler(RequestHandler):
            def _loads(self, body):
                """解析从web端口提交过来的数据.

                可能的数据有字符串和二进制,
                字符串可能是直接字符串,也可能是json编码后的字符串
                二进制可能是图像等直接可用的二进制,也可能是dill编码的二进制pyobject
                """
                try:
                    body = json.loads(body)
                except TypeError:
                    body = dill.loads(body)
                except ValueError:
                    body = body.decode('utf-8')
                finally:
                    return body

            source = self

            @gen.coroutine
            def post(self):
                self.request.body = self._loads(self.request.body)
                yield self.source._emit(self.request.body)
                self.write('OK')

        application = Application([
            (self.path, Handler),
        ])
        self.server = HTTPServer(application, **self.server_kwargs)
        self.server.listen(self.port)

    def start(self):
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self._start_server)

    def stop(self):
        """Shutdown HTTP server."""
        if not self.stopped:
            self.server.stop()
            self.server = None
            self.stopped = True


class StreamTCPServer(TCPServer):
    """
    server.in_s
    server.out_s
    """

    def __init__(self, port=2345, **kwargs):
        self.delimiter = 'zjw-split-0358'.encode('utf-8')
        self.out_s = Stream()
        self.in_s = Stream()
        super(StreamTCPServer, self).__init__(**kwargs)
        self.handlers = dict()
        self.listen(port)

    def __rrshift__(self, x):
        x >> self.out_s

    @gen.coroutine
    def handle_stream(self, stream, address):
        def _write(x):
            try:
                stream.write(x)
                stream.write(self.delimiter)
            except StreamClosedError:
                logger.exception('%s connect close' % str(address))
                self.handlers.get(address).destroy()
                del self.handlers[address]

        self.handlers[address] = self.out_s.map(dill.dumps).sink(_write)
        while True:
            try:
                data = yield stream.read_until(self.delimiter)
                yield self.in_s._emit(dill.loads(data))
            except StreamClosedError:
                logger.exception('%s connect close' % str(address))
                break

    def stop(self):
        self.out_s.emit('exit')
        for handler in self.handlers:
            self.handlers[handler].destroy()
        self.handlers = {}
        super().stop()


class StreamTCPClient():
    """从tcp端口订阅数据
    client.in_s
    client.out_s

    """

    def __init__(self, host='127.0.0.1', port=2345, **kwargs):
        super(StreamTCPClient, self).__init__(**kwargs)
        self.host = host
        self.port = port
        self.delimiter = 'zjw-split-0358'.encode('utf-8')
        self.out_s = Stream()
        self.in_s = Stream(ensure_io_loop=True)
        self._stream = None
        self.in_s.filter(lambda x: x == 'exit').sink(lambda x: self.stop())
        self.start()

    def __rrshift__(self, x):
        x >> self.out_s

    @gen.coroutine
    def start(self):
        try:
            self._stream = yield TCPClient().connect(self.host, self.port)
        except Exception as e:
            logger.exception(e, 'connect', self.host, self.port, 'error')

        def _write(x):
            try:
                self._stream.write(x)
                self._stream.write(self.delimiter)
            except StreamClosedError:
                logger.exception(f'{self.host}:{self.port} connect close')
                self.out_handler.destroy()

        self.out_handler = self.out_s.map(dill.dumps).sink(_write)
#         try:
        while self._stream:
            data = yield self._stream.read_until(self.delimiter)
            yield self.in_s.emit(dill.loads(data))
#         except iostream.StreamClosedError:
#             logger.exception('tornado.iostream.StreamClosedError')

    def stop(self):
        if not self._stream.closed() and self._stream.close():
            self.stopped = True


def gen_block_test() -> int:
    import time
    import datetime
    time.sleep(6)
    return datetime.datetime.now().second
