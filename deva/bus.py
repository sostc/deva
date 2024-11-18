#!/usr/bin/env python
"""总线模块,提供全局事件流和日志功能

本模块提供了一个全局事件总线系统,用于在不同组件间传递消息和事件。
主要包含以下功能:

1. log流: 用于全局日志记录
2. warn流: 用于警告信息
3. debug流: 用于调试信息
4. bus: 通用事件总线

主要组件:
--------
log : NS
    全局日志流,缓存最近消息
warn : NS 
    警告信息流,输出到logging
debug : NS
    调试信息流
bus : NT
    通用事件总线,用于组件间通信

示例:
-----
# 基本日志
'hello' >> log  # 输出日志

# 警告信息
'warning!' >> warn  # 输出警告

# 调试信息
'debug info' >> debug  # 输出调试信息

# 事件总线
def handler(msg):
    print('收到消息:', msg)
    
bus.sink(handler)  # 注册处理器
'event' >> bus  # 发送事件

# 函数调试
@debug  # 装饰器方式
def foo():
    pass

f = range+sum  # 函数组合
ff = f^debug  # 添加调试
'123' >> ff  # 执行时输出调试信息
"""

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
