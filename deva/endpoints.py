from tornado import gen
from tornado.httpclient import HTTPRequest, HTTPError
from tornado.httpclient import AsyncHTTPClient

from .pipe import passed, P
from .core import Stream
from .topic import RedisStream
from .namespace import NB
from pymaybe import maybe
import json


@Stream.register_api()
class to_kafka(Stream):
    """将数据流写入Kafka的流

    该流接受字符串或字节对象。调用 `flush` 确保所有消息都被推送。
    来自Kafka的响应会被推送到下游。

    参数
    ----------
    topic : str
        要写入的Kafka主题
    producer_config : dict
        Kafka生产者配置,参见:
        https://docs.confluent.io/current/clients/confluent-kafka-python/#configuration
        https://github.com/edenhill/librdkafka/blob/master/CONFIGURATION.md
        
        示例配置:
        bootstrap.servers: Kafka连接字符串(host:port)

    示例
    --------
    # 创建源流和Kafka流
    >>> source = Stream()
    >>> ARGS = {'bootstrap.servers': 'localhost:9092'}
    >>> kafka = source.map(str).to_kafka('test', ARGS)
    
    # 发送数据
    >>> for i in range(10):
    ...     source.emit(i)
    
    # 刷新缓冲区
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
            # 执行已投递数据的回调,在当前线程中
            # 如果没有消息发送,则不执行任何操作
            self.producer.poll(0)
            yield gen.sleep(self.polltime)

    def update(self, x, who=None):
        future = gen.Future()
        self.futures.append(future)

        @gen.coroutine
        def _():
            while True:
                try:
                    # 异步运行,在confluent-kafka的线程中
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
        """刷新生产者缓冲区,确保所有消息都被发送

        参数
        ----
        timeout : int, 可选
            超时时间(秒),默认-1表示无限等待
        """
        self.producer.flush(timeout)

@Stream.register_api()
class to_redis(Stream):
    """将上游数据写入Redis流

    该流会将上游数据写入Redis流中。支持设置最大长度限制。

    参数:
    -------
    topic : str
        Redis流的名称
    upstream : Stream, 可选
        上游流对象
    max_len : int, 可选
        Redis流的最大长度,默认100
    **kwargs : dict
        其他参数传递给Stream基类

    示例:
    -------
    # 基本用法
    s = Stream()
    s.to_redis('mystream') >> print  # 写入名为mystream的Redis流

    # 限制长度
    s.to_redis('mystream', max_len=1000)  # 限制最大1000条

    # 链式调用
    s = Stream()
    s.rate_limit(0.1).to_redis('mystream')  # 限速写入
    """

    def __init__(self, topic, upstream=None, max_len=100, **kwargs):
        Stream.__init__(self, upstream=upstream, ensure_io_loop=True)
        self.rs = RedisStream(topic=topic, max_len=max_len)
        self >> self.rs


# 自定义机器人的封装类
class Dtalk(Stream):
    """钉钉群机器人类,用于发送消息到钉钉群。

    该类继承自Stream,提供了发送文本和markdown格式消息到钉钉群的功能。
    支持同步和异步发送,支持签名验证。

    参数:
    -------
    webhook : str, 可选
        钉钉机器人的webhook地址
    secret : str, 可选  
        钉钉机器人的签名密钥
    log : Stream, 可选
        日志流对象,默认passed
    max_retries : int, 可选
        最大重试次数,默认3次
    asynchronous : bool, 可选
        是否异步发送,默认True
    **kwargs : dict
        其他参数传递给Stream基类

    示例:
    -------
    # 基本用法
    dtalk = Dtalk(webhook='https://oapi.dingtalk.com/robot/send?access_token=xxx')
    'Hello' >> dtalk  # 发送文本消息

    # 使用默认配置
    NB('dtalk_deva')['webhook'] = 'https://oapi.dingtalk.com/robot/send?access_token=xxx'
    NB('dtalk_deva')['secret'] = 'SEC085714c31cxxxxxxx'
    dtalk = Dtalk()  # 使用默认配置

    # 发送markdown消息
    '@md@标题|正文内容' >> dtalk

    # 同步发送
    dtalk.send('Hello')  # 同步方式发送
    """

    def __init__(self, webhook=None, secret=None, log=passed,
                 max_retries=3, asynchronous=True, **kwargs):
        self.log = log
        super(Dtalk, self).__init__(ensure_io_loop=True, **kwargs)

        self.client = AsyncHTTPClient()
        self.secret = secret
        self.webhook = webhook
        if not webhook:
            self.webhook = maybe(NB('dtalk_deva'))['webhook'].or_else(None)
            self.secret = maybe(NB('dtalk_deva'))['secret'].or_else(None)
            if not self.webhook:
                raise Exception("""please input a webhook,or set a default webhook and secret to NB("dtalk")["test"] like this:
                    NB('dtalk_deva')['webhook']='https://oapi.dingtalk.com/robot/send?access_token=xxx'
                    NB('dtalk_deva')['secret']='SEC085714c31cxxxxxxx'
                    """)

    def get_sign_url(self,):
        """生成带签名的webhook URL

        如果设置了secret,会根据时间戳和密钥生成签名。
        否则直接返回原始webhook URL。

        Returns:
            str: 带签名的webhook URL
        """
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
            url = self.webhook + f'&timestamp={timestamp}&sign={sign}'
        else:
            url = self.webhook

        return url

    @gen.coroutine
    def emit(self, msg: str, asynchronous=False):
        """发送消息的入口方法

        Args:
            msg (str): 要发送的消息内容
            asynchronous (bool, optional): 是否异步发送. Defaults to False.
        """
        super().emit(msg)
        yield self.post(msg, self.log)

    @gen.coroutine
    def post(self, msg: str, log: Stream):
        """实际发送消息到钉钉的方法

        支持文本和markdown两种格式:
        - 普通文本直接发送
        - markdown格式需要以@md@开头,并用|分隔标题和正文

        Args:
            msg (str): 消息内容
            log (Stream): 日志流对象

        Returns:
            dict: 包含发送结果的字典
        """
        # 二进制或者set类型的,转成json格式前需要先转类型
        msg = str(msg)

        data = {"msgtype": "text", "text": {"content": msg},
                "at": {"atMobiles": [], "isAtAll": '@all' in msg}}

        if msg.startswith('@md@'):
            # @md@财联社新闻汇总|text
            content = msg[4:]
            title, text = content[:content.index(
                '|')], content[content.index('|') + 1:]
            data = {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": text, "content": text}
            }

        post_data = json.JSONEncoder().encode(data)
        # import urllib
        # post_data = urllib.parse.urlencode(data)

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

    def send(self, msg):
        """同步方式发送消息

        Args:
            msg: 要发送的消息内容

        Returns:
            发送结果
        """
        # 同步的发送
        from .core import sync
        return sync(self.loop, self.emit, msg)


@P
def mail(to='zjw0358@gmail.com'):
    """发送邮件的函数装饰器

    该函数用于发送邮件,支持发送文本内容和DataFrame表格。
    需要在NB('mail')中配置邮箱服务器信息。

    参数:
    -------
    to : str, 可选
        收件人邮箱地址,默认'zjw0358@gmail.com'

    配置示例:
    -------
    NB('mail')['username'] = 'sender@example.com'  # 发件人邮箱
    NB('mail')['password'] = 'password'  # 邮箱密码
    NB('mail')['hostname'] = 'smtp.example.com'  # SMTP服务器地址

    示例:
    -------
    # 发送简单文本
    'Hello' >> mail() >> print  # 发送文本内容
    
    # 发送带主题
    ('主题', '正文内容') >> mail('recipient@example.com')
    
    # 发送DataFrame
    import pandas as pd
    df = pd.DataFrame({'a':[1,2], 'b':[3,4]})
    df >> mail()  # 发送表格
    """
    import pandas as pd
    from email.message import EmailMessage
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    async def _send(content):
        username = NB('mail')['username']
        password = NB('mail')['password'] 
        hostname = NB('mail')['hostname']
        if isinstance(content, tuple):
            subject = content[0]
            content = content[1]
        else:
            subject = 'deva message'

        if isinstance(content, pd.DataFrame):
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message.attach(MIMEText(content.to_html(), "html", "utf-8"))
        else:
            content = str(content)
            message = EmailMessage()
            message["Subject"] = subject+':'+content[:10]
            message.set_content(str(content))

        message["To"] = to
        message["From"] = username

        return await aiosmtplib.send(message, hostname=hostname, port=465, use_tls=True, username=username, password=password)

    def run(content):
        return _send(content)

    return run @ P

if __name__ == '__main__':
    123 >> Dtalk()
    from .core import Deva
    Deva().run()