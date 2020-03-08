from __future__ import absolute_import, division, print_function

from operator import getitem

from tornado import gen

from dask.compatibility import apply
from distributed.client import default_client

from .core import Stream
from . import core, sources
from . import compute


class DaskStream(Stream):
    """ A Parallel stream using Dask

    This object is fully compliant with the ``deva.core.Stream`` object but
    uses a Dask client for execution.  Operations like ``map`` and
    ``accumulate`` submit functions to run on the Dask instance using
    ``dask.distributed.Client.submit`` and pass around Dask futures.
    Time-based operations like ``timed_window``, buffer, and so on operate as
    normal.

    Typically one transfers between normal Stream and DaskStream objects using
    the ``Stream.scatter()`` and ``DaskStream.gather()`` methods.

    Examples
    --------
    >>> from dask.distributed import Client
    >>> client = Client()

    >>> from streamz import Stream
    >>> source = Stream()
    >>> source.scatter().map(func).accumulate(binop).gather().sink(...)

    See Also
    --------
    dask.distributed.Client
    """

    def __init__(self, *args, **kwargs):
        if 'loop' not in kwargs:
            kwargs['loop'] = default_client().loop
        super(DaskStream, self).__init__(*args, **kwargs)


@DaskStream.register_api()
class map(DaskStream):
    def __init__(self, upstream, func, *args, **kwargs):
        self.func = func
        self.kwargs = kwargs
        self.args = args

        DaskStream.__init__(self, upstream)

    def update(self, x, who=None):
        client = default_client()
        result = client.submit(self.func, x, *self.args, **self.kwargs)
        return self._emit(result)


@DaskStream.register_api()
class accumulate(DaskStream):
    def __init__(self, upstream, func, start=compute.no_default,
                 returns_state=False, **kwargs):
        self.func = func
        self.state = start
        self.returns_state = returns_state
        self.kwargs = kwargs
        DaskStream.__init__(self, upstream)

    def update(self, x, who=None):
        if self.state is compute.no_default:
            self.state = x
            return self._emit(self.state)
        else:
            client = default_client()
            result = client.submit(self.func, self.state, x, **self.kwargs)
            if self.returns_state:
                state = client.submit(getitem, result, 0)
                result = client.submit(getitem, result, 1)
            else:
                state = result
            self.state = state
            return self._emit(result)


@core.Stream.register_api()
@DaskStream.register_api()
class scatter(DaskStream):
    """ Convert local stream to Dask Stream

    All elements flowing through the input will be scattered out to the cluster
    """
    @gen.coroutine
    def update(self, x, who=None):
        client = default_client()
        future = yield client.scatter(x, asynchronous=True)
        f = yield self._emit(future)
        raise gen.Return(f)


@DaskStream.register_api()
class gather(core.Stream):
    """ Wait on and gather results from DaskStream to local Stream

    This waits on every result in the stream and then gathers that result back
    to the local stream.  Warning, this can restrict parallelism.  It is common
    to combine a ``gather()`` node with a ``buffer()`` to allow unfinished
    futures to pile up.

    Examples
    --------
    >>> local_stream = dask_stream.buffer(20).gather()

    See Also
    --------
    buffer
    scatter
    """
    @gen.coroutine
    def update(self, x, who=None):
        client = default_client()
        result = yield client.gather(x, asynchronous=True)
        result2 = yield self._emit(result)
        raise gen.Return(result2)


@DaskStream.register_api()
class starmap(DaskStream):
    def __init__(self, upstream, func, **kwargs):
        self.func = func
        name = kwargs.pop('name', None)
        self.kwargs = kwargs

        DaskStream.__init__(self, upstream, name=name)

    def update(self, x, who=None):
        client = default_client()
        result = client.submit(apply, self.func, x, self.kwargs)
        return self._emit(result)


@DaskStream.register_api()
class buffer(DaskStream, compute.buffer):
    pass


@DaskStream.register_api()
class combine_latest(DaskStream, compute.combine_latest):
    pass


@DaskStream.register_api()
class delay(DaskStream, compute.delay):
    pass


@DaskStream.register_api()
class latest(DaskStream, compute.latest):
    pass


@DaskStream.register_api()
class partition(DaskStream, compute.partition):
    pass


@DaskStream.register_api()
class rate_limit(DaskStream, compute.rate_limit):
    pass


@DaskStream.register_api()
class sliding_window(DaskStream, compute.sliding_window):
    pass


@DaskStream.register_api()
class timed_window(DaskStream, compute.timed_window):
    pass


@DaskStream.register_api()
class union(DaskStream, compute.union):
    pass


@DaskStream.register_api()
class zip(DaskStream, compute.zip):
    pass


@DaskStream.register_api(staticmethod)
class filenames(DaskStream, sources.filenames):
    pass


@DaskStream.register_api(staticmethod)
class from_textfile(DaskStream, sources.from_textfile):
    pass
