from datetime import timedelta
from functools import partial
import itertools
import json
import operator
from operator import add
import os
from time import time, sleep
import sys

import pytest

from tornado import gen
from tornado.queues import Queue
from tornado.ioloop import IOLoop

import streamz as sz

from streamz import Stream
from streamz.sources import sink_to_file, PeriodicCallback
from streamz.utils_test import (inc, double, gen_test, tmpfile, captured_logger,   # noqa: F401
        clean, await_for)  # noqa: F401
from distributed.utils_test import loop   # noqa: F401


def test_basic():
    source = Stream()
    b1 = source.map(inc)
    b2 = source.map(double)

    c = b1.scan(add)

    Lc = c.sink_to_list()
    Lb = b2.sink_to_list()

    for i in range(4):
        source.emit(i)

    assert Lc == [1, 3, 6, 10]
    assert Lb == [0, 2, 4, 6]


def test_no_output():
    source = Stream()
    assert source.emit(1) is None


def test_scan():
    source = Stream()

    def f(acc, i):
        acc = acc + i
        return acc, acc

    L = source.scan(f, returns_state=True).sink_to_list()
    for i in range(3):
        source.emit(i)

    assert L == [0, 1, 3]


def test_kwargs():
    source = Stream()

    def f(acc, x, y=None):
        acc = acc + x + y
        return acc

    L = source.scan(f, y=10).sink_to_list()
    for i in range(3):
        source.emit(i)

    assert L == [0, 11, 23]


def test_filter():
    source = Stream()
    L = source.filter(lambda x: x % 2 == 0).sink_to_list()

    for i in range(10):
        source.emit(i)

    assert L == [0, 2, 4, 6, 8]


def test_filter_none():
    source = Stream()
    L = source.filter(None).sink_to_list()

    for i in range(10):
        source.emit(i % 3)

    assert L == [1, 2, 1, 2, 1, 2]


def test_map():
    def add(x=0, y=0):
        return x + y

    source = Stream()
    L = source.map(add, y=10).sink_to_list()

    source.emit(1)

    assert L[0] == 11


def test_map_args():
    source = Stream()
    L = source.map(operator.add, 10).sink_to_list()
    source.emit(1)
    assert L == [11]


def test_starmap():
    def add(x=0, y=0):
        return x + y

    source = Stream()
    L = source.starmap(add).sink_to_list()

    source.emit((1, 10))

    assert L[0] == 11


def test_remove():
    source = Stream()
    L = source.remove(lambda x: x % 2 == 0).sink_to_list()

    for i in range(10):
        source.emit(i)

    assert L == [1, 3, 5, 7, 9]


def test_partition():
    source = Stream()
    L = source.partition(2).sink_to_list()

    for i in range(10):
        source.emit(i)

    assert L == [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9)]


def test_sliding_window():
    source = Stream()
    L = source.sliding_window(2).sink_to_list()

    for i in range(10):
        source.emit(i)

    assert L == [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5),
                 (5, 6), (6, 7), (7, 8), (8, 9)]


@gen_test()
def test_backpressure():
    q = Queue(maxsize=2)

    source = Stream(asynchronous=True)
    source.map(inc).scan(add, start=0).sink(q.put)

    @gen.coroutine
    def read_from_q():
        while True:
            yield q.get()
            yield gen.sleep(0.1)

    IOLoop.current().add_callback(read_from_q)

    start = time()
    for i in range(5):
        yield source.emit(i)
    end = time()

    assert end - start >= 0.2


@gen_test()
def test_timed_window():
    source = Stream(asynchronous=True)
    a = source.timed_window(0.01)

    assert a.loop is IOLoop.current()
    L = a.sink_to_list()

    for i in range(10):
        yield source.emit(i)
        yield gen.sleep(0.004)

    yield gen.sleep(a.interval)
    assert L
    assert sum(L, []) == list(range(10))
    assert all(len(x) <= 3 for x in L)
    assert any(len(x) >= 2 for x in L)

    yield gen.sleep(0.1)
    assert not L[-1]


def test_timed_window_timedelta(clean):  # noqa: F811
    pytest.importorskip('pandas')
    source = Stream(asynchronous=True)
    a = source.timed_window('10ms')
    assert a.interval == 0.010


@gen_test()
def test_timed_window_backpressure():
    q = Queue(maxsize=1)

    source = Stream(asynchronous=True)
    source.timed_window(0.01).sink(q.put)

    @gen.coroutine
    def read_from_q():
        while True:
            yield q.get()
            yield gen.sleep(0.1)

    IOLoop.current().add_callback(read_from_q)

    start = time()
    for i in range(5):
        yield source.emit(i)
        yield gen.sleep(0.01)
    stop = time()

    assert stop - start > 0.2


def test_sink_to_file():
    with tmpfile() as fn:
        source = Stream()
        with sink_to_file(fn, source) as f:
            source.emit('a')
            source.emit('b')

        with open(fn) as f:
            data = f.read()

        assert data == 'a\nb\n'


def test_sink_with_args_and_kwargs():
    L = dict()

    def mycustomsink(elem, key, prefix=""):
        key = prefix + key
        if key not in L:
            L[key] = list()
        L[key].append(elem)

    s = Stream()
    s.sink(mycustomsink, "cat", "super")

    s.emit(1)
    s.emit(2)
    assert L['supercat'] == [1, 2]


@gen_test()
def test_counter():
    counter = itertools.count()
    source = PeriodicCallback(lambda: next(counter), 0.001, asynchronous=True)
    L = source.sink_to_list()
    yield gen.sleep(0.05)

    assert L


@gen_test()
def test_rate_limit():
    source = Stream(asynchronous=True)
    L = source.rate_limit(0.05).sink_to_list()

    start = time()
    for i in range(5):
        yield source.emit(i)
    stop = time()
    assert stop - start > 0.2
    assert len(L) == 5


@gen_test()
def test_delay():
    source = Stream(asynchronous=True)
    L = source.delay(0.02).sink_to_list()

    for i in range(5):
        yield source.emit(i)

    assert not L

    yield gen.sleep(0.04)

    assert len(L) < 5

    yield gen.sleep(0.1)

    assert len(L) == 5


@gen_test()
def test_buffer():
    source = Stream(asynchronous=True)
    L = source.map(inc).buffer(10).map(inc).rate_limit(0.05).sink_to_list()

    start = time()
    for i in range(10):
        yield source.emit(i)
    stop = time()

    assert stop - start < 0.01
    assert not L

    start = time()
    for i in range(5):
        yield source.emit(i)
    stop = time()

    assert L
    assert stop - start > 0.04


def test_zip():
    a = Stream()
    b = Stream()
    c = sz.zip(a, b)

    L = c.sink_to_list()

    a.emit(1)
    b.emit('a')
    a.emit(2)
    b.emit('b')

    assert L == [(1, 'a'), (2, 'b')]
    d = Stream()
    # test zip from the object itself
    # zip 3 streams together
    e = a.zip(b, d)
    L2 = e.sink_to_list()

    a.emit(1)
    b.emit(2)
    d.emit(3)
    assert L2 == [(1, 2, 3)]


def test_zip_literals():
    a = Stream()
    b = Stream()
    c = sz.zip(a, 123, b)

    L = c.sink_to_list()
    a.emit(1)
    b.emit(2)

    assert L == [(1, 123, 2)]

    a.emit(4)
    b.emit(5)

    assert L == [(1, 123, 2),
                 (4, 123, 5)]


def test_zip_same():
    a = Stream()
    b = a.zip(a)
    L = b.sink_to_list()

    a.emit(1)
    a.emit(2)
    assert L == [(1, 1), (2, 2)]


def test_combine_latest():
    a = Stream()
    b = Stream()
    c = a.combine_latest(b)
    d = a.combine_latest(b, emit_on=[a, b])

    L = c.sink_to_list()
    L2 = d.sink_to_list()

    a.emit(1)
    a.emit(2)
    b.emit('a')
    a.emit(3)
    b.emit('b')

    assert L == [(2, 'a'), (3, 'a'), (3, 'b')]
    assert L2 == [(2, 'a'), (3, 'a'), (3, 'b')]


def test_combine_latest_emit_on():
    a = Stream()
    b = Stream()
    c = a.combine_latest(b, emit_on=a)

    L = c.sink_to_list()

    a.emit(1)
    b.emit('a')
    a.emit(2)
    a.emit(3)
    b.emit('b')
    a.emit(4)

    assert L == [(2, 'a'), (3, 'a'), (4, 'b')]


def test_combine_latest_emit_on_stream():
    a = Stream()
    b = Stream()
    c = a.combine_latest(b, emit_on=0)

    L = c.sink_to_list()

    a.emit(1)
    b.emit('a')
    a.emit(2)
    a.emit(3)
    b.emit('b')
    a.emit(4)

    assert L == [(2, 'a'), (3, 'a'), (4, 'b')]


@gen_test()
def test_zip_timeout():
    a = Stream(asynchronous=True)
    b = Stream(asynchronous=True)
    c = sz.zip(a, b, maxsize=2)

    L = c.sink_to_list()

    a.emit(1)
    a.emit(2)

    future = a.emit(3)
    with pytest.raises(gen.TimeoutError):
        yield gen.with_timeout(timedelta(seconds=0.01), future)

    b.emit('a')
    yield future

    assert L == [(1, 'a')]


def test_frequencies():
    source = Stream()
    L = source.frequencies().sink_to_list()

    source.emit('a')
    source.emit('b')
    source.emit('a')

    assert L[-1] == {'a': 2, 'b': 1}


def test_flatten():
    source = Stream()
    L = source.flatten().sink_to_list()

    source.emit([1, 2, 3])
    source.emit([4, 5])
    source.emit([6, 7, 8])

    assert L == [1, 2, 3, 4, 5, 6, 7, 8]


def test_unique():
    source = Stream()
    L = source.unique().sink_to_list()

    source.emit(1)
    source.emit(2)
    source.emit(1)

    assert L == [1, 2]


def test_unique_key():
    source = Stream()
    L = source.unique(key=lambda x: x % 2, history=1).sink_to_list()

    source.emit(1)
    source.emit(2)
    source.emit(4)
    source.emit(6)
    source.emit(3)

    assert L == [1, 2, 3]


def test_unique_history():
    source = Stream()
    s = source.unique(history=2)
    L = s.sink_to_list()

    source.emit(1)
    source.emit(2)
    source.emit(1)
    source.emit(2)
    source.emit(1)
    source.emit(2)

    assert L == [1, 2]

    source.emit(3)
    source.emit(2)

    assert L == [1, 2, 3]

    source.emit(1)

    assert L == [1, 2, 3, 1]


def test_union():
    a = Stream()
    b = Stream()
    c = Stream()

    L = a.union(b, c).sink_to_list()

    a.emit(1)
    assert L == [1]
    b.emit(2)
    assert L == [1, 2]
    a.emit(3)
    assert L == [1, 2, 3]
    c.emit(4)
    assert L == [1, 2, 3, 4]


def test_pluck():
    a = Stream()
    L = a.pluck(1).sink_to_list()
    a.emit([1, 2, 3])
    assert L == [2]
    a.emit([4, 5, 6, 7, 8, 9])
    assert L == [2, 5]
    with pytest.raises(IndexError):
        a.emit([1])


def test_pluck_list():
    a = Stream()
    L = a.pluck([0, 2]).sink_to_list()

    a.emit([1, 2, 3])
    assert L == [(1, 3)]
    a.emit([4, 5, 6, 7, 8, 9])
    assert L == [(1, 3), (4, 6)]
    with pytest.raises(IndexError):
        a.emit([1])


def test_collect():
    source1 = Stream()
    source2 = Stream()
    collector = source1.collect()
    L = collector.sink_to_list()
    source2.sink(collector.flush)

    source1.emit(1)
    source1.emit(2)
    assert L == []

    source2.emit('anything')  # flushes collector
    assert L == [(1, 2)]

    source2.emit('anything')
    assert L == [(1, 2), ()]

    source1.emit(3)
    assert L == [(1, 2), ()]

    source2.emit('anything')
    assert L == [(1, 2), (), (3,)]


def test_map_str():
    def add(x=0, y=0):
        return x + y

    source = Stream()
    s = source.map(add, y=10)
    assert str(s) == '<map: add>'


def test_filter_str():
    def iseven(x):
        return x % 2 == 0

    source = Stream()
    s = source.filter(iseven)
    assert str(s) == '<filter: iseven>'


def test_timed_window_str(clean):  # noqa: F811
    source = Stream()
    s = source.timed_window(.05)
    assert str(s) == '<timed_window: 0.05>'


def test_partition_str():
    source = Stream()
    s = source.partition(2)
    assert str(s) == '<partition: 2>'


def test_stream_name_str():
    source = Stream(stream_name='this is not a stream')
    assert str(source) == '<this is not a stream; Stream>'


def test_zip_latest():
    a = Stream()
    b = Stream()
    c = a.zip_latest(b)
    d = a.combine_latest(b, emit_on=a)

    L = c.sink_to_list()
    L2 = d.sink_to_list()

    a.emit(1)
    a.emit(2)
    b.emit('a')
    b.emit('b')
    a.emit(3)

    assert L == [(1, 'a'), (2, 'a'), (3, 'b')]
    assert L2 == [(3, 'b')]


def test_zip_latest_reverse():
    a = Stream()
    b = Stream()
    c = a.zip_latest(b)

    L = c.sink_to_list()

    b.emit('a')
    a.emit(1)
    a.emit(2)
    a.emit(3)
    b.emit('b')
    a.emit(4)

    assert L == [(1, 'a'), (2, 'a'), (3, 'a'), (4, 'b')]


def test_triple_zip_latest():
    from streamz.core import Stream
    s1 = Stream()
    s2 = Stream()
    s3 = Stream()
    s_simple = s1.zip_latest(s2, s3)
    L_simple = s_simple.sink_to_list()

    s1.emit(1)
    s2.emit('I')
    s2.emit("II")
    s1.emit(2)
    s2.emit("III")
    s3.emit('a')
    s3.emit('b')
    s1.emit(3)
    assert L_simple == [(1, 'III', 'a'), (2, 'III', 'a'), (3, 'III', 'b')]


def test_connect():
    source_downstream = Stream()
    # connect assumes this default behaviour
    # of stream initialization
    assert not source_downstream.downstreams
    assert source_downstream.upstreams == [None]

    # initialize the second stream to connect to
    source_upstream = Stream()

    sout = source_downstream.map(lambda x : x + 1)
    L = list()
    sout = sout.map(L.append)
    source_upstream.connect(source_downstream)

    source_upstream.emit(2)
    source_upstream.emit(4)

    assert L == [3, 5]


def test_multi_connect():
    source0 = Stream()
    source1 = Stream()
    source_downstream = source0.union(source1)
    # connect assumes this default behaviour
    # of stream initialization
    assert not source_downstream.downstreams

    # initialize the second stream to connect to
    source_upstream = Stream()

    sout = source_downstream.map(lambda x : x + 1)
    L = list()
    sout = sout.map(L.append)
    source_upstream.connect(source_downstream)

    source_upstream.emit(2)
    source_upstream.emit(4)

    assert L == [3, 5]


def test_disconnect():
    source = Stream()

    upstream = Stream()
    L = upstream.sink_to_list()

    source.emit(1)
    assert L == []
    source.connect(upstream)
    source.emit(2)
    source.emit(3)
    assert L == [2, 3]
    source.disconnect(upstream)
    source.emit(4)
    assert L == [2, 3]


def test_gc():
    source = Stream()

    L = []
    a = source.map(L.append)

    source.emit(1)
    assert L == [1]

    del a
    import gc; gc.collect()
    start = time()
    while source.downstreams:
        sleep(0.01)
        assert time() < start + 1

    source.emit(2)
    assert L == [1]


@gen_test()
def test_from_file():
    with tmpfile() as fn:
        with open(fn, 'wt') as f:
            f.write('{"x": 1, "y": 2}\n')
            f.write('{"x": 2, "y": 2}\n')
            f.write('{"x": 3, "y": 2}\n')
            f.flush()

            source = Stream.from_textfile(fn, poll_interval=0.010,
                                          asynchronous=True, start=False)
            L = source.map(json.loads).pluck('x').sink_to_list()

            assert L == []

            source.start()

            yield await_for(lambda: len(L) == 3, timeout=5)

            assert L == [1, 2, 3]

            f.write('{"x": 4, "y": 2}\n')
            f.write('{"x": 5, "y": 2}\n')
            f.flush()

            start = time()
            while L != [1, 2, 3, 4, 5]:
                yield gen.sleep(0.01)
                assert time() < start + 2  # reads within 2s


@gen_test()
def test_filenames():
    with tmpfile() as fn:
        os.mkdir(fn)
        with open(os.path.join(fn, 'a'), 'w'):
            pass
        with open(os.path.join(fn, 'b'), 'w'):
            pass

        source = Stream.filenames(fn, asynchronous=True)
        L = source.sink_to_list()
        source.start()

        while len(L) < 2:
            yield gen.sleep(0.01)

        assert L == [os.path.join(fn, x) for x in ['a', 'b']]

        with open(os.path.join(fn, 'c'), 'w'):
            pass

        while len(L) < 3:
            yield gen.sleep(0.01)

        assert L == [os.path.join(fn, x) for x in ['a', 'b', 'c']]


def test_docstrings():
    for s in [Stream, Stream()]:
        assert 'every element' in s.map.__doc__
        assert s.map.__name__ == 'map'
        assert 'predicate' in s.filter.__doc__
        assert s.filter.__name__ == 'filter'


def test_subclass():
    class NewStream(Stream):
        pass

    @NewStream.register_api()
    class foo(NewStream):
        pass

    assert hasattr(NewStream, 'map')
    assert hasattr(NewStream(), 'map')
    assert hasattr(NewStream, 'foo')
    assert hasattr(NewStream(), 'foo')
    assert not hasattr(Stream, 'foo')
    assert not hasattr(Stream(), 'foo')


@gen_test()
def test_latest():
    source = Stream(asynchronous=True)

    L = []

    @gen.coroutine
    def slow_write(x):
        yield gen.sleep(0.050)
        L.append(x)

    s = source.map(inc).latest().map(slow_write)  # noqa: F841

    source.emit(1)
    yield gen.sleep(0.010)
    source.emit(2)
    source.emit(3)

    start = time()
    while len(L) < 2:
        yield gen.sleep(0.01)
        assert time() < start + 3
    assert L == [2, 4]

    yield gen.sleep(0.060)
    assert L == [2, 4]


def test_destroy():
    source = Stream()
    s = source.map(inc)
    L = s.sink_to_list()

    source.emit(1)
    assert L == [2]

    s.destroy()

    assert not list(source.downstreams)
    assert not s.upstreams
    source.emit(2)
    assert L == [2]


def dont_test_stream_kwargs(clean):  # noqa: F811
    ''' Test the good and bad kwargs for the stream
        Currently just stream_name
    '''
    test_name = "some test name"

    sin = Stream(stream_name=test_name)
    sin2 = Stream()

    assert sin.name == test_name
    # when not defined, should be None
    assert sin2.name is None

    # add new core methods here, initialized
    # these should be functions, use partial to partially initialize them
    # (if they require more arguments)
    streams = [
               # some filter kwargs, so we comment them out
               partial(sin.map, lambda x : x),
               partial(sin.accumulate, lambda x1, x2 : x1),
               partial(sin.filter, lambda x : True),
               partial(sin.partition, 2),
               partial(sin.sliding_window, 2),
               partial(sin.timed_window, .01),
               partial(sin.rate_limit, .01),
               partial(sin.delay, .02),
               partial(sin.buffer, 2),
               partial(sin.zip, sin2),
               partial(sin.combine_latest, sin2),
               sin.frequencies,
               sin.flatten,
               sin.unique,
               sin.union,
               partial(sin.pluck, 0),
               sin.collect,
              ]

    good_kwargs = dict(stream_name=test_name)
    bad_kwargs = dict(foo="bar")
    for s in streams:
        # try good kwargs
        sout = s(**good_kwargs)
        assert sout.name == test_name
        del sout

        with pytest.raises(TypeError):
            sout = s(**bad_kwargs)
            sin.emit(1)
            # need a second emit for accumulate
            sin.emit(1)
            del sout

    # verify that sout is properly deleted each time by emitting once into sin
    # and not getting TypeError
    # garbage collect and then try
    import gc
    gc.collect()
    sin.emit(1)


@pytest.fixture
def thread(loop):  # noqa: F811
    from threading import Thread, Event
    thread = Thread(target=loop.start)
    thread.daemon = True
    thread.start()

    event = Event()
    loop.add_callback(event.set)
    event.wait()

    return thread


def test_percolate_loop_information(clean):  # noqa: F811
    source = Stream()
    assert not source.loop
    s = source.timed_window(0.5)
    assert source.loop is s.loop


def test_separate_thread_without_time(loop, thread):  # noqa: F811
    assert thread.is_alive()
    source = Stream(loop=loop)
    L = source.map(inc).sink_to_list()

    for i in range(10):
        source.emit(i)
        assert L[-1] == i + 1


def test_separate_thread_with_time(clean):  # noqa: F811
    L = []

    @gen.coroutine
    def slow_write(x):
        yield gen.sleep(0.1)
        L.append(x)

    source = Stream(asynchronous=False)
    source.map(inc).sink(slow_write)

    start = time()
    source.emit(1)
    stop = time()

    assert stop - start > 0.1
    assert L == [2]


def test_execution_order():
    L = []
    for i in range(5):
        s = Stream()
        b = s.pluck(1)
        a = s.pluck(0)
        li = a.combine_latest(b, emit_on=a).sink_to_list()
        z = [(1, 'red'), (2, 'blue'), (3, 'green')]
        for zz in z:
            s.emit(zz)
        L.append((li, ))
    for ll in L:
        assert ll == L[0]

    L2 = []
    for i in range(5):
        s = Stream()
        a = s.pluck(0)
        b = s.pluck(1)
        li = a.combine_latest(b, emit_on=a).sink_to_list()
        z = [(1, 'red'), (2, 'blue'), (3, 'green')]
        for zz in z:
            s.emit(zz)
        L2.append((li,))
    for ll, ll2 in zip(L, L2):
        assert ll2 == L2[0]
        assert ll != ll2


@gen_test()
def test_map_errors_log():
    a = Stream(asynchronous=True)
    b = a.delay(0.001).map(lambda x: 1 / x)  # noqa: F841
    with captured_logger('streamz') as logger:
        a._emit(0)
        yield gen.sleep(0.1)

        out = logger.getvalue()
        assert 'ZeroDivisionError' in out


def test_map_errors_raises():
    a = Stream()
    b = a.map(lambda x: 1 / x)  # noqa: F841
    with pytest.raises(ZeroDivisionError):
        a.emit(0)


@gen_test()
def test_accumulate_errors_log():
    a = Stream(asynchronous=True)
    b = a.delay(0.001).accumulate(lambda x, y: x / y)  # noqa: F841
    with captured_logger('streamz') as logger:
        a._emit(1)
        a._emit(0)
        yield gen.sleep(0.1)

        out = logger.getvalue()
        assert 'ZeroDivisionError' in out


def test_accumulate_errors_raises():
    a = Stream()
    b = a.accumulate(lambda x, y: x / y)  # noqa: F841
    with pytest.raises(ZeroDivisionError):
        a.emit(1)
        a.emit(0)


@gen_test()
def test_sync_in_event_loop():
    a = Stream()
    assert not a.asynchronous
    L = a.timed_window(0.01).sink_to_list()
    sleep(0.05)
    assert L
    assert a.loop
    assert a.loop is not IOLoop.current()


def test_share_common_ioloop(clean):  # noqa: F811
    a = Stream()
    b = Stream()
    aa = a.timed_window(0.01)
    bb = b.timed_window(0.01)
    assert aa.loop is bb.loop


def test_start():
    flag = []

    class MySource(Stream):
        def start(self):
            flag.append(True)

    s = MySource().map(inc)
    s.start()
    assert flag == [True]


if sys.version_info >= (3, 5):
    from streamz.tests.py3_test_core import *  # noqa
