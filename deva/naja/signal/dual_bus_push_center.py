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

        log.info("✅ 双总线推送中心初始化完成")
        
        # 立即设置总线订阅
        self._setup_bus_subscriptions()

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

        self._setup_hotspot_subscriptions()

    def _setup_hotspot_subscriptions(self):
        """设置热点变化和新闻订阅"""
        try:
            from deva.naja.events import get_event_bus

            event_bus = get_event_bus()

            def hotspot_shift_callback(event):
                try:
                    self._on_hotspot_shift_event(event)
                except Exception as e:
                    log.error(f"热点变化事件处理失败: {e}")

            event_bus.subscribe(
                'HotspotShiftEvent',
                hotspot_shift_callback,
                markets={'CN', 'US'},
                priority=5,
            )
            log.info("✅ HotspotShiftEvent 订阅成功")

            def text_focused_callback(event):
                try:
                    self._on_text_focused_event(event)
                except Exception as e:
                    log.error(f"新闻事件处理失败: {e}")

            event_bus.subscribe(
                'TextFocusedEvent',
                text_focused_callback,
                priority=1,
            )
            log.info("✅ TextFocusedEvent 订阅成功")

        except Exception as e:
            log.warning(f"热点/新闻订阅失败: {e}")

    def _on_cognitive_event(self, event):
        """处理认知事件"""
        with self._lock:
            self._stats["cognitive_events"] += 1
            self._stats["total_events"] += 1

        event_data = self._format_cognitive_event(event)
        self._push_event(event_data)

    def _on_hotspot_shift_event(self, event):
        """处理热点变化事件"""
        with self._lock:
            self._stats["cognitive_events"] += 1
            self._stats["total_events"] += 1

        event_data = self._format_hotspot_shift_event(event)
        self._push_event(event_data)

    def _on_text_focused_event(self, event):
        """处理新闻聚焦事件"""
        with self._lock:
            self._stats["cognitive_events"] += 1
            self._stats["total_events"] += 1

        event_data = self._format_text_focused_event(event)
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

    def _format_hotspot_shift_event(self, event) -> Dict:
        """格式化热点转移事件"""
        try:
            if hasattr(event, "__dataclass_fields__"):
                data = asdict(event)
            elif hasattr(event, "to_dict"):
                data = event.to_dict()
            else:
                data = {"raw": str(event)}

            event_type = getattr(event, "event_type", "") or "hotspot_shift"

            title = getattr(event, "title", "")
            content = getattr(event, "content", "")
            block = getattr(event, "block", "")
            symbol = getattr(event, "symbol", "")
            score = getattr(event, "score", 0.0)
            market_time = getattr(event, "market_time", "")
            old_value = getattr(event, "old_value", None)
            new_value = getattr(event, "new_value", None)

            change_str = ""
            if old_value is not None and new_value is not None:
                change_str = f"{old_value:.3f} → {new_value:.3f}"

            summary_parts = []
            if title:
                summary_parts.append(title)
            if block:
                summary_parts.append(f"板块: {block}")
            if symbol:
                summary_parts.append(f"个股: {symbol}")
            if change_str:
                summary_parts.append(change_str)
            summary = " | ".join(summary_parts) if summary_parts else content[:100]

            return {
                "bus_type": "hotspot",
                "event_type": f"🔥 {event_type}",
                "timestamp": getattr(event, "timestamp", time.time()),
                "importance": min(score / 5.0 + 0.3, 1.0) if score else 0.5,
                "confidence": score,
                "source": "market_hotspot",
                "symbol": symbol,
                "block": block,
                "summary": summary,
                "title": title,
                "content": content,
                "data": data,
            }
        except Exception as e:
            log.error(f"格式化热点转移事件失败: {e}")
            return {
                "bus_type": "hotspot",
                "event_type": "🔥 热点转移",
                "timestamp": time.time(),
                "importance": 0.5,
                "data": {"raw": str(event)},
            }

    def _format_text_focused_event(self, event) -> Dict:
        """格式化新闻聚焦事件"""
        try:
            if hasattr(event, "__dataclass_fields__"):
                data = asdict(event)
            elif hasattr(event, "to_dict"):
                data = event.to_dict()
            else:
                data = {"raw": str(event)}

            title = getattr(event, "title", "") or data.get("title", "")
            source = getattr(event, "source", "") or data.get("source", "unknown")
            importance_score = getattr(event, "importance_score", 0.5) or data.get("importance_score", 0.5)
            sentiment = getattr(event, "sentiment", 0.5) or data.get("sentiment", 0.5)
            stock_codes = getattr(event, "stock_codes", []) or data.get("stock_codes", [])
            topics = getattr(event, "topics", []) or data.get("topics", [])
            url = getattr(event, "url", "") or data.get("url", "")

            sentiment_str = "📈正面" if sentiment > 0.6 else ("📉负面" if sentiment < 0.4 else "➖中性")
            stock_str = ", ".join(stock_codes[:3]) if stock_codes else ""
            topic_str = " ".join([f"#{t}" for t in topics[:3]]) if topics else ""

            summary_parts = []
            if title:
                summary_parts.append(title)
            if stock_str:
                summary_parts.append(f"关联: {stock_str}")
            if topic_str:
                summary_parts.append(topic_str)

            summary = " | ".join(summary_parts) if summary_parts else ""

            return {
                "bus_type": "news",
                "event_type": f"📰 {source}",
                "timestamp": getattr(event, "timestamp", time.time()),
                "importance": importance_score,
                "confidence": importance_score,
                "source": source,
                "symbol": stock_codes[0] if stock_codes else None,
                "stock_codes": stock_codes,
                "summary": summary,
                "title": title,
                "sentiment": sentiment,
                "sentiment_str": sentiment_str,
                "topics": topics,
                "url": url,
                "data": data,
            }
        except Exception as e:
            log.error(f"格式化新闻事件失败: {e}")
            return {
                "bus_type": "news",
                "event_type": "📰 新闻",
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
        """获取最近的事件（按时间倒序，最新的在前）"""
        with self._lock:
            events = list(self._recent_events[-limit:])
            events.reverse()
            return events

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
