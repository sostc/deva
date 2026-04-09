"""
Attention Strategy Base - 注意力策略基类

基于热点事件的策略基类，订阅 HotspotComputedEvent 做交易决策
"""

import sys
import time
import logging
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from collections import deque

log = logging.getLogger(__name__)


@dataclass
class HotspotSignal:
    """交易信号"""
    strategy_id: str
    strategy_name: str
    symbol: str
    signal_type: str  # 'buy' | 'sell' | 'hold' | 'watch'
    confidence: float  # 0.0 - 1.0
    score: float
    reason: str
    timestamp: float
    market: str = 'US'
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'strategy_id': self.strategy_id,
            'strategy': self.strategy_name,
            'symbol': self.symbol,
            'type': self.signal_type,
            'confidence': self.confidence,
            'score': self.score,
            'reason': self.reason,
            'timestamp': self.timestamp,
            'market': self.market,
            'metadata': self.metadata
        }


class AttentionStrategyBase(ABC):
    """
    注意力策略基类

    基于 HotspotComputedEvent 事件驱动执行
    """

    def __init__(
        self,
        strategy_id: str,
        name: str,
        market: str = 'US',
        min_global_hotspot: float = 0.0,
        min_symbol_weight: float = 1.0,
        cooldown_period: float = 60.0
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.market = market

        self.min_global_hotspot = min_global_hotspot
        self.min_symbol_weight = min_symbol_weight
        self.cooldown_period = cooldown_period

        self.is_active = False
        self.last_execution_time = 0.0

        self.signals: deque = deque(maxlen=100)
        self.last_signal_time: Dict[str, float] = {}

        self._event_subscription = None

    def subscribe_to_events(self):
        """订阅热点事件"""
        try:
            from deva.naja.events import get_event_bus
            event_bus = get_event_bus()
            event_bus.subscribe(
                'HotspotComputedEvent',
                self._on_hotspot_event,
                markets={self.market},
                priority=20
            )
            log.info(f"[{self.name}] 已订阅热点事件, market={self.market}")
        except Exception as e:
            log.error(f"[{self.name}] 订阅热点事件失败: {e}")

    def unsubscribe_from_events(self):
        """取消订阅"""
        if self._event_subscription:
            try:
                from deva.naja.events import get_event_bus
                event_bus = get_event_bus()
                event_bus.unsubscribe('HotspotComputedEvent', self._on_hotspot_event)
            except Exception:
                pass

    def _on_hotspot_event(self, event):
        """处理热点事件"""
        try:
            if event.global_hotspot < self.min_global_hotspot:
                log.debug(f"[{self.name}] 全局热点 {event.global_hotspot:.3f} < 阈值 {self.min_global_hotspot}, 跳过")
                return

            self._process_hotspot_event(event)
        except Exception as e:
            log.error(f"[{self.name}] 处理热点事件失败: {e}")

    @abstractmethod
    def _process_hotspot_event(self, event):
        """处理热点事件，子类实现具体逻辑"""
        pass

    def _should_signal(self, symbol: str) -> bool:
        """检查是否应该发送信号（冷却期控制）"""
        current_time = time.time()
        last_time = self.last_signal_time.get(symbol, 0)
        if current_time - last_time < self.cooldown_period:
            return False
        return True

    def _emit_signal(self, signal: HotspotSignal):
        """发送信号"""
        signal.timestamp = time.time()
        self.signals.append(signal)
        self.last_signal_time[signal.symbol] = signal.timestamp
        log.debug(f"[{self.name}] 信号: {signal.signal_type} {signal.symbol}, confidence={signal.confidence:.2f}")

    def get_recent_signals(self, n: int = 20) -> List[Dict]:
        """获取最近的信号"""
        signals = list(self.signals)[-n:]
        return [s.to_dict() for s in signals]

    def get_signals_by_symbol(self, symbol: str) -> List[Dict]:
        """获取特定股票的所有信号"""
        return [s.to_dict() for s in self.signals if s.symbol == symbol]
