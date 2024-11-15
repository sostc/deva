from .core import Stream
# from tornado import gen
import logging
import os
from .sources import StreamTCPClient, RedisStream
from urllib.parse import unquote
from tornado.web import RequestHandler, Application
import pandas as pd
import dill
from tornado import gen
import json
"""消息主题模块

本模块提供了基于不同传输协议的消息主题实现,包括:

- Topic: 基于Redis的消息主题
- TCPStream: 基于TCP的消息流
- TCPTopic: 基于TCP的消息主题

主要功能:
- 支持发布/订阅模式
- 支持消息持久化
- 支持消息分组处理
- 支持TCP和Redis两种传输方式

示例
-------
# Redis主题示例
>>> from deva import Topic
>>> t1 = Topic('test_topic')  # 创建主题
>>> t1 >> log  # 订阅并打印消息
>>> 'hello' >> t1  # 发布消息

# TCP流示例
>>> from deva import TCPStream
>>> s1 = TCPStream(port=5000)  # 创建TCP流
>>> s2 = TCPStream(port=5000)  # 创建另一个TCP流
>>> s1.map(lambda x: x*2) >> s2  # 消息处理并转发
>>> 'hello' >> s1  # 发送消息

# TCP主题示例
>>> from deva import TCPTopic 
>>> t1 = TCPTopic('chat')
>>> t1.map(lambda x: f'收到消息: {x}') >> log
>>> '你好' >> t1  # 发送消息到主题

参见
--------
deva.core.Stream : 基础流处理类
deva.sources : 数据源模块
"""

logger = logging.getLogger(__name__)


@Stream.register_api()
class Topic(RedisStream):

    def __init__(self, name='', group=str(os.getpid()), maxsize=None,  **kwargs):
        super().__init__(topic=name,
                         group=group,
                         start=True,
                         name=name,
                         **kwargs)


@Stream.register_api(staticmethod)
class TCPStream(Stream):
    """redis stream,read and write.


    上游进来的写入,读出来的压入下游,
    exapmle::

        bus = TCPStream()
        bus>>log
        bus2 = TCPStream()
        bus2.map(lambda x:x*2)>>log

    """

    def __init__(self, host='127.0.0.1', port=2345, topic='', **kwargs):
        self.topic = topic
        super(TCPStream, self).__init__(ensure_io_loop=True, **kwargs)
        try:
            self.client = StreamTCPClient(host=host, port=port)
            # 进来的消息发下游
            self.client.in_s.sink(lambda x: self._emit(x))
        except Exception as e:
            print(e)

    def emit(self, x, asynchronous=True):
        x >> self.client


@Stream.register_api()
class TCPTopic(TCPStream):

    def __init__(self, name='',   **kwargs):
        super().__init__(topic=name,
                         name=name,
                         **kwargs)


@Stream.register_api(staticmethod)
class http_topic(Stream):

    """Receive data from http request,emit httprequest data to stream."""

    def __init__(self, port=7777, path='/.*', start=False, server_kwargs=None):
        self.port = port
        self.path = path
        self.server_kwargs = server_kwargs or {}
        super(http_topic, self).__init__(ensure_io_loop=True)
        self.stopped = True
        self.server = None
        if start:  # pragma: no cover
            self.start()

    def _start_server(self):
        from .namespace import NS

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
                    try:
                        body = pd.DataFrame.from_dict(body)
                    except:
                        body = body
                except ValueError:
                    body = body.decode('utf-8')
                finally:
                    return body

            def _encode(self, body):
                if isinstance(body, pd.DataFrame):
                    return body.sample(20).to_html()
                else:
                    return json.dumps(body, ensure_ascii=False)

            @gen.coroutine
            def post(self):
                body = dill.loads(self.request.body)
                body = [self._loads(i) for i in body]
                if not isinstance(body, list):
                    body = [body]

                tag = unquote(self.request.headers['tag'])
                print(tag)
                if tag:
                    source = NS(tag)
                    if not source.is_cache:
                        source.start_cache(5, 64*64*24*5)
                else:
                    source = self.source
                for i in body:
                    yield source._emit(i)
                self.write('OK')

            @gen.coroutine
            def get(self):
                topic = unquote(self.request.path)
                if topic == '/':
                    data = self.source.recent()
                else:
                    stream = NS(topic.split('/')[1])
                    if not stream.is_cache:
                        stream.start_cache(10, 64*64*24*7)
                    data = stream.recent()
                if 'deva' in self.request.headers['User-Agent']:
                    self.write(dill.dumps(data))
                else:
                    for i in data:
                        self.write(self._encode(i)+'</br>')

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
