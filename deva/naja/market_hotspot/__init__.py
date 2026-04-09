"""
Market Hotspot System - 市场热点系统

市场热点系统分析市场数据（价格/成交量/涨跌幅）来确定热点题材和个股，
并决定数据获取频率和策略资源分配。

这是注意力基础设施的市场应用层。

子模块:
- core/              - 核心注意力引擎 (GlobalAttention, BlockAttention, WeightPool)
- scheduling/        - 频率调度和策略分配
- engine/           - River + PyTorch 双引擎
- processing/       - 数据预处理（噪音过滤）
- filters/         - 过滤器
- data/            - 市场数据处理
- integration/      - 系统集成
- strategies/       - 基于注意力的交易策略
"""

from .core import (
    GlobalHotspotEngine,
    MarketSnapshot,
    BlockHotspotEngine,
    BlockConfig,
    WeightPool,
    WeightPoolView,
    SymbolWeightConfig,
)
from .scheduling import (
    FrequencyScheduler,
    FrequencyLevel,
    FrequencyConfig,
    AdaptiveFrequencyController,
    StrategyAllocator,
    StrategyRegistry,
    Strategy,
    StrategyConfig,
    StrategyParams,
    StrategyScope,
    StrategyType,
)
from .engine import (
    RiverEngine,
    PyTorchEngine,
    DualEngineCoordinator,
    AnomalySignal,
    PatternSignal,
)
from .processing import (
    NoiseFilter,
    NoiseFilterConfig,
    get_noise_filter,
    get_tick_noise_filter,
    TickNoiseFilterConfig,
)
from .filters import (
    LiquidityRescueFilter,
    PanicAnalyzer,
)
from .integration import (
    MarketHotspotSystem,
    MarketHotspotSystemConfig,
    FallbackConfig,
    MarketSnapshot,
    StepResult,
    IntelligenceAugmentedSystem,
    IntelligenceConfig,
    create_intelligence_system,
    create_system,
    MarketHotspotIntegration,
    get_market_hotspot_integration,
    initialize_hotspot_system,
    register_hotspot_manager,
    get_hotspot_manager,
    process_data_with_hotspots,
    AttentionModeManager,
    get_mode_manager,
)
from .realtime_data_fetcher import (
    RealtimeDataFetcher,
    AsyncRealtimeDataFetcher,
    FetchConfig,
)

__all__ = [
    # Core
    "GlobalHotspotEngine",
    "MarketSnapshot",
    "BlockHotspotEngine",
    "BlockConfig",
    "WeightPool",
    "WeightPoolView",
    "SymbolWeightConfig",
    # Scheduling
    "FrequencyScheduler",
    "FrequencyLevel",
    "FrequencyConfig",
    "AdaptiveFrequencyController",
    "StrategyAllocator",
    "StrategyRegistry",
    "Strategy",
    "StrategyConfig",
    "StrategyParams",
    "StrategyScope",
    "StrategyType",
    # Engine
    "RiverEngine",
    "PyTorchEngine",
    "DualEngineCoordinator",
    "AnomalySignal",
    "PatternSignal",
    # Processing
    "NoiseFilter",
    "NoiseFilterConfig",
    "get_noise_filter",
    "get_tick_noise_filter",
    "TickNoiseFilterConfig",
    # Filters
    "LiquidityRescueFilter",
    "PanicAnalyzer",
    # Integration
    "MarketHotspotSystem",
    "MarketHotspotSystemConfig",
    "FallbackConfig",
    "StepResult",
    "IntelligenceAugmentedSystem",
    "IntelligenceConfig",
    "create_intelligence_system",
    "create_system",
    "MarketHotspotIntegration",
    "get_market_hotspot_integration",
    "initialize_hotspot_system",
    "register_hotspot_manager",
    "get_hotspot_manager",
    "process_data_with_hotspots",
    "AttentionModeManager",
    "get_mode_manager",
    # Realtime Fetcher
    "RealtimeDataFetcher",
    "AsyncRealtimeDataFetcher",
    "FetchConfig",
]

from .events import (
    HotspotComputedEvent,
    MarketSnapshotEvent,
    SymbolUpdateEvent,
)

from .event_bus import (
    HotspotEventBus,
    get_event_bus,
)

__all__ = __all__ + [
    "HotspotComputedEvent",
    "MarketSnapshotEvent",
    "SymbolUpdateEvent",
    "HotspotEventBus",
    "get_event_bus",
]

__version__ = "3.0.0"
