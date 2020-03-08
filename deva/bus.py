#!/usr/bin/env python

import logging
from logbook import Logger, StreamHandler
import sys
from .namespace import *

__all__ = [
    'log', 'warn'
]

warn = NS('warn')
warn.sink(logging.warning)

StreamHandler(sys.stdout).push_application()

logger = Logger(__name__)
log = NS('log', cache_max_len=10, cache_max_age_seconds=60 * 60 * 24)
log.sink(logger.info)


bus = NT('bus')
