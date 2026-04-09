"""
MomentumSurgeTracker - 动量突破追踪

追踪高热点股票的动量突破
"""

import logging
from typing import Dict

from .base import AttentionStrategyBase, HotspotSignal

log = logging.getLogger(__name__)


class MomentumSurgeTracker(AttentionStrategyBase):
    """
    动量突破追踪策略

    在高热点股票中追踪动量突破
    """

    def __init__(
        self,
        market: str = 'US',
        min_symbol_weight: float = 2.0,
        momentum_threshold: float = 0.03
    ):
        super().__init__(
            strategy_id='momentum_surge_tracker',
            name='MomentumSurgeTracker',
            market=market,
            min_global_hotspot=0.4,
            min_symbol_weight=min_symbol_weight,
            cooldown_period=300.0
        )

        self.momentum_threshold = momentum_threshold
        self.symbol_momentum: Dict[str, float] = {}

    def _process_hotspot_event(self, event):
        """处理热点事件，检测动量突破"""
        symbol_weights = event.symbol_weights

        for symbol, weight in symbol_weights.items():
            if weight < self.min_symbol_weight:
                continue

            if not self._should_signal(symbol):
                continue

            momentum = self._calculate_momentum(symbol, weight)

            if momentum > self.momentum_threshold:
                signal = HotspotSignal(
                    strategy_id=self.strategy_id,
                    strategy_name=self.name,
                    symbol=symbol,
                    signal_type='buy',
                    confidence=min(1.0, momentum * 3),
                    score=weight * momentum,
                    reason=f'动量突破: momentum={momentum:.3f}, weight={weight:.2f}',
                    timestamp=event.timestamp,
                    market=self.market,
                    metadata={
                        'weight': weight,
                        'momentum': momentum,
                        'global_hotspot': event.global_hotspot
                    }
                )
                self._emit_signal(signal)

    def _calculate_momentum(self, symbol: str, current_weight: float) -> float:
        """计算动量（简化版：使用权重变化率）"""
        last_weight = self.symbol_momentum.get(symbol, current_weight)
        self.symbol_momentum[symbol] = current_weight
        return current_weight - last_weight
