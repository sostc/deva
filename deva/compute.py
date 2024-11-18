from .core import Stream, identity
from .store import DBStream
from .utils.time import convert_interval
from collections import deque
from collections.abc import Iterable
from tornado import gen
from time import time
from tornado.locks import Condition
from tornado.queues import Queue
import logging

"""计算流模块 (Compute Stream Module)

本模块提供了数据流的计算和处理功能,包括:

主要功能:
- 流速率控制 (rate_limit)
- 数据缓冲和窗口 (buffer, sliding_window, timed_window) 
- 流组合操作 (zip, combine_latest)
- 流转换操作 (flatten, partition)
- 流过滤操作 (slice)
- 流延迟操作 (delay)

示例用法
--------

1. 速率限制:
>>> from deva import Stream
>>> s = Stream()
>>> s.rate_limit('1s') >> print  # 限制每秒最多处理一条数据
>>> for i in range(5):
...     i >> s  # 每秒输出一个数字

2. 数据缓冲:
>>> s = Stream()
>>> s.buffer(n=3) >> print  # 缓冲3条数据后一起处理
>>> for i in range(9):  
...     i >> s  # 每3个数字一组输出

3. 滑动窗口:
>>> s = Stream()
>>> s.sliding_window(n=3) >> print  # 3个元素的滑动窗口
>>> for i in range(5):
...     i >> s
(0, 1, 2)
(1, 2, 3) 
(2, 3, 4)

4. 定时窗口:
>>> s = Stream()
>>> s.timed_window('2s') >> print  # 每2秒输出一次收集的数据
>>> for i in range(10):
...     i >> s
[0,1,2,3]  # 2秒后输出
[4,5,6,7]  # 再过2秒输出
[8,9]      # 最后2秒输出

5. 流组合:
>>> s1 = Stream()
>>> s2 = Stream() 
>>> s1.zip(s2) >> print  # 将两个流组合
>>> 1 >> s1
>>> 'a' >> s2  
(1, 'a')  # 输出组合结果

6. 最新值组合:
>>> s1 = Stream()
>>> s2 = Stream()
>>> s1.combine_latest(s2) >> print
>>> 1 >> s1  # 等待s2有值
>>> 'a' >> s2  # 输出:(1, 'a') 
>>> 2 >> s1  # 输出:(2, 'a')

7. 流分区:
>>> s = Stream()
>>> s.partition(3) >> print  # 每3个元素分为一组
>>> for i in range(7):
...     i >> s
(0, 1, 2)
(3, 4, 5)

8. 延迟处理:
>>> s = Stream()
>>> s.delay('1s') >> print  # 延迟1秒处理
>>> 1 >> s  # 1秒后输出:1
>>> 2 >> s  # 1秒后输出:2

注意事项
--------
1. rate_limit 和 delay 需要事件循环支持
2. buffer 类操作在数据量大时要注意内存使用
3. timed_window 的时间间隔要根据数据流速合理设置
4. 组合操作(zip/combine_latest)要注意上游流的数据到达顺序

参见
--------
deva.core.Stream : 基础流处理类
deva.store : 存储模块
"""


no_default = '--no-default--'
logger = logging.getLogger(__name__)


@Stream.register_api()
class rate_limit(Stream):
    """ Limit the flow of data

    This stops two elements of streaming through in an interval shorter
    than the provided value.

    Parameters
    ----------
    interval: float
        Time in seconds
    """
    _graphviz_shape = 'octagon'

    def __init__(self, upstream, interval, **kwargs):
        self.interval = convert_interval(interval)
        self.next = 0

        Stream.__init__(self, upstream, ensure_io_loop=True, **kwargs)

    @gen.coroutine
    def update(self, x, who=None):
        now = time()
        old_next = self.next
        self.next = max(now, self.next) + self.interval
        if now < old_next:
            yield gen.sleep(old_next - now)
        yield self._emit(x)


@Stream.register_api()
class buffer(Stream):
    """缓冲流.

    在流中的某个点允许结果堆积。当应用背压时,这可以帮助平滑系统中的数据流。

    参数
    ----------
    upstream : Stream
        上游流对象
    n : int
        缓冲区大小,超过此大小将阻塞

    示例
    -------
    >>> source = Stream()
    >>> buff = source.buffer(n=100)  # 创建大小为100的缓冲区
    >>> buff.rate_limit(0.1) >> print  # 限制输出速率为每秒10个

    注意
    -------
    - 缓冲区满时,上游数据将被阻塞
    - 可以配合rate_limit使用来控制下游处理速度
    """
    _graphviz_shape = 'diamond'

    def __init__(self, upstream, n, **kwargs):
        self.queue = Queue(maxsize=n)

        Stream.__init__(self, upstream, ensure_io_loop=True, **kwargs)

        self.loop.add_callback(self.cb)

    def update(self, x, who=None):
        return self.queue.put(x)

    @gen.coroutine 
    def cb(self):
        while True:
            x = yield self.queue.get()
            yield self._emit(x)

@Stream.register_api()
class zip(Stream):
    """将多个流组合成一个元组流.

    当所有上游流都产生新数据时,将它们组合成一个元组发送到下游.

    参数
    ----------
    *upstreams : Stream
        要组合的上游流对象
    **kwargs : dict
        其他参数,包括:
        - maxsize: 缓冲区大小,默认10

    示例
    -------
    >>> s1 = Stream()
    >>> s2 = Stream()
    >>> s3 = s1.zip(s2)  # 将s1和s2组合
    >>> s3.sink(print)  # 打印组合后的元组
    >>> 1 >> s1  # 发送数据到s1
    >>> 'a' >> s2  # 发送数据到s2
    (1, 'a')  # 输出组合后的元组

    注意
    -------
    - 只有当所有流都有新数据时才会发送
    - 可以通过maxsize参数控制缓冲区大小
    - 支持将常量值与流组合

    参见
    --------
    combine_latest : 组合最新值
    zip_latest : 组合最新值的变体
    """
    _graphviz_orientation = 270
    _graphviz_shape = 'triangle'

    def __init__(self, *upstreams, **kwargs):
        self.maxsize = kwargs.pop('maxsize', 10)
        self.condition = Condition()
        self.literals = [(i, val) for i, val in enumerate(upstreams)
                         if not isinstance(val, Stream)]

        self.buffers = {upstream: deque()
                        for upstream in upstreams
                        if isinstance(upstream, Stream)}

        upstreams2 = [
            upstream for upstream in upstreams if isinstance(upstream, Stream)]

        Stream.__init__(self, upstreams=upstreams2, **kwargs)

    def pack_literals(self, tup):
        """将常量值填充到缓冲区.

        参数
        ----------
        tup : tuple
            当前的数据元组

        返回
        -------
        tuple
            填充常量后的元组
        """
        inp = list(tup)[::-1]
        out = []
        for i, val in self.literals:
            while len(out) < i:
                out.append(inp.pop())
            out.append(val)

        while inp:
            out.append(inp.pop())

        return tuple(out)

    def update(self, x, who=None):
        """更新流数据.

        当收到上游数据时:
        1. 将数据加入对应缓冲区
        2. 检查是否所有缓冲区都有数据
        3. 如果都有则组合发送,否则等待
        4. 如果缓冲区满则阻塞

        参数
        ----------
        x : Any
            收到的数据
        who : Stream
            数据来源的流对象

        返回
        -------
        Future
            发送数据的Future对象
        """
        L = self.buffers[who]  # get buffer for stream
        L.append(x)
        if len(L) == 1 and all(self.buffers.values()):
            tup = tuple(self.buffers[up][0] for up in self.upstreams)
            for buf in self.buffers.values():
                buf.popleft()
            self.condition.notify_all()
            if self.literals:
                tup = self.pack_literals(tup)
            return self._emit(tup)
        elif len(L) > self.maxsize:
            return self.condition.wait()

@Stream.register_api()
class combine_latest(Stream):
    """组合最新值流.

    将多个流的最新值组合成元组发送。当任一输入流有新数据时,
    会将所有流的最新值组合成元组发送到下游。

    参数
    ----------
    *upstreams : Stream
        输入流列表
    emit_on : stream或stream列表或None
        指定在哪些流更新时发送组合数据。
        如果为None,则在任意流更新时都发送。

    示例
    --------
    >>> from deva import Stream
    >>> s1 = Stream()
    >>> s2 = Stream()
    >>> s3 = Stream()
    >>> combined = combine_latest(s1, s2, s3)
    >>> combined.sink(print)
    
    >>> s1.emit(1)  # 等待其他流有值
    >>> s2.emit('a')  # 等待s3有值
    >>> s3.emit(True)  # 输出: (1, 'a', True)
    >>> s1.emit(2)  # 输出: (2, 'a', True)
    >>> s2.emit('b')  # 输出: (2, 'b', True)

    # 只在s1更新时发送
    >>> combined = combine_latest(s1, s2, s3, emit_on=s1)
    >>> s2.emit('c')  # 不发送
    >>> s1.emit(3)  # 输出: (3, 'c', True)

    参见
    --------
    zip : 等待所有流都有新值时才组合发送
    """
    _graphviz_orientation = 270
    _graphviz_shape = 'triangle'

    def __init__(self, *upstreams, **kwargs):
        emit_on = kwargs.pop('emit_on', None)

        self.last = [None for _ in upstreams]
        self.missing = set(upstreams)
        if emit_on is not None:
            if not isinstance(emit_on, Iterable):
                emit_on = (emit_on, )
            emit_on = tuple(
                upstreams[x] if isinstance(x, int) else x for x in emit_on)
            self.emit_on = emit_on
        else:
            self.emit_on = upstreams
        Stream.__init__(self, upstreams=upstreams, **kwargs)

    def update(self, x, who=None):
        if self.missing and who in self.missing:
            self.missing.remove(who)

        self.last[self.upstreams.index(who)] = x
        if not self.missing and who in self.emit_on:
            tup = tuple(self.last)
            return self._emit(tup)

@Stream.register_api()
class flatten(Stream):
    """ 将列表或可迭代对象的流展平成单个元素的流
    
    该类用于将包含列表或可迭代对象的流转换成单个元素的流。
    它会遍历输入的列表/可迭代对象,将每个元素单独发送出去。

    Examples
    --------
    >>> source = Stream()
    >>> source.flatten().sink(print) 
    >>> for x in [[1, 2, 3], [4, 5], [6, 7, 7]]:
    ...     source.emit(x)
    1
    2
    3
    4
    5
    6
    7

    参数
    ----
    upstream : Stream
        上游数据流

    返回
    ----
    Stream
        展平后的数据流

    See Also
    --------
    partition : 与flatten相反,将单个元素的流组合成列表的流
    """

    def update(self, x, who=None):
        L = []
        for item in x:
            y = self._emit(item)
            if type(y) is list:
                L.extend(y)
            else:
                L.append(y)
        return L

@Stream.register_api()
class unique(Stream):
    """ 避免发送重复元素的流

    该类用于对流进行去重,只允许新的元素通过。
    可以通过 `maxsize` 参数控制历史记录的大小。
    例如设置 `maxsize=1` 可以避免连续重复的元素通过。

    参数
    ----------
    upstream : Stream
        上游数据流
    maxsize : int 或 None, 可选
        存储的唯一值数量上限
    key : function, 可选
        用于获取数据表示的函数。
        例如 `key=lambda x: x['a']` 可以只允许具有唯一 'a' 值的数据通过。
    hashable : bool, 可选
        如果为True则假定数据是可哈希的,否则不是。这用于确定如何缓存历史记录,
        如果可哈希则使用字典或LRU缓存,否则使用deque。默认为True。
    persistname : str 或 False, 可选
        是否持久化存储历史记录。如果提供字符串则作为存储名称。

    示例
    --------
    >>> source = Stream()
    >>> source.unique(maxsize=1).sink(print)
    >>> for x in [1, 1, 2, 2, 2, 1, 3]:
    ...     source.emit(x)
    1
    2 
    1
    3

    # 持久化去重示例,通常用于报警发送
    >>> to_send = Stream()
    >>> dds = to_send.unique(persistname='alerts', maxsize=1024*1024*2)
    >>> dds >> log
    >>> 232 >> to_send  # 首次发送
    >>> 232 >> to_send  # 重复发送会被过滤
    """

    def __init__(self, upstream, maxsize=None,
                 key=identity, hashable=True,
                 persistname=False,
                 **kwargs):
        self.key = key
        self.log = kwargs.pop('log', None)
        self.maxsize = maxsize
        if hashable:
            self.seen = dict()
            if self.maxsize:
                from zict import LRU
                self.seen = LRU(self.maxsize, self.seen)
        else:
            self.seen = []

        if persistname:
            # self.seen = NODB()

            # self.seen = diskcache.Cache(size_limit=size_limit)
            self.seen = DBStream(name=persistname,
                                 filename='_unique_persist',
                                 maxsize=self.maxsize or 200,
                                 **kwargs)

        Stream.__init__(self, upstream, **kwargs)

    def update(self, x, who=None):
        y = self.key(x)
        emit = True
        if isinstance(self.seen, list):
            if y in self.seen:
                self.seen.remove(y)
                emit = False
            self.seen.insert(0, y)
            if self.maxsize:
                del self.seen[self.maxsize:]
            if emit:
                return self._emit(x)

        else:
            if self.seen.get(str(y), '~~not_seen~~') == '~~not_seen~~':
                self.seen[str(y)] = 1
                return self._emit(x)

@Stream.register_api()
class union(Stream):
    """合并多个流为一个流.

    将多个输入流合并成一个输出流。任一输入流的数据都会立即发送到输出流,
    不会与其他流的数据进行组合。

    参数
    ----------
    *upstreams : Stream
        输入流列表

    示例
    --------
    >>> from deva import Stream
    >>> s1 = Stream()
    >>> s2 = Stream() 
    >>> s3 = Stream()
    >>> merged = union(s1, s2, s3)
    >>> merged.sink(print)
    
    >>> s1.emit(1)  # 输出: 1
    >>> s2.emit('a')  # 输出: 'a'
    >>> s3.emit(True)  # 输出: True
    >>> s1.emit(2)  # 输出: 2

    参见
    --------
    zip : 等待所有流都有新值时才组合发送
    combine_latest : 组合所有流的最新值发送
    """

    def __init__(self, *upstreams, **kwargs):
        super(union, self).__init__(upstreams=upstreams, **kwargs)

    def update(self, x, who=None):
        return self._emit(x)

@Stream.register_api()
class pluck(Stream):
    """提取流中元素的指定字段.

    从流中的每个元素提取指定的字段或索引,生成新的流。
    可以提取单个字段或多个字段。

    参数
    ----------
    pick : object或list
        要从流中元素提取的字段或索引。
        如果是list类型,则提取多个字段。

    示例
    --------
    >>> from deva import Stream
    >>> s = Stream()
    >>> s.pluck([0, 2]).sink(print)  # 提取列表的第0和第2个元素
    >>> s.emit([1, 2, 3, 4])  # 输出: (1, 3)
    >>> s.emit([5, 6, 7, 8])  # ��出: (5, 7)

    >>> s = Stream()
    >>> s.pluck('name').sink(print)  # 提取字典的name字段
    >>> s.emit({'name': '张三', 'age': 20})  # 输出: '张三'
    >>> s.emit({'name': '李四', 'age': 30})  # 输出: '李四'

    参见
    --------
    map : 对流中的元素进行映射转换
    filter : 过滤流中的元素
    """

    def __init__(self, upstream, pick, **kwargs):
        self.pick = pick
        super(pluck, self).__init__(upstream, **kwargs)

    def update(self, x, who=None):
        if isinstance(self.pick, list):
            return self._emit(tuple([x[ind] for ind in self.pick]))
        else:
            return self._emit(x[self.pick])

@Stream.register_api()
class collect(Stream):
    """收集流.

    将流中的元素缓存起来,当收到flush信号时一次性发送所有缓存的元素。
    适用于需要批量处理数据的场景。

    参数
    ----------
    upstream : Stream
        上游流对象
    cache : deque, 可选
        用于缓存元素的双端队列,默认为None时创建新的队列

    示例
    --------
    >>> from deva import Stream
    >>> s1 = Stream()
    >>> s2 = Stream() 
    >>> c = s1.collect()  # 创建收集器
    >>> c.sink(print)  # 打印收集的元素
    >>> s2.sink(c.flush)  # s2用于触发flush
    
    >>> s1.emit(1)  # 缓存元素1
    >>> s1.emit(2)  # 缓存元素2
    >>> s1.emit(3)  # 缓存元素3
    >>> s2.emit('flush')  # 触发flush,输出: (1, 2, 3)

    参见
    --------
    buffer : 固定大小的缓冲区
    rate_limit : 限制数据流速率
    """

    def __init__(self, upstream, cache=None, **kwargs):
        if cache is None:
            cache = deque()
        self.cache = cache

        Stream.__init__(self, upstream, **kwargs)

    def update(self, x, who=None):
        self.cache.append(x)

    def flush(self, _=None):
        out = tuple(self.cache)
        self._emit(out)
        self.cache.clear()

@Stream.register_api()
class zip_latest(Stream):
    """最新值组合流.

    将多个流组合成元组流,其中一个流保持无损,其他流取最新值。

    当无损流收到数据时,会与其他流的最新值组合成元组发送。
    无损流的所有数据都会被发送,不会丢失。其他流只保留最新值。

    参数
    ----------
    lossless : Stream
        无损流,所有数据都会被发送
    *upstreams : Stream
        其他输入流,只保留最新值
    **kwargs : dict
        其他参数

    示例
    --------
    >>> from deva import Stream
    >>> s1 = Stream()  # 无损流
    >>> s2 = Stream()  # 最新值流
    >>> s3 = Stream()  # 最新值流
    >>> zl = zip_latest(s1, s2, s3)
    >>> zl.sink(print)
    
    >>> s2.emit('a')  # 等待s1和s3有值
    >>> s3.emit(True)  # 等待s1有值
    >>> s1.emit(1)  # 输出: (1, 'a', True)
    >>> s2.emit('b')  # 更新s2最新值
    >>> s1.emit(2)  # 输出: (2, 'b', True)
    >>> s1.emit(3)  # 输出: (3, 'b', True)

    参见
    --------
    combine_latest : 组合所有流的最新值
    zip : 等待所有流都有新值时组合
    """

    def __init__(self, lossless, *upstreams, **kwargs):
        upstreams = (lossless,) + upstreams
        self.last = [None for _ in upstreams]
        self.missing = set(upstreams)
        self.lossless = lossless
        self.lossless_buffer = deque()
        Stream.__init__(self, upstreams=upstreams, **kwargs)

    def update(self, x, who=None):
        idx = self.upstreams.index(who)
        if who is self.lossless:
            self.lossless_buffer.append(x)

        self.last[idx] = x
        if self.missing and who in self.missing:
            self.missing.remove(who)

        if not self.missing:
            L = []
            while self.lossless_buffer:
                self.last[0] = self.lossless_buffer.popleft()
                L.append(self._emit(tuple(self.last)))
            return L

@Stream.register_api()
class latest(Stream):
    """最新值流.

    当流中存在背压导致处理速度变慢时,跳过中间元素只保留最新值。
    适用于只关心最新数据,可以丢弃旧数据的场景。

    如果没有背压,则直接传递数据不做修改。

    参数
    ----------
    upstream : Stream
        上游流对象
    **kwargs : dict
        其他参数

    示例
    --------
    >>> source.map(f).latest().map(g)  # 只处理最新值

    注意
    -------
    - 当处理速度跟不上时会丢弃旧数据
    - 适合实时数据处理场景
    - 可以缓解系统背压
    """
    _graphviz_shape = 'octagon'

    def __init__(self, upstream, **kwargs):
        self.condition = Condition()  # 条件变量用于通知
        self.next = []  # 存储最新值

        Stream.__init__(self, upstream, ensure_io_loop=True, **kwargs)

        self.loop.add_callback(self.cb)  # 启动回调处理

    def update(self, x, who=None):
        """更新最新值并通知处理

        Args:
            x: 新数据
            who: 数据来源(未使用)
        """
        self.next = [x]  # 更新最新值
        self.loop.add_callback(self.condition.notify)  # 通知处理

    @gen.coroutine
    def cb(self):
        """异步处理回调

        循环等待新数据并发送到下游
        """
        while True:
            yield self.condition.wait()  # 等待新数据
            [x] = self.next  # 获取最新值
            yield self._emit(x)  # 发送到下游

@Stream.register_api()
class accumulate(Stream):
    """ 累积流.

    对流中的数据进行累积计算,将函数应用于前一个状态和新元素。
    函数应该接收两��参数:前一个累积状态和新元素,并返回新的累积状态。

    - 当returns_state=False时: state = func(previous_state, new_value)
    - 当returns_state=True时: state, result = func(previous_state, new_value) 

    新状态会传递给下一次调用。根据returns_state的值,状态或结果会发送到下游。

    参数
    ----------
    func : callable
        累积计算函数
    start : object
        初始值,作为第一次调用时的previous_state。默认使用第一个元素
    returns_state : boolean
        如果为True,则func应返回状态和要发送的值
        如果为False,则两个值相同,func返回一个值
    **kwargs :
        传递给func的关键字参数

    示例
    --------
    # 计算累加和,生成三角形数
    >>> source = Stream()
    >>> source.accumulate(lambda acc, x: acc + x).sink(print)
    >>> for i in range(5):
    ...     source.emit(i)
    0
    1
    3
    6
    10

    # 计数器,统计事件数量
    >>> source = Stream()
    >>> source.accumulate(lambda acc, x: acc + 1, start=0).sink(print)
    >>> for _ in range(5):
    ...     source.emit(0)
    1
    2
    3
    4
    5

    # 类似内置的enumerate
    >>> source = Stream()
    >>> source.accumulate(lambda acc, x: ((acc[0] + 1, x), (acc[0], x)),
    ...                   start=(0, 0), returns_state=True
    ...                   ).sink(print)
    >>> for i in range(3):
    ...     source.emit(0)
    (0, 0)
    (1, 0)
    (2, 0)
    """
    _graphviz_shape = 'box'

    def __init__(self, upstream, func, start=no_default, returns_state=False,
                 **kwargs):
        self.func = func
        self.kwargs = kwargs
        self.state = start
        self.returns_state = returns_state
        # this is one of a few stream specific kwargs
        name = kwargs.pop('name', None)
        Stream.__init__(self, upstream, name=name)

    def update(self, x, who=None):
        if self.state is no_default:
            self.state = x
            return self._emit(x)
        else:
            try:
                result = self.func(self.state, x, **self.kwargs)
            except Exception as e:
                logger.exception(e)
                raise
            if self.returns_state:
                state, result = result
            else:
                state = result
            self.state = state
            return self._emit(result)

@Stream.register_api()
class slice(Stream):
    """按位置获取流中的部分事件.

    该类用于从流中���择指定位置范围内的事件,类似于Python列表的切片语法。

    参数
    ----------
    start : int
        起始位置。如果为None,则从头开始。
    end : int 
        结束位置(不包含)。如果为None,则一直持续。
        不支持负数索引。
    step : int
        步长,每隔多少个事件取一个。如果为None,则每个都取。

    示例
    --------
    >>> source = Stream()
    >>> source.slice(2, 6, 2).sink(print)  # 从第2个开始,每隔2个取一个,直到第6个
    >>> for i in range(5):
    ...     source.emit(0)
    2  # 输出第2个
    4  # 输出第4个
    """

    def __init__(self, upstream, start=None, end=None, step=None, **kwargs):
        self.state = 0
        self.star = start or 0
        self.end = end
        self.step = step or 1
        if any((_ or 0) < 0 for _ in [start, end, step]):
            raise ValueError("Negative indices not supported by slice")
        name = kwargs.pop('name', None)
        Stream.__init__(self, upstream, name=name)
        self._check_end()

    def update(self, x, who=None):
        if self.state >= self.star and self.state % self.step == 0:
            self.emit(x)
        self.state += 1
        self._check_end()

    def _check_end(self):
        if self.end and self.state >= self.end:
            # we're done
            self.upstream.downstreams.remove(self)

@Stream.register_api()
class partition(Stream):
    """将流分割成固定大小的元组.

    该类用于将输入流按照指定大小n分组,每组n个元素组成一个元组输出。
    当缓冲区积累了n个元素后,将它们作为一个元组发送到下游。

    参数
    ----------
    upstream : Stream
        上游数据流
    n : int
        每组元素的数量

    示例
    --------
    >>> source = Stream()
    >>> source.partition(3).sink(print)  # 每3个元素分为一组
    >>> for i in range(10):
    ...     source.emit(i)
    (0, 1, 2)  # 输出第一组
    (3, 4, 5)  # 输出第二组
    (6, 7, 8)  # 输出第三组

    注意
    -------
    - 如果元素总数不是n的整数倍,最后剩余的元素将被丢弃
    - 每组输出的是元组形式
    - 与sliding_window不同,partition的分组之间没有重叠

    参见
    --------
    sliding_window : 滑动窗口,产生重叠的分组
    flatten : 与partition相反,将元组/列表展平成单个元素
    """
    _graphviz_shape = 'diamond'

    def __init__(self, upstream, n, **kwargs):
        self.n = n
        self.buffer = []
        Stream.__init__(self, upstream, **kwargs)

    def update(self, x, who=None):
        self.buffer.append(x)
        if len(self.buffer) == self.n:
            result, self.buffer = self.buffer, []
            return self._emit(tuple(result))
        else:
            return []

@Stream.register_api()
class sliding_window(Stream):
    """滑动窗口流.

    产生固定大小的重叠元组序列。每当有新数据到来时,将其添加到窗口中,
    并输出当前窗口内的所有数据。

    参数
    ----------
    upstream : Stream
        上游数据流
    n : int
        窗口大小
    return_partial : bool
        如果为True,则在窗口未满时也会输出部分数据。
        如果为False,则只有在窗口满时才会输出。

    示例
    --------
    >>> source = Stream()
    >>> source.sliding_window(3, return_partial=False).sink(print)
    >>> for i in range(8):
    ...     source.emit(i)
    (0, 1, 2)  # 窗口满时开始输出
    (1, 2, 3)  # 窗口向右滑动
    (2, 3, 4)
    (3, 4, 5)
    (4, 5, 6)
    (5, 6, 7)

    注意
    -------
    - 使用deque作为固定大小的缓冲区
    - 可以通过return_partial控制是否输出部分窗口
    - 每次输出的是元组形式的窗口数据
    """
    _graphviz_shape = 'diamond'

    def __init__(self, upstream, n, return_partial=True, **kwargs):
        self.n = n
        self.buffer = deque(maxlen=n)
        self.partial = return_partial
        Stream.__init__(self, upstream, **kwargs)

    def update(self, x, who=None):
        self.buffer.append(x)
        if self.partial or len(self.buffer) == self.n:
            return self._emit(tuple(self.buffer))
        else:
            return []

@Stream.register_api()
class timed_window(Stream):
    """定时窗口流.

    每隔指定的时间间隔发送一次收集到的所有结果。
    这可以帮助对高频流数据进行批量处理。

    参数
    ----------
    upstream : Stream
        上游数据流
    interval : float 或 str
        时间间隔,可以是秒数或时间字符串(如'1s','5min')

    示例
    --------
    >>> source = Stream()
    >>> source.timed_window('2s').sink(print)  # 每2秒打印收集的数据
    >>> for i in range(10):  # 快速发送数据
    ...     source.emit(i)
    [0, 1, 2, 3]  # 2秒后输出
    [4, 5, 6, 7]  # 再过2秒输出
    [8, 9]  # 最后2秒输出

    注意
    -------
    - 使用ensure_io_loop=True确保有事件循环
    - 通过buffer缓存数据
    - 每interval秒发送一次缓存数据
    """
    _graphviz_shape = 'octagon'

    def __init__(self, upstream, interval, **kwargs):
        self.interval = convert_interval(interval)
        self.buffer = []
        self.last = gen.moment

        Stream.__init__(self, upstream, ensure_io_loop=True, **kwargs)

        self.loop.add_callback(self.cb)

    def update(self, x, who=None):
        self.buffer.append(x)
        return self.last

    @gen.coroutine
    def cb(self):
        while True:
            L, self.buffer = self.buffer, []
            self.last = self._emit(L)
            yield self.last
            yield gen.sleep(self.interval)

@Stream.register_api()
class delay(Stream):
    """延迟流.

    为流中的每个元素添加固定的时间延迟。
    可用于模拟网络延迟、限流等场景。

    参数
    ----------
    upstream : Stream
        上游数据流
    interval : float 或 str
        延迟时间,可以是秒数或时间字符串(如'1s','5min')
    **kwargs : dict
        其他参数

    示例
    --------
    >>> from deva import Stream
    >>> s = Stream()
    >>> d = s.delay('1s')  # 添加1秒延迟
    >>> d.sink(print)
    
    >>> s.emit(1)  # 1秒后输出: 1
    >>> s.emit(2)  # 1秒后输出: 2
    >>> s.emit(3)  # 1秒后输出: 3

    参见
    --------
    rate_limit : 限制数据流速率
    buffer : 缓冲数据
    """
    _graphviz_shape = 'octagon'

    def __init__(self, upstream, interval, **kwargs):
        self.interval = convert_interval(interval)
        self.queue = Queue()

        Stream.__init__(self, upstream, ensure_io_loop=True, **kwargs)

        self.loop.add_callback(self.cb)

    @gen.coroutine
    def cb(self):
        while True:
            last = time()
            x = yield self.queue.get()
            yield self._emit(x)
            duration = self.interval - (time() - last)
            if duration > 0:
                yield gen.sleep(duration)

    def update(self, x, who=None):
        return self.queue.put(x)