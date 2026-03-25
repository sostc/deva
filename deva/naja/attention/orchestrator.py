"""
Attention Orchestrator - 兼容层

此类名已从 AttentionCenter 重命名为 AttentionOrchestrator
"""

import warnings
warnings.warn(
    "deva.naja.attention.orchestrator 模块已废弃 "
    "请使用 'from deva.naja.attention import AttentionOrchestrator, get_orchestrator'",
    DeprecationWarning,
    stacklevel=2
)

from deva.naja.attention.center import (
    AttentionOrchestrator,
    AttentionCenter,
    Orchestrator,
    get_orchestrator as _get_orchestrator,
    initialize_orchestrator,
)

_orchestrator_instance = None


def get_orchestrator():
    """获取 orchestrator 单例"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = _get_orchestrator()
    return _orchestrator_instance


__all__ = [
    "get_orchestrator",
    "AttentionOrchestrator",
    "AttentionCenter",
    "Orchestrator",
]