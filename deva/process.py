from .stream import *
from .pipe import *

class PBus(object):
    """
    跨进程的消息流任务驱动
pbus = PBus()

@pbus.route(lambda x:type(x)==str)
def foo(x):
    x*2>>log

'aa'>>pbus

    """
    def __init__(self,):
        self.write_bus = Stream().to_share('pbus')
        self.read_bus = Stream.from_share('pbus')
        self.handlers = []
#         self.read_bus.sink(lambda x:x>>log)
        
    def __rrshift__(self, value):  # stream左边的>>
        """emit value to stream ,end,return emit result"""
        return value>>self.write_bus
 
    def route(self, expr):
        """
        expr:路由函数表达式,比如lambda x:x.startswith('foo') 或者 lambda x:type(x)==str,
        """
        def param_wraper(func):
            """ 
            预处理函数，定义包装函数wraper取代老函数，定义完成后将目标函数增加到handlers中    
            """
            
            @wraps(func)
            def wraper(*args, **kw):
                """包装函数，这个函数是处理用户函数的，在用户函数执行前和执行后分别执行任务，甚至可以处理函数的参数"""
                func(*args, **kw)  # 需要这里显式调用用户函数

            self.read_bus.filter(expr).sink(wraper)
            self.handlers.append(func)
            # 包装定义阶段执行，包装后函数是个新函数了，
            # 老函数已经匿名，需要新函数加入handlers列表,这样才可以执行前后发消息

            return wraper
            # 返回的这个函数实际上取代了老函数。
            # 为了将老函数的函数名和docstring继承，需要用functools的wraps将其包装

        return param_wraper

