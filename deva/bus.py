
from .stream import NT

"""
    跨进程的消息流任务驱动


@bus.route(lambda x:type(x)==str)
def foo(x):
    x*2>>log


'aa'>pbus
如果是单独进程中使用,需要固定一个循环来hold主线程
from tornado import ioloop
ioloop.IOLoop.current().start()

"""


bus = NT('bus')
