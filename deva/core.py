from __future__ import absolute_import, division, print_function
import os

import collections
from datetime import datetime, timedelta
import functools
import logging
import six
import sys
import threading
import weakref
import inspect

import toolz
from tornado import gen
from tornado.ioloop import IOLoop
try:
    from tornado.ioloop import PollIOLoop
except ImportError:
    PollIOLoop = None  # dropped in tornado 6.0

from expiringdict import ExpiringDict
from pampy import match, ANY
import io
from .pipe import P, print
from threading import get_ident as get_thread_identity
from requests_html import AsyncHTMLSession

"""
deva 是一个基于 Python 的异步流式处理框架。它提供了以下主要功能:

1. 流式处理
- 支持数据流的创建、转换和组合
- 提供丰富的流操作符(map, filter, reduce等)
- 支持异步流处理

2. HTTP 客户端
- 基于 requests-html 的异步 HTTP 客户端
- 支持网页抓取和解析
- 支持 JavaScript 渲染

3. 事件处理
- 基于 tornado 的事件循环
- 支持异步事件处理
- 提供定时器和调度功能

4. 管道操作
- 链式调用风格的数据处理
- 支持自定义管道操作符
- 方便的数据转换和过滤

5. 路由函数
- 支持根据特定条件路由函数
- 可以使用 lambda 表达式或者自定义函数
- 可以根据函数的返回值或者参数进行路由

6. 异常捕获
- catch 方法用于捕获函数执行结果到流内
- 支持异步和同步函数的捕获
- 可以在函数执行前和执行后执行任务

7. 异常捕获（catch_except）
- catch_except 方法用于捕获函数执行异常到流内
- 支持异步和同步函数的异常捕获
- 可以在函数执行前和执行后执行任务

主要用途:
- 网络爬虫和数据采集
- 实时数据处理
- 异步任务调度
- ETL 数据处理
- 事件驱动应用

使用示例:

1. 流式处理
from deva import Stream
# 创建数据流并进行转换
source = Stream()
result = (source.map(lambda x: x * 2)
                .filter(lambda x: x > 0)
                .rate_limit(0.5))  # 限流
                
# 输入数据
for i in range(5):
    source.emit(i)

2. 网页抓取
from deva import http
# 异步抓取网页
urls = ['http://example1.com', 'http://example2.com']
(Stream()
 .emit(urls)
 .rate_limit(0.5)  # 限制请求速率
 .map(http.get)  # 异步HTTP请求
 .map(lambda r: r.html.find('h1', first=True))  # 解析HTML
 .sink(print))  # 打印结果

3. 定时任务
from deva import Stream, timer
# 每30秒执行一次任务
(timer(30)
 .rate_limit(30)  # 限制执行频率
 .map(lambda _: http.get('http://api.example.com/data'))  # 定时获取数据
 .map(lambda r: r.json())
 .sink(print))  # 处理结果

4. 管道处理
from deva import P
# 使用管道操作符处理数据
data = [{'name': 'foo', 'value': 1}, 
        {'name': 'bar', 'value': 2}]
(data >> P.map(lambda x: x['value'])  # 提取value字段
      >> P.filter(lambda x: x > 1)    # 过滤
      >> P.reduce(lambda x,y: x + y)  # 求和
      >> print)                       # 打印结果

5. 存储和回放
from deva import Stream, store
# 将数据流存储到Redis
source = Stream()
store = store('redis://localhost:6379')
(source.map(lambda x: {'time': time.time(), 'value': x})
       .sink(store.save))  # 保存到Redis

# 从Redis回放数据
(store.load()  # 加载历史数据
      .rate_limit(0.1)  # 控制回放速度
      .sink(print))  # 打印结果

6. HTTP请求处理
from deva import http
# 异步并发请求
h = http(workers=10)  # 10个并发worker
urls = ['http://api1.com', 'http://api2.com']
(urls >> h.map(lambda r: r.json())  # 解析JSON响应
         >> print)

# 渲染JavaScript
h = http(render=True)  # 启用JS渲染
'http://spa.com' >> h.map(lambda r: r.html.search('data-value="{}"')[0]) >> print

7. 命名空间(namespace)
from deva import NB
# 创建命名空间
# 创建一个新的流对象
stream = Stream()

# 使用装饰器订阅主题
@stream.sub('topic1')  # 订阅topic1
def handler1(msg):
    print(f'收到消息: {msg}')

@stream.sub('topic2')  # 订阅topic2 
def handler2(msg):
    print(f'收到消息: {msg}')

# 发布消息
stream.pub('topic1', '你好')  # 输出: 收到消息: 你好
stream.pub('topic2', '世界')  # 输出: 收到消息: 世界

# 远程过程调用(RPC)
@nb.rpc('add')  # 注册RPC方法
def add(a, b):
    return a + b
    
# 调用RPC方法
result = nb.call('add', 1, 2)  # 返回3

# 共享状态
nb.set('counter', 0)  # 设置共享变量
nb.get('counter')  # 获取共享变量
nb.incr('counter')  # 原子递增

# 分布式锁
with nb.lock('resource'):  # 获取分布式锁
    # 临界区代码
    pass

# 任务队列
@nb.task('process_data')  # 注册任务处理器
def process_data(data):
    print(f'处理数据: {data}')
    
nb.send_task('process_data', '待处理数据')  # 发送任务

# 事件总线
@nb.on('user.created')  # 监听事件
def on_user_created(user):
    print(f'新用户创建: {user}')
    
nb.emit('user.created', {'id': 1, 'name': 'test'})  # 触发事件

8. 路由函数
from deva import Stream
# 创建数据流
source = Stream()

# 定义路由函数
@source.route(lambda x: x % 2 == 0)  # 跱要求是偶数的函数
def even_handler(x):
    print(f'偶数: {x}')

@source.route(lambda x: x % 2 != 0)  # 要求是奇数的函数
def odd_handler(x):
    print(f'奇数: {x}')

# 发送数据
for i in range(5):
    source.emit(i)

# 输出结果
# 偶数: 0
# 奇数: 1
# 偶数: 2
# 奇数: 3
# 偶数: 4

9. 异常捕获
from deva import Stream
# 创建数据流
source = Stream()

# 定义一个可能抛出异常的函数
def divide(x, y):
    if y == 0:
        raise ZeroDivisionError
    return x / y

# 使用catch方法捕获异常
@source.catch(divide)
def handle_division(x, y):
    print(f'结果: {x / y}')

# 发送数据
source.emit((10, 2))  # 正常情况
source.emit((10, 0))  # 异常情况

# 输出结果
# 结果: 5.0
# 异常: division by zero

10. 缓存和回放
from deva import Stream
# 创建数据流
source = Stream()

# 缓存数据
source.cache = {'key': 'value'}

# 回放缓存的数据
source.recent()  # 获取最近的数据

11. 过滤器
from deva import Stream
# 创建数据流
source = Stream()

# 定义过滤器
@source.filter(lambda x: x > 0)  # 过滤出正数
def positive_filter(x):
    print(f'正数: {x}')

# 发送数据
for i in range(-5, 6):
    source.emit(i)

# 输出结果
# 正数: 1
# 正数: 2
# 正数: 3
# 正数: 4
# 正数: 5

12. 映射
from deva import Stream
# 创建数据流
source = Stream()

# 定义映射
@source.map(lambda x: x * 2)  # 将数据乘以2
def double_map(x):
    print(f'乘以2后的结果: {x}')

# 发送数据
for i in range(5):
    source.emit(i)

# 输出结果
# 乘以2后的结果: 0
# 乘以2后的结果: 2
# 乘以2后的结果: 4
# 乘以2后的结果: 6
# 乘以2后的结果: 8

13. reduce
from deva import Stream
# 创建数据流
source = Stream()

# 定义减少操作
@source.reduce(lambda x, y: x + y)  # 累加数据
def sum_reduce(x):
    print(f'累加结果: {x}')

# 发送数据
for i in range(5):
    source.emit(i)

# 输出结果
# 累加结果: 10

14. 异常捕获（catch_except）
from deva import Stream
# 创建数据流
source = Stream()


# 使用装饰器捕获异常
@source.catch_except
def divide(x, y):
    if y == 0:
        raise ZeroDivisionError
    return x / y

# 发送数据
divide(10,0)执行时，异常会被发送到 source 中



# 使用^运算符捕获异常
divide = lambda x, y: x / y if y != 0 else raise ZeroDivisionError
(10,0) | divide^source


更多信息请访问: https://github.com/sostc/deva
"""


no_default = '--no-default--'

# sinks add themselves here to avoid being garbage-collected
_global_sinks = set()

_html_update_streams = set()

thread_state = threading.local()

logger = logging.getLogger(__name__)


_io_loops = []


class OrderedSet(collections.abc.MutableSet):
    def __init__(self, values=()):
        self._od = collections.OrderedDict().fromkeys(values)

    def __len__(self):
        return len(self._od)

    def __iter__(self):
        return iter(self._od)

    def __contains__(self, value):
        return value in self._od

    def add(self, value):
        self._od[value] = None

    def discard(self, value):
        self._od.pop(value, None)


class OrderedWeakrefSet(weakref.WeakSet):
    def __init__(self, values=()):
        super(OrderedWeakrefSet, self).__init__()
        self.data = OrderedSet()
        for elem in values:
            self.add(elem)


def get_io_loop(asynchronous=None):
    if asynchronous:
        return IOLoop.current()

    if not _io_loops:
        loop = IOLoop()
        thread = threading.Thread(target=loop.start)
        thread.daemon = True
        thread.start()
        _io_loops.append(loop)

    return _io_loops[-1]


def identity(x):
    return x


class Stream(object):
    """ 流是一个无限的数据序列

    流之间可以相互订阅,传递和转换数据。
    流对象监听上游更新,对这些更新做出反应,
    然后向下游发送更多数据到所有订阅它的流对象。
    下游流对象可以在流图的任意点连接,获取该点的完整数据视图。

    参数
    ----------
    asynchronous: boolean or None
        这个流是否会在异步函数或普通Python函数中使用。
        如果不确定就保持为None。
        True会导致emit等操作返回可等待的Future
        False会在另一个线程中使用事件循环(如果需要则启动它)
    ensure_io_loop: boolean
        确保会创建某个IOLoop。如果asynchronous是None或False,
        则会在单独的线程中创建,否则会使用IOLoop.current

    示例
    --------
    >>> def inc(x):
    ...     return x + 1

    >>> source = Stream()  # 创建一个流对象
    >>> s = source.map(inc).map(str)  # 订阅创建新流
    >>> s.sink(print)  # 当元素到达末端时执行动作

    >>> L = list()
    >>> s.sink(L.append)  # 或执行多个动作(流可以分支)

    >>> for i in range(5):
    ...     source.emit(i)  # 在源头推入数据
    '1'
    '2'
    '3'
    '4'
    '5'
    >>> L  # 动作在sink处执行
    ['1', '2', '3', '4', '5']
    """
    _graphviz_shape = 'ellipse'  # graphviz图形形状
    _graphviz_style = 'rounded,filled'  # graphviz样式
    _graphviz_fillcolor = 'white'  # graphviz填充颜色
    _graphviz_orientation = 0  # graphviz方向

    _instances = set()  # 所有Stream实例的集合

    str_list = ['func', 'predicate', 'n', 'interval', 'port', 'host',
                'ttl', 'cache_max_len', '_scheduler', 'filename', 'path']  # 用于字符串表示的属性列表

    def __init__(self, upstream=None, upstreams=None, name=None,
                 cache_max_len=None, cache_max_age_seconds=None,  # 缓存长度和事件长度
                 loop=None, asynchronous=None, ensure_io_loop=False,
                 refuse_none=True):  # 禁止传递None到下游
        self.downstreams = OrderedWeakrefSet()  # 下游流的有序弱引用集合
        if upstreams is not None:
            self.upstreams = list(upstreams)
        else:
            self.upstreams = [upstream]

        self._set_asynchronous(asynchronous)  # 设置异步标志
        self._set_loop(loop)  # 设置事件循环
        if ensure_io_loop and not self.loop:
            self._set_asynchronous(False)
        if self.loop is None and self.asynchronous is not None:
            self._set_loop(get_io_loop(self.asynchronous))

        for upstream in self.upstreams:
            if upstream:
                upstream.downstreams.add(self)  # 将自己添加到上游的下游集合中

        self.name = name  # 流的名称

        self.cache = {}  # 缓存字典
        self.is_cache = False  # 是否启用缓存
        if cache_max_len or cache_max_age_seconds:
            self.start_cache(cache_max_len, cache_max_age_seconds)

        self.refuse_none = refuse_none  # 是否拒绝None值

        self.handlers = []  # 处理器列表

        self.__class__._instances.add(weakref.ref(self))  # 添加到实例集合

        self._subscribers = collections.defaultdict(list)  # 主题订阅者字典

    def start_cache(self, cache_max_len=None, cache_max_age_seconds=None):
        """
        启动缓存功能

        参数:
            cache_max_len: 缓存的最大长度
            cache_max_age_seconds: 缓存的最大存活时间(秒)
        """
        self.is_cache = True
        self.cache_max_len = cache_max_len or 1
        self.cache_max_age_seconds = cache_max_age_seconds or 60 * 5
        self.cache = ExpiringDict(
            max_len=self.cache_max_len,
            max_age_seconds=self.cache_max_age_seconds
        )

    def stop_cache(self,):
        """停止缓存功能"""
        self.is_cache = False

    def clear_cache(self,):
        """清空缓存"""
        self.cache.clear()

    def _set_loop(self, loop):
        """设置事件循环"""
        self.loop = None
        if loop is not None:
            self._inform_loop(loop)
        else:
            for upstream in self.upstreams:
                if upstream and upstream.loop:
                    self.loop = upstream.loop
                    break

    def _inform_loop(self, loop):
        """
        将事件循环信息传播到流的其余部分
        """
        if self.loop is not None:
            if self.loop is not loop:
                raise ValueError("Two different event loops active")
        else:
            self.loop = loop
            for upstream in self.upstreams:
                if upstream:
                    upstream._inform_loop(loop)
            for downstream in self.downstreams:
                if downstream:
                    downstream._inform_loop(loop)

    def _set_asynchronous(self, asynchronous):
        """设置异步标志"""
        self.asynchronous = None
        if asynchronous is not None:
            self._inform_asynchronous(asynchronous)
        else:
            for upstream in self.upstreams:
                if upstream and upstream.asynchronous:
                    self.asynchronous = upstream.asynchronous
                    break

    def _inform_asynchronous(self, asynchronous):
        """
        将异步信息传播到流的其余部分
        """
        if self.asynchronous is not None:
            if self.asynchronous is not asynchronous:
                raise ValueError(
                    "Stream has both asynchronous and synchronous elements")
        else:
            self.asynchronous = asynchronous
            for upstream in self.upstreams:
                if upstream:
                    upstream._inform_asynchronous(asynchronous)
            for downstream in self.downstreams:
                if downstream:
                    downstream._inform_asynchronous(asynchronous)

    @classmethod
    def instances(cls):
        """返回所有存活的Stream实例"""
        dead = set()
        for ref in cls._instances:
            obj = ref()
            if obj is not None:
                yield obj
            else:
                dead.add(ref)
        cls._instances -= dead

    streams = instances  # streams是instances的别名

    @classmethod
    def register_api(cls, modifier=identity):
        """ 向Stream API添加可调用对象

        这允许你在这个类上注册一个新方法。你可以将其用作装饰器。

        示例::

            >>> @Stream.register_api()
            ... class foo(Stream):
            ...     ...

            >>> Stream().foo(...)  # 现在可以工作了

        它将可调用对象作为普通属性附加到类对象上。这样做时它
        会考虑继承(Stream的所有子类也会获得foo属性)。

        默认情况下可调用对象被假定为实例方法。如果你愿意,
        你可以在附加到类之前包含修饰符,就像下面的例子中
        我们构造一个``staticmethod``。

            >>> @Stream.register_api(staticmethod)
            ... class foo(Stream):
            ...     ...

            >>> Stream.foo(...)  # Foo作为静态方法运行
        """
        def _(func):
            @functools.wraps(func)
            def wrapped(*args, **kwargs):
                return func(*args, **kwargs)
            setattr(cls, func.__name__, modifier(wrapped))
            return func
        return _

    def start(self):
        """启动任何上游源"""
        for upstream in self.upstreams:
            upstream.start()

    def __str__(self):
        """返回流的字符串表示"""
        s_list = []
        if self.name:
            s_list.append('{}; {}'.format(
                self.name, self.__class__.__name__))
        else:
            s_list.append(self.__class__.__name__)

        for m in self.str_list:
            s = ''
            at = getattr(self, m, None)
            if at:
                if not callable(at):
                    s = str(at)
                elif hasattr(at, '__name__'):
                    s = getattr(self, m).__name__
                elif hasattr(at.__class__, '__name__'):
                    s = getattr(self, m).__class__.__name__
                else:
                    s = None
            if s:
                s_list.append('{}={}'.format(m, s))
        if len(s_list) <= 2:
            s_list = [term.split('=')[-1] for term in s_list]

        text = "<"
        text += s_list[0]
        if len(s_list) > 1:
            text += ': '
            text += ', '.join(s_list[1:])
        text += '>'
        return text

    __repr__ = __str__

    def _ipython_display_(self, **kwargs):
        """IPython显示方法"""
        try:
            from ipywidgets import Output
            import IPython
        except ImportError:
            if hasattr(self, '_repr_html_'):
                return self._repr_html_()
            else:
                return self.__repr__()
        output = Output(_view_count=0)
        output_ref = weakref.ref(output)

        def update_cell(val):
            output = output_ref()
            if output is None:
                return
            with output:
                IPython.display.clear_output(wait=True)
                IPython.display.display(val)

        s = self.map(update_cell)
        _html_update_streams.add(s)

        self.output_ref = output_ref
        s_ref = weakref.ref(s)

        def remove_stream(change):
            output = output_ref()
            if output is None:
                return

            if output._view_count == 0:
                ss = s_ref()
                ss.destroy()
                _html_update_streams.remove(ss)  # trigger gc

        output.observe(remove_stream, '_view_count')

        if hasattr(output,'_ipython_display_'):
            return output._ipython_display_(**kwargs)

    def _emit(self, x):
        """向下游发送数据"""
        if self.is_cache:
            self.cache[datetime.now()] = x

        if self.refuse_none and x is None:
            return

        result = []
        for downstream in list(self.downstreams):
            r = downstream.update(x, who=self)
            if type(r) is list:
                result.extend(r)
            else:
                result.append(r)

        return [element for element in result if element is not None]

    def emit(self, x, asynchronous=False):
        """在此点将数据推入流

        这通常只在源流上完成,但理论上可以在任何点完成
        """
        self.update(x)

    def update(self, x, who=None):
        """更新流中的数据"""
        try:
            if isinstance(x, gen.Awaitable):
                futs = gen.convert_yielded(x)
                if not self.loop:
                    self._set_asynchronous(False)
                if self.loop is None and self.asynchronous is not None:
                    self._set_loop(get_io_loop(self.asynchronous))
                self.loop.add_future(futs, lambda x: self._emit(x.result()))
            else:
                return self._emit(x)
        except Exception as e:
            logger.exception(e)
            raise

    def gather(self):
        """这是core streamz的空操作

        这允许gather在dask和core流中都可以使用
        """
        return self

    def connect(self, downstream):
        """将此流连接到下游元素

        参数
        ----------
        downstream: Stream
            要连接到的下游流
        """
        self.downstreams.add(downstream)

        if downstream.upstreams == [None]:
            downstream.upstreams = [self]
        else:
            downstream.upstreams.append(self)

    def disconnect(self, downstream):
        """断开此流与下游元素的连接

        参数
        ----------
        downstream: Stream
            要断开连接的下游流
        """
        self.downstreams.remove(downstream)

        downstream.upstreams.remove(self)

    @property
    def upstream(self):
        """返回唯一的上游流"""
        if len(self.upstreams) != 1:
            raise ValueError("Stream has multiple upstreams")
        else:
            return self.upstreams[0]

    def destroy(self, streams=None):
        """断开此流与任何上游源的连接"""
        if streams is None:
            streams = self.upstreams
        for upstream in list(streams):
            upstream.downstreams.remove(self)
            self.upstreams.remove(upstream)

    def scatter(self, **kwargs):
        """分散流到dask"""
        from .dask import scatter
        return scatter(self, **kwargs)

    def remove(self, predicate):
        """只传递predicate返回False的元素"""
        return self.filter(lambda x: not predicate(x))

    @property
    def scan(self):
        """scan是accumulate的别名"""
        return self.accumulate

    @property
    def concat(self):
        """concat是flatten的别名"""
        return self.flatten

    def to_list(self):
        """将流的所有元素追加到列表中

        示例
        --------
        >>> source = Stream()
        >>> L = source.map(lambda x: 10 * x).to_list()
        >>> for i in range(5):
        ...     source.emit(i)
        >>> L
        [0, 10, 20, 30, 40]
        """
        L = []
        self.sink(L.append)
        return L

    def frequencies(self, **kwargs):
        """计算元素出现的频率"""
        def update_frequencies(last, x):
            return toolz.assoc(last, x, last.get(x, 0) + 1)

        return self.scan(update_frequencies, start={}, **kwargs)

    def visualize(self, filename='mystream.png', source_node=False, **kwargs):
        """使用graphviz渲染此对象的任务图的计算。

        需要安装``graphviz``。

        参数
        ----------
        filename : str, optional
            要写入磁盘的文件名。
        source_node: bool, optional
            如果为True,则该节点是源节点,我们可以按执行顺序标记边。
            默认为False
        kwargs:
            要传递给graphviz的图形属性,如``rankdir="LR"``
        """
        from .graph import visualize
        return visualize(self, filename, source_node=source_node, **kwargs)

    def __ror__(self, x):  # |
        """将值发送到流,结束,返回发送结果"""
        self.emit(x, asynchronous=False)
        return x

    def __rrshift__(self, x):  # stream左边的>>
        """将值发送到流,结束,返回发送结果"""
        return self.__ror__(x)

    def __lshift__(self, x):  # stream右边的<<
        """将值发送到流,结束,返回发送结果"""
        return self.__ror__(x)

    def catch(self, func):
        """捕获函数执行结果到流内。

        示例::

            @log.catch
            @warn.catch_except
            def f1(*args,**kwargs):
                return sum(*args,**kwargs)


            @log.catch
            @gen.coroutine
            def a_foo(n):
                yield gen.sleep(n)
                print(1)
                return 123

            @log.catch
            async def a_foo(n):
                import asyncio
                await asyncio.sleep(n)
                print(1)
                return 123

        """
        @functools.wraps(func)
        def wraper(*args, **kwargs):
            result = func(*args, **kwargs)
            # 异步函数
            if isinstance(result, gen.Awaitable):
                futs = gen.convert_yielded(result)
                if not self.loop:
                    self._set_asynchronous(False)
                if self.loop is None and self.asynchronous is not None:
                    self._set_loop(get_io_loop(self.asynchronous))
                self.loop.add_future(futs, lambda x: self._emit(x.result()))

            # 同步函数
            else:
                self._emit(result)

            return result

        return wraper.__call__ @ P

    def catch_except(self, func):
        """捕获函数执行异常到流内。

        示例::

            @log.catch
            @warn.catch_except
            def f1(*args,**kwargs):
                return sum(*args,**kwargs)

        """

        @functools.wraps(func)
        def wraper(*args, **kwargs):
            try:
                #todo:异步函数如何处置？
                return func(*args, **kwargs)  # 需要这里显式调用用户函数
            except Exception as e:
                {
                    'function': func.__name__,
                    'param': (args, kwargs),
                    'except': e,
                } >> self

        return wraper.__call__ @ P

    def __rmatmul__(self, func):
        """左边的 @.，函数结果进入流内。"""
        return self.catch(func).__call__ @ P

    def __rxor__(self, func):
        """左边的 ^.，函数异常入流。优先级不高"""
        return self.catch_except(func).__call__ @ P

    def __rshift__(self, ref):  # stream右边的
        """Stream右边>>,sink到右边的对象。

        支持5种类型:list| text file| str | stream | callable
        """
        return match(ref,
                     list, lambda ref: self.sink(ref.append),
                     io.TextIOWrapper, lambda ref: self.to_textfile(ref),
                     str, lambda ref: self.map(str).to_textfile(ref),
                     Stream, lambda ref: self.sink(ref.emit),
                     callable, lambda ref: self.sink(ref),
                     ANY, lambda ref: TypeError(
                         f'{ref}:{type(ref)} is'
                         'Unsupported type, must be '
                         'list| str | text file| stream | callable')
                     )

    def __getitem__(self, *args):
        """获取缓存的值"""
        return self.cache.values().__getitem__(*args)

    def route(self, occasion):
        """路由函数。

        参数:
            occasion: 路由函数表达式,
            比如 lambda x:x.startswith('foo')
            或者 lambda x:type(x)==str

        示例::
            e = Stream.engine()
            e.start()

            @e.route(lambda x:type(x)==int)
            def goo(x):
                x*2>>log

            @bus.route('world')
            def goo(x):
                print('hello',x)

        """
        def param_wraper(func):
            """ 预处理函数，定义包装函数wraper取代老函数。
            定义完成后将目标函数增加到handlers中
            """
            @functools.wraps(func)
            def wraper(*args, **kwargs):
                """包装函数，这个函数是处理用户函数的，在用户函数执行前和执行后分别执行任务，甚至可以处理函数的参数"""
                func(*args, **kwargs)  # 需要这里显式调用用户函数

            if callable(occasion):
                self.filter(occasion).sink(wraper)
            else:
                self.filter(lambda x: x == occasion).sink(wraper)

            self.handlers.append((occasion, func))
            return wraper

        return param_wraper

    def recent(self, n=5, seconds=None):
        """获取最近的n个值或最近seconds秒内的值"""
        if self.is_cache:
            if not seconds:
                return self.cache.values()[-n:]
            else:
                begin = datetime.now() - timedelta(seconds=seconds)
                return [i[1] for i in self.cache.items() if begin < i[0]]
        else:
            return {}

    def __iter__(self,):
        """迭代缓存的值"""
        return self.cache.values().__iter__()

    def sub(self, topic):
        """装饰器，用于订阅特定主题的消息。

        参数:
            topic: 主题名称。
        """
        def decorator(handler):
            self._subscribers[topic].append(handler)
            return handler
        return decorator

    def pub(self, topic, message):
        """发布消息到特定主题。

        参数:
            topic: 主题名称。
            message: 要发布的消息。
        """
        if topic in self._subscribers:
            for handler in self._subscribers[topic]:
                handler(message)

    def __call__(self,func):
        return self.catch(func=func)



class Sink(Stream):

    _graphviz_shape = 'trapezium'

    def __init__(self, upstream, **kwargs):
        super().__init__(upstream, **kwargs)
        _global_sinks.add(self)


@Stream.register_api()
class sink(Sink):
    """ 对流中的每个元素应用一个函数

    参数
    ----------
    func: callable
        要应用的函数
    args:
        传递给func的位置参数,在输入元素之后传入
    kwargs:
        Stream相关的参数会传给Stream.__init__,其余参数传给func

    示例
    --------
    >>> source = Stream()
    >>> L = list()
    >>> source.sink(L.append)  # 将元素添加到列表
    >>> source.sink(print)     # 打印元素
    >>> source.sink(print)     # 可以有多个sink
    >>> source.emit(123)       # 发送数据
    123
    123
    >>> L
    [123]

    另见
    --------
    map
    Stream.to_list
    """

    def __init__(self, upstream, func, *args, **kwargs):
        self.func = self.wrapper_function(func)
        # 提取Stream特有的kwargs参数
        sig = set(inspect.signature(Stream).parameters)
        stream_kwargs = {k: v for (k, v) in kwargs.items() if k in sig}
        self.kwargs = {k: v for (k, v) in kwargs.items() if k not in sig}
        self.args = args
        super().__init__(upstream, **stream_kwargs)

    def wrapper_function(self,func):
        def inner(*args, **kwargs):
            # 获取原函数的参数签名
            signature = inspect.signature(func)
            parameters = signature.parameters
            
            # 检查原函数是否需要参数
            if parameters:
                # 如果原函数需要参数，调用原函数并传递参数
                return func(*args, **kwargs)
            else:
                # 如果原函数不需要参数，调用原函数时不传递参数
                return func()
    
        return inner
    
    def update(self, x, who=None, metadata=None):
        # 执行函数并处理结果
        try:
            result = self.func(x, *self.args, **self.kwargs)
            if isinstance(result, gen.Awaitable):
                # 处理异步结果
                futs = gen.convert_yielded(result)
                if not self.loop:
                    self._set_asynchronous(False)
                if self.loop is None and self.asynchronous is not None:
                    self._set_loop(get_io_loop(self.asynchronous))
                self.loop.add_future(futs, lambda x: self._emit(x.result()))
            else:
                # 处理同步结果
                return self._emit(result)
        except Exception as e:
            logger.exception(e)
            raise

    def destroy(self):
        # 销毁时从全局sink集合中移除
        super().destroy()
        _global_sinks.remove(self)


@Stream.register_api()
class to_textfile(Sink):
    """ 将元素写入纯文本文件，每个元素一行。
        元素的类型必须是 ``str``。
        参数
        ----------
        file: str 或 file-like
            要写入元素的文件。``str`` 将被视为要打开的文件名。
            如果是 file-like，描述符必须以文本模式打开。注意，文件
            描述符将在此sink被销毁时关闭。
        end: str, 可选
            这个值将在每个元素后写入文件中。
            默认为换行符。
        mode: str, 可选
            如果 file 是 ``str``, 文件将以此模式打开。默认为 ``"a"``
            (追加模式)。
        示例
        --------
        >>> source = Stream()
        >>> source.map(str).to_textfile("test.txt")
        >>> source.emit(0)
        >>> source.emit(1)
        >>> print(open("test.txt", "r").read())
        0
        1
    """

    def __init__(self, upstream, file, end="\n", mode="a", **kwargs):
        self._end = end
        self._fp = open(file, mode=mode) if isinstance(file, str) else file
        weakref.finalize(self, self._fp.close)
        super().__init__(upstream, **kwargs)

    def __del__(self):
        self._fp.close()

    def update(self, x, who=None, metadata=None):
        self._fp.write(x + self._end)
        self._fp.flush()

@Stream.register_api()
class map(Stream):
    """ 对流中的每个元素应用一个函数

    参数
    ----------
    func: callable
        要应用的函数
    *args :
        传递给函数的位置参数
    **kwargs:
        传递给函数的关键字参数

    示例
    --------
    >>> source = Stream()
    >>> source.map(lambda x: 2*x).sink(print)  # 对每个元素乘以2并打印
    >>> for i in range(5):
    ...     source.emit(i)
    0
    2
    4
    6
    8
    """

    def __init__(self, upstream, func=None, *args, **kwargs):
        self.func = func
        # 从kwargs中提取name参数
        name = kwargs.pop('name', None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, name=name)

    def update(self, x, who=None):
        try:
            # 应用函数到输入值
            result = self.func(x, *self.args, **self.kwargs)

            # 处理异步结果
            if isinstance(result, gen.Awaitable):
                # 转换为Future对象
                futs = gen.convert_yielded(result)

                # 设置异步模式
                if not self.loop:
                    self._set_asynchronous(False)
                if self.loop is None and self.asynchronous is not None:
                    self._set_loop(get_io_loop(self.asynchronous))

                # 添加Future到事件循环
                self.loop.add_future(futs, lambda x: self._emit(x.result()))
            else:
                # 同步结果直接发射
                return self._emit(result)
        except Exception as e:
            # 记录并重新抛出异常
            logger.exception(e)
            raise


@Stream.register_api()
class starmap(Stream):
    """ 对流中的每个元素应用一个函数，展开
    使用 map 时，函数 func 期望单个参数。
    使用 starmap 时，函数 func 期望多个参数，
    且每个元素是一个可迭代对象（如元组），
    starmap 会自动解包这些元素。

    参见 ``itertools.starmap``

    参数
    ----------
    func: callable
    *args :
        要传递给函数的参数。
    **kwargs:
        要传递给func的关键字参数

    示例
    --------
    >>> source = Stream()
    >>> source.starmap(lambda a, b: a + b).sink(print)  # 对每个元素乘以2并打印
    >>> for i in range(5):
    ...     source.emit((i, i))
    0
    2
    4
    6
    8
    """

    def __init__(self, upstream, func, *args, **kwargs):
        self.func = func
        # this is one of a few stream specific kwargs
        name = kwargs.pop('name', None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, name=name)

    def update(self, x, who=None):
        y = x + self.args
        try:
            result = self.func(*y, **self.kwargs)
        except Exception as e:
            logger.exception(e)
            raise
        else:
            return self._emit(result)

def _truthy(x):
    return not not x


@Stream.register_api()
class filter(Stream):
    """ 只允许满足谓词的元素通过

    参数
    ----------
    predicate : 函数
        谓词。应该返回True或False，其中
        True意味着谓词被满足。

    示例
    --------
    >>> source = Stream()
    >>> source.filter(lambda x: x % 2 == 0).sink(print)
    >>> for i in range(5):
    ...     source.emit(i)
    0
    2
    4
    """

    def __init__(self, upstream, predicate, *args, **kwargs):
        if predicate is None:
            predicate = _truthy
        self.predicate = predicate
        name = kwargs.pop('name', None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, name=name,)

    def update(self, x, who=None):
        if self.predicate(x, *self.args, **self.kwargs):
            return self._emit(x)

@gen.coroutine
def httpx(req, render=False, timeout=30, **kwargs):
    """异步HTTP请求函数

    参数:
        req: 请求参数,可以是URL字符串或请求参数字典
        render: 是否渲染JavaScript,默认False
        timeout: 请求超时时间(秒),默认30秒
        **kwargs: 渲染参数,传递给arender()方法

    返回:
        response: 响应对象

    示例:
        # URL字符串
        response = yield httpx('http://example.com')

        # 请求参数字典
        response = yield httpx({
            'url': 'http://example.com',
            'method': 'post',
            'data': {'key': 'value'}
        })

        # 渲染JavaScript
        response = yield httpx('http://example.com', render=True)
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

    httpclient = AsyncHTMLSession(workers=1)
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
        print(req, e)
        logger.exception(e)
@Stream.register_api()
class http(Stream):
    """自动处理流中的HTTP请求,返回response对象.

    接受两种上游数据格式:
    1. URL字符串
    2. 请求参数字典

    注意:上游流需要限速,因为这是并发执行,速度很快

    参数:
        error: 流或pipe函数,发生异常时URL会被发送到这里
        workers: 并发线程池数量
        render: 是否渲染JavaScript,默认False
        **kwargs: 渲染参数,包括:
            - retries: 重试次数,默认8
            - script: 自定义JavaScript脚本
            - wait: 等待时间,默认0.2秒
            - scrolldown: 是否向下滚动
            - sleep: 休眠时间
            - reload: 是否重新加载,默认True
            - timeout: 超时时间,默认8秒
            - keep_page: 是否保持页面,默认False

    示例:
        # 基本用法
        s = Stream()
        get_data = lambda x:x.body.decode('utf-8')>>chinese_extract>>sample(20)>>concat('|')
        s.rate_limit(0.1).http(workers=20,error=log).map(get_data).sink(print)

        url>>s

        # 使用请求参数字典
        {'url':'','headers'='','params':''}>>s

        # 提取标题
        h = http()
        h.map(lambda r:(r.url,r.html.search('<title>{}</title>')[0]))>>log
        'http://www.518.is'>>h

        [2020-03-17 03:46:30.902542] INFO: log: ('http://518.is/', 'NajaBlog')

    返回:
        response对象,常用方法:
        - r.html.absolute_links: 提取所有完整链接
        - r.html.find(): CSS选择器
        - r.html.search(): 搜索模板
        - r.html.xpath(): XPath查询
        - r.url: 请求URL
        - r.base_url: 基础URL
        - r.text: 响应文本
        - r.full_text: 完整文本
    """

    def __init__(self, upstream=None, render=False, workers=None, error=print, **kwargs):
        """初始化HTTP流

        参数:
            upstream: 上游流
            render: 是否渲染JavaScript
            workers: 并发线程池数量
            error: 错误处理函数
            **kwargs: 渲染参数
        """
        self.error = error
        self.render = render
        Stream.__init__(self, upstream=upstream, ensure_io_loop=True)
        self.httpclient = AsyncHTMLSession(workers=workers)
        self.kwargs = kwargs

    def update(self, req, who=None):
        """更新流数据

        参数:
            req: 请求(URL或字典)
            who: 更新者标识
        """
        self.loop.add_future(
            self._request(req),
            lambda x: self._emit(x.result())
        )

    def emit(self, req, **kwargs):
        """发送请求

        参数:
            req: 请求(URL或字典)
            **kwargs: 额外参数

        返回:
            req: 原始请求
        """
        self.update(req)
        return req

    @gen.coroutine
    def _request(self, req):
        """执行异步请求

        参数:
            req: 请求(URL或字典)

        返回:
            response: 响应对象
        """
        try:
            if isinstance(req, str):
                response = yield self.httpclient.get(req)
            elif isinstance(req, dict):
                response = yield self.httpclient.get(**req)

            if self.render:
                yield response.html.arender(**self.kwargs)

            return response
        except Exception as e:
            (req, e) >> self.error
            logger.exception(e)

    @classmethod
    def request(cls, url, **kwargs):
        """同步HTTP请求

        参数:
            url: 请求URL
            **kwargs: 请求参数

        返回:
            response: 响应对象
        """
        from requests_html import HTMLSession
        httpclient = HTMLSession()
        try:
            kwargs.update({'url': url})
            response = httpclient.get(**kwargs)

            return response
        except Exception as e:
            logger.exception(e)

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

    x = httpx

    @classmethod
    async def get_web_article(cls, url, key='text'):
        """提取网页文章内容

        参数:
            url: 网页URL
            key: 提取字段,可选值:title|description|image|text等,默认text

        返回:
            提取的内容或完整数据字典
        """
        from trafilatura import bare_extraction

        response = await httpx(url)
        data = bare_extraction(response.content)
        if key:
            return data.get(key)
        else:
            return data


def sync(loop, func, *args, **kwargs):
    """在单独线程中运行的事件循环中执行协程函数

    参数:
        loop: 事件循环对象,如果为None则使用get_io_loop()获取
        func: 要执行的协程函数
        *args: 传递给func的位置参数
        **kwargs: 传递给func的关键字参数,其中callback_timeout用于设置超时时间

    返回:
        协程函数的执行结果

    异常:
        RuntimeError: 如果事件循环已关闭,或在运行loop的线程中调用
        TimeoutError: 如果执行超时
    """
    # 检查事件循环是否已关闭
    loop = loop or get_io_loop()
    if PollIOLoop\
        and ((isinstance(loop, PollIOLoop)
              and getattr(loop, '_closing', False))
             or (hasattr(loop, 'asyncio_loop')
                 and loop.asyncio_loop._closed)):
        raise RuntimeError("IOLoop is closed")

    # 获取超时设置
    timeout = kwargs.pop('callback_timeout', None)

    # 用于同步的事件对象
    e = threading.Event()
    main_tid = get_thread_identity()
    result = [None]
    error = [False]

    @gen.coroutine
    def f():
        try:
            # 检查是否在事件循环线程中调用
            if main_tid == get_thread_identity():
                raise RuntimeError("sync() called from thread of running loop")
            yield gen.moment
            thread_state.asynchronous = True
            future = func(*args, **kwargs)
            # 添加超时控制
            if timeout is not None:
                future = gen.with_timeout(timedelta(seconds=timeout), future)
            result[0] = yield future
        except Exception:
            error[0] = sys.exc_info()
        finally:
            thread_state.asynchronous = False
            e.set()

    # 将协程添加到事件循环
    loop.add_callback(f)

    # 等待执行完成或超时
    if timeout is not None:
        if not e.wait(timeout):
            raise gen.TimeoutError("timed out after %s s." % (timeout,))
    else:
        while not e.is_set():
            e.wait(10)

    # 处理执行结果
    if error[0]:
        six.reraise(*error[0])
    else:
        return result[0]



class Deva():
    @classmethod
    def run(cls,):
        """启动事件循环

        这个方法会启动一个Tornado IOLoop事件循环,并在接收到键盘中断时退出。

        有几种可选的事件循环实现方式:
        1. 使用IOLoop创建新的事件循环:
           loop = IOLoop()
           loop.make_current() 
           loop.start()

        2. 使用get_io_loop获取事件循环:
           loop = get_io_loop(asynchronous=False)
           loop.instance().start()

        3. 使用asyncio创建事件循环:
           import asyncio
           loop = asyncio.new_event_loop()
           loop.run_forever()

        当前使用的是最简单的方式 - 直接创建并启动一个IOLoop。

        Returns:
            None

        Raises:
            KeyboardInterrupt: 当收到Ctrl+C时退出
        """
         
        try:
            IOLoop().start()
        except KeyboardInterrupt:
            exit()

        


print(os.getpid())
