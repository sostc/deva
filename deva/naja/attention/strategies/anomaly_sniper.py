"""
AnomalyPatternSniper - 异常模式狙击

检测统计异常和深度学习模式识别
"""

import logging
from typing import Dict, List

from .base import AttentionStrategyBase, HotspotSignal

log = logging.getLogger(__name__)


class AnomalyPatternSniper(AttentionStrategyBase):
    """
    异常模式狙击策略

    检测价格/成交量的异常模式
    """

    def __init__(
        self,
        market: str = 'US',
        anomaly_threshold: float = 2.0
    ):
        super().__init__(
            strategy_id='anomaly_pattern_sniper',
            name='AnomalyPatternSniper',
            market=market,
            min_global_hotspot=0.5,
            cooldown_period=600.0
        )

        self.anomaly_threshold = anomaly_threshold
        self.symbol_anomaly_score: Dict[str, List[float]] = {}

    def _process_hotspot_event(self, event):
        """处理热点事件，检测异常模式"""
        symbol_weights = event.symbol_weights

        for symbol, weight in symbol_weights.items():
            if not self._should_signal(symbol):
                continue

            anomaly_score = self._detect_anomaly(symbol, weight)

            if anomaly_score > self.anomaly_threshold:
                signal = HotspotSignal(
                    strategy_id=self.strategy_id,
                    strategy_name=self.name,
                    symbol=symbol,
                    signal_type='watch',
                    confidence=min(1.0, anomaly_score / 3),
                    score=anomaly_score,
                    reason=f'异常模式检测: score={anomaly_score:.2f}',
                    timestamp=event.timestamp,
                    market=self.market,
                    metadata={
                        'weight': weight,
                        'anomaly_score': anomaly_score
                    }
                )
                self._emit_signal(signal)

    def _detect_anomaly(self, symbol: str, current_weight: float) -> float:
        """检测异常（简化版：使用权重突变）"""
        if symbol not in self.symbol_anomaly_score:
            self.symbol_anomaly_score[symbol] = []

        history = self.symbol_anomaly_score[symbol]
        history.append(current_weight)

        if len(history) < 3:
            return 0.0

        if len(history) > 10:
            history.pop(0)

        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / len(history)
        std = variance ** 0.5

        if std == 0:
            return 0.0

        return abs(current_weight - mean) / std
