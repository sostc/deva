"""MarketNode - 市场节点

跟踪单个市场的状态变化，包括：
- 价格变动
- 波动率
- 成交量异常
- 叙事匹配度
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class MarketState:
    """市场瞬时状态"""
    market_id: str
    timestamp: float

    price_change: float = 0.0
    volume_ratio: float = 1.0
    volatility: float = 0.0

    attention_score: float = 0.0
    narrative_match_score: float = 0.0

    price_history: List[float] = field(default_factory=list)
    volume_history: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_id": self.market_id,
            "timestamp": self.timestamp,
            "price_change": self.price_change,
            "volume_ratio": self.volume_ratio,
            "volatility": self.volatility,
            "attention_score": self.attention_score,
            "narrative_match_score": self.narrative_match_score,
        }


class MarketNode:
    """市场节点

    跟踪单个市场的状态变化，并计算变化强度。
    变化强度用于决定是否向其他市场传播注意力。
    """

    def __init__(
        self,
        market_id: str,
        name: str,
        market_type: str,
        volatility_window: int = 10,
        attention_threshold: float = 0.3,
    ):
        self.market_id = market_id
        self.name = name
        self.market_type = market_type

        self._volatility_window = volatility_window
        self._attention_threshold = attention_threshold

        self._price_history: List[float] = []
        self._volume_history: List[float] = []
        self._change_history: List[float] = []

        self._last_state: Optional[MarketState] = None
        self._current_state: Optional[MarketState] = None

        self._change_count: int = 0
        self._last_change_ts: float = 0

        self._attention_score: float = 0.0
        self._narrative_match_score: float = 0.0

    def update(
        self,
        price: float,
        volume: float = 0,
        timestamp: float = None,
        narrative_score: float = 0.0,
    ) -> Optional[MarketState]:
        """更新市场状态"""
        if timestamp is None:
            timestamp = time.time()

        if price <= 0:
            return None

        self._price_history.append(price)
        if len(self._price_history) > 100:
            self._price_history.pop(0)

        if volume > 0:
            self._volume_history.append(volume)
            if len(self._volume_history) > 100:
                self._volume_history.pop(0)

        prev_price = self._price_history[-2] if len(self._price_history) >= 2 else price
        price_change = ((price - prev_price) / prev_price) * 100 if prev_price > 0 else 0.0

        self._change_history.append(abs(price_change))
        if len(self._change_history) > self._volatility_window:
            self._change_history.pop(0)

        volatility = self._calculate_volatility()

        avg_volume = sum(self._volume_history[-10:]) / len(self._volume_history[-10:]) if self._volume_history else 1
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

        self._current_state = MarketState(
            market_id=self.market_id,
            timestamp=timestamp,
            price_change=price_change,
            volume_ratio=volume_ratio,
            volatility=volatility,
            attention_score=self._attention_score,
            narrative_match_score=narrative_score,
            price_history=self._price_history.copy(),
            volume_history=self._volume_history.copy(),
        )

        self._update_attention_score(price_change, volatility, volume_ratio)

        if self._is_significant_change(price_change, volatility):
            self._last_state = self._current_state
            self._last_change_ts = timestamp
            self._change_count += 1

        return self._current_state

    def _calculate_volatility(self) -> float:
        """计算波动率"""
        if len(self._change_history) < 2:
            return 0.0

        import numpy as np
        try:
            changes = np.array(self._change_history)
            return float(np.std(changes))
        except Exception:
            return 0.0

    def _update_attention_score(
        self,
        price_change: float,
        volatility: float,
        volume_ratio: float,
    ):
        """更新注意力分数"""
        change_factor = min(1.0, abs(price_change) / 5.0)

        volatility_factor = min(1.0, volatility / 2.0)

        volume_factor = min(1.0, (volume_ratio - 1.0) / 2.0) if volume_ratio > 1 else 0

        self._attention_score = (
            change_factor * 0.4 +
            volatility_factor * 0.3 +
            volume_factor * 0.3
        ) * (1 + self._narrative_match_score)

        self._attention_score = min(1.0, self._attention_score)

    def _is_significant_change(self, price_change: float, volatility: float) -> bool:
        """判断是否有显著变化"""
        if abs(price_change) < 0.5:
            return False
        if volatility > 1.5:
            return True
        if abs(price_change) > 1.0:
            return True
        return abs(price_change) > 2 * volatility

    def update_narrative_score(self, narrative_score: float):
        """更新叙事匹配分数"""
        self._narrative_match_score = narrative_score
        if self._current_state:
            self._current_state.narrative_match_score = narrative_score

    def is_active(self, threshold: float = None) -> bool:
        """判断市场是否活跃"""
        if threshold is None:
            threshold = self._attention_threshold
        return self._attention_score >= threshold

    def get_attention_level(self) -> str:
        """获取注意力级别"""
        if self._attention_score >= 0.8:
            return "critical"
        elif self._attention_score >= 0.6:
            return "high"
        elif self._attention_score >= 0.4:
            return "medium"
        elif self._attention_score >= 0.2:
            return "low"
        return "dormant"

    def decay_attention(self, decay_rate: float = 0.95):
        """衰减注意力分数"""
        self._attention_score *= decay_rate
        self._attention_score = max(0.0, self._attention_score)

        if self._narrative_match_score > 0:
            self._narrative_match_score *= decay_rate

    def get_state(self) -> Optional[MarketState]:
        """获取当前状态"""
        return self._current_state

    def get_change_intensity(self) -> float:
        """获取变化强度 (0-1)"""
        return min(1.0, self._attention_score)

    def get_info(self) -> Dict[str, Any]:
        """获取节点信息"""
        return {
            "market_id": self.market_id,
            "name": self.name,
            "market_type": self.market_type,
            "attention_score": round(self._attention_score, 3),
            "attention_level": self.get_attention_level(),
            "narrative_match_score": round(self._narrative_match_score, 3),
            "change_count": self._change_count,
            "last_change_ts": self._last_change_ts,
            "is_active": self.is_active(),
            "current_state": self._current_state.to_dict() if self._current_state else None,
        }
