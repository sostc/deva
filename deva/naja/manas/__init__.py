"""
Manas Module - 末那识层

提供顺应型末那识能力和统一末那识决策框架

类：
- AdaptiveManas: 顺应型末那识（保留兼容）
- UnifiedManas: 统一末那识（新）
- UnifiedManasOutput: 统一输出
- PortfolioDrivenEventRecall: 持仓驱动事件召回
- ManasFeedbackLoop: 闭环反馈
"""

from typing import Dict, Any

from .adaptive_manas import (
    AdaptiveManas,
    WuWeiDecision,
    TianShiResponse,
    RegimeHarmony,
    RenShiResponse,
    HarmonyState,
)

from .output import (
    UnifiedManasOutput,
    AttentionFocus,
    ActionType,
    PortfolioSignal,
)

from .unified_manas import (
    UnifiedManas,
    TimingEngine,
    RegimeEngine,
    ConfidenceEngine,
    RiskEngine,
    MetaManas,
    PortfolioAnalyzer,
)

from .event_recall import (
    PortfolioDrivenEventRecall,
    RecalledEvent,
)

from .feedback_loop import (
    ManasFeedbackLoop,
    FeedbackRecord,
    OutcomeType,
)


class ManasCore:
    """末那识核心 - 系统监控用wrapper"""

    def __init__(self):
        self._adaptive_manas = AdaptiveManas()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        state = self._adaptive_manas.get_state()
        return {
            "eyes_active": 0,
            "decision_count": state.get("decision_count", 0),
            "recent_success_rate": state.get("recent_success_rate", 0),
            "last_decision": state.get("last_decision"),
        }


_manas_core_instance = None


def get_manas_core() -> ManasCore:
    """获取末那识核心单例"""
    global _manas_core_instance
    if _manas_core_instance is None:
        _manas_core_instance = ManasCore()
    return _manas_core_instance


__all__ = [
    "AdaptiveManas",
    "WuWeiDecision",
    "TianShiResponse",
    "RegimeHarmony",
    "RenShiResponse",
    "HarmonyState",
    "UnifiedManas",
    "UnifiedManasOutput",
    "AttentionFocus",
    "ActionType",
    "PortfolioSignal",
    "TimingEngine",
    "RegimeEngine",
    "ConfidenceEngine",
    "RiskEngine",
    "MetaManas",
    "PortfolioAnalyzer",
    "PortfolioDrivenEventRecall",
    "RecalledEvent",
    "ManasFeedbackLoop",
    "FeedbackRecord",
    "OutcomeType",
    "ManasCore",
    "get_manas_core",
]