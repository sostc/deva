
from .stream import Stream, NS, namespace
from .log import warn


"""
    跨进程的消息流任务驱动


@bus.route(lambda x:type(x)==str)
def foo(x):
    x*2>>log


'aa'>>pbus
如果是单独进程中使用,需要固定一个循环来hold主线程
from tornado import ioloop
ioloop.IOLoop.current().start()

"""


def create_cps(stream_name, **kwargs):
    """创建一个跨进程的stream"""
    if stream_name in namespace:
        return namespace[stream_name]
    else:
        namespace[stream_name] = Stream.from_share(stream_name, **kwargs)
        namespace[stream_name].emit = Stream().to_share(stream_name).emit
        return namespace[stream_name]


try:
    bus = create_cps('bus')
except Exception as e:
    bus = NS('bus')
    f'{e}, start a local bus ' >> warn
