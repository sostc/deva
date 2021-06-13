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
    写入异步，所以为了避免下游读取消化慢，max_len设置要足够长，防止丢数据
    exapmle::

        news = Stream.RedisStream('news',max_len=1000)
        l = list()
        news>>l
        for i in range(1000):
            i>>news

        l|len

    """

    def __init__(self, topic, start=True,
                 group=None, max_len=100, address='redis://localhost', db=0, password=None, **kwargs):
        self.topic = topic
        self.redis_address = address
        self.redis_password = password
        if not group:
            group = hash(self)+hash(time.time())
        self.group = group
        self.consumer = hash(self)
        self.max_len = max_len

        super(RedisStream, self).__init__(ensure_io_loop=True, **kwargs)
        self.redis = None
        self.stopped = True
        if start:
            self.start()

    @gen.coroutine
    def process(self):
        if not self.redis:
            self.redis = yield aioredis.create_redis(self.redis_address, password=self.redis_password, loop=self.loop)

        exists = yield self.redis.exists(self.topic)
        if not exists:
            yield self.redis.xadd(self.topic, {'data': dill.dumps('go')})
        try:
            yield self.redis.xgroup_create(self.topic, self.group)
        except Exception as e:
            print(e)

        while True:
            result = yield self.redis.xread_group(self.group, self.consumer, [self.topic], count=1, latest_ids=['>'])
            data = dill.loads(result[0][2][b'data'])
            self._emit(data)
            if self.stopped:
                break

    @gen.coroutine
    def _send(self, data):
        if not self.redis:
            self.redis = yield aioredis.create_redis(self.redis_address, password=self.redis_password, loop=self.loop)
        yield self.redis.xadd(self.topic, {'data': dill.dumps(data)}, max_len=self.max_len)

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

    def __init__(self, name='', maxsize=None,  **kwargs):
        super().__init__(topic=name,
                         group=str(os.getpid()),
                         start=True,
                         name=name,
                         **kwargs)
