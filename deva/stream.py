import json
import time
from tornado import gen

from .streamz.core import Stream as Streamz
#from .streamz_ext import Stream as Streamz
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.httpserver import HTTPServer
from tornado.queues import Queue
from tornado.iostream import StreamClosedError


import weakref

import subprocess
from tornado.web import Application, RequestHandler
from .pipe import *
from .expiringdict import ExpiringDict
import datetime

import os
from dataclasses import dataclass,field

import dill

class Stream(Streamz):
    _graphviz_shape = "doubleoctagon"
    
    _instances = set()
    
    def __init__(self,name=None,store=True,cache_max_len=1, cache_max_age_seconds=60*5,*args,**kwargs):
        self.cache_max_len = cache_max_len
        self.cache_max_age_seconds = cache_max_age_seconds
        
        super(Stream,self).__init__(*args,**kwargs)
        self.name=name
        self._instances.add(weakref.ref(self))
        if store:
            self._store_recent()
            
    
    @classmethod
    def getinstances(cls):
        dead = set()
        for ref in cls._instances:
            obj = ref()
            if obj is not None  and obj.name is not None and not obj.name.startswith('_'):
                yield obj
            else:
                dead.add(ref)
        cls._instances -= dead
        

    def write(self, value):  # |
        """emit value to stream ,end,return emit result"""
        self.emit(value)

    def send(self, value):  # |
        """emit value to stream ,end,return emit result"""
        self.emit(value)

    def to_redis_stream(self, topic, db=None,maxlen=None):
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
        madd = F(producer.add,maxlen=maxlen)
        self.map(lambda x: {"data": dill.dumps(x)}).sink(
            madd)  # producer only accept non-empty dict dict
        return self

    def to_web_stream(self, name=None,app=None):
        """输出web_stream需要先启动start_web_stream_server"""
        if name:
            url = r'/'+name
        else:
            url = r'/'+self.name

        app.add_handlers(r".*",  [(url,EventSource, {'stream': self})])                 
        
    
    def to_share(self,name=None):
        if not name:
            name = self.name
                    
        self.to_redis_stream(topic=name,maxlen=10)
        return self
            
    @classmethod
    def from_share(cls,name,**kwargs):
        #使用pid做group,区分不同进程消费,一个进程消费结束,不影响其他进程继续消费
        return cls.from_redis(name,start=True,group=str(os.getpid()),**kwargs).map(lambda x:x.msg_body)
    
    @classmethod
    def from_tcp(cls,port=1234,**kwargs):
        def dec(x):
            try:
                return dill.loads(x)
            except:
                return x
        return Streamz.from_tcp(port,start=True,**kwargs).map(dec)
            
    def _store_recent(self):#second
        self._cache = ExpiringDict(max_len=self.cache_max_len, max_age_seconds=self.cache_max_age_seconds)
        def _store(x):
            key = datetime.datetime.now()
            value = x
            self._cache[key]=value
             
        self.sink(_store)
  
    def recent(self,n=5,seconds=None):
        if not seconds:
            return self._cache.values()[-n:]
        else:
            df = self._cache>>to_dataframe
            df.columns = ['value']
            now_time = datetime.datetime.now()
            begin = now_time + datetime.timedelta(seconds=-seconds)
            return df[begin:]
    




class EventSource(RequestHandler):
    def initialize(self, stream):
        #assert isinstance(stream, Stream)
        self.stream = stream
        self.messages = Queue()
        self.finished = False
        self.set_header('content-type', 'text/event-stream')
        self.set_header('cache-control', 'no-cache')
        self.store = self.stream.sink(self.messages.put)

    @gen.coroutine
    def publish(self, message):
        """Pushes data to a listener."""
        try:
            self.write(message>>to_str)
            yield self.flush()
        except StreamClosedError:
            self.finished = True
            (self.request.remote_ip,StreamClosedError)>>log

    @gen.coroutine
    def get(self, *args, **kwargs):
        try:
            while not self.finished:
                message = yield self.messages.get()
                yield self.publish(message)
        except Exception:
            pass
        finally:
            self.store.destroy()
            self.messages.empty()
            self.finish()


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

class HTTPStreamHandler(RequestHandler):
    output = None
    def post(self, *args, **kwargs):
        self.request.body = loads(self.request.body)   
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



@Stream.register_api(staticmethod)
class from_command(Stream):
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




            
            
            
@Stream.register_api(staticmethod)
class manager(Stream):
    def __init__(self,interval=1, start=True,**kwargs):
        
        self.interval = interval
        self.stopped = True
        super(manager, self).__init__(ensure_io_loop=True, **kwargs)
        if start:
            self.start()
            
        self.name='_stream_manager'
 
    def do_poll(self):
        return 

    @gen.coroutine
    def poll_manage(self):
        while True:
            vals = Stream.getinstances()>>pmap(lambda s:{s.name:s.recent()})
            self._emit(vals)

            yield gen.sleep(self.interval)
            if self.stopped:
                break

    def start(self):
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.poll_manage)

    def stop(self):
       self.stopped = True
                      
            
class NamedStream(Stream):
    """A named generic notification emitter."""

    def __init__(self, name,**kwds):
        Stream.__init__(self,**kwds)

        #: The name of this stream.
        self.name = name

    def __repr__(self):
        base = Stream.__repr__(self)
        return "%s; %r>" % (base[:-1], self.name)


class Namespace(dict):
    """A mapping of signal names to signals."""

    def stream(self, name, **kwds):
        """Return the :class:`NamedSignal` *name*, creating it if required.
        Repeated calls to this function will return the same signal object.
        """
        try:
            return self[name]
        except KeyError:
            return self.setdefault(name, NamedStream(name,**kwds))


namedstream = Namespace().stream
NS = namedstream

from logbook import Logger,StreamHandler
import sys
StreamHandler(sys.stdout).push_application()
logger = Logger(__name__)
log = NS('log',cache_max_age_seconds=60*60*24)
log.sink(logger.info)


import logging
warn = NS('warn')
warn.sink(logging.warning)



try:
    from .process import bus
except:
    'bus not import,check your redis server  '>>warn

def start_web_stream_server(port=9999):
    """输出web_stream需要先启动start_web_stream_server"""
    stream_index = Stream.manager().map(lambda x:x>>to_list)
    app = Application([(r'/', EventSource, {'stream': stream_index})],debug=True)
    http_server = HTTPServer(app, xheaders=True)
        # 最原始的方式
    http_server.bind(port)
    http_server.start()


def get_all_live_stream_as_stream(recent_limit=5):
    """取得当前系统运行的所有流,并生成一个合并的流做展示"""
    return engine(func=lambda :Stream.getinstances()>>pmap(lambda s:{s.name:s.recent(recent_limit)})>>to_list,interval=1,start=True)


def write_to_file(fn,prefix='', suffix='\n', flush=True):
    def write(text):
        with open(fn, 'a+') as f:
            f.write(prefix + str(text) + suffix)
            #if flush:
                #f.flush()
        return text
        
    return write



    
def gen_quant():
    import pandas as pd
    import easyquotation
    quotation_engine = easyquotation.use("sina")
    q1 = quotation_engine.all
    df = pd.DataFrame(q1).T
    df = df[(True^df['close'].isin([0]))]
    df['p_change']=(df.now-df.close)/df.close
    df['code']=df.index
    return df


def gen_test():
    import moment as mm
    return mm.now().seconds


def gen_block_test():
    import moment as mm
    import time
    time.sleep(6)
    return mm.now().seconds
    
  
