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

    def __init__(self, webhook=None, log=passed, max_retries=3, **kwargs):
        self.log = log
        super(Dtalk, self).__init__(ensure_io_loop=True, **kwargs)
        self.webhook = maybe(webhook).or_else(
            "https://oapi.dingtalk.com/robot/send?access_token="
            "c7a5a2b2b23ea1677657b743e8f6ca9"
            "ffe0785ef5f378b5fdc443bb29a5defc3")
        self.retry_client = RetryClient(max_retries=max_retries)

    # text类型
    @gen.coroutine
    def emit(self, msg: str, asynchronous=False) -> dict:
        yield self.post(msg, self.webhook, self.log)

    @gen.coroutine
    def post(self, msg: str, webhook: str, log: Stream) -> dict:
        # 二进制或者set类型的,转成json格式前需要先转类型
        if isinstance(msg, bytes) or isinstance(msg, set):
            msg = str(msg)
        data = {"msgtype": "text", "text": {"content": msg},
                "at": {"atMobiles": [], "isAtAll": False}}
        post_data = json.JSONEncoder().encode(data)

        headers = {'Content-Type': 'application/json'}
        request = HTTPRequest(
            webhook,
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
                'webhook': webhook,
                'result': result,
                } >> log


if __name__ == '__main__':
    123 >> Dtalk()
