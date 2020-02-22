from .tornado_retry_client import RetryClient
from tornado import gen
from tornado.httpclient import HTTPRequest, HTTPError
from .pipe import passed
from .stream import Stream
from pymaybe import maybe
import json


# 自定义机器人的封装类
class Dtalk(Stream):
    """钉钉群机器人."""

    def __init__(self, webhook=None, secret=None, log=passed, max_retries=3, asynchronous=True, **kwargs):
        # todo 实现一个同步的dtalk
        self.log = log
        super(Dtalk, self).__init__(ensure_io_loop=True, **kwargs)

        self.retry_client = RetryClient(max_retries=max_retries)
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
            response = yield self.retry_client.fetch(request)
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
