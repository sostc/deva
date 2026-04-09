"""
Strategies - 基于热点的交易策略
"""

from .base import HotspotStrategyBase, Signal
from .global_sentinel import GlobalMarketSentinel
from .block_hunter import BlockRotationHunter
from .momentum_tracker import MomentumSurgeTracker
from .anomaly_sniper import AnomalyPatternSniper
from .smart_money_detector import SmartMoneyFlowDetector
from .us_strategies import (
    USGlobalMarketSentinel,
    USBlockRotationHunter,
    USMomentumSurgeTracker,
    USAnomalyPatternSniper,
    USSmartMoneyFlowDetector,
)
from .strategy_manager import (
    HotspotStrategyManager,
    StrategyConfig,
    get_hotspot_manager,
    get_strategy_manager,
    initialize_hotspot_strategies
)
from .config import (
    StrategySettings,
    HotspotStrategyConfig,
    ConfigManager,
    get_config_manager
)
from .wrapper import (
    HotspotStrategyWrapper,
    wrap_hotspot_strategy,
    register_hotspot_strategies_to_manager,
)
from .liquidity_rescue_strategies import (
    PanicPeakDetector,
    LiquidityCrisisTracker,
    RecoveryConfirmationMonitor,
    LiquidityRescueOrchestrator,
    RescueSignal,
    RescueSignalType,
    LiquidityCrisisState,
)

__all__ = [
    "HotspotStrategyBase",
    "Signal",
    "GlobalMarketSentinel",
    "BlockRotationHunter",
    "MomentumSurgeTracker",
    "AnomalyPatternSniper",
    "SmartMoneyFlowDetector",
    "USGlobalMarketSentinel",
    "USBlockRotationHunter",
    "USMomentumSurgeTracker",
    "USAnomalyPatternSniper",
    "USSmartMoneyFlowDetector",
    "HotspotStrategyManager",
    "StrategyConfig",
    "get_hotspot_manager",
    "get_strategy_manager",
    "initialize_hotspot_strategies",
    "StrategySettings",
    "HotspotStrategyConfig",
    "ConfigManager",
    "get_config_manager",
    "setup_hotspot_strategies",
    "HotspotStrategyWrapper",
    "wrap_hotspot_strategy",
    "register_hotspot_strategies_to_manager",
    "PanicPeakDetector",
    "LiquidityCrisisTracker",
    "RecoveryConfirmationMonitor",
    "LiquidityRescueOrchestrator",
    "RescueSignal",
    "RescueSignalType",
    "LiquidityCrisisState",
]


def setup_hotspot_strategies():
    """快速设置热点策略系统"""
    config_manager = get_config_manager()
    manager = initialize_hotspot_strategies()
    return manager
