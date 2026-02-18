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
from .namespace import NS
import atexit
import os
from .bus_parts.runtime import BusRuntime
from .logging_adapter import (
    normalize_record as _adapter_normalize_record,
    format_line as _adapter_format_line,
    should_emit_level as _adapter_should_emit_level,
    setup_deva_logging,
)

# from .endpoints import Dtalk

__all__ = [
    'log', 'warn', 'debug', 'bus',
    'get_bus_runtime_status', 'get_bus_clients', 'get_bus_recent_messages', 'send_bus_message',
    'configure_log_behavior',
]

warn = NS('warn')
debug = NS('debug')
setup_deva_logging()


_DEFAULT_LOGGER = logging.getLogger("deva.log")
_LOG_SINK_INSTALLED = False


def _normalize_log_record(x):
    return _adapter_normalize_record(x, default_level="INFO", default_source="deva")


def _format_log_line(record):
    return _adapter_format_line(record)


def _should_emit_level(level_name):
    return _adapter_should_emit_level(level_name)


def _emit_to_python_logger(record):
    level_name = str(record.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    _DEFAULT_LOGGER.log(level, record.get("message", ""), extra={"deva_extra": record.get("extra", {})})


def _default_log_sink(x):
    record = _normalize_log_record(x)
    if not _should_emit_level(record.get("level")):
        return
    print(_format_log_line(record))
    if os.getenv("DEVA_LOG_FORWARD_TO_LOGGING", "0").strip() == "1":
        _emit_to_python_logger(record)


def _emit_with_defaults(x, *, level="INFO", source="deva"):
    record = _normalize_log_record(x)
    if not record.get("level"):
        record["level"] = level
    if str(record.get("level", "")).upper() == "INFO" and level != "INFO":
        record["level"] = level
    if not record.get("source") or record.get("source") == "deva":
        record["source"] = source
    return record


def _warn_sink(x):
    record = _emit_with_defaults(x, level="WARNING", source="deva.warn")
    log.emit(record)


def _debug_sink(x):
    record = _emit_with_defaults(x, level="DEBUG", source="deva.debug")
    log.emit(record)


def configure_log_behavior():
    """配置 deva 默认日志行为（结构化、可转发到 logging）。"""
    global _LOG_SINK_INSTALLED
    if _LOG_SINK_INSTALLED:
        return
    log.sink(_default_log_sink)
    warn.sink(_warn_sink)
    debug.sink(_debug_sink)
    _LOG_SINK_INSTALLED = True


log = NS(
    'log',
    cache_max_len=int(os.getenv("DEVA_LOG_CACHE_MAX_LEN", "200")),
    cache_max_age_seconds=60 * 60 * 24,
)
configure_log_behavior()

_BUS_RUNTIME = BusRuntime(
    warn_stream=warn,
    topic=os.getenv("DEVA_BUS_TOPIC", "bus"),
)
bus = _BUS_RUNTIME.start()


def get_bus_clients(ttl_seconds=30):
    return _BUS_RUNTIME.get_clients(ttl_seconds=ttl_seconds)


def get_bus_recent_messages(limit=10):
    return _BUS_RUNTIME.get_recent_messages(limit=limit)


def send_bus_message(message, sender="admin", extra=None):
    return _BUS_RUNTIME.send_message(message, sender=sender, extra=extra)


def get_bus_runtime_status():
    return _BUS_RUNTIME.get_status()


@atexit.register
def exit():
    """进程退出时发信号到log.

    Examples:
    ----------
    when('exit',source=log).then(lambda :print('bye bye'))
    """
    #
    try:
        _BUS_RUNTIME.stop()
    except Exception as e:
        e >> log

# debug.map(str).unique() >> Dtalk()
# debug.sink(lambda x: console.log(x, log_locals=True))
