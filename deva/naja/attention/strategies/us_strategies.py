"""
US Market Strategies - 美股专用策略

美股市场特点：
- 权重数值较小（0.0001-0.01）vs A股（0.1-5.0）
- 波动较小，阈值需要调整
- 使用美股专用的过滤器
"""

from .base import AttentionStrategyBase, HotspotSignal
from .global_sentinel import GlobalMarketSentinel
from .block_rotation import BlockRotationHunter
from .momentum_tracker import MomentumSurgeTracker
from .anomaly_sniper import AnomalyPatternSniper
from .smart_money import SmartMoneyFlowDetector


class USMarketAdapter:
    """美股市场适配器 - 提供美股专用的上下文和方法"""

    def __init__(self, market: str = 'US'):
        self.market = market

    def get_us_hotspot_state(self) -> dict:
        """获取美股热点状态"""
        try:
            from deva.naja.events import get_event_bus
            event_bus = get_event_bus()
            event = event_bus.get_latest_event(market=self.market)
            if event:
                return {
                    'global_hotspot': event.global_hotspot,
                    'activity': event.activity,
                    'block_hotspot': event.block_hotspot,
                    'symbol_weights': event.symbol_weights,
                    'symbols': event.symbols,
                }
        except Exception:
            pass
        return {
            'global_hotspot': 0.5,
            'activity': 0.5,
            'block_hotspot': {},
            'symbol_weights': {},
            'symbols': [],
        }

    def get_symbol_weight(self, symbol: str) -> float:
        """获取个股权重"""
        state = self.get_us_hotspot_state()
        return state.get('symbol_weights', {}).get(symbol, 0.0)

    def get_active_blocks(self, threshold: float = 0.001) -> list:
        """获取活跃题材（美股阈值更低）"""
        state = self.get_us_hotspot_state()
        block_hotspot = state.get('block_hotspot', {})
        return [s for s, w in block_hotspot.items() if w >= threshold]

    def should_execute_us(
        self,
        global_hotspot: float = None,
        activity: float = None,
        last_execution_time: float = None,
        cooldown_period: float = 60.0
    ) -> bool:
        """
        美股策略执行判断

        美股数据稀疏时降低活跃度门槛
        """
        if activity is not None and activity < 0.05:
            return False

        if last_execution_time is not None:
            import time
            if time.time() - last_execution_time < cooldown_period:
                return False

        return True


class USGlobalMarketSentinel(GlobalMarketSentinel):
    """美股全局市场监控策略"""

    def __init__(self):
        super().__init__(market='US')
        self.strategy_id = 'us_global_sentinel'
        self.name = 'US Global Market Sentinel'

        self.volatility_threshold = 2.5
        self.panic_threshold = 4.0
        self.history_window = 20

        self.volatility_history = []

    def _process_hotspot_event(self, event):
        """处理热点事件，判断美股市场风险"""
        global_hotspot = event.global_hotspot
        activity = event.activity

        if global_hotspot >= 0.8:
            self.risk_level = 'Panic'
        elif global_hotspot >= 0.65:
            self.risk_level = 'Danger'
        elif global_hotspot >= 0.5:
            self.risk_level = 'Warning'
        elif global_hotspot >= 0.35:
            self.risk_level = 'Caution'
        else:
            self.risk_level = 'Normal'

        self.volatility_history.append(global_hotspot)
        if len(self.volatility_history) > self.history_window:
            self.volatility_history.pop(0)

        self.risk_history.append({
            'timestamp': event.timestamp,
            'global_hotspot': global_hotspot,
            'activity': activity,
            'risk_level': self.risk_level
        })


class USBlockRotationHunter(BlockRotationHunter):
    """美股题材轮动追踪"""

    def __init__(self):
        super().__init__(market='US')
        self.strategy_id = 'us_block_rotation_hunter'
        self.name = 'US Block Rotation Hunter'

        self.min_global_hotspot = 0.25
        self.min_hotspot_change = 0.15
        self.cooldown_period = 300.0


class USMomentumSurgeTracker(MomentumSurgeTracker):
    """美股动量突破追踪"""

    def __init__(self):
        super().__init__(
            market='US',
            min_symbol_weight=0.0002,
            momentum_threshold=0.001
        )
        self.strategy_id = 'us_momentum_surge_tracker'
        self.name = 'US Momentum Surge Tracker'

        self.price_threshold = 0.008
        self.volume_threshold = 1.3
        self.combined_threshold = 0.25
        self.min_global_hotspot = 0.3
        self.cooldown_period = 45.0


class USAnomalyPatternSniper(AnomalyPatternSniper):
    """美股异常模式狙击"""

    def __init__(self):
        super().__init__(
            market='US',
            anomaly_threshold=1.5
        )
        self.strategy_id = 'us_anomaly_pattern_sniper'
        self.name = 'US Anomaly Pattern Sniper'

        self.min_symbol_weight = 0.00025
        self.min_global_hotspot = 0.45
        self.cooldown_period = 90.0


class USSmartMoneyFlowDetector(SmartMoneyFlowDetector):
    """美股聪明资金流向检测"""

    def __init__(self):
        super().__init__(
            market='US',
            min_weight_change=0.001
        )
        self.strategy_id = 'us_smart_money_flow_detector'
        self.name = 'US Smart Money Flow Detector'

        self.large_order_threshold = 500000
        self.smart_money_imbalance_threshold = 0.55
        self.accumulation_threshold = 0.65
        self.distribution_threshold = -0.65
        self.min_symbol_weight = 0.0003
        self.min_global_hotspot = 0.28
        self.cooldown_period = 180.0


__all__ = [
    'USMarketAdapter',
    'USGlobalMarketSentinel',
    'USBlockRotationHunter',
    'USMomentumSurgeTracker',
    'USAnomalyPatternSniper',
    'USSmartMoneyFlowDetector',
]
