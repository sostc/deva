"""
Attention Orchestrator - 兼容层

此文件已废弃，请使用 deva.naja.attention.center
新的 AttentionCenter 替代了旧的 AttentionOrchestrator

此文件将在未来版本中移除
"""

import warnings
warnings.warn(
    "deva.naja.attention.orchestrator 模块已废弃 "
    "请使用 'from deva.naja.attention import AttentionCenter, get_orchestrator'",
    DeprecationWarning,
    stacklevel=2
)

from deva.naja.attention.center import (
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
]