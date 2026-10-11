"""流算子：Sink / sink / to_textfile / map / starmap / filter / run_future。

从 core.py 拆出（P2 #11）。
"""
from __future__ import absolute_import, division, print_function

import logging
import weakref
import inspect

try:
    from tornado import gen
except ImportError:
    gen = None
try:
    from tornado.ioloop import PollIOLoop
except ImportError:
    PollIOLoop = None  # dropped in tornado 6.0

from .stream import Stream, _STREAM_INIT_PARAMS

__all__ = [
    'Sink', 'sink', 'to_textfile', 'map', 'starmap', 'filter', 'run_future',
    'no_default',
]

logger = logging.getLogger(__name__)

# 算子参数的「未传值」哨兵，用于区分 None 与未传
no_default = '--no-default--'

# sinks 把自己登记在这里，避免被垃圾回收
_global_sinks = set()


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
        sig = _STREAM_INIT_PARAMS
        stream_kwargs = {k: v for (k, v) in kwargs.items() if k in sig}
        self.kwargs = {k: v for (k, v) in kwargs.items() if k not in sig}
        self.args = args
        super().__init__(upstream, **stream_kwargs)

    def wrapper_function(self, func):
        # 签名解析结果只算一次并缓存（首次调用时惰性解析，
        # 保持与原实现相同的异常时机），避免每个元素都做 inspect.signature 反射。
        cache = {}

        def inner(*args, **kwargs):
            has_params = cache.get("has_params")
            if has_params is None:
                has_params = bool(inspect.signature(func).parameters)
                cache["has_params"] = has_params

            # 检查原函数是否需要参数
            if has_params:
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
                self._defer(result, self._emit)
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
    """将流数据写入文本文件的Sink类

    该类用于将流中的每个元素写入文本文件，每个元素占一行。元素类型必须是字符串。

    特性:
    - 支持文件路径字符串或已打开的文件对象
    - 自动处理文件关闭，避免资源泄漏
    - 可自定义行尾符和文件打开模式
    - 线程安全，确保数据完整写入

    参数:
        file (str | file-like): 
            - 文件路径字符串：将自动以指定模式打开文件
            - 文件对象：必须是以文本模式打开的文件描述符
        end (str, 可选): 每行末尾追加的字符串，默认为换行符"\n"
        mode (str, 可选): 文件打开模式，默认为追加模式"a"

    方法:
        update(x, who=None, metadata=None): 
            将数据写入文件，确保立即刷新到磁盘

    示例:
        >>> # 基本用法
        >>> source = Stream()
        >>> source.map(str).to_textfile("output.log")
        >>> source.emit("Hello")
        >>> source.emit("World")

        >>> # 自定义行尾符
        >>> source.map(str).to_textfile("output.csv", end=",")

        >>> # 使用文件对象
        >>> with open("data.txt", "w") as f:
        ...     source.map(str).to_textfile(f)

    注意:
        - 文件会在Sink销毁时自动关闭
        - 如果传入文件对象，请确保以文本模式打开
        - 写入操作会立即刷新到磁盘，确保数据不丢失
    """

    def __init__(self, upstream, file, end="\n", mode="a", **kwargs):
        self._end = end
        self._fp = open(file, mode=mode) if isinstance(file, str) else file
        weakref.finalize(self, self._fp.close)  # 确保文件在对象销毁时关闭
        super().__init__(upstream, **kwargs)

    def __del__(self):
        """对象销毁时关闭文件"""
        self._fp.close()

    def update(self, x, who=None, metadata=None):
        """将数据写入文件并立即刷新

        参数:
            x (str): 要写入的字符串数据
            who: 数据来源（未使用）
            metadata: 元数据（未使用）
        """
        self._fp.write(x + self._end)
        self._fp.flush()  # 确保数据立即写入磁盘


@Stream.register_api()
class map(Stream):
    """ 对流中的每个元素应用一个函数，支持同步和异步操作

    参数
    ----------
    func: callable
        要应用的函数，可以是同步或异步函数
    *args :
        传递给函数的位置参数
    **kwargs:
        传递给函数的关键字参数

    属性
    ----------
    func: callable
        当前使用的映射函数
    args: tuple
        存储的位置参数
    kwargs: dict
        存储的关键字参数

    方法
    ----------
    update(x, who=None):
        处理输入数据，应用映射函数并向下游发送结果
        支持同步和异步函数调用

    示例
    --------
    基本使用:
    >>> source = Stream()
    >>> source.map(lambda x: x**2).sink(print)
    >>> for i in range(5):
    ...     source.emit(i)
    0
    1
    4
    9
    16

    带参数的映射:
    >>> source = Stream()
    >>> def add(x, y): return x + y
    >>> source.map(add, 10).sink(print)
    >>> for i in range(5):
    ...     source.emit(i)
    10
    11
    12
    13
    14

    异步映射:
    >>> import asyncio
    >>> source = Stream()
    >>> async def async_square(x):
    ...     await asyncio.sleep(0.1)
    ...     return x**2
    >>> source.map(async_square).sink(print)
    >>> for i in range(5):
    ...     source.emit(i)
    0
    1
    4
    9
    16
    """

    def __init__(self, upstream, func=None, *args, **kwargs):
        """
        初始化映射流

        参数
        ----------
        upstream: Stream
            上游数据流
        func: callable
            映射函数
        *args:
            传递给函数的位置参数
        **kwargs:
            传递给函数的关键字参数
        """
        self.func = func
        # 从kwargs中提取name参数
        name = kwargs.pop('name', None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, name=name)

    def update(self, x, who=None):
        """
        处理输入数据，应用映射函数并向下游发送结果

        参数
        ----------
        x: Any
            输入数据
        who: Stream, optional
            触发更新的上游流

        返回
        -------
        list
            下游处理结果列表

        异常
        -------
        Exception
            如果映射函数执行失败，记录并重新抛出异常
        """
        try:
            # 应用函数到输入值
            result = self.func(x, *self.args, **self.kwargs)

            # 处理异步结果
            if isinstance(result, gen.Awaitable):
                self._defer(result, self._emit)
                return []  # 异步操作立即返回空列表
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

@Stream.register_api()
class run_future(Stream):
    """将上游传入的 Future/Awaitable 的最终结果发射到下游。建议上游使用 rate_limit 限速。"""

    def __init__(self, upstream=None, **kwargs):
        Stream.__init__(self, upstream=upstream, ensure_io_loop=True, **kwargs)

    def emit(self, x, **kwargs):
        self.update(x, **kwargs)
        return x

    def update(self, x, who=None):
        assert isinstance(x, gen.Awaitable)
        # 构造时已 ensure_io_loop=True，_ensure_loop 在此是 no-op
        self._defer(x, self._emit)
