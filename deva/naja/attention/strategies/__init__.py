"""
Attention Strategies - 基于注意力的交易策略

这些策略订阅 HotspotComputedEvent，基于热点数据做交易决策

市场适配:
- A股策略: GlobalMarketSentinel, BlockRotationHunter, MomentumSurgeTracker, etc.
- 美股策略: USGlobalMarketSentinel, USBlockRotationHunter, USMomentumSurgeTracker, etc.
"""

from .base import (
    AttentionStrategyBase,
    HotspotSignal,
)
from .block_rotation import BlockRotationHunter
from .global_sentinel import GlobalMarketSentinel
from .momentum_tracker import MomentumSurgeTracker
from .anomaly_sniper import AnomalyPatternSniper
from .smart_money import SmartMoneyFlowDetector
from .liquidity_rescue import (
    LiquidityCrisisTracker,
    PanicPeakDetector,
    RecoveryConfirmationMonitor,
)
from .us_strategies import (
    USMarketAdapter,
    USGlobalMarketSentinel,
    USBlockRotationHunter,
    USMomentumSurgeTracker,
    USAnomalyPatternSniper,
    USSmartMoneyFlowDetector,
)

__all__ = [
    "AttentionStrategyBase",
    "HotspotSignal",
    "GlobalMarketSentinel",
    "BlockRotationHunter",
    "MomentumSurgeTracker",
    "AnomalyPatternSniper",
    "SmartMoneyFlowDetector",
    "LiquidityCrisisTracker",
    "PanicPeakDetector",
    "RecoveryConfirmationMonitor",
    "USMarketAdapter",
    "USGlobalMarketSentinel",
    "USBlockRotationHunter",
    "USMomentumSurgeTracker",
    "USAnomalyPatternSniper",
    "USSmartMoneyFlowDetector",
]
