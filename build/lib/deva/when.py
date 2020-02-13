
import atexit
from .log import log


@atexit.register
def exit():
    """进程退出时发信号到log.

    Example:
    when('exit',source=log).then(lambda :print('bye bye'))
    """
    'exit' >> log


class when(object):
    """when a  occasion(from source) appear, then do somthing .

    Example:
    when('open').then(lambda :print(f'开盘啦'))
    """

    def __init__(self, occasion, source=log):
        self.occasion = occasion
        self.source = source
        # 接受来自总线的信号

    def then(self, func, *args, **kwargs):
        if callable(self.occasion):
            self.source.filter(self.occasion).sink(
                lambda x: func(x, *args, **kwargs))
        else:
            self.source.filter(lambda x: x == self.occasion).sink(lambda x: func())
