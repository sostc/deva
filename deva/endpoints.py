from tornado import gen
from tornado.httpclient import HTTPRequest, HTTPError
from tornado.httpclient import AsyncHTTPClient

from .pipe import passed
from .core import Stream
from .topic import RedisStream
from pymaybe import maybe
import json


@Stream.register_api()
class to_kafka(Stream):
    """ Writes data in the stream to Kafka

    This stream accepts a string or bytes object. Call ``flush`` to ensure all
    messages are pushed. Responses from Kafka are pushed downstream.

    Parameters
    ----------
    topic : string
        The topic which to write
    producer_config : dict
        Settings to set up the stream, see
        https://docs.confluent.io/current/clients/confluent-kafka-python/#configuration
        https://github.com/edenhill/librdkafka/blob/master/CONFIGURATION.md
        Examples:
        bootstrap.servers: Connection string (host:port) to Kafka

    Examples
    --------
    >>> from streamz import Stream
    >>> ARGS = {'bootstrap.servers': 'localhost:9092'}
    >>> source = Stream()
    >>> kafka = source.map(lambda x: str(x)).to_kafka('test', ARGS)
    <to_kafka>
    >>> for i in range(10):
    ...     source.emit(i)
    >>> kafka.flush()
    """

    def __init__(self, upstream, topic, producer_config, **kwargs):
        import confluent_kafka as ck

        self.topic = topic
        self.producer = ck.Producer(producer_config)

        Stream.__init__(self, upstream, ensure_io_loop=True, **kwargs)
        self.stopped = False
        self.polltime = 0.2
        self.loop.add_callback(self.poll)
        self.futures = []

    @gen.coroutine
    def poll(self):
        while not self.stopped:
            # executes callbacks for any delivered data, in this thread
            # if no messages were sent, nothing happens
            self.producer.poll(0)
            yield gen.sleep(self.polltime)

    def update(self, x, who=None):
        future = gen.Future()
        self.futures.append(future)

        @gen.coroutine
        def _():
            while True:
                try:
                    # this runs asynchronously, in C-K's thread
                    self.producer.produce(self.topic, x, callback=self.cb)
                    return
                except BufferError:
                    yield gen.sleep(self.polltime)
                except Exception as e:
                    future.set_exception(e)
                    return

        self.loop.add_callback(_)
        return future

    @gen.coroutine
    def cb(self, err, msg):
        future = self.futures.pop(0)
        if msg is not None and msg.value() is not None:
            future.set_result(None)
            yield self._emit(msg.value())
        else:
            future.set_exception(err or msg.error())

    def flush(self, timeout=-1):
        self.producer.flush(timeout)


@Stream.register_api()
class to_redis(Stream):

    def __init__(self, upstream, topic, max_len=100, **kwargs):
        Stream.__init__(self, upstream=upstream, ensure_io_loop=True)
        self.rs = RedisStream(topic=topic, max_en=max_len)
        self >> self.rs


# 自定义机器人的封装类
class Dtalk(Stream):
    """钉钉群机器人."""

    def __init__(self, webhook=None, secret=None, log=passed, max_retries=3, asynchronous=True, **kwargs):
        # todo 实现一个同步的dtalk
        self.log = log
        super(Dtalk, self).__init__(ensure_io_loop=True, **kwargs)

        self.client = AsyncHTTPClient()
        self.secret = secret
        self.webhook = webhook
        if not webhook:
            self.webhook = maybe(webhook).or_else(
                "https://oapi.dingtalk.com/robot/send?access_token="
                "c7a5a2b2b23ea1677657b743e8f6ca9"
                "ffe0785ef5f378b5fdc443bb29a5defc3")
            self.secret = 'SEC085714c31c3621f773d892d67d436be64d32227a248a84320f74a1733588fc35'

    # text类型

    def get_sign_url(self,):
        if self.secret:
            import time
            import hmac
            import hashlib
            import base64
            import urllib
            timestamp = int(round(time.time() * 1000))
            secret_enc = self.secret.encode('utf-8')
            string_to_sign = '{}\n{}'.format(timestamp, self.secret)
            string_to_sign_enc = string_to_sign.encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign_enc,
                                 digestmod=hashlib.sha256).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            url = self.webhook+f'&timestamp={timestamp}&sign={sign}'
        else:
            url = self.webhook

        return url

    @gen.coroutine
    def emit(self, msg: str, asynchronous=False) -> dict:
        yield self.post(msg, self.log)

    @gen.coroutine
    def post(self, msg: str, log: Stream) -> dict:
        # 二进制或者set类型的,转成json格式前需要先转类型
        if isinstance(msg, bytes) or isinstance(msg, set):
            msg = str(msg)
        data = {"msgtype": "text", "text": {"content": msg},
                "at": {"atMobiles": [], "isAtAll": False}}
        if isinstance(msg, str) and '@all' in msg:
            data = {"msgtype": "text", "text": {"content": msg},
                    "at": {"atMobiles": [], "isAtAll": True}}
        elif isinstance(msg, str) and msg.startswith('@md@'):
            # @md@财联社新闻汇总|text
            content = msg[4:]
            title, text = content[:content.index(
                '|')], content[content.index('|')+1:]
            data = {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": text}
            }

        post_data = json.JSONEncoder().encode(data)

        headers = {'Content-Type': 'application/json'}

        url = self.get_sign_url()

        request = HTTPRequest(
            url,
            body=post_data,
            method="POST",
            headers=headers,
            validate_cert=False)
        # validate_cert=False 服务器ssl问题解决
        try:
            # response = yield self.retry_client.fetch(request)
            response = yield self.client.fetch(request)
            result = json.loads(response.body.decode('utf-8'))
        except HTTPError as e:
            result = f"send dtalk eror,msg:{data},{e}"

        return {'class': 'Dtalk',
                'msg': msg,
                'webhook': self.webhook,
                'result': result,
                } >> log


if __name__ == '__main__':
    123 >> Dtalk()
