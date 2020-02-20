#!/usr/bin/env python

import logging
from logbook import Logger, StreamHandler
from .stream import NS
import sys
from functools import wraps
import pprint

__all__ = [
    'log', 'warn', 'log_to'
]

warn = NS('warn')
warn.map(pprint.pformat).sink(logging.warning)

StreamHandler(sys.stdout).push_application()
logger = Logger(__name__)
log = NS('log', cache_max_len=10, cache_max_age_seconds=60 * 60 * 24)
log.sink(logger.info)


class log_to(object):
    """函数装饰器，将函数返回值重新定向到一个指定的流"""

    def __init__(self, stream=log):
        self.stream = stream

    def __call__(self, func):
        @wraps(func)
        def wraper(*args, **kwargs):
            # some action before
            result = func(*args, **kwargs)  # 需要这里显式调用用户函数
            # action after
            {
                'function': func.__name__,
                'param': (args, kwargs),
                'return': result
            } >> self.stream

            return result

        return wraper
