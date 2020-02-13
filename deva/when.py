
import os
import atexit
from .log import log


@atexit.register
def exit():
    """进程退出时发信号到log.

    Example:
    when('exit',source=log).then(lambda :print('bye bye'))
    """
    return 'exit' >> log


class when(object):
    """when a  occasion(from source) appear, then do somthing .

    Example:
    when('open').then(lambda :print(f'开盘啦'))
    when(lambda x:x>2).then(lambda x:print('x大于二'))
    """

    def __init__(self, occasion, source=log):
        self.occasion = occasion
        self.source = source
        # 接受来自总线的信号

    def then(self, func, *args, **kwargs):
        if callable(self.occasion):  # 检查发生的函数，函数输入为流里的值，输出为布尔
            return self.source.filter(self.occasion).sink(
                lambda x: func(x, *args, **kwargs))
        else:  # 不处理流的值
            return self.source.filter(lambda x: x is self.occasion).sink(
                lambda x: func(*args, **kwargs))


when('exit', source=log).then(lambda: print('bye bye,', os.getpid()))
