"""
Market Hotspot System - 市场热点系统

提供市场热点计算、题材跟踪、热点预测等功能。
"""

from .integration.market_hotspot_system import (
    MarketHotspotSystem,
    MarketHotspotSystemConfig,
    MarketSnapshot,
    StepResult,
)
from .integration.hotspot_intelligence_system import (
    IntelligenceConfig,
    create_intelligence_system,
    create_system,
)
from .integration.market_hotspot_integration import (
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
from .market_hotspot_history_tracker import (
    MarketHotspotHistoryTracker,
    get_history_tracker,
)

__all__ = [
    "MarketHotspotSystem",
    "MarketHotspotSystemConfig",
    "MarketSnapshot",
    "StepResult",
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
    "RealtimeDataFetcher",
    "AsyncRealtimeDataFetcher",
    "FetchConfig",
    "MarketHotspotHistoryTracker",
    "get_history_tracker",
]