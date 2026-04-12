"""Cognition module - 认知中枢

包含：
- NewsMindStrategy: 新闻心智策略，驱动认知流水线
- CognitionEngine: 认知引擎，平台级认知输入输出入口
- InsightEngine/InsightPool: 洞察引擎，管理认知产物
- CrossSignalAnalyzer: 跨信号分析器，合并新闻和注意力信号
- HistoryTracker: 历史事件追踪器，追踪注意力变化
"""

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
# 统一认知事件总线
from .cognitive_signal_bus import (
    CognitiveSignalBus,
    CognitiveEventType,
    get_cognitive_bus,
)
# 拆分出的子模块
from .news_event import NewsEvent, SignalType, DATASOURCE_TYPE_MAP, get_datasource_type
from .topic_manager import Topic
from .attention_scorer import AttentionScorer as AttentionScorerModule
from .memory_manager import MemoryManager
# 统一数据流入口
from .ingestion import CognitionIngestion, get_cognition_ingestion

__all__ = [
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
    # 叙事-题材映射
    "NARRATIVE_TO_BLOCK_LINK",
    "NARRATIVE_TO_MARKET_LINK",
    "MARKET_TO_NARRATIVE_LINK",
    "MARKET_INDEX_CONFIG",
    "get_linked_blocks",
    "get_linked_markets",
    "get_market_config",
    # 统一认知事件总线
    "CognitiveSignalBus",
    "CognitiveEventType",
    "get_cognitive_bus",
    # 拆分子模块
    "NewsEvent",
    "SignalType",
    "DATASOURCE_TYPE_MAP",
    "get_datasource_type",
    "Topic",
    "AttentionScorerModule",
    "MemoryManager",
    # 统一数据流入口
    "CognitionIngestion",
    "get_cognition_ingestion",
]

