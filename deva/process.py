

from .stream import Stream
from tornado.ioloop import IOLoop

bus = Stream().from_share('bus')
bus.emit = Stream().to_share('bus').emit


bus.__doc__ = """
    跨进程的消息流任务驱动
pbus = PBus()

@pbus.route(lambda x:type(x)==str)
def foo(x):
    x*2>>log


'aa'>>pbus
如果是单独进程中使用,需要固定一个循环来hold主线程,流将在线程中执行
while 1:
    import time
    time.sleep(60*60*24)

"""
