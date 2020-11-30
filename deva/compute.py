from .core import Stream, identity
from .store import DBStream
from collections import deque
from collections.abc import Iterable
from tornado import gen
from time import time
from tornado.locks import Condition
from tornado.queues import Queue
import logging

no_default = '--no-default--'
logger = logging.getLogger(__name__)


def convert_interval(interval):
    if isinstance(interval, str):
        import pandas as pd
        interval = pd.Timedelta(interval).total_seconds()
    return interval


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
