# %%

from tornado.iostream import StreamClosedError
from tornado.tcpserver import TCPServer
from tornado.tcpclient import TCPClient
from tornado import gen, ioloop
from tornado.httpserver import HTTPServer
from deva.streamz.core import Stream as Streamz
import subprocess
from tornado.web import Application, RequestHandler
import dill
import json
import walrus
import moment
import os


class Stream(Streamz):
    _graphviz_shape = "doubleoctagon"

    def __init__(self, name=None, *args, **kwargs):
        super(Stream, self).__init__(*args, **kwargs)

    def write(self, value):
        """Emit value to stream ,end,return emit result."""
        self.emit(value)
        return value

    def to_redis(self, topic, maxlen=1):
        """
        Push stream to redis stream.

        ::topic:: redis stream topic
        ::maxlen:: data store in redis stream max len
        """
        producer = walrus.Database().Stream(topic)
        # producer only accept non-empty dict
        self.map(lambda x: {"data": dill.dumps(x)})\
            .sink(producer.add, maxlen=maxlen)
        return self

    @classmethod
    def from_tcp(cls, port=1234, **kwargs):
        def dec(x):
            try:
                return dill.loads(x)
            except Exception:
                return x
        return Streamz.from_tcp(port, start=True, **kwargs).map(dec)


@Stream.register_api(staticmethod)
class engine(Stream):
    """持续生产数据的引擎.

    ::func:: func to gen data
    ::interval:: func to run interval time
    ::asyncflag:: func execute in threadpool
    ::threadcount:: if asyncflag ,this is threadpool count
    """

    def __init__(self,
                 interval=1,
                 start=False,
                 func=lambda: moment.now().seconds,
                 asyncflag=False,
                 threadcount=5,
                 **kwargs):

        self.interval = interval
        self.func = func
        self.asyncflag = asyncflag
        if self.asyncflag:
            from concurrent.futures import ThreadPoolExecutor
            self.thread_pool = ThreadPoolExecutor(threadcount)

        super(engine, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    @gen.coroutine
    def run(self):
        while True:
            if self.asyncflag:
                self.thread_pool.submit(lambda: self._emit(self.func()))
            else:
                self._emit(self.func())
            yield gen.sleep(self.interval)
            if self.stopped:
                break

    def start(self):
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.run)

    def stop(self):
        self.stopped = True


@Stream.register_api(staticmethod)
class from_redis(Stream):
    def __init__(self, topics: list, interval=0.1, start=False,
                 group="test", **kwargs):
        self.consumer = None
        if not isinstance(topics, list):
            topics = [topics]
        self.topics = topics
        self.group = group
        self.interval = interval
        self.db = walrus.Database()
        self.consumer = self.db.consumer_group(self.group,
                                               self.topics)
        self.consumer.create()  # Create the consumer group.
        # self.consumer.set_id('$')  # 不会从头读

        super(from_redis, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def do_poll(self):
        """同步redis库,todo:寻找异步的stream库来查询."""
        if self.consumer is not None:
            meta_msgs = self.consumer.read(count=1)
            # Returns:
            """
            [('stream-a', [(b'1539023088125-0', {b'message': b'new a'})]),
             ('stream-b', [(b'1539023088125-0', {b'message': b'new for b'})]),
             ('stream-c', [(b'1539023088126-0', {b'message': b'c-0'})])]
             """
            for meta_msg in meta_msgs:
                # {b'data':'dills'},
                topic, (rid, body) = meta_msg[0], meta_msg[1][0]
                data = dill.loads(body[b'data'])
                # self._emit({'topic': topic, 'rid': rid, 'data': data})
                self._emit(data)

    @gen.coroutine
    def poll_redis(self):
        while True:
            self.do_poll()
            yield gen.sleep(self.interval)
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


@Stream.register_api(staticmethod)
class from_command(Stream):
    """Receive command eval result data from subprocess,emit to stream."""

    def __init__(self, interval=0.1, command=None, **kwargs):
        self.interval = interval
        super(from_command, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        from concurrent.futures import ThreadPoolExecutor
        self.thread_pool = ThreadPoolExecutor(2)
        self.command = command
        if self.command:
            self.run(self.command)

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

    def run(self, command):
        self.subp = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=1,
            stdin=subprocess.PIPE)
        self.thread_pool.submit(self.poll_err)
        self.thread_pool.submit(self.poll_out)


@Stream.register_api(staticmethod)
class scheduler(Stream):
    """定时流.

    Examples:
    s = scheduler()
    s.add_job(name='hello',seconds=5,start_date='2019-04-03 09:25:00')
    s.get_jobs()>>pmap(lambda x:x.next_run_time)>>to_list

    con = s.map(lambda x:
       match(x,
            'open',lambda x:x>>warn,
             'hello',lambda x:x>>warn,
             ANY,'None',
            ))

    s.add_job(func=lambda :print('yahoo'),seconds=5)

    Parameters:
    weeks (int) – number of weeks to wait
    days (int) – number of days to wait
    hours (int) – number of hours to wait
    minutes (int) – number of minutes to wait
    seconds (int) – number of seconds to wait
    start_date (datetime|str) – starting point for the interval calculation
    end_date (datetime|str) – latest possible date/time to trigger on
    timezone (datetime.tzinfo|str) – to use for the date/time calculations.
    jitter (int|None) – advance or delay  by jitter seconds at most.

    """

    def __init__(self, start=True, **kwargs):
        from apscheduler.schedulers.tornado import TornadoScheduler
        from apscheduler.executors.pool import ThreadPoolExecutor
        import pytz

        self._scheduler = TornadoScheduler(
            timezone=pytz.timezone('Asia/Shanghai'),
            executors={'default': ThreadPoolExecutor(20)},
            job_defaults={
                'coalesce': False,
                'max_instances': 1  # 相同job重复执行与否的判断，相同job最多同时多少个实例
            }
        )
        super(scheduler, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def start(self):
        if self.stopped:
            self.stopped = False
        self._scheduler.start()

    def stop(self):
        self._scheduler.shutdown()
        self.stopped = True

    def add_job(self, func, name=None, **kwargs):
        """增加任务.

        Example:
         i.add_job(name='hello',func = lambda x:'heoo',
         seconds=5,start_date='2019-04-03 09:25:00')
        """
        return self._scheduler.add_job(
            func=lambda: self._emit(func()),
            name=name,
            id=name,
            trigger='interval',
            **kwargs)

    def remove_job(self, name):
        return self._scheduler.remove_job(job_id=name)

    def get_jobs(self,):
        return self._scheduler.get_jobs()


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
                print('%s connect close' % str(address))
                self.handlers.get(address).destroy()
                del self.handlers[address]

        self.handlers[address] = self.out_s.map(dill.dumps).sink(_write)
        while True:
            try:
                data = yield stream.read_until(self.delimiter)
                yield self.in_s._emit(dill.loads(data))
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
            print(e, 'connect', self.host, self.port, 'error')

        def _write(x):
            try:
                self._stream.write(x)
                self._stream.write(self.delimiter)
            except StreamClosedError:
                print(f'{self.host}:{self.port} connect close')
                self.out_handler.destroy()

        self.out_handler = self.out_s.map(dill.dumps).sink(_write)
#         try:
        while self._stream:
            data = yield self._stream.read_until(self.delimiter)
            yield self.in_s.emit(dill.loads(data))
#         except iostream.StreamClosedError:
#             print('tornado.iostream.StreamClosedError')

    def stop(self):
        if not self._stream.closed() and self._stream.close():
            self.stopped = True


class Namespace(dict):
    def create_stream(self, stream_name, **kwargs):
        try:
            return self[stream_name]
        except KeyError:
            return self.setdefault(
                stream_name,
                Stream(stream_name=stream_name, **kwargs)
            )

    def create_topic(self, topic, **kwargs):
        """创建一个跨进程的stream"""
        try:
            return self[topic]
        except KeyError:
            self[topic] = Stream.from_redis(
                topics=[topic],
                group=str(os.getpid()),
                start=True,
                stream_name=topic,
                **kwargs
            )
            out_s = Stream().to_redis(topic)
            self[topic].emit = out_s.emit

            return self[topic]


namespace = Namespace()


def NS(*args, **kwargs):
    return namespace.create_stream(*args, **kwargs)


def NT(topic, *args, **kwargs):
    try:
        return namespace.create_topic(topic=topic, *args, **kwargs)
    except Exception as e:
        print(f'Warn:{e}, start a single process topic ')
        return NS(topic)


def gen_block_test() -> int:
    import time
    import moment
    time.sleep(6)
    return moment.now().seconds


class Deva(Stream):
    def __init__(self, name=None, *args, **kwargs):
        super(Stream, self).__init__(*args, **kwargs)

    @classmethod
    def run(cls):
        ioloop.IOLoop.current().start()
        # %%
