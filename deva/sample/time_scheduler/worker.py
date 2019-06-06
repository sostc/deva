from tornado import ioloop
from deva import bus, log


@bus.route(lambda x: x == 'open')
def onopen(x):
    'open' >> log


@bus.route(lambda x: x == 'close')
def onclose(x):
    'close' >> log


ioloop.IOLoop.current().start()
