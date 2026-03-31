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
]
