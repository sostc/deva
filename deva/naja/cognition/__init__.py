"""Cognition module - 认知中枢

包含子域：
- semantic/: 语义层（NewsEvent、Topic、AttentionScorer、KeywordRegistry、SemanticColdStart）
- analysis/: 分析推理层（CrossSignalAnalyzer、FirstPrinciplesMind、SoftInfoConfidence）
- narrative/: 叙事追踪（NarrativeTracker、TimingNarrative、SupplyChainLinker）
- insight/: 洞察引擎（InsightEngine、InsightPool）
- merrill_clock/: 美林时钟（经济周期判断）
- liquidity/: 流动性分析
- ui/: 认知系统 UI

核心文件（保留根目录）：
- core.py: NewsMindStrategy 认知流水线主驱动
- engine.py: CognitionEngine 平台级认知入口
- memory_manager.py: 三层记忆管理
- ingestion.py: Radar→Cognition 数据流桥梁
- openrouter_monitor.py: OpenRouter TOKEN 监控
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
# ── semantic 子域 ──────────────────────────────────────
from .semantic import SemanticColdStart
from .semantic import (
    NewsEvent,
    SignalType,
    DATASOURCE_TYPE_MAP,
    get_datasource_type,
    Topic,
    AttentionScorer as AttentionScorerModule,
)
# ── analysis 子域 ──────────────────────────────────────
from .analysis import (
    CrossSignalAnalyzer,
    ResonanceSignal,
    ResonanceType,
    SignalSource,
    NewsSignal,
    AttentionSnapshot as CrossAttentionSnapshot,
    CognitionFeedback,
    get_cross_signal_analyzer,
)
# ── insight 子域 ───────────────────────────────────────
from .insight import InsightEngine, InsightPool
# ── 统一认知事件总线（已迁移到 events 模块） ──────────────
from deva.naja.events import (
    CognitiveSignalBus,
    CognitiveEventType,
    get_cognitive_bus,
)
# ── 保留根目录的模块 ──────────────────────────────────
from .memory_manager import MemoryManager
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
    # 跨信号分析器 (analysis子域)
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
    # 统一认知事件总线 (已迁移到 events/)
    "CognitiveSignalBus",
    "CognitiveEventType",
    "get_cognitive_bus",
    # 语义子模块 (semantic子域)
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
