from .core import Stream, get_io_loop
from .bus import log
from .pipe import P
from tornado import gen
"""Future相关工具

提供处理Future对象的工具函数和流操作，主要用于异步任务的结果处理。

主要功能
--------
- 处理Tornado和asyncio的Future对象
- 将Future的结果作为流数据发射
- 支持并发执行多个Future任务

参数
----
upstream : Stream, 可选
    上游流对象，用于接收Future对象
**kwargs : dict
    其他参数传递给Stream基类

示例
----
>>> from tornado import gen
>>> @gen.coroutine 
... def foo():
...     yield gen.sleep(1)
...     return 42
...
>>> future = foo()
>>> # 使用run_future流处理Future
>>> s = Stream()
>>> s.run_future() >> print  # 创建run_future流
>>> future >> s  # 输出: 42

>>> # 处理多个Future
>>> s = Stream()
>>> s.rate_limit(1).run_future() >> log  # 限速处理
>>> for i in range(3):
...     foo() >> s  # 并发执行多个Future

注意事项
--------
- 上游流建议使用rate_limit进行限速，避免并发过高
- 支持Tornado和asyncio的Future对象
- Future的结果会作为流数据发射到下游
"""


@Stream.register_api()
class run_future(Stream):
    """获取上游进来的future的最终值并放入下游
    注意上游流要限速，这个是并发执行，速度很快

    examples::

        @gen.coroutine
        def foo():
            yield gen.sleep(3)
            return range<<10>>sample>>first

        async def foo2():
            import asyncio
            await asyncio.sleep(3)
            return range<<10>>sample>>first

        s = Stream()
        s.rate_limit(1).run_future()>>log

        for i in range(3):
            foo()>>s
            foo2()>>s

        [2020-02-26 18:14:37.991321] INFO: deva.log: 1
        [2020-02-26 18:14:37.993260] INFO: deva.log: 7
        [2020-02-26 18:14:37.995112] INFO: deva.log: 5

        run = run_future()
        run>>log

        foo()>>run
        foo2()>>run
    """

    def __init__(self, upstream=None, **kwargs):
        """初始化run_future流
        
        Args:
            upstream: 上游流
            **kwargs: 其他参数
        """
        Stream.__init__(self, upstream=upstream, ensure_io_loop=True)

    def emit(self, x, **kwargs):
        """发射数据到下游
        
        Args:
            x: 要发射的数据
            **kwargs: 其他参数
            
        Returns:
            发射的数据x
        """
        self.update(x)
        return x

    def update(self, x, who=None):
        """更新流中的数据
        
        Args:
            x: 要更新的数据,必须是Awaitable对象
            who: 更新者标识
        """
        assert isinstance(x, gen.Awaitable)
        futs = gen.convert_yielded(x)
        self.loop.add_future(futs, lambda x: self._emit(x.result()))


# @P
# def attend(stream: Stream = log):
    """安排future执行，并将结果入流
        server=from_http_request()
        server>>log
        server.start()


        '你好'>>post_to() | attend(log)

[20:49:07] 你好                                                        bus.py:31
[20:49:08] HTTPResponse(_body=None,_error_is_response_code=False,buffe bus.py:31
           r=<_io.BytesIO object at 0x106930310>,code=200,effective_ur
           l='http://127.0.0.1:7777',error=None,headers=<tornado.httpu
           til.HTTPHeaders object at 0x108743af0>,reason='OK',request=
           <tornado.httpclient.HTTPRequest object at 0x11ae449a0>,requ
           est_time=0.04534506797790527,start_time=1606567747.946251,t
           ime_info={})

    """
    # def _attend(x):
    #     assert isinstance(x, gen.Awaitable)
    #     futs = gen.convert_yielded(x)
    #     get_io_loop().add_future(futs, lambda x: stream._emit(x.result()))

    # if isinstance(stream, Stream):
    #     return _attend @ P
    # else:
    #     futs, stream = stream, log
    #     return _attend(futs)
