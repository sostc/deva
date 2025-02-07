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

class PollingSource(Source):
    """轮询数据源基类"""
    
    def __init__(self, poll_interval=0.1, **kwargs):
        super().__init__(**kwargs)
        self.poll_interval = poll_interval
        self.stopped = True

    @gen.coroutine
    def do_poll(self):
        """轮询主循环"""
        while True:
            data = self._fetch_data()
            if data:
                yield self._emit(data)
            else:
                yield gen.sleep(self.poll_interval)
            if self.stopped:
                break

    def _fetch_data(self):
        """子类实现具体的数据获取逻辑"""
        raise NotImplementedError
    
    
@Stream.register_api(staticmethod)
class from_textfile(PollingSource):
    """从文本文件创建数据流

    该类用于从文本文件中读取数据并生成流。支持按指定分隔符分割数据，并可以定期轮询文件获取新内容。

    Attributes:
        file (file): 打开的文件对象
        delimiter (str): 数据分隔符
        poll_interval (float): 轮询间隔时间
        stopped (bool): 流是否已停止

    Args:
        f (file or str): 要读取的文件对象或文件路径
        poll_interval (float, optional): 轮询文件的时间间隔(秒). 默认值: 0.1
        delimiter (str, optional): 用于分割数据的分隔符. 默认值: '\n'
        start (bool, optional): 是否立即启动. 默认值: False
        **kwargs: 其他传递给父类的参数

    Examples:
        >>> source = Stream.from_textfile('myfile.json')  # doctest: +SKIP
        >>> js.map(json.loads).pluck('value').sum().sink(print)  # doctest: +SKIP
        >>> source.start()  # doctest: +SKIP

    Returns:
        Stream: 返回流对象
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
        super(from_textfile, self).__init__(poll_interval=poll_interval, 
                                          ensure_io_loop=True, 
                                          **kwargs)
        if start:
            self.start()

    def _fetch_data(self):
        """从文件中读取数据并返回
        
        返回:
            list: 分割后的数据列表，如果没有新数据则返回空列表
        """
        buffer = ''
        data = []
        line = self.file.read()
        if line:
            buffer = buffer + line
            if self.delimiter in buffer:
                parts = buffer.split(self.delimiter)
                buffer = parts.pop(-1)
                for part in parts:
                    data.append(part + self.delimiter)
        return data
    
@Stream.register_api(staticmethod)
class filenames(PollingSource):
    """监控目录中的文件名流

    监控指定目录或文件模式，当有新文件出现时将文件名发送到流中。
    支持目录监控和glob模式匹配，可配置轮询间隔。

    参数
    ----------
    path: str
        要监控的目录路径或glob匹配模式，如'/path/to/dir'或'/path/to/*.csv'
    poll_interval: float, 默认0.1
        检查目录的时间间隔(秒)，建议根据文件产生频率调整
    start: bool, 默认False
        是否立即启动监控，否则需要手动调用start()方法
    recursive: bool, 默认False
        是否递归监控子目录（仅当path为目录时有效）

    示例
    --------
    >>> # 监控目录下所有文件
    >>> source = Stream.filenames('path/to/dir')
    
    >>> # 监控特定文件类型，设置轮询间隔为0.5秒
    >>> source = Stream.filenames('path/to/*.csv', poll_interval=0.500)
    """

    def __init__(self, path, poll_interval=0.100, start=False, recursive=False, **kwargs):
        """初始化文件名流

        Args:
            path: 监控的目录路径或glob模式
            poll_interval: 轮询间隔，默认0.1秒
            start: 是否自动启动，默认False
            recursive: 是否递归监控子目录，默认False
            **kwargs: 其他参数
        """
        # 处理路径格式
        if '*' not in path:
            if os.path.isdir(path):
                if not path.endswith(os.path.sep):
                    path = path + '/'
                path = path + ('**/*' if recursive else '*')
        
        self.path = path
        self.seen = set()  # 已处理文件集合
        self.recursive = recursive
        
        super(filenames, self).__init__(poll_interval=poll_interval, 
                                      ensure_io_loop=True, 
                                      **kwargs)
        if start:
            self.start()

    @gen.coroutine
    def poll(self):
        """轮询目录并处理新文件

        使用glob模式匹配文件，检测新文件并发送到流中
        """
        try:
            # 获取匹配的文件列表
            filenames = set(glob(self.path, recursive=self.recursive))
            new_files = filenames - self.seen
            
            # 按文件名排序后处理
            for filename in sorted(new_files):
                if os.path.isfile(filename):  # 确保是文件
                    self.seen.add(filename)
                    yield self._emit(filename)
                    
        except Exception as e:
            logger.error(f"文件监控出错: {str(e)}")
            yield gen.sleep(1)  # 出错后等待1秒重试
            
@Stream.register_api(staticmethod)
class from_tcp_port(Source):
    """从TCP端口创建事件流

    使用tornado TCPServer从socket读取数据。传入的字节流会根据指定的分隔符进行分割，
    分割后的部分作为事件发送。

    Attributes:
        port (int): 要监听的端口号。只有在source启动时才会打开，stop()时关闭。
        delimiter (bytes): 用于分割传入数据的分隔符。分割后的事件末尾仍会保留分隔符。
        start (bool): 是否立即启动source。建议先设置好下游节点再启动。
        server_kwargs (dict or None): 如果提供，会作为额外参数传递给TCPServer。

    Methods:
        __init__: 初始化TCP端口source
        _start_server: 启动TCP服务器
        start: 启动source
        stop: 停止source

    Example:
        >>> source = Source.from_tcp_port(4567)  # doctest: +SKIP
    """

    def __init__(self, port, delimiter=b'\n', start=False, server_kwargs=None):
        """初始化TCP端口source

        Args:
            port (int): 监听的端口号
            delimiter (bytes): 数据分隔符，默认换行符
            start (bool): 是否自动启动
            server_kwargs (dict): TCPServer的额外参数
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

                持续从流中读取数据，按分隔符分割后发送事件

                Args:
                    stream: TCP数据流
                    address: 客户端地址
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
    """从Kafka接收消息的数据源类

    使用confluent-kafka库实现Kafka消息的消费。
    参考文档:
    https://docs.confluent.io/current/clients/confluent-kafka-python/

    参数:
    ----------
    topics: list of str
        要消费的Kafka主题列表
    consumer_params: dict
        Kafka消费者配置参数，参考:
        https://docs.confluent.io/current/clients/confluent-kafka-python/#configuration
        https://github.com/edenhill/librdkafka/blob/master/CONFIGURATION.md
        常用配置示例:
        bootstrap.servers: Kafka连接地址(host:port)
        group.id: 消费者组ID。如果多个消费者使用相同的group.id，
            每条消息只会被其中一个消费者接收
    poll_interval: number
        轮询Kafka新消息的时间间隔(秒)
    start: bool (False)
        是否在初始化时自动开始轮询

    示例:
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
        """执行一次Kafka消息轮询"""
        if self.consumer is not None:
            msg = self.consumer.poll(0)
            if msg and msg.value() and msg.error() is None:
                return msg.value()

    @gen.coroutine
    def poll_kafka(self):
        """持续轮询Kafka消息的主循环"""
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
        """启动Kafka消费者"""
        import confluent_kafka as ck
        if self.stopped:
            self.stopped = False
            self.consumer = ck.Consumer(self.cpars)
            self.consumer.subscribe(self.topics)
            tp = ck.TopicPartition(self.topics[0], 0, 0)

            # 阻塞直到消费者线程启动
            self.consumer.get_watermark_offsets(tp)
            self.loop.add_callback(self.poll_kafka)

    def _close_consumer(self):
        """关闭Kafka消费者"""
        if self.consumer is not None:
            consumer = self.consumer
            self.consumer = None
            consumer.unsubscribe()
            consumer.close()
        self.stopped = True

@Stream.register_api(staticmethod)
class RedisStream(Stream):
    """Redis流处理类，用于读写Redis Stream数据

    该类实现了基于Redis Stream的数据流处理，支持数据的读写操作。
    上游数据写入Redis，从Redis读取的数据会推送到下游。

    参数:
        topic: str
            Redis Stream的主题名称
        start: bool, 默认为True
            是否在初始化时自动启动
        group: str, 可选
            Redis消费者组名称，默认为自动生成
        address: str, 默认为'localhost'
            Redis服务器地址
        db: int, 默认为0
            Redis数据库编号
        password: str, 可选
            Redis认证密码

    示例:
        # 创建Redis流
        news = Stream.RedisStream('news')
        
        # 创建列表用于接收数据
        l = list()
        
        # 将流数据输出到列表
        news >> l
        
        # 向流中写入1000条数据
        for i in range(1000):
            i >> news

        # 查看接收到的数据量
        len(l)
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
        """处理Redis Stream数据的主循环"""
        if not self.redis:
            self.redis = yield aioredis.Redis(host=self.redis_address, password=self.redis_password)

        # 检查主题是否存在，不存在则创建
        topic_exists = yield self.redis.exists(self.topic)
        if not topic_exists:
            print('创建主题:', self.topic)
            yield self.redis.xadd(self.topic, {'data': dill.dumps('go')})
        
        # 创建消费者组
        try:
            yield self.redis.xgroup_create(self.topic, self.group)
        except Exception as e:
            print(e)

        # 主循环：持续读取并处理数据
        while True:
            results = yield self.redis.xread(count=10, block=500, streams={self.topic: '$'})
            if results:
                for result in results:
                    print('收到数据:', result)
                    data = dill.loads(result[1][0][1][b'data'])
                    self._emit(data)

            if self.stopped:
                break

    @gen.coroutine
    def _send(self, data):
        """向Redis Stream发送数据"""
        if not self.redis:
            self.redis = yield aioredis.Redis(host=self.redis_address, password=self.redis_password)
        x = yield self.redis.xadd(self.topic, {'data': dill.dumps(data)}, maxlen=20)
        print('发送数据:', x)

    def emit(self, x, asynchronous=True):
        """发送数据到Redis Stream"""
        self.loop.add_callback(self._send, x)
        return x

    def start(self):
        """启动Redis流处理"""
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.process)

    def stop(self):
        """停止Redis流处理"""
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
    """从HTTP请求接收数据，并将请求数据发送到流中

    该类实现了一个HTTP服务器，用于接收HTTP请求并将请求数据作为流数据发送。
    支持POST和GET请求，可以处理多种数据格式。

    属性:
        port: int
            HTTP服务器监听端口，默认为7777
        path: str
            请求路径匹配模式，默认为'/.*'
        server_kwargs: dict
            服务器配置参数
        stopped: bool
            服务器运行状态标志
        server: HTTPServer
            HTTP服务器实例

    方法:
        __init__: 初始化HTTP服务器
        _start_server: 启动HTTP服务器
        start: 启动数据流和服务器
        stop: 停止服务器

    示例:
        # 创建并启动HTTP服务器
        http_stream = from_http_request(port=8888)
        http_stream.start()

        # 停止服务器
        http_stream.stop()
    """

    def __init__(self, port=7777, path='/.*', start=False, server_kwargs=None):
        """初始化HTTP服务器

        参数:
            port: int, 默认7777
                服务器监听端口号
            path: str, 默认'/.*'
                请求路径匹配模式
            start: bool, 默认False
                是否立即启动服务器
            server_kwargs: dict, 默认None
                服务器配置参数
        """
        self.port = port
        self.path = path
        self.server_kwargs = server_kwargs or {}
        super(from_http_request, self).__init__(ensure_io_loop=True)
        self.stopped = True
        self.server = None
        if start:  # pragma: no cover
            self.start()

    def _start_server(self):
        """启动HTTP服务器，初始化请求处理器"""
        class Handler(RequestHandler):
            source = self

            def _loads(self, body):
                """解析HTTP请求体数据

                支持多种数据格式：
                - dill序列化的Python对象
                - JSON格式数据
                - 普通字符串
                - 二进制数据

                参数:
                    body: bytes
                        HTTP请求体数据

                返回:
                    解析后的数据对象
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
                """处理POST请求"""
                self.request.body = self._loads(self.request.body)
                yield self.source._emit(self.request.body)
                self.write('OK')

            @gen.coroutine
            def get(self):
                """处理GET请求，返回最近的数据"""
                self.write(dill.dumps(self.source.recent()))

        # 创建Tornado应用并启动服务器
        self.application = Application([
            (self.path, Handler),
        ])
        self.server = self.application.listen(self.port)

    def start(self):
        """启动HTTP服务器和数据流"""
        if self.stopped:
            self.stopped = False
            self._start_server()
            self.start_cache(5, 60*60*48)  # 启动缓存，保留48小时数据

    def stop(self):
        """停止HTTP服务器"""
        if not self.stopped:
            self.server.stop()
            self.server = None
            self.stopped = True

class StreamTCPServer(TCPServer):
    """TCP服务器流类，用于通过TCP端口收发数据

    该类实现了TCP服务器功能，可以监听指定端口，
    并通过流式接口进行数据收发。

    属性:
        delimiter: bytes
            消息分隔符，用于区分不同消息
        out_s: Stream
            输出流，用于发送数据到客户端
        in_s: Stream
            输入流，用于接收来自客户端的数据
        handlers: dict
            客户端连接处理器字典，key为客户端地址，value为处理器对象
        port: int
            服务器监听端口号

    方法:
        __init__: 初始化TCP服务器
        __rrshift__: 重载右移运算符，用于直接发送数据
        handle_stream: 处理客户端连接和数据收发
        stop: 停止TCP服务器

    示例:
        # 创建并启动TCP服务器
        server = StreamTCPServer(port=2345)
        server.start()

        # 直接发送数据到所有客户端
        "hello" >> server

        # 停止服务器
        server.stop()
    """

    def __init__(self, port=2345, **kwargs):
        """初始化TCP服务器

        参数:
            port: int, 默认2345
                服务器监听端口号
            **kwargs: 其他参数
        """
        self.delimiter = 'zjw-split-0358'.encode('utf-8')
        self.out_s = Stream()
        self.in_s = Stream()

        # 配置输入输出流管道
        self.in_s >> self.out_s

        super(StreamTCPServer, self).__init__(**kwargs)
        self.handlers = dict()
        self.listen(port)

    def __rrshift__(self, x):
        """重载右移运算符，用于直接发送数据到输入流

        参数:
            x: 要发送的数据
        """
        x >> self.in_s

    @gen.coroutine
    def handle_stream(self, stream, address):
        """处理客户端连接和数据收发

        参数:
            stream: tornado.iostream.IOStream
                客户端连接流对象
            address: tuple
                客户端地址 (ip, port)
        """
        def _write(x):
            """向客户端写入数据

            参数:
                x: 要写入的数据
            """
            try:
                stream.write(x)
                stream.write(self.delimiter)
            except StreamClosedError:
                print('%s 连接关闭' % str(address))
                self.handlers.get(address).destroy()
                del self.handlers[address]

        # 配置输出流处理器
        self.handlers[address] = self.out_s.map(dill.dumps).sink(_write)

        # 主循环：持续读取客户端数据
        while True:
            try:
                data = yield stream.read_until(self.delimiter)
                # 将接收到的数据发送到输入流
                yield self.in_s.emit(dill.loads(data))
            except StreamClosedError:
                print('%s 连接关闭' % str(address))
                break

    def stop(self):
        """停止TCP服务器

        关闭所有客户端连接，清理资源
        """
        self.out_s.emit('exit')
        for handler in self.handlers:
            self.handlers[handler].destroy()
        self.handlers = {}
        super().stop()

class StreamTCPClient():
    """TCP客户端流类，用于从TCP端口订阅数据

    该类实现了TCP客户端功能，可以连接到指定的TCP服务器，
    并通过流式接口进行数据收发。

    属性:
        host: str, 默认'127.0.0.1'
            服务器主机地址
        port: int, 默认2345
            服务器端口号
        delimiter: bytes
            消息分隔符，用于区分不同消息
        out_s: Stream
            输出流，用于发送数据到服务器
        in_s: Stream
            输入流，用于接收来自服务器的数据
        _stream: tornado.iostream.IOStream
            TCP连接流对象
        stopped: bool
            连接状态标志

    方法:
        __init__: 初始化TCP客户端
        __rrshift__: 重载右移运算符，用于直接发送数据
        start: 启动TCP连接并开始数据收发
        stop: 停止TCP连接

    示例:
        # 创建并启动TCP客户端
        client = StreamTCPClient(host='127.0.0.1', port=2345)
        client.start()

        # 直接发送数据到服务器
        "hello" >> client

        # 停止客户端
        client.stop()
    """

    def __init__(self, host='127.0.0.1', port=2345, **kwargs):
        """初始化TCP客户端

        参数:
            host: str, 默认'127.0.0.1'
                服务器主机地址
            port: int, 默认2345
                服务器端口号
            **kwargs: 其他参数
        """
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
        """重载右移运算符，用于直接发送数据到服务器

        参数:
            x: 要发送的数据
        """
        x >> self.out_s

    @gen.coroutine
    def start(self):
        """启动TCP连接并开始数据收发"""
        try:
            self._stream = yield TCPClient().connect(self.host, self.port)
            self.stopped = False
        except Exception as e:
            print(e, 'connect', self.host, self.port, 'error')

        def _write(x):
            """数据写入回调函数"""
            try:
                self._stream.write(x)
                self._stream.write(self.delimiter)
            except StreamClosedError:
                print(f'{self.host}:{self.port} connect close')
                self.out_handler.destroy()

        # 将客户端io输出挂载到分发管道
        self.out_handler = self.out_s.map(dill.dumps).sink(_write)

        while self._stream:
            try:
                data = yield self._stream.read_until(self.delimiter)
                yield self.in_s.emit(dill.loads(data))
            except StreamClosedError:
                print('tornado.iostream.StreamClosedError')
                break

    def stop(self):
        """停止TCP连接"""
        if not self._stream.closed() and self._stream.close():
            self.stopped = True

@Stream.register_api(staticmethod)
class from_mail(Source):
    """邮件数据源类，用于从邮件服务器获取未读邮件并生成数据流
    
    该类继承自Source类，通过定期轮询邮件服务器获取未读邮件，
    并将每封邮件作为数据流中的事件发出。

    参数:
        host: str, 可选
            邮件服务器地址，如果未提供则从配置中获取
        username: str, 可选
            邮件账户用户名，如果未提供则从配置中获取
        password: str, 可选
            邮件账户密码，如果未提供则从配置中获取
        ssl: bool, 默认True
            是否使用SSL加密连接
        ssl_context: ssl.SSLContext, 可选
            自定义SSL上下文
        starttls: bool, 默认False
            是否使用STARTTLS协议
        interval: int, 默认900
            轮询间隔时间，单位为秒
        start: bool, 默认False
            是否在初始化后立即启动轮询
        **kwargs: 其他传递给父类的参数

    方法:
        poll_mail(): 轮询邮件服务器获取未读邮件
        start(): 启动邮件轮询
        stop(): 停止邮件轮询
        logout(): 登出邮件服务器
    """

    def __init__(self, host=None,
                 username=None,
                 password=None,
                 ssl=True,
                 ssl_context=None,
                 starttls=False,
                 interval=60*15, start=False, **kwargs):
        from imbox import Imbox
        from .namespace import NB
        
        # 如果未提供host，则从配置中获取邮件服务器信息
        if not host:
            try:
                hostname = NB('mail')['hostname']
                username = NB('mail')['username']
                password = NB('mail')['password']
            except:
                raise Exception('未配置邮件服务器信息：缺少host、username或password')

        # 初始化Imbox邮件客户端
        self.imbox = Imbox(hostname,
                         username=username,
                         password=password,
                         ssl=ssl,
                         ssl_context=ssl_context,
                         starttls=starttls)

        self.interval = interval  # 设置轮询间隔
        super(from_mail, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True  # 初始状态为停止
        
        # 如果start为True，则立即启动轮询
        if start:
            self.start()

    @gen.coroutine
    def poll_mail(self):
        """轮询邮件服务器获取未读邮件
        
        该方法会定期检查邮件服务器中的未读邮件，
        将每封邮件作为事件发出，并标记为已读。
        """
        while True:
            # 获取所有未读邮件
            for uid, msg in self.imbox.messages(unread=True):
                self._emit(msg)  # 将邮件作为事件发出
                self.imbox.mark_seen(uid)  # 标记为已读
            yield gen.sleep(self.interval)  # 等待下次轮询
            if self.stopped:  # 如果已停止则退出循环
                break

    def start(self):
        """启动邮件轮询"""
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.poll_mail)

    def stop(self):
        """停止邮件轮询"""
        self.stopped = True

    def logout(self):
        """登出邮件服务器"""
        self.imbox.logout()

@Stream.register_api(staticmethod)
class from_periodic(Source):
    """周期性数据源类，通过定期调用函数生成数据流
    
    参考: `streamz.dataframe.PeriodicDataFrame`
    
    参数:
        callback: 可调用对象
            每次迭代时调用的函数，不接受参数
        poll_interval: float
            每次调用之间的休眠时间（秒）
    """

    def __init__(self, callback, poll_interval=0.1, **kwargs):
        """初始化周期性数据源
        
        参数:
            callback: 要定期执行的回调函数
            poll_interval: 调用间隔时间，默认为0.1秒
            **kwargs: 其他传递给父类的参数
        """
        self._cb = callback  # 回调函数
        self._poll = poll_interval  # 调用间隔
        super().__init__(**kwargs)  # 调用父类初始化

    async def _run(self):
        """异步运行任务
        
        执行流程:
        1. 调用回调函数并发送结果
        2. 等待指定间隔时间
        """
        await asyncio.gather(*self._emit(self._cb()))  # 调用并发送结果
        await asyncio.sleep(self._poll)  # 等待指定时间间隔

def gen_block_test() -> int:
    import time
    import datetime
    time.sleep(6)
    return datetime.datetime.now().second
