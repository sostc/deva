from __future__ import absolute_import, division, print_function

from collections import deque, Iterable
from datetime import datetime, timedelta
import functools
import logging
import six
import sys
import threading
from time import time
import weakref

import toolz
from tornado import gen
from tornado.locks import Condition
from tornado.ioloop import IOLoop
from tornado.queues import Queue
try:
    from tornado.ioloop import PollIOLoop
except ImportError:
    PollIOLoop = None  # dropped in tornado 6.0

from .compatibility import get_thread_identity
from .orderedweakset import OrderedWeakrefSet

from .expiringdict import ExpiringDict
from pampy import match, ANY
import io
import pandas as pd
from ..pipe import *

import pkg_resources
from .sqlitedict import SqliteDict
import moment


no_default = '--no-default--'

_global_sinks = set()

_html_update_streams = set()

thread_state = threading.local()

logger = logging.getLogger(__name__)


_io_loops = []


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
    """ A Stream is an infinite sequence of data

    Streams subscribe to each other passing and transforming data between them.
    A Stream object listens for updates from upstream, reacts to these updates,
    and then emits more data to flow downstream to all Stream objects that
    subscribe to it.  Downstream Stream objects may connect at any point of a
    Stream graph to get a full view of the data coming off of that point to do
    with as they will.

    Parameters
    ----------
    asynchronous: boolean or None
        Whether or not this stream will be used in asynchronous functions or
        normal Python functions.  Leave as None if you don't know.
        True will cause operations like emit to return awaitable Futures
        False will use an Event loop in another thread (starts it if necessary)
    ensure_io_loop: boolean
        Ensure that some IOLoop will be created.  If asynchronous is None or
        False then this will be in a separate thread, otherwise it will be
        IOLoop.current

    Examples
    --------
    >>> def inc(x):
    ...     return x + 1

    >>> source = Stream()  # Create a stream object
    >>> s = source.map(inc).map(str)  # Subscribe to make new streams
    >>> s.sink(print)  # take an action whenever an element reaches the end

    >>> L = list()
    >>> s.sink(L.append)  # or take multiple actions (streams can branch)

    >>> for i in range(5):
    ...     source.emit(i)  # push data in at the source
    '1'
    '2'
    '3'
    '4'
    '5'
    >>> L  # and the actions happen at the sinks
    ['1', '2', '3', '4', '5']
    """
    _graphviz_shape = 'ellipse'
    _graphviz_style = 'rounded,filled'
    _graphviz_fillcolor = 'white'
    _graphviz_orientation = 0

    _instances = set()

    str_list = ['func', 'predicate', 'n', 'interval']

    def __init__(self, upstream=None, upstreams=None, stream_name=None,
                 cache_max_len=None, cache_max_age_seconds=None,
                 loop=None, asynchronous=None, ensure_io_loop=False):
        self.downstreams = OrderedWeakrefSet()
        if upstreams is not None:
            self.upstreams = list(upstreams)
        else:
            self.upstreams = [upstream]

        self._set_asynchronous(asynchronous)
        self._set_loop(loop)
        if ensure_io_loop and not self.loop:
            self._set_asynchronous(False)
        if self.loop is None and self.asynchronous is not None:
            self._set_loop(get_io_loop(self.asynchronous))

        for upstream in self.upstreams:
            if upstream:
                upstream.downstreams.add(self)

        self.stream_name = stream_name

        if cache_max_len or cache_max_age_seconds:
            self.set_cache(cache_max_len, cache_max_age_seconds)
        else:
            self.clear_cache()

        self.handlers = []

        Stream._instances.add(weakref.ref(self))

    def set_cache(self, cache_max_len=None, cache_max_age_seconds=None):
        self.is_cache = True
        if not cache_max_len:
            cache_max_len = 1
        if not cache_max_age_seconds:
            cache_max_age_seconds = 60*5

        self.cache_max_len = cache_max_len
        self.cache_max_age_seconds = cache_max_age_seconds
        self._store = ExpiringDict(
            max_len=self.cache_max_len,
            max_age_seconds=self.cache_max_age_seconds
        )

    def clear_cache(self,):
        self.is_cache = False
        self._store = None

    def _set_loop(self, loop):
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
        Percolate information about an event loop to the rest of the stream
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
        Percolate information about an event loop to the rest of the stream
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
    def getinstances(cls):
        dead = set()
        for ref in cls._instances:
            obj = ref()
            if obj is not None\
                    and obj.stream_name is not None\
                    and not obj.stream_name.startswith('_'):
                yield obj
            else:
                dead.add(ref)
        cls._instances -= dead

    @classmethod
    def register_api(cls, modifier=identity):
        """ Add callable to Stream API

        This allows you to register a new method onto this class.  You can use
        it as a decorator.::

            >>> @Stream.register_api()
            ... class foo(Stream):
            ...     ...

            >>> Stream().foo(...)  # this works now

        It attaches the callable as a normal attribute to the class object.  In
        doing so it respsects inheritance (all subclasses of Stream will also
        get the foo attribute).

        By default callables are assumed to be instance methods.  If you like
        you can include modifiers to apply before attaching to the class as in
        the following case where we construct a ``staticmethod``.

            >>> @Stream.register_api(staticmethod)
            ... class foo(Stream):
            ...     ...

            >>> Stream.foo(...)  # Foo operates as a static method
        """
        def _(func):
            @functools.wraps(func)
            def wrapped(*args, **kwargs):
                return func(*args, **kwargs)
            setattr(cls, func.__name__, modifier(wrapped))
            return func
        return _

    def start(self):
        """ Start any upstream sources """
        for upstream in self.upstreams:
            upstream.start()

    def __str__(self):
        s_list = []
        if self.stream_name:
            s_list.append('{}; {}'.format(
                self.stream_name, self.__class__.__name__))
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

        return output._ipython_display_(**kwargs)

    def _emit(self, x):
        if self.is_cache:
            self._cache(x)

        result = []
        for downstream in list(self.downstreams):
            r = downstream.update(x, who=self)
            if type(r) is list:
                result.extend(r)
            else:
                result.append(r)

        return [element for element in result if element is not None]

    def emit(self, x, asynchronous=False):
        """ Push data into the stream at this point

        This is typically done only at source Streams but can theortically be
        done at any point
        """
        ts_async = getattr(thread_state, 'asynchronous', False)
        if self.loop is None or asynchronous or self.asynchronous or ts_async:
            if not ts_async:
                thread_state.asynchronous = True
            try:
                result = self._emit(x)
                if self.loop:
                    return gen.convert_yielded(result)
            finally:
                thread_state.asynchronous = ts_async
        else:
            @gen.coroutine
            def _():
                thread_state.asynchronous = True
                try:
                    result = yield self._emit(x)
                finally:
                    del thread_state.asynchronous

                raise gen.Return(result)
            sync(self.loop, _)

    def update(self, x, who=None):
        self._emit(x)

    def gather(self):
        """ This is a no-op for core streamz

        This allows gather to be used in both dask and core streams
        """
        return self

    def connect(self, downstream):
        ''' Connect this stream to a downstream element.

        Parameters
        ----------
        downstream: Stream
            The downstream stream to connect to
        '''
        self.downstreams.add(downstream)

        if downstream.upstreams == [None]:
            downstream.upstreams = [self]
        else:
            downstream.upstreams.append(self)

    def disconnect(self, downstream):
        ''' Disconnect this stream to a downstream element.

        Parameters
        ----------
        downstream: Stream
            The downstream stream to disconnect from
        '''
        self.downstreams.remove(downstream)

        downstream.upstreams.remove(self)

    @property
    def upstream(self):
        if len(self.upstreams) != 1:
            raise ValueError("Stream has multiple upstreams")
        else:
            return self.upstreams[0]

    def destroy(self, streams=None):
        """
        Disconnect this stream from any upstream sources
        """
        if streams is None:
            streams = self.upstreams
        for upstream in list(streams):
            upstream.downstreams.remove(self)
            self.upstreams.remove(upstream)

    def scatter(self, **kwargs):
        from .dask import scatter
        return scatter(self, **kwargs)

    def remove(self, predicate):
        """Only pass through elements for which the predicate returns False """
        return self.filter(lambda x: not predicate(x))

    @property
    def scan(self):
        return self.accumulate

    @property
    def concat(self):
        return self.flatten

    def sink_to_list(self):
        """ Append all elements of a stream to a list as they come in

        Examples
        --------
        >>> source = Stream()
        >>> L = source.map(lambda x: 10 * x).sink_to_list()
        >>> for i in range(5):
        ...     source.emit(i)
        >>> L
        [0, 10, 20, 30, 40]
        """
        L = []
        self.sink(L.append)
        return L

    def frequencies(self, **kwargs):
        """ Count occurrences of elements """
        def update_frequencies(last, x):
            return toolz.assoc(last, x, last.get(x, 0) + 1)

        return self.scan(update_frequencies, start={}, **kwargs)

    def visualize(self, filename='mystream.png', source_node=False, **kwargs):
        """Render the computation of this object's task graph using graphviz.

        Requires ``graphviz`` to be installed.

        Parameters
        ----------
        filename : str, optional
            The name of the file to write to disk.
        source_node: bool, optional
            If True then the node is the source node and we can label the
            edges in their execution order. Defaults to False
        kwargs:
            Graph attributes to pass to graphviz like ``rankdir="LR"``
        """
        from .graph import visualize
        return visualize(self, filename, source_node=source_node, **kwargs)

    def to_dataframe(self, example):
        """ Convert a stream of Pandas dataframes to a DataFrame

        Examples
        --------
        >>> source = Stream()
        >>> sdf = source.to_dataframe()
        >>> L = sdf.groupby(sdf.x).y.mean().stream.sink_to_list()
        >>> source.emit(pd.DataFrame(...))  # doctest: +SKIP
        >>> source.emit(pd.DataFrame(...))  # doctest: +SKIP
        >>> source.emit(pd.DataFrame(...))  # doctest: +SKIP
        """
        from .dataframe import DataFrame
        return DataFrame(stream=self, example=example)

    def to_batch(self, **kwargs):
        """ Convert a stream of lists to a Batch

        All elements of the stream are assumed to be lists or tuples

        Examples
        --------
        >>> source = Stream()
        >>> batches = source.to_batch()
        >>> L = batches.pluck('value').map(inc).sum().stream.sink_to_list()
        >>> source.emit([{'name': 'Alice', 'value': 1},
        ...              {'name': 'Bob', 'value': 2},
        ...              {'name': 'Charlie', 'value': 3}])
        >>> source.emit([{'name': 'Alice', 'value': 4},
        ...              {'name': 'Bob', 'value': 5},
        ...              {'name': 'Charlie', 'value': 6}])
        """
        from .batch import Batch
        return Batch(stream=self, **kwargs)

    def __ror__(self, value):  # |
        """emit value to stream ,end,return emit result"""
        self.emit(value)
        return value

    def __rrshift__(self, value):  # stream左边的>>
        """emit value to stream ,end,return emit result"""
        self.emit(value, asynchronous=True)
        return value

    def __lshift__(self, value):  # stream右边的<<
        """emit value to stream ,end,return emit result"""
        self.emit(value)
        return value

    def log_to(self, func):
        """decorater 初始化."""
        from functools import wraps

        # @Pipe
        @wraps(func)
        def wraper(*args, **kwargs):
            # some action before
            try:
                result = func(*args, **kwargs)  # 需要这里显式调用用户函数
                # action after
                # {
                #     'function': func.__name__,
                #     'param': (args, kwargs),
                #     'return': result,
                # } >> self

                return result
            except Exception as e:
                {
                    'function': func.__name__,
                    'param': (args, kwargs),
                    'except': e,
                } >> self

        return wraper

    def __rmatmul__(self, func):
        """左边的 @."""
        return self.log_to(func).__call__@P

    def __rshift__(self, ref):  # stream右边的
        """Stream右边>>,sink到右边的对象.

        支持三种类型:list| text file| stream | callable
        """
        def write(x):
            ref.write(str(x)+'\n')
            ref.flush()
        return match(ref,
                     list, lambda ref: self.sink(ref.append),
                     io.TextIOWrapper, lambda ref: self.sink(write),
                     Stream, lambda ref: self.sink(ref.emit),
                     # 内置函数被转换成pipe，不能pipe优先，需要stream的sink优先
                     # Pipe, lambda ref: ref(self),
                     callable, lambda ref: self.sink(ref),
                     ANY, lambda ref: TypeError(
                         f'{ref}:{type(ref)} is'
                         'Unsupported type, must be '
                         'list| text file| stream | callable')
                     )

    def route(self, occasion):
        """
        occasion:路由函数表达式,比如lambda x:x.startswith('foo') 或者 lambda x:type(x)==str,
        完整例子:
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
            """ 预处理函数，定义包装函数wraper取代老函数.
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

            # self.filter(occasion).sink(wraper)
            self.handlers.append((occasion, func))
            # 包装定义阶段执行，包装后函数是个新函数了，
            # 老函数已经匿名，需要新函数加入handlers列表,这样才可以执行前后发消息
            return wraper
            # 返回的这个函数实际上取代了老函数。
            # 为了将老函数的函数名和docstring继承，需要用functools的wraps将其包装

        return param_wraper

    def _cache(self, value):
        self._store[datetime.now()] = value

    def recent(self, n=5, seconds=None):
        if not self.is_cache:
            return None
        elif not seconds:
            return self._store.values()[-n:]
        else:
            df = self._store >> to_dataframe
            df.columns = ['value']
            now_time = datetime.now()
            begin = now_time + timedelta(seconds=-seconds)
            return df[begin:]

    def __iter__(self,):
        return self._store.values().__iter__()


@Stream.register_api()
class sink(Stream):
    """ Apply a function on every element

    Examples
    --------
    >>> source = Stream()
    >>> L = list()
    >>> source.sink(L.append)
    >>> source.sink(print)
    >>> source.sink(print)
    >>> source.emit(123)
    123
    123
    >>> L
    [123]

    See Also
    --------
    map
    Stream.sink_to_list
    """
    _graphviz_shape = 'trapezium'

    def __init__(self, upstream, func, *args, **kwargs):
        self.func = func
        # take the stream specific kwargs out
        stream_name = kwargs.pop("stream_name", None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, stream_name=stream_name)
        _global_sinks.add(self)

    def update(self, x, who=None):
        result = self.func(x, *self.args, **self.kwargs)
        if gen.isawaitable(result):
            return result
        else:
            return []


@Stream.register_api()
class map(Stream):
    """ Apply a function to every element in the stream

    Parameters
    ----------
    func: callable
    *args :
        The arguments to pass to the function.
    **kwargs:
        Keyword arguments to pass to func

    Examples
    --------
    >>> source = Stream()
    >>> source.map(lambda x: 2*x).sink(print)
    >>> for i in range(5):
    ...     source.emit(i)
    0
    2
    4
    6
    8
    """

    def __init__(self, upstream, func, cache_max_len=None, *args, **kwargs):
        self.func = func
        # this is one of a few stream specific kwargs
        stream_name = kwargs.pop('stream_name', None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, stream_name=stream_name,
                        cache_max_len=cache_max_len)

    def update(self, x, who=None):
        try:
            result = self.func(x, *self.args, **self.kwargs)
        except Exception as e:
            logger.exception(e)
            raise
        else:
            return self._emit(result)


@Stream.register_api()
class starmap(Stream):
    """ Apply a function to every element in the stream, splayed out

    See ``itertools.starmap``

    Parameters
    ----------
    func: callable
    *args :
        The arguments to pass to the function.
    **kwargs:
        Keyword arguments to pass to func

    Examples
    --------
    >>> source = Stream()
    >>> source.starmap(lambda a, b: a + b).sink(print)
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
        stream_name = kwargs.pop('stream_name', None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, stream_name=stream_name)

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
    if not isinstance(pd.DataFrame):
        return not not x
    else:
        return x.empty


@Stream.register_api()
class filter(Stream):
    """ Only pass through elements that satisfy the predicate

    Parameters
    ----------
    predicate : function
        The predicate. Should return True or False, where
        True means that the predicate is satisfied.

    Examples
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
        stream_name = kwargs.pop('stream_name', None)
        cache_max_len = kwargs.pop('cache_max_len', None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, stream_name=stream_name,)

    def update(self, x, who=None):
        if self.predicate(x, *self.args, **self.kwargs):
            return self._emit(x)


@Stream.register_api()
class accumulate(Stream):
    """ Accumulate results with previous state

    This performs running or cumulative reductions, applying the function
    to the previous total and the new element.  The function should take
    two arguments, the previous accumulated state and the next element and
    it should return a new accumulated state,
    - ``state = func(previous_state, new_value)`` (returns_state=False)
    - ``state, result = func(previous_state, new_value)`` (returns_state=True)

    where the new_state is passed to the next invocation. The state or result
    is emitted downstream for the two cases.

    Parameters
    ----------
    func: callable
    start: object
        Initial value, passed as the value of ``previous_state`` on the first
        invocation. Defaults to the first submitted element
    returns_state: boolean
        If true then func should return both the state and the value to emit
        If false then both values are the same, and func returns one value
    **kwargs:
        Keyword arguments to pass to func

    Examples
    --------
    A running total, producing triangular numbers

    >>> source = Stream()
    >>> source.accumulate(lambda acc, x: acc + x).sink(print)
    >>> for i in range(5):
    ...     source.emit(i)
    0
    1
    3
    6
    10

    A count of number of events (including the current one)

    >>> source = Stream()
    >>> source.accumulate(lambda acc, x: acc + 1, start=0).sink(print)
    >>> for _ in range(5):
    ...     source.emit(0)
    1
    2
    3
    4
    5

    Like the builtin "enumerate".

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
        stream_name = kwargs.pop('stream_name', None)
        Stream.__init__(self, upstream, stream_name=stream_name)

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
    """
    Get only some events in a stream by position. Works like list[] syntax.

    Parameters
    ----------
    start : int
        First event to use. If None, start from the beginnning
    end : int
        Last event to use (non-inclusive). If None, continue without stopping.
        Does not support negative indexing.
    step : int
        Pass on every Nth event. If None, pass every one.

    Examples
    --------
    >>> source = Stream()
    >>> source.slice(2, 6, 2).sink(print)
    >>> for i in range(5):
    ...     source.emit(0)
    2
    4
    """

    def __init__(self, upstream, start=None, end=None, step=None, **kwargs):
        self.state = 0
        self.star = start or 0
        self.end = end
        self.step = step or 1
        if any((_ or 0) < 0 for _ in [start, end, step]):
            raise ValueError("Negative indices not supported by slice")
        stream_name = kwargs.pop('stream_name', None)
        Stream.__init__(self, upstream, stream_name=stream_name)
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
    """ Partition stream into tuples of equal size

    Examples
    --------
    >>> source = Stream()
    >>> source.partition(3).sink(print)
    >>> for i in range(10):
    ...     source.emit(i)
    (0, 1, 2)
    (3, 4, 5)
    (6, 7, 8)
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
    """ Produce overlapping tuples of size n

    Parameters
    ----------
    return_partial : bool
        If True, yield tuples as soon as any events come in, each tuple being
        smaller or equal to the window size. If False, only start yielding
        tuples once a full window has accrued.

    Examples
    --------
    >>> source = Stream()
    >>> source.sliding_window(3, return_partial=False).sink(print)
    >>> for i in range(8):
    ...     source.emit(i)
    (0, 1, 2)
    (1, 2, 3)
    (2, 3, 4)
    (3, 4, 5)
    (4, 5, 6)
    (5, 6, 7)
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


def convert_interval(interval):
    if isinstance(interval, str):
        import pandas as pd
        interval = pd.Timedelta(interval).total_seconds()
    return interval


@Stream.register_api()
class timed_window(Stream):
    """ Emit a tuple of collected results every interval

    Every ``interval`` seconds this emits a tuple of all of the results
    seen so far.  This can help to batch data coming off of a high-volume
    stream.
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
    """ Add a time delay to results """
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


@Stream.register_api()
class httpget(Stream):
    """自动http get流中的url，返回response对象

    参数error，流或者pipe函数，发生异常时url会被发送到这里
    注意上游流要限速，这个是并发执行，速度很快
    例子：
    s = Stream()
    get_data = lambda x:x.body.decode('utf-8')>>chinese_extract>>sample(20)>>concat('|')
    s.rate_limit(0.1).httpget(error=log).map(get_data).sink(print)
    """

    def __init__(self, upstream, render=False, error=print, **kwargs):
        self.error = error
        # from tornado import httpclient
        from requests_html import AsyncHTMLSession
        Stream.__init__(self, upstream=upstream)
        # self.http_client = httpclient.AsyncHTTPClient()
        self.httpclient = AsyncHTMLSession()
        self.render = render

    def update(self, url, who=None):
        gen.multi([self._http(url)])

    def emit(self, url, **kwargs):
        gen.multi([self._http(url)])
        return url

    @gen.coroutine
    def _http(self, url):
        try:
            response = yield self.httpclient.get(url)
            if self.render:
                response = response.html.render()

            self._emit(response)
        except Exception as e:
            url >> self.error
            logger.exception(e)
            # raise


@Stream.register_api()
class from_coroutine(Stream):
    """获取上游进来的future的最终值并放入下游
    注意上游流要限速，这个是并发执行，速度很快
    例子：
    @gen.coroutine
    def foo():
        yield gen.sleep(3)
        return range<<10>>sample>>first

    async def foo2():
        import asyncio
        await asyncio.sleep(3)
        return range<<10>>sample>>first

    s = Stream()
    s.rate_limit(1).from_coroutine()>>log

    for i in range(3):
        (foo,arg1,arg2)>>s
        (foo2,arg2)>>s

    [2020-02-26 18:14:37.991321] INFO: deva.log: 1
    [2020-02-26 18:14:37.993260] INFO: deva.log: 7
    [2020-02-26 18:14:37.995112] INFO: deva.log: 5
    """

    def __init__(self, upstream, timeout=3, **kwargs):
        # from tornado import httpclient
        Stream.__init__(self, upstream=upstream, ensure_io_loop=True)
        self.timeout = 3

    def update(self, x, who=None):
        self._emit(sync(self.loop, *x))


@Stream.register_api()
class from_future(Stream):
    """获取上游进来的future的最终值并放入下游
    注意上游流要限速，这个是并发执行，速度很快
    例子：
    @gen.coroutine
    def foo():
        yield gen.sleep(3)
        return range<<10>>sample>>first

    async def foo2():
        import asyncio
        await asyncio.sleep(3)
        return range<<10>>sample>>first

    s = Stream()
    s.rate_limit(1).from_future()>>log

    for i in range(3):
        foo()>>s
        foo2()>>s

    [2020-02-26 18:14:37.991321] INFO: deva.log: 1
    [2020-02-26 18:14:37.993260] INFO: deva.log: 7
    [2020-02-26 18:14:37.995112] INFO: deva.log: 5
    """

    def __init__(self, upstream, **kwargs):
        # from tornado import httpclient
        Stream.__init__(self, upstream=upstream, ensure_io_loop=True)

    def update(self, x, who=None):
        from collections.abc import Coroutine
        if isinstance(x, gen.Future):
            self.loop.add_future(x, lambda x: self._emit(x.result()))
        elif isinstance(x, Coroutine):
            task = self.loop.asyncio_loop.create_task(x)
            task.add_done_callback(lambda x: self._emit(x.result()))


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
    """ Allow results to pile up at this point in the stream

    This allows results to buffer in place at various points in the stream.
    This can help to smooth flow through the system when backpressure is
    applied.
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
    """ Combine streams together into a stream of tuples

    We emit a new tuple once all streams have produce a new tuple.

    See also
    --------
    combine_latest
    zip_latest
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
        """ Fill buffers for literals whenever we empty them """
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
    """ Combine multiple streams together to a stream of tuples

    This will emit a new tuple of all of the most recent elements seen from
    any stream.

    Parameters
    ----------
    emit_on : stream or list of streams or None
        only emit upon update of the streams listed.
        If None, emit on update from any stream

    See Also
    --------
    zip
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
    """ Flatten streams of lists or iterables into a stream of elements

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

    See Also
    --------
    partition
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
class ODBStream(Stream):
    """
    所有输入都会被作为字典在sqlite中做持久存储，若指定tablename，则将所有数据单独存储一个table。使用方式和字典一样
    输入是元组时，第一个值作为key，第二个作为value。
    输入时一个值时，默认时间作为key，moment.unix(key)可还原为moment时间
    输入是字典时，更新字典
    maxsize保持定长字典
    stream_name是表名
    fname是文件路径

    本身对象是一个流，也是一个iterable对象
    """

    def __init__(self, tablename='default', fname='_dictstream', maxsize=None, log=passed, **kwargs):
        self.log = log
        self.tablename = tablename
        self.maxsize = maxsize

        super(ODBStream, self).__init__()
        if fname == '_dictstream':
            self.fname = pkg_resources.resource_filename(__name__, fname+'.sqlite')
        else:
            self.fname = fname+'.sqlite'

        # self.fname = fname+'.sqlite'
        self.db = SqliteDict(
            self.fname,
            tablename=self.tablename,
            autocommit=True)

        # self.db['tablename'] = self.tablename

        self.keys = self.db.keys
        self.values = self.db.values
        self.items = self.db.items
        self.get = self.db.get
        self.clear = self.db.clear
        self.get_tablenames = self.db.get_tablenames
        self._check_size_limit()

    def emit(self, x, asynchronous=False):
        self._to_store(x)
        return super().emit(x, asynchronous=asynchronous)

    def _check_size_limit(self):
        if self.maxsize is not None:
            while len(self.db) > self.maxsize:
                self.db.popitem()

    def _to_store(self, x):
        x >> self.log
        if isinstance(x, dict):
            self.db.update(x)
        elif isinstance(x, tuple):
            key, value = x
            self.db.update({key: value})
        else:
            key = moment.now().epoch()
            # moment.unix(now.epoch())
            value = x
            self.db.update({key: value})

        self._check_size_limit()

    def __len__(self,):
        return self.db.__len__()

    def __getitem__(self, x):
        return self.db.__getitem__(x)

    def __setitem__(self, key, value):
        self.db.__setitem__(key, value)
        self._check_size_limit()
        return self

    def __delitem__(self, x):
        return self.db.__delitem__(x)

    def __contains__(self, x):
        return self.db.__contains__(x)

    def __iter__(self,):
        return self.db.__iter__()


class ODBNamespace(dict):
    def create_table(self, tablename='default', **kwargs):
        try:
            return self[tablename]
        except KeyError:
            return self.setdefault(
                tablename,
                ODBStream(tablename=tablename, **kwargs)
            )


odbnamespace = ODBNamespace()


def NB(*args, **kwargs):
    """创建命名的数据库
    NB(tablename,fname)
    tablename:流名，底层是表名
    fname，存储文件路径名字
    """
    return odbnamespace.create_table(*args, **kwargs)


@Stream.register_api()
class unique(Stream):
    """ Avoid sending through repeated elements

    This deduplicates a stream so that only new elements pass through.
    You can control how much of a history is stored with the ``history=``
    parameter.  For example setting ``history=1`` avoids sending through
    elements when one is repeated right after the other.

    Parameters
    ----------
    history : int or None, optional
        number of stored unique values to check against
    key : function, optional
        Function which returns a representation of the incoming data.
        For example ``key=lambda x: x['a']`` could be used to allow only
        pieces of data with unique ``'a'`` values to pass through.
    hashable : bool, optional
        If True then data is assumed to be hashable, else it is not. This is
        used for determining how to cache the history, if hashable then
        either dicts or LRU caches are used, otherwise a deque is used.
        Defaults to True.

    Examples
    --------
    >>> source = Stream()
    >>> source.unique(history=1).sink(print)
    >>> for x in [1, 1, 2, 2, 2, 1, 3]:
    ...     source.emit(x)

    持久化的去重复，一般用在报警发送
    to_send = Stream()
    dds = to_send.unique(persist=True,size_limit=1024*1024*2)
    dds>>log
    232>>to_send
    232>>to_send

    1
    2
    1
    3
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
            self.seen = NB(tablename=persistname,
                           fname='_unique_persist',
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
    """ Combine multiple streams into one

    Every element from any of the upstreams streams will immediately flow
    into the output stream.  They will not be combined with elements from
    other streams.

    See also
    --------
    Stream.zip
    Stream.combine_latest
    """

    def __init__(self, *upstreams, **kwargs):
        super(union, self).__init__(upstreams=upstreams, **kwargs)

    def update(self, x, who=None):
        return self._emit(x)


@Stream.register_api()
class pluck(Stream):
    """ Select elements from elements in the stream.

    Parameters
    ----------
    pluck : object, list
        The element(s) to pick from the incoming element in the stream
        If an instance of list, will pick multiple elements.

    Examples
    --------
    >>> source = Stream()
    >>> source.pluck([0, 3]).sink(print)
    >>> for x in [[1, 2, 3, 4], [4, 5, 6, 7], [8, 9, 10, 11]]:
    ...     source.emit(x)
    (1, 4)
    (4, 7)
    (8, 11)

    >>> source = Stream()
    >>> source.pluck('name').sink(print)
    >>> for x in [{'name': 'Alice', 'x': 123}, {'name': 'Bob', 'x': 456}]:
    ...     source.emit(x)
    'Alice'
    'Bob'
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
    """
    Hold elements in a cache and emit them as a collection when flushed.

    Examples
    --------
    >>> source1 = Stream()
    >>> source2 = Stream()
    >>> collector = collect(source1)
    >>> collector.sink(print)
    >>> source2.sink(collector.flush)
    >>> source1.emit(1)
    >>> source1.emit(2)
    >>> source2.emit('anything')  # flushes collector
    ...
    [1, 2]
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
    """Combine multiple streams together to a stream of tuples

    The stream which this is called from is lossless. All elements from
    the lossless stream are emitted reguardless of when they came in.
    This will emit a new tuple consisting of an element from the lossless
    stream paired with the latest elements from the other streams.
    Elements are only emitted when an element on the lossless stream are
    received, similar to ``combine_latest`` with the ``emit_on`` flag.

    See Also
    --------
    Stream.combine_latest
    Stream.zip
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
    """ Drop held-up data and emit the latest result

    This allows you to skip intermediate elements in the stream if there is
    some back pressure causing a slowdown.  Use this when you only care about
    the latest elements, and are willing to lose older data.

    This passes through values without modification otherwise.

    Examples
    --------
    >>> source.map(f).latest().map(g)  # doctest: +SKIP
    """
    _graphviz_shape = 'octagon'

    def __init__(self, upstream, **kwargs):
        self.condition = Condition()
        self.next = []

        Stream.__init__(self, upstream, ensure_io_loop=True, **kwargs)

        self.loop.add_callback(self.cb)

    def update(self, x, who=None):
        self.next = [x]
        self.loop.add_callback(self.condition.notify)

    @gen.coroutine
    def cb(self):
        while True:
            yield self.condition.wait()
            [x] = self.next
            yield self._emit(x)


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


def sync(loop, func, *args, **kwargs):
    """
    Run coroutine in loop running in separate thread.
    """
    # This was taken from distrbuted/utils.py

    # Tornado's PollIOLoop doesn't raise when using closed, do it ourselves
    if PollIOLoop\
        and ((isinstance(loop, PollIOLoop)
              and getattr(loop, '_closing', False))
             or (hasattr(loop, 'asyncio_loop')
                 and loop.asyncio_loop._closed)):
        raise RuntimeError("IOLoop is closed")

    timeout = kwargs.pop('callback_timeout', None)

    e = threading.Event()
    main_tid = get_thread_identity()
    result = [None]
    error = [False]

    @gen.coroutine
    def f():
        try:
            if main_tid == get_thread_identity():
                raise RuntimeError("sync() called from thread of running loop")
            yield gen.moment
            thread_state.asynchronous = True
            future = func(*args, **kwargs)
            if timeout is not None:
                future = gen.with_timeout(timedelta(seconds=timeout), future)
            result[0] = yield future
        except Exception:
            error[0] = sys.exc_info()
        finally:
            thread_state.asynchronous = False
            e.set()

    loop.add_callback(f)
    if timeout is not None:
        if not e.wait(timeout):
            raise gen.TimeoutError("timed out after %s s." % (timeout,))
    else:
        while not e.is_set():
            e.wait(10)
    if error[0]:
        six.reraise(*error[0])
    else:
        return result[0]
