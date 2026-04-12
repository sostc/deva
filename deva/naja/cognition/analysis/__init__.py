"""Cognition Analysis - 分析推理子域

包含：
- CrossSignalAnalyzer: 天-地共振检测，跨信号分析
- FirstPrinciplesMind: 第一性原理/因果分析/推理引擎
- SoftInfoConfidence: 软信息置信度评估
"""

from .cross_signal_analyzer import (
    CrossSignalAnalyzer,
    ResonanceSignal,
    ResonanceType,
    SignalSource,
    NewsSignal,
    AttentionSnapshot,
    CognitionFeedback,
    get_cross_signal_analyzer,
)
from .first_principles_mind import (
    FirstPrinciplesMind,
    FirstPrinciplesAnalyzer,
    FirstPrinciplesInsight,
    CausalityChain,
    CausalityTracker,
    ContradictionDetector,
    ReasoningEngine,
    CognitiveIntegrator,
    MarketCausalityGraph,
)
from .soft_info_confidence import (
    SoftInfoConfidence,
    SoftInfoSignal,
    SoftInfoSource,
)

__all__ = [
    # 跨信号分析
    "CrossSignalAnalyzer",
    "ResonanceSignal",
    "ResonanceType",
    "SignalSource",
    "NewsSignal",
    "AttentionSnapshot",
    "CognitionFeedback",
    "get_cross_signal_analyzer",
    # 第一性原理
    "FirstPrinciplesMind",
    "FirstPrinciplesAnalyzer",
    "FirstPrinciplesInsight",
    "CausalityChain",
    "CausalityTracker",
    "ContradictionDetector",
    "ReasoningEngine",
    "CognitiveIntegrator",
    "MarketCausalityGraph",
    # 软信息置信度
    "SoftInfoConfidence",
    "SoftInfoSignal",
    "SoftInfoSource",
]
