"""
Manas Module - 末那识层

提供末那识决策能力

注意：核心实现已迁移到 AttentionKernel 中的 ManasEngine
此处保留兼容接口供旧代码使用
"""

from typing import Dict, Any

from .output import (
    HarmonyState,
    ActionType,
    AttentionFocus,
    PortfolioSignal,
)

from .feedback_loop import (
    ManasFeedbackLoop,
    FeedbackRecord,
    OutcomeType,
)

from .event_recall import (
    PortfolioDrivenEventRecall,
    RecalledEvent,
)


class ManasCore:
    """末那识核心 - 兼容层 wrapper"""

    def __init__(self):
        from deva.naja.attention.trading_center import get_trading_center
        tc = get_trading_center()
        self._manas_engine = tc.get_attention_os().kernel.get_manas_engine()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "eyes_active": 0,
            "decision_count": 0,
            "recent_success_rate": 0.5,
            "last_decision": None,
        }

    def compute(self, *args, **kwargs):
        """转发到 ManasEngine"""
        return self._manas_engine.compute(*args, **kwargs)


_manas_core_instance = None


def get_manas_core() -> ManasCore:
    """获取末那识核心单例"""
    global _manas_core_instance
    if _manas_core_instance is None:
        _manas_core_instance = ManasCore()
    return _manas_core_instance


__all__ = [
    "HarmonyState",
    "ActionType",
    "AttentionFocus",
    "PortfolioSignal",
    "ManasFeedbackLoop",
    "FeedbackRecord",
    "OutcomeType",
    "PortfolioDrivenEventRecall",
    "RecalledEvent",
    "ManasCore",
    "get_manas_core",
]
