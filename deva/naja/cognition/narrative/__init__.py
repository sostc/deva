"""Narrative Module - 叙事追踪模块（天-地框架）

天-地-人：
- 天 (timing): 时机感知、阶段判断、叙事转换
- 地 (tracker): 外部叙事、价值发现、主题映射
- 供应链联动: 叙事→供应链影响分析
"""

from .tracker import (
    NarrativeTracker,
    NarrativeState,
    ValueSignal,
    get_narrative_tracker,
    NARRATIVE_PERSISTENCE_TABLE,
    NARRATIVE_PERSISTENCE_TABLE as _persistence_table,
    OPPORTUNITY_TYPES,
    RESOLVERS,
    MAX_PERSIST_STATES,
    MAX_PERSIST_HITS,
)

from .timing import (
    TimingNarrative,
    TimingNarrativeTracker,
    TimingNarrativeSense,
    TimingType,
    TimingStage,
    NarrativeTransition,
    StoryConflict,
    NarrativeTransitionSense,
    StoryConflictDetector,
)

from .supply_chain_linker import (
    NarrativeSupplyChainLinker,
    SupplyChainImpact,
    NarrativeSupplyChainEvent,
    RiskLevel,
    get_supply_chain_linker,
)

from .block_mapping import (
    NARRATIVE_TO_BLOCK_LINK,
    NARRATIVE_TO_MARKET_LINK,
    MARKET_TO_NARRATIVE_LINK,
    MARKET_INDEX_CONFIG,
    NARRATIVE_CATEGORY,
    BLOCK_TO_NARRATIVE_REVERSE,
    NARRATIVE_BLOCK_LINKING_ENABLED,
    get_linked_blocks,
    get_linked_narratives,
    get_linked_markets,
    get_linked_narratives_for_market,
    get_market_config,
    get_narrative_category,
    is_macro_narrative,
    is_industry_narrative,
    is_linking_enabled,
    set_linking_enabled,
)

from .ui import (
    render_narrative_page,
    render_narrative_lifecycle_page,
)

__all__ = [
    # Tracker (地)
    "NarrativeTracker",
    "NarrativeState",
    "ValueSignal",
    "get_narrative_tracker",
    "NARRATIVE_PERSISTENCE_TABLE",
    "OPPORTUNITY_TYPES",
    "RESOLVERS",
    # Timing (天)
    "TimingNarrative",
    "TimingNarrativeTracker",
    "TimingNarrativeSense",
    "TimingType",
    "TimingStage",
    "NarrativeTransition",
    "StoryConflict",
    "NarrativeTransitionSense",
    "StoryConflictDetector",
    # Supply Chain Linker
    "NarrativeSupplyChainLinker",
    "SupplyChainImpact",
    "NarrativeSupplyChainEvent",
    "RiskLevel",
    "get_supply_chain_linker",
    # Block Mapping
    "NARRATIVE_TO_BLOCK_LINK",
    "NARRATIVE_TO_MARKET_LINK",
    "MARKET_TO_NARRATIVE_LINK",
    "MARKET_INDEX_CONFIG",
    "NARRATIVE_CATEGORY",
    "BLOCK_TO_NARRATIVE_REVERSE",
    "NARRATIVE_BLOCK_LINKING_ENABLED",
    "get_linked_blocks",
    "get_linked_narratives",
    "get_linked_markets",
    "get_linked_narratives_for_market",
    "get_market_config",
    "get_narrative_category",
    "is_macro_narrative",
    "is_industry_narrative",
    "is_linking_enabled",
    "set_linking_enabled",
    # Web UI
    "render_narrative_page",
    "render_narrative_lifecycle_page",
]