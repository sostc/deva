import subprocess
import json
from tornado.web import RequestHandler, Application
# from tornado.httpserver import HTTPServer
from tornado import gen
from tornado.tcpserver import TCPServer
from tornado.tcpclient import TCPClient
from tornado.iostream import StreamClosedError
import dill
from glob import glob
import os
import tornado.ioloop

from .core import Stream

import logging
import asyncio


import aioredis
import time

logger = logging.getLogger(__name__)

"""
Source 类的辅助函数和工具类

主要功能:
1. PeriodicCallback - 创建定期回调的流
2. Source - 基础数据源类
3. from_textfile - 从文本文件创建流

主要用法:
1. 定期回调:
    # 每5秒执行一次回调
    source = PeriodicCallback(callback_fn, 5000)

2. 文本文件流:
    # 从文件创建流
    source = Stream.from_textfile('data.txt')
    source.start()

参数说明:
    callback: 回调函数
    callback_time: 回调间隔(毫秒)
    asynchronous: 是否异步执行
"""

def PeriodicCallback(callback, callback_time, asynchronous=False, **kwargs):
    """创建定期回调的流

    Args:
        callback: 要定期执行的回调函数
        callback_time: 回调时间间隔(毫秒)
        asynchronous: 是否异步执行,默认False
        **kwargs: 其他参数

    Returns:
        Stream: 返回流对象
    """
    source = Stream(asynchronous=asynchronous)

    def _():
        result = callback()
        source._emit(result)

    pc = tornado.ioloop.PeriodicCallback(_, callback_time, **kwargs)
    pc.start()
    return source


class Source(Stream):
    """基础数据源类
    
    继承自Stream类,提供数据源的基本功能。
    用于创建各种数据源的基类。

    Attributes:
        _graphviz_shape: 图形化显示的形状
        stopped: 是否停止标志
    """
    _graphviz_shape = 'doubleoctagon'

    def __init__(self, **kwargs):
        """初始化数据源

        Args:
            **kwargs: 传递给父类的参数
        """
        self.stopped = True
        super(Source, self).__init__(**kwargs)

    def stop(self):  # pragma: no cover
        """停止数据源
        
        用于停止轮询等循环操作的后备方法
        """
        if not self.stopped:
            self.stopped = True


@Stream.register_api(staticmethod)
class from_textfile(Source):
    """从文本文件创建数据流

    从文本文件中读取数据并生成流。支持按指定分隔符分割数据,并可以定期轮询文件获取新内容。

    参数
    ----------
    f: file或string
        要读取的文件对象或文件路径
    poll_interval: Number
        轮询文件的时间间隔(秒),默认0.1秒
    delimiter: str ("\n")
        用于分割数据的分隔符,默认为换行符
    start: bool (False)
        是否立即启动;否则需要显式调用stream.start()启动

    示例
    -------
    >>> source = Stream.from_textfile('myfile.json')  # doctest: +SKIP
    >>> js.map(json.loads).pluck('value').sum().sink(print)  # doctest: +SKIP
    >>> source.start()  # doctest: +SKIP

    返回
    -------
    Stream对象
    """

    def __init__(self, f, poll_interval=0.100, delimiter='\n', start=False,
                 **kwargs):
        """初始化文本文件流

        Args:
            f: 文件对象或路径
            poll_interval: 轮询间隔,默认0.1秒
            delimiter: 分隔符,默认换行符
            start: 是否自动启动
            **kwargs: 其他参数
        """
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
        """启动文件流处理"""
        self.stopped = False
        self.loop.add_callback(self.do_poll)

    @gen.coroutine
    def do_poll(self):
        """轮询文件并处理数据

        按分隔符分割数据并发送到流中
        """
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
    """监控目录中的文件名流

    监控指定目录,当有新文件出现时将文件名发送到流中。

    参数
    ----------
    path: string
        要监控的目录路径或glob匹配模式
    poll_interval: Number
        检查目录的时间间隔(秒)
    start: bool (False)
        是否立即启动,否则需要手动调用stream.start()启动

    示例
    --------
    >>> source = Stream.filenames('path/to/dir')  # doctest: +SKIP
    >>> source = Stream.filenames('path/to/*.csv', poll_interval=0.500)
    """

    def __init__(self, path, poll_interval=0.100, start=False, **kwargs):
        """初始化文件名流

        Args:
            path: 监控的目录路径
            poll_interval: 轮询间隔,默认0.1秒
            start: 是否自动启动
            **kwargs: 其他参数
        """
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
        """启动文件监控"""
        self.stopped = False
        self.loop.add_callback(self.do_poll)

    @gen.coroutine
    def do_poll(self):
        """轮询目录并处理新文件

        检查目录中的新文件,将文件名发送到流中
        """
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
    """从TCP端口创建事件流

    使用tornado TCPServer从socket读取数据。
    传入的字节流会根据指定的分隔符进行分割,分割后的部分作为事件发送。

    参数
    ----------
    port : int
        要监听的端口号。只有在source启动时才会打开,stop()时关闭。
    delimiter : bytes
        用于分割传入数据的分隔符。分割后的事件末尾仍会保留分隔符。
    start : bool
        是否立即启动source。建议先设置好下游节点再启动。
    server_kwargs : dict or None
        如果提供,会作为额外参数传递给TCPServer。

    示例
    -------
    >>> source = Source.from_tcp_port(4567)  # doctest: +SKIP
    """

    def __init__(self, port, delimiter=b'\n', start=False,
                 server_kwargs=None):
        """初始化TCP端口source

        Args:
            port: 监听的端口号
            delimiter: 数据分隔符,默认换行符
            start: 是否自动启动
            server_kwargs: TCPServer的额外参数
        """
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
        """启动TCP服务器

        创建一个EmitServer实例来处理TCP连接和数据读取
        """
        from tornado.tcpserver import TCPServer
        from tornado.iostream import StreamClosedError

        class EmitServer(TCPServer):
            source = self

            @gen.coroutine
            def handle_stream(self, stream, address):
                """处理TCP流

                持续从流中读取数据,按分隔符分割后发送事件
                """
                while True:
                    try:
                        data = yield stream.read_until(self.source.delimiter)
                        yield self.source._emit(data)
                    except StreamClosedError:
                        break

        self.server = EmitServer(**self.server_kwargs)
        self.server.listen(self.port)

    def start(self):
        """启动source"""
        if self.stopped:
            self.loop.add_callback(self._start_server)
            self.stopped = False

    def stop(self):
        """停止source"""
        if not self.stopped:
            self.server.stop()
            self.server = None
            self.stopped = True


@Stream.register_api(staticmethod)
class from_http_server(Source):
    """HTTP服务器数据源

    监听指定端口的HTTP POST请求,每个连接将发出一个包含请求体数据的事件。

    参数
    ----------
    port : int
        监听的端口号
    path : str
        监听的具体路径。可以是正则表达式,但内容不会被使用。
    start : bool
        是否立即启动服务器。通常需要先连接下游节点,然后调用.start()。
    server_kwargs : dict or None
        如果提供,将传递给HTTPServer的额外参数字典

    示例
    -------
    >>> source = Source.from_http_server(4567)  # doctest: +SKIP
    """

    def __init__(self, port, path='/.*', start=False, server_kwargs=None):
        """初始化HTTP服务器数据源

        Args:
            port: 监听的端口号
            path: 监听的路径,默认为'/.*'
            start: 是否立即启动,默认False
            server_kwargs: 传递给HTTPServer的参数
        """
        self.port = port
        self.path = path
        self.server_kwargs = server_kwargs or {}
        super(from_http_server, self).__init__(ensure_io_loop=True)
        self.stopped = True
        self.server = None
        if start:  # pragma: no cover
            self.start()

    def _start_server(self):
        """启动HTTP服务器

        创建一个Application和Handler来处理HTTP请求
        """
        from tornado.web import Application, RequestHandler
        from tornado.httpserver import HTTPServer

        class Handler(RequestHandler):
            source = self

            @gen.coroutine
            def post(self):
                """处理POST请求,发出请求体数据"""
                yield self.source._emit(self.request.body)
                self.write('OK')

            @gen.coroutine 
            def get(self):
                """处理GET请求,发出查询参数"""
                response = self.get_arguments("question")
                yield self.source._emit(response)
                self.write('OK')

        application = Application([
            (self.path, Handler),
        ])
        self.server = HTTPServer(application, **self.server_kwargs)
        self.server.listen(self.port)

    def start(self):
        """启动HTTP服务器并开始监听"""
        if self.stopped:
            self.loop.add_callback(self._start_server)
            self.stopped = False

    def stop(self):
        """关闭HTTP服务器"""
        if not self.stopped:
            self.server.stop()
            self.server = None
            self.stopped = True


@Stream.register_api(staticmethod)
class from_command(Stream):
    """从外部命令创建数据流

    通过执行外部命令并监听其输出来创建数据流。
    注意:此功能在Windows上不可用。

    参数
    ----------
    cmd : list of str or str
        要执行的命令:程序名称,后跟参数
    open_kwargs : dict
        传递给进程打开函数的参数,参见 ``subprocess.Popen``
    with_stderr : bool
        是否在流中包含进程的标准错误输出
    start : bool
        是否立即启动进程。通常需要先连接下游节点,然后调用 ``.start()``。

    示例
    -------
    >>> source = Source.from_command('ping localhost')  # doctest: +SKIP
    """

    def __init__(self, interval=0.1, command=None, **kwargs):
        """初始化命令流

        Args:
            interval: 轮询间隔时间,默认0.1秒
            command: 要执行的命令字符串
            **kwargs: 传递给Stream基类的其他参数
        """
        self.interval = interval
        super(from_command, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        from concurrent.futures import ThreadPoolExecutor
        self.thread_pool = ThreadPoolExecutor(2)
        self.command = command
        if self.command:
            self.emit(self.command)

    def poll_out(self):
        """轮询并发送标准输出流数据
        
        从子进程的标准输出读取数据,解码并发送到流中
        """
        for out in self.subp.stdout:
            out = out.decode('utf-8').strip()
            if out:
                print(out)
                self._emit(out)

    def poll_err(self):
        """轮询并发送标准错误流数据
        
        从子进程的标准错误读取数据,解码并发送到流中
        """
        for err in self.subp.stderr:
            err = err.decode('utf-8').strip()
            if err:
                self._emit(err)

    def emit(self, command, asynchronous=False):
        """执行命令并启动输出监听

        创建子进程执行命令,并启动线程监听标准输出和标准错误

        Args:
            command: 要执行的命令字符串
            asynchronous: 是否异步执行,默认False
        """
        self.subp = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # bufsize=1,
            stdin=subprocess.PIPE)
        self.thread_pool.submit(self.poll_err)
        self.thread_pool.submit(self.poll_out)
        # self.loop.add_callback(self.poll_err)
        # self.loop.add_callback(self.poll_out)

@Stream.register_api(staticmethod)
class from_process(Source):
    """从外部进程获取消息流

    注意:此功能在Windows系统上不可用

    参数
    ----------
    cmd : list of str or str
        要运行的命令:程序名称及其参数
    open_kwargs : dict
        传递给进程打开函数的参数,参见 ``subprocess.Popen``
    with_stderr : bool
        是否在流中包含进程的标准错误输出
    start : bool
        是否在实例化时立即启动进程。通常建议先连接下游节点,然后再调用 ``.start()``

    示例
    -------
    >>> source = Source.from_process(['ping', 'localhost'])  # doctest: +SKIP
    """

    def __init__(self, cmd, open_kwargs=None, with_stderr=False, start=False):
        """初始化进程流

        Args:
            cmd: 要执行的命令
            open_kwargs: 进程打开参数
            with_stderr: 是否包含标准错误
            start: 是否自动启动
        """
        self.cmd = cmd
        self.open_kwargs = open_kwargs or {}
        self.with_stderr = with_stderr
        super(from_process, self).__init__(ensure_io_loop=True)
        self.stopped = True
        self.process = None
        if start:  # pragma: no cover
            self.start()

    @gen.coroutine
    def _start_process(self):
        """启动并监听外部进程

        使用tornado的异步进程管理启动外部进程,
        并持续读取进程输出直到进程结束
        """
        from tornado.process import Subprocess
        from tornado.iostream import StreamClosedError
        import subprocess
        stderr = subprocess.STDOUT if self.with_stderr else subprocess.PIPE
        process = Subprocess(self.cmd, stdout=Subprocess.STREAM,
                             stderr=stderr, **self.open_kwargs)
        while not self.stopped:
            try:
                out = yield process.stdout.read_until(b'\n')
            except StreamClosedError:
                # 进程已退出
                break
            yield self._emit(out)
        yield process.stdout.close()
        process.proc.terminate()

    def start(self):
        """启动外部进程"""
        if self.stopped:
            self.loop.add_callback(self._start_process)
            self.stopped = False

    def stop(self):
        """关闭外部进程"""
        if not self.stopped:
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
        bootstrap.servers: Connection string(s) (host:port) by
             which to reach Kafka
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

    def __init__(self, topics, consumer_params,
                 poll_interval=0.1, start=False, **kwargs):
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
class RedisStream(Stream):
    """redis stream,read and write.


    上游进来的写入redis ，redis的读出来的压入下游,
    exapmle::

        news = Stream.RedisStream('news')
        l = list()
        news>>l
        for i in range(1000):
            i>>news

        l|len

    """

    def __init__(self, topic, start=True,
                 group=None, address='localhost', db=0, password=None, **kwargs):
        self.topic = topic
        self.redis_address = address
        self.redis_password = password
        self.group = group or hash(self)+hash(time.time())
        self.consumer = hash(self)

        super(RedisStream, self).__init__(ensure_io_loop=True, **kwargs)
        self.redis = None
        self.stopped = True
        if start:
            self.start()

    @gen.coroutine
    def process(self):
        if not self.redis:
            self.redis = yield aioredis.Redis(host=self.redis_address, password=self.redis_password)

        topic_exists = yield self.redis.exists(self.topic)
        if not topic_exists:
            print('create topic:', self.topic)
            yield self.redis.xadd(self.topic, {'data': dill.dumps('go')})
        try:
            yield self.redis.xgroup_create(self.topic, self.group)
        except Exception as e:
            print(e)

        while True:
            results = yield self.redis.xread(count=10, block=500, streams={self.topic: '$'})
            if results:
                for result in results:
                    print('rec:', result)
                    data = dill.loads(result[1][0][1][b'data'])
                    self._emit(data)

            if self.stopped:
                break

    @gen.coroutine
    def _send(self, data):
        if not self.redis:
            self.redis = yield aioredis.Redis(host=self.redis_address, password=self.redis_password)
        x = yield self.redis.xadd(self.topic, {'data': dill.dumps(data)}, maxlen=20)
        print('send:', x)

    def emit(self, x, asynchronous=True):
        self.loop.add_callback(self._send, x)
        return x

    def start(self):
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.process)

    def stop(self,):
        self.stopped = True
        self.loop.add_callback(self.redis.close)


@Stream.register_api(staticmethod)
class from_redis(Stream):
    def __init__(self, topic, group=None, max_len=100, **kwargs):
        Stream.__init__(self, ensure_io_loop=True)
        self.source = RedisStream(topic=topic, group=group, max_len=max_len)
        self.source >> self


@Stream.register_api(staticmethod)
class from_http_request(Stream):
    """Receive data from http request,emit httprequest data to stream."""

    def __init__(self, port=7777, path='/.*', start=False, server_kwargs=None):
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
            source = self

            def _loads(self, body):
                """解析从web端口提交过来的数据.

                可能的数据有字符串和二进制,
                字符串可能是直接字符串,也可能是json编码后的字符串
                二进制可能是图像等直接可用的二进制,也可能是dill编码的二进制pyobject
                """
                try:
                    body = dill.loads(body)
                except TypeError:
                    body = json.loads(body)
                except ValueError:
                    body = body.decode('utf-8')
                finally:
                    return body

            @gen.coroutine
            def post(self):
                self.request.body = self._loads(self.request.body)
                yield self.source._emit(self.request.body)
                self.write('OK')

            @gen.coroutine
            def get(self):
                self.write(dill.dumps(self.source.recent()))

        self.application = Application([
            (self.path, Handler),
        ])
        # self.server = HTTPServer(application, **self.server_kwargs)
        self.server = self.application.listen(self.port)

    def start(self):
        if self.stopped:
            self.stopped = False
            self._start_server()
            self.start_cache(5, 60*60*48)
            # self.loop.add_callback(self._start_server)#这个会导致在端口占用情况下不报错

    def stop(self):
        """Shutdown HTTP server."""
        if not self.stopped:
            self.server.stop()
            self.server = None
            self.stopped = True


class StreamTCPServer(TCPServer):
    def __init__(self, port=2345, **kwargs):
        self.delimiter = 'zjw-split-0358'.encode('utf-8')
        self.out_s = Stream()
        self.in_s = Stream()

        # 进来的数据，处理后，再发出去。
        self.in_s >> self.out_s

        super(StreamTCPServer, self).__init__(**kwargs)
        self.handlers = dict()
        self.listen(port)

    def __rrshift__(self, x):
        # 进入消息来源之一，直接塞入数据
        x >> self.in_s

    @gen.coroutine
    def handle_stream(self, stream, address):
        def _write(x):
            try:
                stream.write(x)
                stream.write(self.delimiter)
            except StreamClosedError:
                print('%s connect close' % str(address))
                self.handlers.get(address).destroy()
                del self.handlers[address]

        # 将客户端io输出挂载到分发管道 ，出去的消息，dill后写出
        self.handlers[address] = self.out_s.map(dill.dumps).sink(_write)

        # 进入消息来源之二，不停的读取网络消息
        while True:
            try:
                data = yield stream.read_until(self.delimiter)
                # 进入消息来源之一、服务端读取客户端消息后放入接收管道
                yield self.in_s.emit(dill.loads(data))
                # yield self.out_s._emit(dill.loads(data))
            except StreamClosedError:
                print('%s connect close' % str(address))
                break

    def stop(self):
        self.out_s.emit('exit')
        for handler in self.handlers:
            self.handlers[handler].destroy()
        self.handlers = {}
        super().stop()


class StreamTCPClient():
    """从tcp端口订阅数据
    c1 = StreamTCPClient("127.0.0.1", 23)
    c1.start()
    client = StreamTCPClient(host='127.0.0.1',port=2345)
    client2 = StreamTCPClient()

    """

    def __init__(self, host='127.0.0.1', port=2345, **kwargs):
        super(StreamTCPClient, self).__init__(**kwargs)
        self.host = host
        self.port = port
        self.delimiter = 'zjw-split-0358'.encode('utf-8')

        self.out_s = Stream()  # 发去服务端
        self.in_s = Stream(ensure_io_loop=True)  # 进入消息
        self._stream = None
        self.in_s.filter(lambda x: x == 'exit').sink(lambda x: self.stop())
        self.stopped = True
        self.start()

    def __rrshift__(self, x):
        # 直接发消息去服务端
        x >> self.out_s

    @gen.coroutine
    def start(self):
        try:
            self._stream = yield TCPClient().connect(self.host, self.port)
            self.stopped = False
        except Exception as e:
            print(e, 'connect', self.host, self.port, 'error')

        def _write(x):
            try:
                self._stream.write(x)
                self._stream.write(self.delimiter)
            except StreamClosedError:
                print(f'{self.host}:{self.port} connect close')
                self.out_handler.destroy()

        # 将客户端io输出挂载到分发管道
        self.out_handler = self.out_s.map(dill.dumps).sink(_write)
#
        while self._stream:
            try:
                data = yield self._stream.read_until(self.delimiter)
                yield self.in_s.emit(dill.loads(data))
            except StreamClosedError:
                print('tornado.iostream.StreamClosedError')
                break

    def stop(self):
        if not self._stream.closed() and self._stream.close():
            self.stopped = True


@Stream.register_api(staticmethod)
class from_mail(Source):
    def __init__(self, host=None,
                 username=None,
                 password=None,
                 ssl=True,
                 ssl_context=None,
                 starttls=False,
                 interval=60*15, start=False, **kwargs):
        from imbox import Imbox
        from .namespace import NB
        if not host:
            try:
                hostname = NB('mail')['hostname']
                username = NB('mail')['username']
                password = NB('mail')['password']
            except:
                raise('no host username password ')
        self.imbox = Imbox(hostname,
                           username=username,
                           password=password,
                           ssl=True,
                           ssl_context=None,
                           starttls=False)

        self.interval = interval
        super(from_mail, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    @gen.coroutine
    def poll_mail(self):
        while True:
            for uid, msg in self.imbox.messages(unread=True):
                self._emit(msg)
                self.imbox.mark_seen(uid)
            yield gen.sleep(self.interval)
            if self.stopped:
                break

    def start(self):
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.poll_mail)

    def stop(self):
        self.stopped = True

    def logout(self):
        self.imbox.logout()


@Stream.register_api(staticmethod)
class from_periodic(Source):
    """Generate data from a function on given period
    cf ``streamz.dataframe.PeriodicDataFrame``
    Parameters
    ----------
    callback: callable
        Function to call on each iteration. Takes no arguments.
    poll_interval: float
        Time to sleep between calls (s)
    """

    def __init__(self, callback, poll_interval=0.1, **kwargs):
        self._cb = callback
        self._poll = poll_interval
        super().__init__(**kwargs)

    async def _run(self):
        await asyncio.gather(*self._emit(self._cb()))
        await asyncio.sleep(self._poll)


def gen_block_test() -> int:
    import time
    import datetime
    time.sleep(6)
    return datetime.datetime.now().second
