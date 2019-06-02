# %%

from tornado import gen
from tornado.httpserver import HTTPServer
from deva.streamz.core import Stream as Streamz
import subprocess
from tornado.web import Application, RequestHandler
import os
import dill
import json
from pymaybe import maybe
import walrus
import moment


class Stream(Streamz):
    _graphviz_shape = "doubleoctagon"

    def __init__(self, name=None, *args, **kwargs):
        super(Stream, self).__init__(*args, **kwargs)

    def write(self, value):
        """Emit value to stream ,end,return emit result."""
        self.emit(value)
        return value

    def to_redis_stream(self, topic, maxlen=1):
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

    def to_share(self, topic=None):
        topic = maybe(topic).or_else(self.stream_name)
        self.to_redis_stream(topic=topic, maxlen=1)
        return self

    @classmethod
    def from_share(cls, topics, group=str(os.getpid()), **kwargs):
        # 使用pid做group,区分不同进程消费,一个进程消费结束,不影响其他进程继续消费
        return cls.from_redis(topics=topics, start=True, group=group)\
                  .map(lambda x: x['data'], stream_name=topics, **kwargs)

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
    def __init__(self, topics, interval=0.1, start=False,
                 group="test", **kwargs):
        self.consumer = None
        self.topics = topics
        self.group = group
        self.interval = interval
        self.consumer = walrus.Database().consumer_group(self.group,
                                                         self.topics)
        self.consumer.create()  # Create the consumer group.
        # self.consumer.set_id('$')  # 不会从头读

        super(from_redis, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def do_poll(self) -> list:
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
                self._emit({'topic': topic, 'rid': rid, 'data': data})

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

    def _start_server(self):
        class Handler(RequestHandler):
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

    def __init__(self, interval=0.1, **kwargs):
        self.interval = interval
        super(from_command, self).__init__(ensure_io_loop=True, **kwargs)
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
        import pytz

        self._scheduler = TornadoScheduler(
            timezone=pytz.timezone('Asia/Shanghai'))
        super(scheduler, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def start(self):
        if self.stopped:
            self.stopped = False
        self._scheduler.start()

    def stop(self):
        self._scheduler.stop()
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


class Namespace(dict):
    def create_stream(self, stream_name, **kwargs):
        try:
            return self[stream_name]
        except KeyError:
            return self.setdefault(
                stream_name,
                Stream(stream_name=stream_name, **kwargs)
            )


namespace = Namespace()


def NS(*args, **kwargs):
    NS.namespace = namespace
    return namespace.create_stream(*args, **kwargs)


def gen_block_test() -> int:
    import time
    import moment
    time.sleep(6)
    return moment.now().seconds

# %%
