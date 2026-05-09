"""
双总线推送中心 - 整合认知总线和交易总线的事件推送

提供统一的事件订阅和推送接口
"""

import logging
import time
import threading
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Callable
from collections import defaultdict

log = logging.getLogger(__name__)


class DualBusPushCenter:
    """双总线推送中心"""

    def __init__(self):
        self._lock = threading.RLock()
        self._subscribers: List[Callable] = []
        self._recent_events: List[Dict] = []
        self._max_recent_events = 50

        # 统计信息
        self._stats = {
            "cognitive_events": 0,
            "trading_events": 0,
            "total_events": 0,
        }

        # 订阅总线回调
        self._setup_bus_subscriptions()

        log.info("✅ 双总线推送中心初始化完成")

    def _setup_bus_subscriptions(self):
        """设置总线订阅"""
        try:
            # 订阅认知总线
            from deva.naja.events import get_cognitive_bus

            cognitive_bus = get_cognitive_bus()

            # 订阅所有认知事件类型
            def cognitive_callback(event):
                try:
                    self._on_cognitive_event(event)
                except Exception as e:
                    log.error(f"认知事件处理失败: {e}")

            # 订阅 CognitiveEventType 枚举类型
            from deva.naja.events import CognitiveEventType

            for event_type in CognitiveEventType:
                try:
                    cognitive_bus.subscribe_cognitive(
                        module_name=f"dual_bus_ui_{event_type.value}",
                        callback=cognitive_callback,
                        event_types=[event_type],
                        min_importance=0.0,
                    )
                except Exception as e:
                    log.debug(f"订阅认知事件类型 {event_type} 失败: {e}")

            log.info("✅ 认知总线订阅成功")

        except Exception as e:
            log.warning(f"认知总线订阅失败: {e}")

        try:
            # 订阅交易总线
            from deva.naja.events import get_trading_bus

            trading_bus = get_trading_bus()

            def trading_callback(event):
                try:
                    self._on_trading_event(event)
                except Exception as e:
                    log.error(f"交易事件处理失败: {e}")

            # 订阅常见的交易事件类型
            for event_type in ["StrategySignalEvent", "TradeDecisionEvent"]:
                try:
                    trading_bus.subscribe(
                        event_type=event_type,
                        callback=trading_callback,
                        subscription_id=f"dual_bus_ui_{event_type}",
                    )
                except Exception as e:
                    log.debug(f"订阅交易事件类型 {event_type} 失败: {e}")

            log.info("✅ 交易总线订阅成功")

        except Exception as e:
            log.warning(f"交易总线订阅失败: {e}")

    def _on_cognitive_event(self, event):
        """处理认知事件"""
        with self._lock:
            self._stats["cognitive_events"] += 1
            self._stats["total_events"] += 1

        event_data = self._format_cognitive_event(event)
        self._push_event(event_data)

    def _on_trading_event(self, event):
        """处理交易事件"""
        with self._lock:
            self._stats["trading_events"] += 1
            self._stats["total_events"] += 1

        event_data = self._format_trading_event(event)
        self._push_event(event_data)

    def _format_cognitive_event(self, event) -> Dict:
        """格式化认知事件"""
        try:
            # 检查是否是 dataclass 实例
            if hasattr(event, "__dataclass_fields__"):
                data = asdict(event)
            elif hasattr(event, "to_dict"):
                data = event.to_dict()
            elif isinstance(event, dict):
                data = event
            else:
                data = {"raw": str(event)}

            event_type = getattr(event, "event_type", None)
            if hasattr(event_type, "value"):
                event_type = event_type.value

            summary = ""
            if hasattr(event, "narratives") and event.narratives:
                summary = " | ".join(event.narratives[:3])
            elif hasattr(event, "metadata") and event.metadata:
                summary = str(event.metadata)

            return {
                "bus_type": "cognitive",
                "event_type": event_type or "CognitiveEvent",
                "timestamp": getattr(event, "timestamp", time.time()),
                "importance": getattr(event, "importance", 0.5),
                "confidence": getattr(event, "confidence", 0.5),
                "source": getattr(event, "source", "unknown"),
                "symbol": getattr(event, "symbol", None)
                or (data.get("stock_codes", [None])[0] if data.get("stock_codes") else None),
                "summary": summary,
                "data": data,
            }
        except Exception as e:
            log.error(f"格式化认知事件失败: {e}")
            return {
                "bus_type": "cognitive",
                "event_type": "CognitiveEvent",
                "timestamp": time.time(),
                "importance": 0.5,
                "data": {"raw": str(event)},
            }

    def _format_trading_event(self, event) -> Dict:
        """格式化交易事件"""
        try:
            if hasattr(event, "__dataclass_fields__"):
                data = asdict(event)
            elif hasattr(event, "to_dict"):
                data = event.to_dict()
            elif isinstance(event, dict):
                data = event
            else:
                data = {"raw": str(event)}

            event_type = type(event).__name__ if hasattr(event, "__class__") else "TradingEvent"

            summary = ""
            symbol = getattr(event, "symbol", data.get("symbol"))
            direction = getattr(event, "direction", data.get("direction"))
            if symbol and direction:
                summary = f"{symbol} {direction}"
            elif hasattr(event, "decision"):
                summary = f"决策: {event.decision}"

            return {
                "bus_type": "trading",
                "event_type": event_type,
                "timestamp": getattr(event, "timestamp", time.time()),
                "importance": getattr(event, "importance", 0.5),
                "confidence": getattr(event, "confidence", data.get("confidence", 0.5)),
                "symbol": symbol,
                "direction": direction,
                "strategy_name": getattr(event, "strategy_name", data.get("strategy_name")),
                "summary": summary,
                "data": data,
            }
        except Exception as e:
            log.error(f"格式化交易事件失败: {e}")
            return {
                "bus_type": "trading",
                "event_type": "TradingEvent",
                "timestamp": time.time(),
                "importance": 0.5,
                "data": {"raw": str(event)},
            }

    def _push_event(self, event_data: Dict):
        """推送事件给所有订阅者"""
        with self._lock:
            self._recent_events.append(event_data)
            if len(self._recent_events) > self._max_recent_events:
                self._recent_events.pop(0)

            subscribers = list(self._subscribers)

        for callback in subscribers:
            try:
                callback(event_data)
            except Exception as e:
                log.error(f"推送事件失败: {e}")

    def subscribe(self, callback: Callable):
        """订阅事件推送"""
        with self._lock:
            self._subscribers.append(callback)
        log.debug(f"新订阅者加入，当前共 {len(self._subscribers)} 个订阅者")

    def unsubscribe(self, callback: Callable):
        """取消订阅"""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
        log.debug(f"订阅者离开，当前共 {len(self._subscribers)} 个订阅者")

    def get_recent_events(self, limit: int = 20) -> List[Dict]:
        """获取最近的事件"""
        with self._lock:
            return list(self._recent_events[-limit:])

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            return dict(self._stats)


# 单例
_push_center: Optional[DualBusPushCenter] = None
_push_center_lock = threading.Lock()


def get_dual_bus_push_center() -> DualBusPushCenter:
    """获取双总线推送中心单例"""
    global _push_center
    if _push_center is None:
        with _push_center_lock:
            if _push_center is None:
                _push_center = DualBusPushCenter()
    return _push_center


def reset_dual_bus_push_center():
    """重置推送中心（测试用）"""
    global _push_center
    with _push_center_lock:
        _push_center = None
