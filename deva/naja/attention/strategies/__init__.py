"""
Strategies - 基于注意力的交易策略
"""

from .base import AttentionStrategyBase, Signal
from .global_sentinel import GlobalMarketSentinel
from .sector_hunter import SectorRotationHunter
from .momentum_tracker import MomentumSurgeTracker
from .anomaly_sniper import AnomalyPatternSniper
from .smart_money_detector import SmartMoneyFlowDetector
from .us_strategies import (
    USGlobalMarketSentinel,
    USSectorRotationHunter,
    USMomentumSurgeTracker,
    USAnomalyPatternSniper,
    USSmartMoneyFlowDetector,
)
from .strategy_manager import (
    AttentionStrategyManager,
    StrategyConfig,
    get_strategy_manager,
    initialize_attention_strategies
)
from .config import (
    StrategySettings,
    AttentionStrategyConfig,
    ConfigManager,
    get_config_manager
)
from .wrapper import (
    AttentionStrategyWrapper,
    wrap_attention_strategy,
    register_attention_strategies_to_manager,
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
    "AttentionStrategyBase",
    "Signal",
    "GlobalMarketSentinel",
    "SectorRotationHunter",
    "MomentumSurgeTracker",
    "AnomalyPatternSniper",
    "SmartMoneyFlowDetector",
    "USGlobalMarketSentinel",
    "USSectorRotationHunter",
    "USMomentumSurgeTracker",
    "USAnomalyPatternSniper",
    "USSmartMoneyFlowDetector",
    "AttentionStrategyManager",
    "StrategyConfig",
    "get_strategy_manager",
    "initialize_attention_strategies",
    "StrategySettings",
    "AttentionStrategyConfig",
    "ConfigManager",
    "get_config_manager",
    "setup_attention_strategies",
    "AttentionStrategyWrapper",
    "wrap_attention_strategy",
    "register_attention_strategies_to_manager",
    "PanicPeakDetector",
    "LiquidityCrisisTracker",
    "RecoveryConfirmationMonitor",
    "LiquidityRescueOrchestrator",
    "RescueSignal",
    "RescueSignalType",
    "LiquidityCrisisState",
]


def setup_attention_strategies():
    """快速设置注意力策略系统"""
    config_manager = get_config_manager()
    manager = initialize_attention_strategies()
    return manager
