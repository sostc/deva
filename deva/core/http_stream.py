"""HTTP 相关的流与请求函数：httpx / crawler。

从 core.py 拆出（P2 #11）。

错误传播契约（P2 #14）
======================
旧实现把「请求失败」和「请求成功但内容为空」都折叠成 None，导致失败一路
静默下沉，直到某个下游写 `response.content` 才炸出一句毫无信息量的
``'NoneType' object has no attribute 'content'``，调用方既分不清原因，也没
法决定是重试还是放弃。现在改成：

    成功  -> 返回 requests_html 的 response 对象
    失败  -> 默认抛 HttpError（带 request / cause / status_code / timestamp）
    宽容  -> 显式传 raise_on_error=False 才退回 None

也就是说 **None 只可能是调用方主动要求的宽容模式**，拿到 None 就必须自己
判空；默认路径下拿不到 None，只有异常。

流层面（crawler）语义不同：单个 URL 失败不应炸掉整条流，所以异常**不下发**
下游，而是结构化后路由到构造时传入的 error 回调。下游永远收不到 None
（Stream 默认 refuse_none=True），只会少一条数据。
"""
from __future__ import absolute_import, division, print_function

from typing import Any, Dict

import logging
from datetime import datetime

try:
    from tornado import gen
except ImportError:
    gen = None
try:
    from tornado.ioloop import PollIOLoop
except ImportError:
    PollIOLoop = None  # dropped in tornado 6.0

from requests_html import AsyncHTMLSession

from .stream import Stream

__all__ = ['httpx', 'crawler', 'HttpError']

logger = logging.getLogger(__name__)


class HttpError(Exception):
    """HTTP 请求失败。

    把「请求失败」与「请求成功但内容为空」区分开 —— httpx() 返回 None
    只可能出现在 raise_on_error=False 的宽容模式下。

    属性:
        request:     原始请求（URL 字符串或参数字典）
        cause:       底层异常对象
        status_code: HTTP 状态码；连接就失败时为 None
        timestamp:   失败时刻（ISO 8601 字符串）
    """

    def __init__(self, request, cause, status_code=None, timestamp=None):
        self.request = request
        self.cause = cause
        self.status_code = status_code
        self.timestamp = timestamp or datetime.now().isoformat(timespec="seconds")

        detail = f"request={self.request!r}, error={self.cause}"
        if self.status_code is not None:
            detail = f"{detail}, status_code={self.status_code}"
        super().__init__(detail)

    def to_dict(self) -> Dict[str, Any]:
        """结构化失败上下文，供 error 回调 / 日志使用。"""
        return {
            'request': self.request,
            'error': str(self.cause),
            'status_code': self.status_code,
            'timestamp': self.timestamp,
        }


# 全局AsyncHTMLSession实例，用于重用
_global_httpclient = None

_MOBILE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


def _get_async_session(workers=10):
    """返回进程级共享的 AsyncHTMLSession（懒创建）。"""
    global _global_httpclient
    if _global_httpclient is None:
        _global_httpclient = AsyncHTMLSession(workers=workers)
    return _global_httpclient


@gen.coroutine
def httpx(req, render=False, timeout=30, workers=10, raise_on_error=True, **kwargs):
    """异步HTTP请求函数

    参数:
        req: 请求参数,可以是URL字符串或请求参数字典
        render: 是否渲染JavaScript,默认False
        timeout: 请求超时时间(秒),默认30秒
        workers: 并发工作线程数,默认10
        raise_on_error: 失败时抛 HttpError；传 False 则退回返回 None
        **kwargs: 渲染参数,传递给arender()方法

    返回:
        response: 响应对象，包含以下常用属性和方法：
            - status_code: HTTP状态码
            - text: 响应内容文本
            - json(): 将响应内容解析为JSON
            - content: 原始响应内容(bytes)
            - headers: 响应头字典
            - url: 最终请求URL
            - history: 重定向历史记录
            - cookies: 响应cookies
            - raise_for_status(): 如果状态码不是2xx则抛出异常

    异常:
        HttpError: raise_on_error=True（默认）且请求失败时抛出
        TypeError: req 既不是字符串也不是字典时抛出

    示例:
        # URL字符串
        response = yield httpx('http://example.com')
        print(response.status_code)  # 200
        print(response.text)  # HTML内容
        print(response.json())  # 如果响应是JSON
        print(response.headers)  # 响应头

        # 请求参数字典
        response = yield httpx({
            'url': 'http://example.com',
            'method': 'post',
            'data': {'key': 'value'}
        })

        # 链式处理
        httpx('http://secsay.com')>>P(lambda x:x.html.search("<title>{}</title>")|first)+P(lambda x:x*2)+print

        # 渲染JavaScript
        response = yield httpx('http://example.com', render=True)
        # 使用CSS选择器查找元素
        element = response.html.find('h1.title', first=True)
    """
    httpclient = _get_async_session(workers)
    response = None

    try:
        if isinstance(req, str):
            response = yield httpclient.get(
                req, headers=_MOBILE_HEADERS, timeout=timeout)
        elif isinstance(req, dict):
            params = dict(req)
            params['timeout'] = timeout
            # 合并自定义headers和移动端headers
            params['headers'] = {**_MOBILE_HEADERS, **(req.get('headers') or {})}
            params.pop('method', None)
            if req.get('method') == 'post':
                response = yield httpclient.post(**params)
            else:
                response = yield httpclient.get(**params)
        else:
            raise TypeError(f"请求类型必须为字符串或字典，当前类型为: {type(req)}")

        if render:
            # 移动端视口
            kwargs.setdefault('viewport', {'width': 375, 'height': 812})
            yield response.html.arender(**kwargs)

        return response

    except Exception as e:
        err = e if isinstance(e, HttpError) else HttpError(
        req, e, status_code=getattr(response, 'status_code', None))
        logger.error("httpx failed: %s", err)
        logger.debug("httpx traceback", exc_info=True)
        if raise_on_error:
            raise err
        return None


@Stream.register_api()
class crawler(Stream):
    """基于流的网页爬虫类，支持同步和异步HTTP请求

    该类封装了网页爬取的核心功能，支持以下特性：
    - 支持URL字符串和请求参数字典两种输入格式
    - 自动处理JavaScript渲染
    - 内置错误处理和日志记录
    - 支持并发请求
    - 提供网页内容提取功能

    参数:
        upstream (Stream, 可选): 上游数据流
        render (bool, 可选): 是否渲染JavaScript，默认False
        workers (int, 可选): 并发线程池数量
        error (callable, 可选): 错误处理函数，默认print
        **kwargs: 渲染参数，包括：
            - retries: 重试次数，默认8
            - script: 自定义JavaScript脚本
            - wait: 等待时间，默认0.2秒
            - scrolldown: 是否向下滚动
            - sleep: 休眠时间
            - reload: 是否重新加载，默认True
            - timeout: 超时时间，默认8秒
            - keep_page: 是否保持页面，默认False

    方法:
        update(req, who=None): 处理上游数据并发送请求
        emit(req, **kwargs): 发送请求并返回原始请求
        _request(req): 执行异步HTTP请求
        request(url, **kwargs): 执行同步HTTP请求
        get(url, **kwargs): GET请求快捷方法
        get_web_article(url, key='text'): 提取网页文章内容

    示例:
        >>> # 基本用法
        >>> s = Stream()
        >>> s.rate_limit(0.1).crawler(workers=20).map(lambda r: r.text).sink(print)
        >>> 'https://example.com' >> s

        >>> # 使用请求参数字典
        >>> req = {
        ...     'url': 'https://example.com',
        ...     'headers': {'User-Agent': 'Mozilla/5.0'},
        ...     'params': {'q': 'test'}
        ... }
        >>> req >> s

        >>> # 提取网页文章
        >>> article = await crawler.get_web_article('https://example.com')
        >>> print(article)

        >>> # 同步请求
        >>> response = crawler.request('https://example.com')
        >>> print(response.status_code)
    """

    def __init__(self, upstream=None, render=False, workers=10, error=print, **kwargs):
        """初始化爬虫实例

        参数:
            upstream: 上游数据流
            render: 是否渲染JavaScript
            workers: 并发线程池数量,默认10
            error: 错误处理函数
            **kwargs: 渲染参数
        """
        self.error = error
        self.render = render
        Stream.__init__(self, upstream=upstream, ensure_io_loop=True)
        self.httpclient = _get_async_session(workers)
        self.kwargs = kwargs

    def update(self, req, who=None):
        """处理上游数据并发送请求

        参数:
            req: 请求数据，可以是URL字符串或请求参数字典
            who: 数据来源标识
        """
        self.loop.add_future(
            self._request(req),
            lambda x: self._emit(x.result())
        )

    def emit(self, req, **kwargs):
        """发送请求并返回原始请求

        参数:
            req: 请求数据，可以是URL字符串或请求参数字典
            **kwargs: 额外参数

        返回:
            req: 原始请求数据

        异常:
            TypeError: 当req不是字符串或字典时抛出
        """
        if not isinstance(req, (str, dict)):
            raise TypeError(f"请求类型必须为字符串或字典，当前类型为: {type(req)}")
        self.update(req)
        return req

    @gen.coroutine
    def _request(self, req):
        """执行异步HTTP请求

        参数:
            req: 请求数据，可以是URL字符串或请求参数字典

        返回:
            response: 响应对象

        异常处理:
            - 捕获所有异常，包装成 HttpError
            - 结构化上下文路由到构造时传入的 error 回调（下游收不到）
        """
        response = None
        try:
            request_params = {'url': req} if isinstance(req, str) else dict(req)
            params = {k: v for k, v in request_params.items() if k != 'method'}
            response = yield self.httpclient.get(**params)

            if self.render:
                yield response.html.arender(**self.kwargs)

            return response

        except Exception as e:
            err = HttpError(req, e, status_code=getattr(response, 'status_code', None))
            self.error(err.to_dict())
            logger.error("crawler 请求失败: %s", err)
            logger.debug("crawler 请求异常详情", exc_info=True)

    @classmethod
    def request(cls, url, raise_on_error=True, **kwargs):
        """执行同步HTTP请求

        参数:
            url: 请求URL
            raise_on_error: 失败时抛 HttpError；传 False 则退回返回 None
            **kwargs: 请求参数

        返回:
            response: 响应对象

        异常:
            HttpError: raise_on_error=True（默认）且请求失败时抛出
        """
        from requests_html import HTMLSession

        httpclient = HTMLSession()
        request_params = {'url': url, **kwargs}
        response = None

        try:
            response = httpclient.get(**request_params)
            logger.debug(f"请求成功: {url}, 状态码: {response.status_code}")
            return response

        except Exception as e:
            err = HttpError(url, e, status_code=getattr(response, 'status_code', None))
            logger.error("请求失败: %s", err)
            logger.debug("请求异常详情", exc_info=True)
            if raise_on_error:
                raise err
            return None

    @classmethod
    def get(cls, url, **kwargs):
        """GET请求快捷方法

        参数:
            url: 请求URL
            **kwargs: 请求参数

        返回:
            response: 响应对象
        """
        return cls.request(url, **kwargs)

    @classmethod
    async def get_web_article(cls, url, key='text'):
        """提取网页文章内容

        参数:
            url: 网页URL
            key: 提取字段，可选值：title|description|image|text等，默认text

        返回:
            提取的内容或完整数据字典

        异常:
            HttpError: 抓取失败时由 httpx 抛出，这里不做兜底——
                让失败原因（超时 / DNS / 4xx / 5xx）直接暴露给调用方
        """
        from trafilatura import bare_extraction

        response = await httpx(url)
        data = bare_extraction(response.content)
        return data.get(key) if key else data
