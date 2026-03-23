"""Cognition module - 认知中枢

包含：
- NewsMindStrategy: 新闻心智策略，驱动认知流水线
- CognitionEngine: 认知引擎，平台级认知输入输出入口
- InsightEngine/InsightPool: 洞察引擎，管理认知产物
- CrossSignalAnalyzer: 跨信号分析器，合并新闻和注意力信号
"""

from .core import NewsMindStrategy, AttentionScorer
from .engine import CognitionEngine, get_cognition_engine
from .narrative_tracker import NarrativeTracker
from .semantic_cold_start import SemanticColdStart
from .insight import InsightEngine, InsightPool, get_insight_engine, get_insight_pool
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

__all__ = [
    # 核心策略
    "NewsMindStrategy",
    "AttentionScorer",
    # 认知引擎
    "CognitionEngine",
    "get_cognition_engine",
    # 向后兼容别名
    "MemoryEngine",
    "get_memory_engine",
    # 叙事追踪
    "NarrativeTracker",
    "SemanticColdStart",
    # 洞察引擎
    "InsightEngine",
    "InsightPool",
    "get_insight_engine",
    "get_insight_pool",
    # 跨信号分析器
    "CrossSignalAnalyzer",
    "ResonanceSignal",
    "ResonanceType",
    "SignalSource",
    "NewsSignal",
    "AttentionSnapshot",
    "CognitionFeedback",
    "get_cross_signal_analyzer",
]

# 向后兼容别名
MemoryEngine = CognitionEngine
get_memory_engine = get_cognition_engine