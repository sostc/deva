
import atexit
from .log import log
from .bus import bus


@atexit.register
def exit():
    """进程退出时发信号到log.

    Example:
    when('exit',source=log).then(lambda :print(bye bye))
    """
    'exit' >> log


class when(object):
    """when a  occasion(from source) appear, then do somthing .

    Example:
    when('open').then(lambda :print(f'开盘啦'))
    """

    def __init__(self, occasion, source=bus):
        self.occasion = occasion
        self.source = source

    def then(self, func):
        self.source.filter(lambda x: x is self.occasion).sink(lambda x: func())
