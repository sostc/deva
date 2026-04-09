"""
Integration - 市场热点系统集成
"""

from .market_hotspot_system import (
    MarketHotspotSystem,
    MarketHotspotSystemConfig,
    FallbackConfig,
    MarketSnapshot,
    StepResult,
)
from .integration import (
    IntelligenceAugmentedSystem,
    IntelligenceConfig,
    create_intelligence_system,
    create_system,
)
from .extended import (
    MarketHotspotIntegration,
    get_market_hotspot_integration,
    initialize_hotspot_system,
    register_hotspot_manager,
    get_hotspot_manager,
    process_data_with_hotspots,
    AttentionModeManager,
    get_mode_manager,
)

__all__ = [
    "MarketHotspotSystem",
    "MarketHotspotSystemConfig",
    "FallbackConfig",
    "MarketSnapshot",
    "StepResult",
    "IntelligenceAugmentedSystem",
    "IntelligenceConfig",
    "create_intelligence_system",
    "create_system",
    "MarketHotspotIntegration",
    "get_market_hotspot_integration",
    "initialize_hotspot_system",
    "get_hotspot_manager",
    "process_data_with_hotspots",
    "AttentionModeManager",
    "get_mode_manager",
]
