"""Stream 基类与流基础设施。

从 core.py 拆出（P2 #11）：流的创建、订阅、发射、缓存与生命周期。
core.py 保留为兼容聚合层，`from deva.core.core import Stream` 仍然可用。
"""
from __future__ import absolute_import, division, print_function

import collections
from datetime import datetime, timedelta
import functools
import logging
import time
import weakref
import inspect

import toolz
try:
    from tornado import gen
except ImportError:
    gen = None
try:
    from tornado.ioloop import PollIOLoop
except ImportError:
    PollIOLoop = None  # dropped in tornado 6.0

from expiringdict import ExpiringDict
from pampy import match, ANY
import io
from .pipe import P
from deva.utils.ioloop import get_io_loop

__all__ = ['Stream', 'identity', 'OrderedSet', 'OrderedWeakrefSet']

logger = logging.getLogger(__name__)

# 持有页面里需要持续刷新的 HTML 流，避免被 GC 掉
_html_update_streams = set()


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

    def copy(self):
        return OrderedSet(list(self._od.keys()))


class OrderedWeakrefSet(weakref.WeakSet):
    def __init__(self, values=()):
        super(OrderedWeakrefSet, self).__init__()
        self.data = OrderedSet()
        for elem in values:
            self.add(elem)


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
                 refuse_none=True, description=None):  # 禁止传递None到下游，添加description参数
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
        self.description = description  # 流的描述/介绍
        self.last_update_time = None  # 最后更新时间

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

        参数
        ----------
        modifier: callable, 可选
            用于修改注册方法的装饰器，默认为identity（即不修改）。
            常用选项包括：
            - identity: 将方法注册为实例方法（默认）
            - staticmethod: 将方法注册为静态方法
            - classmethod: 将方法注册为类方法

        示例::

            >>> @Stream.register_api()  # 注册为实例方法
            ... class foo(Stream):
            ...     ...

            >>> Stream().foo(...)  # 作为实例方法调用

            >>> @Stream.register_api(staticmethod)  # 注册为静态方法
            ... class foo(Stream):
            ...     ...

            >>> Stream.foo(...)  # 作为静态方法调用
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
        """IPython显示方法

        该方法用于在Jupyter Notebook中显示流对象。它会创建一个动态更新的输出区域，
        当流中有新数据时自动更新显示内容。

        实现原理：
        1. 尝试导入IPython和ipywidgets库
        2. 创建Output小部件作为显示容器
        3. 定义更新函数，当流中有新数据时更新显示
        4. 使用弱引用管理资源，防止内存泄漏
        5. 监听视图计数，在不需要时自动清理资源

        参数:
            kwargs: 传递给IPython显示方法的额外参数

        返回:
            IPython显示结果或流对象的字符串表示
        """
        try:
            from ipywidgets import Output
            import IPython
        except ImportError:
            # 如果无法导入IPython相关库，则回退到普通显示方式
            return self._repr_html_() if hasattr(self, '_repr_html_') else self.__repr__()

        # 创建输出区域并设置初始视图计数
        output = Output(_view_count=0)
        output_ref = weakref.ref(output)  # 使用弱引用防止内存泄漏

        def update_cell(val):
            """更新显示内容的回调函数"""
            output = output_ref()
            if output is None:
                return
            with output:
                IPython.display.clear_output(wait=True)  # 清除旧内容
                IPython.display.display(val)  # 显示新内容

        # 创建映射流来触发更新
        update_stream = self.map(update_cell)
        _html_update_streams.add(update_stream)  # 注册到全局更新流集合

        # 保存引用以便后续清理
        self.output_ref = output_ref
        stream_ref = weakref.ref(update_stream)

        def remove_stream(change):
            """清理不再使用的资源"""
            output = output_ref()
            if output is None:
                return

            if output._view_count == 0:  # 当视图计数为0时清理
                stream = stream_ref()
                if stream:
                    stream.destroy()
                    _html_update_streams.remove(stream)  # 从全局集合中移除

        # 监听视图计数变化
        output.observe(remove_stream, '_view_count')

        # 调用IPython显示方法
        if hasattr(output, '_ipython_display_'):
            return output._ipython_display_(**kwargs)

    def _emit(self, x):
        """向下游发送数据"""
        self.last_update_time = time.time()

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

    def _ensure_loop(self):
        """确保事件循环就绪，并返回它

        异步分支共用：首次进入异步时 self.loop 为 None，需先按 asynchronous
        标记创建。此前这段 3 行逻辑在 6 处逐字重复，改一处要改 6 个地方。
        """
        if not self.loop:
            self._set_asynchronous(False)
        if self.loop is None and self.asynchronous is not None:
            self._set_loop(get_io_loop(self.asynchronous))
        return self.loop

    def _defer(self, awaitable, callback):
        """把 awaitable 挂到事件循环，就绪后将**结果值**交给 callback

        callback 收到的是 awaitable 的结果（已取 .result()），不是 Future 本身。
        返回转换出的 Future，便于调用方需要时使用。
        """
        futs = gen.convert_yielded(awaitable)
        loop = self._ensure_loop()
        loop.add_future(futs, lambda f: callback(f.result()))
        return futs

    def update(self, x, who=None):
        """更新流中的数据"""
        try:
            if isinstance(x, gen.Awaitable):
                self._defer(x, self._emit)
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
        from .compute import visualize
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
        """捕获函数执行结果到流内

        该方法用于捕获函数执行结果并将其发送到流中。支持同步和异步函数。

        参数:
            func: 要捕获的函数，可以是普通函数、协程函数或生成器函数

        返回:
            装饰后的函数，保持原函数的签名和文档

        特性:
        - 支持同步函数：直接捕获返回值并发送到流
        - 支持异步函数：等待异步操作完成，捕获结果并发送到流
        - 自动处理事件循环：对于异步函数，会自动设置和获取IOLoop
        - 保持函数签名：使用functools.wraps保留原函数的元信息

        示例:
            1. 同步函数捕获:
                @stream.catch
                def sync_func(x):
                    return x + 1

            2. 异步协程捕获:
                @stream.catch
                async def async_func(x):
                    await asyncio.sleep(1)
                    return x + 1

            3. 生成器协程捕获:
                @stream.catch
                @gen.coroutine
                def gen_func(x):
                    yield gen.sleep(1)
                    return x + 1

        注意:
            - 对于异步函数，会自动创建事件循环（如果不存在）
            - 捕获的结果会通过_emit方法发送到流中
            - 原函数的返回值会被保留并返回
        """
        @functools.wraps(func)
        def wraper(*args, **kwargs):
            result = func(*args, **kwargs)
            # 处理异步函数
            if isinstance(result, gen.Awaitable):
                self._defer(result, self._emit)
            # 处理同步函数
            else:
                self._emit(result)

            return result

        return wraper.__call__ @ P

    def catch_except(self, func):
        """捕获函数执行异常到流内。

        该方法用于捕获函数执行过程中抛出的异常，并将异常信息发送到流中。支持同步和异步函数。

        参数:
            func: 要捕获的函数，可以是普通函数、协程函数或生成器函数

        返回:
            装饰后的函数，保持原函数的签名和文档

        特性:
        - 捕获函数执行时的异常信息
        - 将异常信息以结构化数据形式发送到流中
        - 支持同步函数：直接捕获异常
        - 支持异步函数：自动处理异步异常
        - 保持函数签名：使用functools.wraps保留原函数的元信息

        异常信息结构:
        {
            'function': 函数名,
            'param': (位置参数, 关键字参数),
            'except': 异常对象
        }

        示例:
            1. 同步函数异常捕获:
                @stream.catch_except
                def sync_func(x):
                    return x / 0  # 可能抛出ZeroDivisionError

            2. 异步协程异常捕获:
                @stream.catch_except
                async def async_func(x):
                    await asyncio.sleep(1)
                    return x / 0  # 可能抛出ZeroDivisionError

        注意:
            - 对于异步函数，会自动创建事件循环（如果不存在）
            - 捕获的异常信息会通过_emit方法发送到流中
            - 原函数的异常会被保留并抛出
        """

        @functools.wraps(func)
        def wraper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                # 处理异步函数
                if isinstance(result, gen.Awaitable):
                    # 回调里不做任何事：这里只为触发 awaitable 内部的异常，
                    # 由事件循环的异常处理器接管（原写法 lambda x: x.result() 同理）
                    self._defer(result, lambda _: None)
                return result
            except Exception as e:
                {
                    'function': func.__name__,
                    'param': (args, kwargs),
                    'except': e,
                } >> self
                raise  # 重新抛出异常以保持原有行为

        return wraper.__call__ @ P

    def __rmatmul__(self, func):
        """左边的 @.，函数结果进入流内。"""
        return self.catch(func).__call__ @ P

    def __rxor__(self, func):
        """左边的 ^.，函数异常入流。优先级不高"""
        return self.catch_except(func).__call__ @ P

    def __rshift__(self, ref):
        """将流数据输出到目标对象

        该方法实现了流对象的>>操作符，用于将流数据输出到不同类型的对象。
        支持以下目标类型：

        1. list: 将数据追加到列表中
        2. text file: 将数据写入文本文件
        3. str: 将 str 作为文本文件名处理，将流内的数据转换为字符串后写入文件
        4. Stream: 将数据发送到另一个流
        5. callable: 将数据传递给可调用对象

        参数:
            ref: 目标对象，可以是list、文件对象、字符串、Stream或可调用对象

        返回:
            根据目标类型返回相应的处理结果

        异常:
            TypeError: 当目标类型不被支持时抛出

        示例:
            # 输出到列表
            result = []
            stream >> result

            # 输出到文件
            with open('output.txt', 'w') as f:
                stream >> f

            # 输出到另一个流
            stream >> another_stream

            # 输出到可调用对象
            stream >> print
        """
        return match(ref,
                     list, lambda ref: self.sink(ref.append),
                     io.TextIOWrapper, lambda ref: self.to_textfile(ref),
                     str, lambda ref: self.map(str).to_textfile(ref),
                     Stream, lambda ref: self.sink(ref.emit),
                     callable, lambda ref: self.sink(ref),
                     ANY, lambda ref: (_ for _ in ()).throw(TypeError(
                         f'不支持的输出类型: {ref} ({type(ref)})，'
                         '必须是 list | 文本文件名 | 文本文件句柄 | stream | 可调用对象'))
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
        """获取最近的缓存数据

        该方法用于从缓存中获取最近的数据，支持两种模式：
        1. 获取最近n条数据
        2. 获取最近seconds秒内的数据

        参数:
            n (int, optional): 要获取的最近数据条数，默认为5
            seconds (int, optional): 要获取的时间范围（秒），默认为None

        返回:
            list: 最近的数据列表。如果未启用缓存，则返回空字典

        注意:
            - 如果未启用缓存（is_cache=False），将返回空字典
            - 当指定seconds时，返回的数据按时间戳过滤

        示例:
            >>> stream.recent()  # 获取最近5条数据
            >>> stream.recent(n=10)  # 获取最近10条数据
            >>> stream.recent(seconds=60)  # 获取最近60秒内的数据
        """
        if not self.is_cache:
            return {}

        if seconds is not None:
            begin = datetime.now() - timedelta(seconds=seconds)
            return [value for timestamp, value in self.cache.items()
                    if timestamp > begin][:n]

        return list(self.cache.values())[-n:]

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

    def __call__(self, obj):
        if callable(obj):
            return self.catch(func=obj)
        else:
            return self.emit(obj)


# Stream.__init__ 的参数名集合。Sink 子类构造时需要区分「Stream 参数」与
# 「函数参数」；Stream 的签名是固定的，模块加载时算一次即可，避免每个 Sink
# 实例化都做一次 inspect.signature 反射。
_STREAM_INIT_PARAMS = frozenset(inspect.signature(Stream).parameters)
