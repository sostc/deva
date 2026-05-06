"""
信号流模块

提供实时信号流的展示和管理功能
"""

from .ui import (
    render_signal_page,
)
from .dispatcher import (
    SignalDispatcher,
    get_dispatcher,
    dispatch_result,
)

__all__ = [
    'render_signal_page',
    'SignalDispatcher',
    'get_dispatcher',
    'dispatch_result',
]
