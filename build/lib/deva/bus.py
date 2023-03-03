#!/usr/bin/env python
"""公共总线流.

Exsample::

    f = range+sum
    ff = f^debug
    '123'>>ff
    #函数异常将被发到debug，并且push到钉钉
"""
import logging
from .namespace import NS, NT
import datetime
import atexit

# from .endpoints import Dtalk

__all__ = [
    'log', 'warn', 'debug', 'bus',
]

warn = NS('warn')
warn.sink(logging.warning)


def log_print(x):
    try:
        # from termcolor import cprint
        # _log_print = (lambda x: cprint(x, 'red', 'on_cyan'))@P
        # str(datetime.datetime.now()) + ':' + str(x) >> _log_print
        # from rich.console import Console
        # console = Console()
        # console.log(x, log_locals=False)
        print(datetime.datetime.now(), ':', x)
    except:
        print(datetime.datetime.now(), ':', x)


log = NS('log', cache_max_len=10, cache_max_age_seconds=60 * 60 * 24)
log.sink(log_print)


bus = NT('bus')


@atexit.register
def exit():
    """进程退出时发信号到log.

    Examples:
    ----------
    when('exit',source=log).then(lambda :print('bye bye'))
    """
    #
    try:
        bus.stop()
    except Exception as e:
        e >> log


debug = NS('debug')
# debug.map(str).unique() >> Dtalk()
# debug.sink(lambda x: console.log(x, log_locals=True))
