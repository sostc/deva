"""InfluenceEdge - 市场间影响边

表示两个市场之间的影响关系：
- 源市场变化时，预测目标市场的变化方向
- 验证传播是否成功
- 动态调整边权重（成功增强，失败衰减）
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class PropagationEvent:
    """传播事件"""
    from_market: str
    to_market: str
    timestamp: float
    predicted_direction: str
    predicted_strength: float
    source_change: float

    actual_change: Optional[float] = None
    verified: bool = False
    verification_timestamp: Optional[float] = None


@dataclass
class InfluenceEdgeState:
    """影响边状态"""
    from_market: str
    to_market: str

    base_strength: float = 0.7
    current_weight: float = 0.7
    confidence: float = 0.5

    success_count: int = 0
    failure_count: int = 0
    total_propagations: int = 0

    delay_hours: float = 0

    last_propagation_ts: float = 0
    last_verification_ts: float = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_market": self.from_market,
            "to_market": self.to_market,
            "base_strength": self.base_strength,
            "current_weight": round(self.current_weight, 3),
            "confidence": round(self.confidence, 3),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_propagations": self.total_propagations,
            "delay_hours": self.delay_hours,
            "propagation_rate": round(self.success_count / max(1, self.total_propagations), 2),
        }


class InfluenceEdge:
    """市场间影响边

    跟踪两个市场之间的影响关系：
    1. 记录传播事件
    2. 验证传播是否成功
    3. 动态调整权重
    """

    def __init__(
        self,
        from_market: str,
        to_market: str,
        base_strength: float = 0.7,
        delay_hours: float = 0,
    ):
        self.from_market = from_market
        self.to_market = to_market

        self._base_strength = base_strength
        self._current_weight = base_strength

        self._delay_seconds = delay_hours * 3600

        self._success_count = 0
        self._failure_count = 0
        self._total_propagations = 0

        self._pending_events: List[PropagationEvent] = []
        self._verified_events: List[PropagationEvent] = []

        self._last_propagation_ts: float = 0
        self._last_verification_ts: float = 0
        self._confidence: float = 0.5

        self._decay_rate = 0.98

    def propagate(
        self,
        source_change: float,
        timestamp: float = None,
    ) -> PropagationEvent:
        """发起一次传播"""
        if timestamp is None:
            timestamp = time.time()

        direction = "up" if source_change > 0 else "down" if source_change < 0 else "flat"

        strength = min(1.0, abs(source_change) / 3.0) * self._current_weight

        event = PropagationEvent(
            from_market=self.from_market,
            to_market=self.to_market,
            timestamp=timestamp,
            predicted_direction=direction,
            predicted_strength=strength,
            source_change=source_change,
        )

        self._pending_events.append(event)
        self._total_propagations += 1
        self._last_propagation_ts = timestamp

        return event

    def verify(
        self,
        target_change: float,
        timestamp: float = None,
    ) -> Optional[PropagationEvent]:
        """验证传播是否成功"""
        if timestamp is None:
            timestamp = time.time()

        if not self._pending_events:
            return None

        event = self._pending_events.pop(0)

        event.actual_change = target_change
        event.verification_timestamp = timestamp
        event.verified = self._check_verification(event)

        self._verified_events.append(event)
        if len(self._verified_events) > 50:
            self._verified_events.pop(0)

        self._last_verification_ts = timestamp

        if event.verified:
            self._success_count += 1
            self._boost_weight()
        else:
            self._failure_count += 1
            self._decay_weight()

        self._update_confidence()

        return event

    def _check_verification(self, event: PropagationEvent) -> bool:
        """检查传播是否成功"""
        if event.actual_change is None:
            return False

        source_dir = 1 if event.source_change > 0 else -1 if event.source_change < 0 else 0
        target_dir = 1 if event.actual_change > 0 else -1 if event.actual_change < 0 else 0

        direction_match = source_dir == target_dir

        strength_ratio = abs(event.actual_change) / max(0.1, abs(event.source_change))
        strength_reasonable = 0.1 < strength_ratio < 3.0

        return direction_match and strength_reasonable

    def _boost_weight(self):
        """增强边权重（传播成功）"""
        boost = 0.1 * (1 - self._current_weight)
        self._current_weight = min(1.0, self._current_weight + boost)

    def _decay_weight(self):
        """衰减边权重（传播失败）"""
        decay = 0.15 * self._current_weight
        self._current_weight = max(0.1, self._current_weight - decay)

    def natural_decay(self, rate: float = None):
        """自然衰减"""
        if rate is None:
            rate = self._decay_rate
        self._current_weight = max(self._base_strength * 0.5, self._current_weight * rate)

    def _update_confidence(self):
        """更新置信度"""
        total = self._success_count + self._failure_count
        if total == 0:
            self._confidence = 0.5
        else:
            self._confidence = self._success_count / total

    def get_weight(self) -> float:
        """获取当前权重"""
        return self._current_weight

    def get_confidence(self) -> float:
        """获取置信度"""
        return self._confidence

    def get_propagation_probability(self) -> float:
        """获取传播概率"""
        return self._current_weight * self._confidence

    def get_state(self) -> InfluenceEdgeState:
        """获取边状态"""
        return InfluenceEdgeState(
            from_market=self.from_market,
            to_market=self.to_market,
            base_strength=self._base_strength,
            current_weight=self._current_weight,
            confidence=self._confidence,
            success_count=self._success_count,
            failure_count=self._failure_count,
            total_propagations=self._total_propagations,
            delay_hours=self._delay_seconds / 3600,
            last_propagation_ts=self._last_propagation_ts,
            last_verification_ts=self._last_verification_ts,
        )

    def get_pending_events(self) -> List[PropagationEvent]:
        """获取待验证的传播事件"""
        return self._pending_events.copy()

    def cleanup_expired_events(self, max_age_seconds: float = 86400):
        """清理过期的事件"""
        now = time.time()
        self._pending_events = [
            e for e in self._pending_events
            if now - e.timestamp < max_age_seconds
        ]
        self._verified_events = [
            e for e in self._verified_events
            if now - e.verification_timestamp < max_age_seconds * 2
        ]

    def get_info(self) -> Dict[str, Any]:
        """获取边信息"""
        return {
            "from_market": self.from_market,
            "to_market": self.to_market,
            "current_weight": round(self._current_weight, 3),
            "base_strength": self._base_strength,
            "confidence": round(self._confidence, 3),
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "total_propagations": self._total_propagations,
            "propagation_rate": round(self._success_count / max(1, self._total_propagations), 2),
            "pending_events": len(self._pending_events),
            "delay_hours": round(self._delay_seconds / 3600, 1),
        }
