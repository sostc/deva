"""
SmartMoneyFlowDetector - 聪明资金流向

检测机构资金的建仓/出货行为
"""

import logging
from typing import Dict

from .base import AttentionStrategyBase, HotspotSignal

log = logging.getLogger(__name__)


class SmartMoneyFlowDetector(AttentionStrategyBase):
    """
    聪明资金流向策略

    通过权重变化检测机构资金动向
    """

    def __init__(
        self,
        market: str = 'US',
        min_weight_change: float = 0.5
    ):
        super().__init__(
            strategy_id='smart_money_flow_detector',
            name='SmartMoneyFlowDetector',
            market=market,
            min_global_hotspot=0.35,
            cooldown_period=600.0
        )

        self.min_weight_change = min_weight_change
        self.last_weights: Dict[str, float] = {}

    def _process_hotspot_event(self, event):
        """处理热点事件，检测聪明钱"""
        symbol_weights = event.symbol_weights

        for symbol, weight in symbol_weights.items():
            if not self._should_signal(symbol):
                continue

            last_weight = self.last_weights.get(symbol, weight)
            change = weight - last_weight

            if abs(change) >= self.min_weight_change:
                signal_type = 'buy' if change > 0 else 'sell'
                confidence = min(1.0, abs(change) / 2)

                signal = HotspotSignal(
                    strategy_id=self.strategy_id,
                    strategy_name=self.name,
                    symbol=symbol,
                    signal_type=signal_type,
                    confidence=confidence,
                    score=abs(change),
                    reason=f'聪明钱{"建仓" if change > 0 else "出货"}: change={change:.2f}',
                    timestamp=event.timestamp,
                    market=self.market,
                    metadata={
                        'last_weight': last_weight,
                        'current_weight': weight,
                        'change': change
                    }
                )
                self._emit_signal(signal)

            self.last_weights[symbol] = weight
