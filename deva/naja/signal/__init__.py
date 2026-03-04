"""
信号流模块

提供实时信号流的展示和管理功能
"""

from .ui import (
    render_signal_page,
    set_auto_refresh,
    is_auto_refresh_enabled,
)

__all__ = [
    'render_signal_page',
    'set_auto_refresh',
    'is_auto_refresh_enabled',
]
