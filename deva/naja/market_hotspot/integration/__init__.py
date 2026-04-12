"""
Integration - 市场热点系统集成
"""

from .system_config import (
    MarketHotspotSystemConfig,
    StepResult,
    FallbackConfig,
)
from .market_hotspot_system import (
    MarketHotspotSystem,
    MarketSnapshot,
)
from .system_integration import MarketHotspotSystemIntegration
from .hotspot_intelligence_system import (
    _HotspotIntelligenceSystemInternal,
    IntelligenceConfig,
    create_intelligence_system,
    create_system,
)
from .market_hotspot_integration import (
    MarketHotspotIntegration,
    get_market_hotspot_integration,
    initialize_hotspot_system,
    register_hotspot_manager,
    get_hotspot_manager,
    process_data_with_hotspots,
    AttentionModeManager,
    get_mode_manager,
)

HotspotIntelligenceSystem = _HotspotIntelligenceSystemInternal

__all__ = [
    "MarketHotspotSystem",
    "MarketHotspotSystemConfig",
    "MarketHotspotSystemIntegration",
    "FallbackConfig",
    "MarketSnapshot",
    "StepResult",
    "HotspotIntelligenceSystem",
    "_HotspotIntelligenceSystemInternal",
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
]