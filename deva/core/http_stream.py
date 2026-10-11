"""HTTP 相关的流与请求函数：httpx / crawler。

从 core.py 拆出（P2 #11）。
"""
from __future__ import absolute_import, division, print_function

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

__all__ = ['httpx', 'crawler']

logger = logging.getLogger(__name__)


# 全局AsyncHTMLSession实例，用于重用
_global_httpclient = None

@gen.coroutine
def httpx(req, render=False, timeout=30, workers=10, **kwargs):
    """异步HTTP请求函数

    参数:
        req: 请求参数,可以是URL字符串或请求参数字典
        render: 是否渲染JavaScript,默认False
        timeout: 请求超时时间(秒),默认30秒
        workers: 并发工作线程数,默认10
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
            - html: 包含以下方法：
                * find(selector): 使用CSS选择器查找元素
                * xpath(expr): 使用XPath查找元素
                * arender(**kwargs): 异步渲染JavaScript
                * search(template): 使用模板搜索内容
                * absolute_links: 获取所有绝对链接

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
    # 移动端浏览器User-Agent
    mobile_headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    global _global_httpclient
    if _global_httpclient is None:
        print(f"Initializing global HTTP client with {workers} workers")
        _global_httpclient = AsyncHTMLSession(workers=workers)
        print(f"Global HTTP client initialized: {_global_httpclient}")
    httpclient = _global_httpclient
    
    try:
        if isinstance(req, str):
            # 添加移动端headers
            response = yield httpclient.get(req, headers=mobile_headers, timeout=timeout)
        elif isinstance(req, dict):
            req['timeout'] = timeout  # 将超时参数添加到请求字典
            # 合并自定义headers和移动端headers
            req['headers'] = {**mobile_headers, **req.get('headers', {})}
            if req.get('method') == 'post':
                response = yield httpclient.post(**req)
            else:
                response = yield httpclient.get(**req)

        if render:
            # 设置移动端视口大小
            kwargs.setdefault('viewport', {'width': 375, 'height': 812})
            yield response.html.arender(**kwargs)

        return response
    except Exception as e:
        logger.error("crawler failed, req=%s, error=%s", req, e)
        logger.exception(e)
        # 即使出现异常，也返回None而不是抛出异常，这样测试脚本可以继续执行
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
        global _global_httpclient
        if _global_httpclient is None:
            _global_httpclient = AsyncHTMLSession(workers=workers)
        self.httpclient = _global_httpclient
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
            - 捕获所有异常并记录日志
            - 将错误信息通过error流输出
            - 保持请求上下文信息
        """
        try:
            request_params = {'url': req} if isinstance(req, str) else req
            response = yield self.httpclient.get(**request_params)

            if self.render:
                yield response.html.arender(**self.kwargs)

            return response

        except Exception as e:
            error_context = {
                'request': req,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            error_context >> self.error
            logger.exception(f"请求失败: {error_context}")

    @classmethod
    def request(cls, url, **kwargs):
        """执行同步HTTP请求

        参数:
            url: 请求URL
            **kwargs: 请求参数

        返回:
            response: 响应对象

        异常:
            捕获所有异常并记录日志，但不中断程序执行
        """
        from requests_html import HTMLSession

        httpclient = HTMLSession()
        request_params = {'url': url, **kwargs}

        try:
            response = httpclient.get(**request_params)
            logger.debug(f"请求成功: {url}, 状态码: {response.status_code}")
            return response

        except Exception as e:
            logger.error(f"请求失败: {url}, 错误: {str(e)}")
            logger.exception("请求异常详情:")
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
        """
        from trafilatura import bare_extraction

        response = await httpx(url)
        data = bare_extraction(response.content)
        return data.get(key) if key else data
