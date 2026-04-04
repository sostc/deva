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


def get_adaptive_weights(scanner=None) -> Dict[str, Any]:
    """
    获取四维引擎的自适应权重（提案2.4.2）

    对外暴露的接口，供外部模块查询当前权重配置

    Returns:
        {
            "timing": {component: weight},
            "regime": {component: weight},
        }
    """
    try:
        from deva.naja.attention.kernel.manas_engine import TimingEngine, RegimeEngine

        te = TimingEngine()
        re = RegimeEngine()

        return {
            "timing": te._get_adaptive_weights(scanner, 0.5),
            "regime": re._get_adaptive_regime_weights(scanner),
        }
    except ImportError:
        # 降级：返回固定权重
        return {
            "timing": {
                "time_pressure": 0.4,
                "volatility": 0.25,
                "density": 0.2,
                "structure": 0.15,
            },
            "regime": {
                "trend": 0.4,
                "liquidity": 0.35,
                "diffusion": 0.25,
            },
        }


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
    "get_adaptive_weights",
]
