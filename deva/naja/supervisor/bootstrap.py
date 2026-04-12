"""Supervisor 模块级启动/停止函数"""

from __future__ import annotations

import threading
from typing import Optional, TYPE_CHECKING

import logging

if TYPE_CHECKING:
    from .core import NajaSupervisor

log = logging.getLogger(__name__)


_naja_supervisor: Optional["NajaSupervisor"] = None
_supervisor_lock = threading.Lock()


def get_naja_supervisor() -> "NajaSupervisor":
    """获取 Naja 监控器单例"""
    global _naja_supervisor
    if _naja_supervisor is None:
        with _supervisor_lock:
            if _naja_supervisor is None:
                from .core import NajaSupervisor
                _naja_supervisor = NajaSupervisor()
                _register_atexit_cleanup()
    return _naja_supervisor


def _register_atexit_cleanup():
    """注册退出时的清理函数"""
    import atexit

    supervisor = get_naja_supervisor()

    def _cleanup():
        try:
            from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
            tracker = get_history_tracker()
            if tracker:
                tracker.save_state()
                log.info("[atexit] 热点历史已保存")
        except Exception as e:
            log.warning(f"[atexit] 保存热点历史失败: {e}")

        try:
            attention = supervisor._get_component('attention')
            if attention and hasattr(attention, 'persist_state'):
                attention.persist_state()
                log.info("[atexit] 注意力系统状态已持久化")
        except Exception as e:
            log.warning(f"[atexit] 持久化注意力系统状态失败: {e}")

    atexit.register(_cleanup)


def stop_supervisor() -> None:
    """停止 Naja 监控器"""
    supervisor = get_naja_supervisor()
    supervisor.stop_monitoring()


def start_supervisor(force_realtime: bool = False, lab_mode: bool = False) -> None:
    """启动 Naja 监控器

    Args:
        force_realtime: 是否强制实时模式（暂未使用）
        lab_mode: 是否为实验模式（暂未使用）
    """
    supervisor = get_naja_supervisor()
    if hasattr(supervisor, 'start_monitoring'):
        supervisor.start_monitoring()


# 别名，保持向后兼容
def get_supervisor() -> "NajaSupervisor":
    """获取 Naja 监控器单例（向后兼容别名）"""
    return get_naja_supervisor()
