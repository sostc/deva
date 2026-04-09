"""Cognition module - 认知中枢

包含：
- NewsMindStrategy: 新闻心智策略，驱动认知流水线
- CognitionEngine: 认知引擎，平台级认知输入输出入口
- InsightEngine/InsightPool: 洞察引擎，管理认知产物
- CrossSignalAnalyzer: 跨信号分析器，合并新闻和注意力信号
- HistoryTracker: 历史事件追踪器，追踪注意力变化
"""

from .cognition_bus import (
    cognition_bus,
    CognitionEventType,
    CognitionEvent,
    emit_attention_snapshot,
    emit_news_signal,
    emit_resonance,
    emit_insight,
    emit_cognition_feedback,
    subscribe_to_event,
    subscribe_to_all,
)
from .core import NewsMindStrategy, AttentionScorer
from .engine import CognitionEngine
from .narrative import (
    NarrativeTracker,
    NarrativeState,
    ValueSignal,
    get_narrative_tracker,
    TimingNarrative,
    TimingNarrativeTracker,
    TimingNarrativeSense,
    TimingType,
    TimingStage,
    NarrativeTransition,
    StoryConflict,
    NarrativeSupplyChainLinker,
    SupplyChainImpact,
    NarrativeSupplyChainEvent,
    RiskLevel,
    get_supply_chain_linker,
    NARRATIVE_TO_BLOCK_LINK,
    NARRATIVE_TO_MARKET_LINK,
    MARKET_TO_NARRATIVE_LINK,
    MARKET_INDEX_CONFIG,
    get_linked_blocks,
    get_linked_markets,
    get_market_config,
)
from .semantic_cold_start import SemanticColdStart
from .insight import InsightEngine, InsightPool
from .cross_signal_analyzer import (
    CrossSignalAnalyzer,
    ResonanceSignal,
    ResonanceType,
    SignalSource,
    NewsSignal,
    AttentionSnapshot as CrossAttentionSnapshot,
    CognitionFeedback,
    get_cross_signal_analyzer,
)

__all__ = [
    # 认知事件总线
    "cognition_bus",
    "CognitionEventType",
    "CognitionEvent",
    "emit_attention_snapshot",
    "emit_news_signal",
    "emit_resonance",
    "emit_insight",
    "emit_cognition_feedback",
    "subscribe_to_event",
    "subscribe_to_all",
    # 核心策略
    "NewsMindStrategy",
    "AttentionScorer",
    # 认知引擎
    "CognitionEngine",
    # 天-地 叙事追踪 (narrative模块)
    "NarrativeTracker",
    "NarrativeState",
    "ValueSignal",
    "get_narrative_tracker",
    "TimingNarrative",
    "TimingNarrativeTracker",
    "TimingNarrativeSense",
    "TimingType",
    "TimingStage",
    "NarrativeTransition",
    "StoryConflict",
    "SemanticColdStart",
    # 洞察引擎
    "InsightEngine",
    "InsightPool",
    # 跨信号分析器
    "CrossSignalAnalyzer",
    "ResonanceSignal",
    "ResonanceType",
    "SignalSource",
    "NewsSignal",
    "CognitionFeedback",
    "get_cross_signal_analyzer",
    # 叙事-供应链联动器
    "NarrativeSupplyChainLinker",
    "SupplyChainImpact",
    "NarrativeSupplyChainEvent",
    "RiskLevel",
    "get_supply_chain_linker",
    # 叙事-板块映射
    "NARRATIVE_TO_BLOCK_LINK",
    "NARRATIVE_TO_MARKET_LINK",
    "MARKET_TO_NARRATIVE_LINK",
    "MARKET_INDEX_CONFIG",
    "get_linked_blocks",
    "get_linked_markets",
    "get_market_config",
]

# 向后兼容别名
MemoryEngine = CognitionEngine
