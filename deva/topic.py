from .core import Stream, sync
from tornado import gen
import aioredis
import dill
import logging
import os
import time

logger = logging.getLogger(__name__)


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
            result = yield self.redis.xread(count=1, block=500, streams={self.topic: '$'})
            if result:
                data = dill.loads(result[0][1][0][1][b'data'])
                self._emit(data)
                if self.stopped:
                    break

    @gen.coroutine
    def _send(self, data):
        if not self.redis:
            self.redis = yield aioredis.Redis(host=self.redis_address, password=self.redis_password)
        yield self.redis.xadd(self.topic, {'data': dill.dumps(data)})

    def emit(self, x, asynchronous=True):
        self.loop.add_callback(self._send, x)
        return x

    def start(self):
        if self.stopped:
            self.stopped = False
            self.loop.add_callback(self.process)

    def stop(self,):
        self.stopped = True
        self.redis.close()


@Stream.register_api()
class Topic(RedisStream):

    def __init__(self, name='', group=str(os.getpid()), maxsize=None,  **kwargs):
        super().__init__(topic=name,
                         group=group,
                         start=True,
                         name=name,
                         **kwargs)
