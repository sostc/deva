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

    str_list = ['func', 'predicate', 'n', 'interval', 'port', 'host',
                'ttl', 'cache_max_len', '_scheduler', 'filename', 'path']

    def __init__(self, upstream=None, upstreams=None, name=None,
                 cache_max_len=None, cache_max_age_seconds=None,  # 缓存长度和事件长度
                 loop=None, asynchronous=None, ensure_io_loop=False,
                 refuse_none=True):  # 禁止传递None到下游
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

        self.name = name

        self.cache = {}
        self.is_cache = False
        if cache_max_len or cache_max_age_seconds:
            self.start_cache(cache_max_len, cache_max_age_seconds)

        self.refuse_none = refuse_none

        self.handlers = []

        self.__class__._instances.add(weakref.ref(self))

    def start_cache(self, cache_max_len=None, cache_max_age_seconds=None):
        self.is_cache = True
        self.cache_max_len = cache_max_len or 1
        self.cache_max_age_seconds = cache_max_age_seconds or 60 * 5
        self.cache = ExpiringDict(
            max_len=self.cache_max_len,
            max_age_seconds=self.cache_max_age_seconds
        )

    def stop_cache(self,):
        self.is_cache = False

    def clear_cache(self,):
        self.cache.clear()

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
    def instances(cls):
        dead = set()
        for ref in cls._instances:
            obj = ref()
            if obj is not None:
                yield obj
            else:
                dead.add(ref)
        cls._instances -= dead

    streams = instances

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

    def to_list(self):
        """ Append all elements of a stream to a list as they come in

        Examples
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

    def attend(self, x):
        """#async等将执行结果入流"""
        assert isinstance(x, gen.Awaitable)
        futs = gen.convert_yielded(x)
        if not self.loop:
            self.loop = get_io_loop()
        self.loop.add_future(futs, lambda x: self._emit(x.result()))

    def __ror__(self, x):  # |
        """emit value to stream ,end,return emit result"""
        if isinstance(x, gen.Awaitable):
            self.attend(x)
        else:
            self.emit(x)
        return x

    def __rrshift__(self, value):  # stream左边的>>
        """emit value to stream ,end,return emit result"""
        self.emit(value, asynchronous=True)
        return value

    def __lshift__(self, value):  # stream右边的<<
        """emit value to stream ,end,return emit result"""
        self.emit(value)
        return value

    def catch(self, func):
        """捕获函数执行结果到流内.

        examples::

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

        # @Pipe
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
        """捕获函数执行异常到流内.

        examples::

            @log.catch
            @warn.catch_except
            def f1(*args,**kwargs):
                return sum(*args,**kwargs)

        """
        @functools.wraps(func)
        def wraper(*args, **kwargs):
            # some action before
            try:
                return func(*args, **kwargs)  # 需要这里显式调用用户函数
            except Exception as e:
                {
                    'function': func.__name__,
                    'param': (args, kwargs),
                    'except': e,
                } >> self

        return wraper.__call__ @ P

    def __rmatmul__(self, func):
        """左边的 @.，函数结果进入流内."""
        return self.catch(func).__call__ @ P

    def __rxor__(self, func):
        """左边的 ~.，函数异常入流.优先级不高"""
        return self.catch_except(func).__call__ @ P

    def __rshift__(self, ref):  # stream右边的
        """Stream右边>>,sink到右边的对象.

        支持三种类型:list| text file| stream | callable
        """
        return match(ref,
                     list, lambda ref: self.sink(ref.append),
                     io.TextIOWrapper, lambda ref: self.to_textfile(ref),
                     str, lambda ref: self.map(str).to_textfile(ref),
                     Stream, lambda ref: self.sink(ref.emit),
                     # 内置函数被转换成pipe，不能pipe优先，需要stream的sink优先
                     # Pipe, lambda ref: ref(self),
                     callable, lambda ref: self.sink(ref),
                     ANY, lambda ref: TypeError(
                         f'{ref}:{type(ref)} is'
                         'Unsupported type, must be '
                         'list| str | text file| stream | callable')
                     )

    def route(self, occasion):
        """路由函数.

        :param occasion: 路由函数表达式,
        比如 lambda x:x.startswith('foo')
        或者 lambda x:type(x)==str

        examples::
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

    # @property
    def recent(self, n=5, seconds=None):
        if self.is_cache:
            if not seconds:
                return self.cache.values()[-n:]
            else:
                begin = datetime.now() - timedelta(seconds=seconds)
                return [i[1] for i in self.cache.items() if begin < i[0]]
        else:
            return {}

    def __iter__(self,):
        return self.cache.values().__iter__()


class Sink(Stream):

    _graphviz_shape = 'trapezium'

    def __init__(self, upstream, **kwargs):
        super().__init__(upstream, **kwargs)
        _global_sinks.add(self)


@Stream.register_api()
class sink(Sink):
    """ Apply a function on every element
    Parameters
    ----------
    func: callable
        A function that will be applied on every element.
    args:
        Positional arguments that will be passed to ``func`` after the incoming element.
    kwargs:
        Stream-specific arguments will be passed to ``Stream.__init__``, the rest of
        them will be passed to ``func``.
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
    Stream.to_list
    """

    def __init__(self, upstream, func, *args, **kwargs):
        self.func = func
        # take the stream specific kwargs out
        sig = set(inspect.signature(Stream).parameters)
        stream_kwargs = {k: v for (k, v) in kwargs.items() if k in sig}
        self.kwargs = {k: v for (k, v) in kwargs.items() if k not in sig}
        self.args = args
        super().__init__(upstream, **stream_kwargs)

    def update(self, x, who=None, metadata=None):
        result = self.func(x, *self.args, **self.kwargs)
        if gen.isawaitable(result):
            return result
        else:
            return []

    def destroy(self):
        super().destroy()
        _global_sinks.remove(self)


@Stream.register_api()
class to_textfile(Sink):
    """ Write elements to a plain text file, one element per line.
        Type of elements must be ``str``.
        Parameters
        ----------
        file: str or file-like
            File to write the elements to. ``str`` is treated as a file name to open.
            If file-like, descriptor must be open in text mode. Note that the file
            descriptor will be closed when this sink is destroyed.
        end: str, optional
            This value will be written to the file after each element.
            Defaults to newline character.
        mode: str, optional
            If file is ``str``, file will be opened in this mode. Defaults to ``"a"``
            (append mode).
        Examples
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

    def __init__(self, upstream, func=None, *args, **kwargs):
        self.func = func
        # this is one of a few stream specific kwargs
        name = kwargs.pop('name', None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, name=name)

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
    # if not isinstance(pd.DataFrame):
    #     return not not x
    # else:
    #     return x.empty


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
        name = kwargs.pop('name', None)
        self.kwargs = kwargs
        self.args = args

        Stream.__init__(self, upstream, name=name,)

    def update(self, x, who=None):
        if self.predicate(x, *self.args, **self.kwargs):
            return self._emit(x)


@gen.coroutine
def httpx(req, render=False, **kwargs):
    httpclient = AsyncHTMLSession(workers=1)
    try:
        if isinstance(req, str):
            response = yield httpclient.get(req)
        elif isinstance(req, dict):
            response = yield httpclient.get(**req)

        if render:
            yield response.html.arender(**kwargs)

        return response
    except Exception as e:
        (req, e) >> print
        logger.exception(e)


@Stream.register_api()
class http(Stream):
    """自动http 流中的url，返回response对象.

    接受url和requestsdict两种上游数据格式，注意上游流要限速，这个是并发执行，速度很快


    :param error:，流或者pipe函数，发生异常时url会被发送到这里
    :param workers:并发线程池数量


    example::

        s = Stream()
        get_data = lambda x:x.body.decode(
            'utf-8')>>chinese_extract>>sample(20)>>concat('|')
        s.rate_limit(0.1).http(workers=20,error=log).map(get_data).sink(print)

        url>>s

        {'url':'','headers'='','params':''}>>s


        h = http()
        h.map(lambda r:(r.url,r.html.search('<title>{}</title>')[0]))>>log
        'http://www.518.is'>>h

        [2020-03-17 03:46:30.902542] INFO: log: ('http://518.is/', 'NajaBlog')

    Returns::

        response, 常用方法,可用self.request方法获取回来做调试
        # 完整链接提取
        r.html.absolute_links

        # css selector
        about = r.html.find('#about', first=True) #css slectotr
        about.text
        about.attrs
        about.html
        about.find('a')
        about.absolute_links

        # 搜索模版
        r.html.search('Python is a {} language')[0]

        # xpath
        r.html.xpath('a')

        # 条件表达式
        r.html.find('a', containing='kenneth')

        # 常用属性
        response.url
        response.base_url
        response.text
        response.full_text



    """

    def __init__(self, upstream=None, render=False, workers=None, error=print, **kwargs):
        """http arender surport.

        [description]

        Args:
            **kwargs: render args retries: int = 8, script: str = None, wait: float = 0.2, scrolldown=False, sleep: int = 0, reload: bool = True, timeout: Union[float, int] = 8.0, keep_page: bool = False
            upstream: [description] (default: {None})
            render: [description] (default: {False})
            workers: [description] (default: {None})
            error: [description] (default: {print})
        """
        self.error = error
        self.render = render
        Stream.__init__(self, upstream=upstream, ensure_io_loop=True)
        self.httpclient = AsyncHTMLSession(workers=workers)
        self.kwargs = kwargs

    def update(self, req, who=None):
        self.loop.add_future(
            self._request(req),
            lambda x: self._emit(x.result())
        )

    def emit(self, req, **kwargs):
        self.update(req)
        return req

    @gen.coroutine
    def _request(self, req):
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
        return cls.request(url, **kwargs)

    x = httpx


def sync(loop, func, *args, **kwargs):
    """
    Run coroutine in loop running in separate thread.
    """
    # This was taken from distrbuted/utils.py

    # Tornado's PollIOLoop doesn't raise when using closed, do it ourselves
    if not loop:
        loop = get_io_loop()
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


class Deva():
    @classmethod
    def run(cls,):
        # loop = IOLoop()
        # loop.make_current()
        # loop.start()

        loop = get_io_loop(asynchronous=False)
        loop.instance().start()
        # import asyncio
        # l = asyncio.new_event_loop()

        # l.run_forever()


print(os.getpid())
