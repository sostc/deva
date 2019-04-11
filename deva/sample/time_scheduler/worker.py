from deva import *

@bus.route(lambda x:x=='open')
def onopen(x):
    'open'>>log
    
@bus.route(lambda x:x=='close')
def onclose(x):
    'close'>>log

from tornado import ioloop
ioloop.IOLoop.current().start()