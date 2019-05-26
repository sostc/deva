
import logging
from logbook import Logger, StreamHandler
from tornado import gen

from .streamz.core import Stream as Streamz
from tornado.httpserver import HTTPServer
from tornado.queues import Queue
from tornado.iostream import StreamClosedError
import atexit

import weakref

import subprocess
from tornado.web import Application, RequestHandler
from .pipe import *

import os
from dataclasses import dataclass, field

import dill
from pampy import match, ANY
from pymaybe import maybe

import sys


class Stream(Streamz):
    _graphviz_shape = "doubleoctagon"

    def __init__(self, name=None, *args, **kwargs):
        super(Stream, self).__init__(*args, **kwargs)

    def write(self, value):  # |
        """emit value to stream ,end,return emit result"""
        self.emit(value)

    def send(self, value):  # |
        """emit value to stream ,end,return emit result"""
        self.emit(value)

    def to_redis_stream(self, topic, db=None, maxlen=None):
        """
        push stream to redis stream

        ::topic:: redis stream topic
        ::db:: walrus redis databse object ,default :from walrus import Database,db=Database()
        """
        import dill
        if not db:
            try:
                import walrus
                self.db = walrus.Database()
            except:
                raise
        producer = self.db.Stream(topic)

        from fn import F
        madd = F(producer.add, maxlen=maxlen)
        self.map(lambda x: {"data": dill.dumps(x)}).sink(
            madd)  # producer only accept non-empty dict dict
        return self

    def to_share(self, name=None):
        if not name:
            name = self.stream_name

        self.to_redis_stream(topic=name, maxlen=10)
        return self

    @classmethod
    def from_share(cls, topics, group=str(os.getpid()), **kwargs):
        # 使用pid做group,区分不同进程消费,一个进程消费结束,不影响其他进程继续消费
        return cls.from_redis(topics=topics, start=True, group=group).map(lambda x: x.msg_body, stream_name=topics, **kwargs)

    @classmethod
    def from_tcp(cls, port=1234, **kwargs):
        def dec(x):
            try:
                return dill.loads(x)
            except:
                return x
        return Streamz.from_tcp(port, start=True, **kwargs).map(dec)


def gen_test():
    import moment
    return moment.now().seconds


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
                 func=gen_test,
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
        # self.consumer.set_id('$')  # 不会从头读

        super(from_redis, self).__init__(ensure_io_loop=True, **kwargs)
        self.stopped = True
        if start:
            self.start()

    def do_poll(self):
        """同步redis 库,todo:寻找异步的stream库来查询"""
        if self.consumer is not None:
            meta_msgs = self.consumer.read(count=1)

            # Returns:
            [('stream-a', [(b'1539023088125-0', {b'message': b'new a'})]),
             ('stream-b', [(b'1539023088125-0', {b'message': b'new for b'})]),
             ('stream-c', [(b'1539023088126-0', {b'message': b'c-0'})])]

            if meta_msgs:
                l = []
                for meta_msg in meta_msgs:
                    topic, msg = meta_msg[0], meta_msg[1][0]
                    msg_id, msg_body = msg
                    msg_body = msg_body.values() >> first  # {'data':'dills'}
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
    if not isinstance(body, bytes):
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
class from_http_request(Stream):
    """ receive data from http request,emit httprequest data to stream"""

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
            source = self

            @gen.coroutine
            def post(self):
                self.request.body = loads(self.request.body)
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
        """Shutdown HTTP server"""
        if not self.stopped:
            self.server.stop()
            self.server = None
            self.stopped = True


@Stream.register_api(staticmethod)
class from_command(Stream):
    """ receive command eval result data from subprocess,emit  data into stream"""

    def __init__(self, poll_interval=0.1, **kwargs):
        self.poll_interval = poll_interval
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
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, stdin=subprocess.PIPE)
        self.thread_pool.submit(self.poll_err)
        self.thread_pool.submit(self.poll_out)


@Stream.register_api(staticmethod)
class scheduler(Stream):
    """
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
    timezone (datetime.tzinfo|str) – time zone to use for the date/time calculations
    jitter (int|None) – advance or delay the job execution by jitter seconds at most.

    """

    def __init__(self, poll_interval=0.1, start=True, **kwargs):
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

    def add_job(self, name, func=None, **kwargs):
        """
        example: i.add_job(name='hello',seconds=5,start_date='2019-04-03 09:25:00')
        i.add_job(name='hello',seconds=5,start_date='2019-04-03 09:25:00')
        """
        if not func:
            def myfunc(): return self._emit(name)
        else:
            def myfunc(): return self._emit(func())
        return self._scheduler.add_job(func=myfunc, name=name, id=name, trigger='interval', **kwargs)

    def remove_job(self, name):
        return self._scheduler.remove_job(job_id=name)

    def get_jobs(self,):
        return self._scheduler.get_jobs()


# 自定义机器人的封装类
class Dtalk(Stream):
    """docstring for DtRobot"""

    def __init__(self, webhook=None, log=passed, **kwargs):
        self.log = log
        super(Dtalk, self).__init__(ensure_io_loop=True, **kwargs)
        self.webhook = maybe(webhook)\
            .or_else("https://oapi.dingtalk.com/robot/send?access_token=c7a5a2b2b23ea1677657b743e8f6ca9ffe0785ef5f378b5fdc443bb29a5defc3")

    # text类型
    @gen.coroutine
    def emit(self, msg, asynchronous=False):
        yield self.post(msg)

    @gen.coroutine
    def post(self, msg):
        from tornado.httpclient import HTTPRequest, HTTPError

        from .tornado_retry_client import RetryClient
        retry_client = RetryClient(max_retries=3)

        import json
        if isinstance(msg, bytes) or isinstance(msg, set):
            msg = str(msg)

        data = {"msgtype": "text", "text": {"content": msg},
                "at": {"atMobiles": [], "isAtAll": False}}

        post_data = json.JSONEncoder().encode(data)
        headers = {'Content-Type': 'application/json'}
        request = HTTPRequest(self.webhook, body=post_data,
                              method="POST", headers=headers, validate_cert=False)
        # validate_cert=False 服务器ssl问题解决
        try:
            result = yield retry_client.fetch(request)
            result = json.loads(result.body.decode('utf-8'))
        except HTTPError as e:
            # My request failed after 2 retries
            result = 'send dtalk eror,msg:{data},{e}'

        {'class': Dtalk, 'data': msg, 'webhook': self.webhook,
            'result': result} >> self.log


class Namespace(dict):
    def create_stream(self, stream_name, **kwargs):
        try:
            return self[stream_name]
        except KeyError:
            return self.setdefault(stream_name, Stream(stream_name=stream_name, **kwargs))


namespace = Namespace()
NS = namespace.create_stream

StreamHandler(sys.stdout).push_application()
logger = Logger(__name__)
log = NS('log', cache_max_age_seconds=60*60*24)
log.sink(logger.info)


warn = NS('warn')
warn.sink(logging.warning)

try:
    from .process import bus
except:
    bus = NS('bus')
    'bus not import,check your redis server,start a local bus ' >> warn


@atexit.register
def exit():
    'exit' >> log


class when():
    """when a  occasion(from source) appear, then do somthing 
    when('open').then(lambda :print(f'开盘啦'))
    """

    def __init__(self, occasion, source=bus):
        self.occasion = occasion
        self.source = source

    def then(self, func):
        self.source.filter(lambda x: maybe(
            x) == self.occasion).sink(lambda x: func())


def get_all_live_stream_as_stream(recent_limit=5):
    """取得当前系统运行的所有流,并生成一个合并的流做展示"""
    return engine(func=lambda: Stream.getinstances() >> pmap(lambda s: {s.name: s.recent(recent_limit)}) >> to_list, interval=1, start=True)


def gen_all_stream_recent():
    return Stream.getinstances() >> pmap(lambda s: {s.stream_name: s.recent()}) >> to_list


def gen_quant():
    import pandas as pd
    import easyquotation
    quotation_engine = easyquotation.use("sina")
    q1 = quotation_engine.market_snapshot(prefix=False)
    df = pd.DataFrame(q1).T
    df = df[(True ^ df['close'].isin([0]))]  # 昨天停牌
    df = df[(True ^ df['now'].isin([0]))]  # 今日停牌
    df['p_change'] = (df.now-df.close)/df.close
    df['code'] = df.index
    return df


def gen_block_test():
    import time
    import moment
    time.sleep(6)
    return moment.now().seconds
