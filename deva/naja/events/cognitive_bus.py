"""
NajaEventBus - Naja 统一事件总线

合并了原事件分发和认知信号事件功能。系统中所有事件通信统一经由此总线。
系统中所有事件通信统一经由此总线。

📡 两种事件通道：
  1. Dataclass 事件（按类名字符串路由）：TextFetchedEvent / HotspotComputedEvent 等
     - 支持 market 字段过滤、priority 优先级、事件缓存
  2. 认知信号事件（按 CognitiveEventType 枚举路由）：叙事/共振/风险等
     - 支持去重窗口、重要性阈值、模块启用/禁用

使用方式：
    from deva.naja.events import get_event_bus

    # dataclass 事件
    bus = get_event_bus()
    bus.publish(TextFetchedEvent(...))
    bus.subscribe('TextFetchedEvent', callback, markets={'US'}, priority=10)

    # 认知信号事件
    bus.publish_cognitive_event(source="...", event_type=CognitiveEventType.XXX, ...)
    bus.subscribe_cognitive("ManasEngine", callback, event_types=[...])
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Set

log = logging.getLogger(__name__)


# ============== 认知事件类型枚举 ==============

class CognitiveEventType(Enum):
    """认知事件类型"""
    # 地 - BlockNarrative 叙事更新
    BLOCK_NARRATIVE_UPDATE = "block_narrative_update"
    NARRATIVE_BOOST = "narrative_boost"
    NARRATIVE_DECAY = "narrative_decay"

    # 天 - TimingNarrative 时机更新
    TIMING_NARRATIVE_UPDATE = "timing_narrative_update"
    TIMING_NARRATIVE_SHIFT = "timing_narrative_shift"

    # 🔥 共振分析（CrossSignalAnalyzer）
    RESONANCE_DETECTED = "resonance_detected"
    RESONANCE_DECAY = "resonance_decay"

    # 供应链风险
    SUPPLY_CHAIN_RISK = "supply_chain_risk"
    SUPPLY_CHAIN_IMPACT = "supply_chain_impact"
    NARRATIVE_SUPPLY_LINK = "narrative_supply_link"

    # 🚀 全球市场事件（给 LiquidityCognition）
    GLOBAL_MARKET_EVENT = "global_market_event"

    # 组合级信号
    PORTFOLIO_SIGNAL = "portfolio_signal"
    RISK_ALERT = "risk_alert"

    # 通用
    COGNITION_RESET = "cognition_reset"

    # ── 原 CognitionEventType ──
    HOTSPOT_SNAPSHOT = "hotspot_snapshot"
    NEWS_SIGNAL = "news_signal"
    INSIGHT_GENERATED = "insight_generated"
    COGNITION_FEEDBACK = "cognition_feedback"
    NARRATIVE_UPDATE = "narrative_update"
    SEMANTIC_GRAPH_UPDATE = "semantic_graph_update"


# ============== 数据类 ==============

@dataclass
class CognitiveSignalEvent:
    """认知信号事件 — 代表认知层内部模块的重要状态变化"""
    source: str
    event_type: CognitiveEventType
    timestamp: float = field(default_factory=time.time)
    narratives: List[str] = field(default_factory=list)
    importance: float = 0.5
    confidence: float = 0.5
    stock_codes: List[str] = field(default_factory=list)
    risk_level: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"CognitiveSignalEvent(source={self.source}, "
            f"type={self.event_type.value}, "
            f"narratives={self.narratives[:2]}{'...' if len(self.narratives) > 2 else ''}, "
            f"importance={self.importance:.2f})"
        )


@dataclass
class CognitiveSubscriber:
    """认知事件订阅者"""
    module_name: str
    callback: Callable[[CognitiveSignalEvent], None]
    event_types: List[CognitiveEventType] = field(default_factory=list)
    min_importance: float = 0.3
    enabled: bool = True


@dataclass
class EventSubscription:
    """Dataclass 事件订阅记录（原 NajaEventBus 接口）"""
    callback: Callable
    event_type: str
    markets: Set[str] = field(default_factory=set)
    priority: int = 0


@dataclass
class CognitiveBusStats:
    """总线统计"""
    total_published: int = 0
    total_delivered: int = 0
    by_module: Dict[str, int] = field(default_factory=dict)
    by_event_type: Dict[str, int] = field(default_factory=dict)
    dropped: int = 0


# ============== 统一事件总线 ==============

class NajaEventBus:
    """
    Naja 统一事件总线

    同时支持：
    - dataclass 事件 publish/subscribe（按类名字符串路由）
    - 认知信号事件 publish_cognitive_event/subscribe_cognitive（按枚举路由）
    """

    def __init__(self):
        self._lock = threading.Lock()

        # ── 认知信号通道 ──
        self._cognitive_subscribers: Dict[str, List[CognitiveSubscriber]] = defaultdict(list)
        self._event_type_modules: Dict[CognitiveEventType, Set[str]] = defaultdict(set)
        self._module_names: Set[str] = set()
        self._recent_events: List[CognitiveSignalEvent] = []
        self._dedup_window = 30.0

        # ── Dataclass 事件通道（原 NajaEventBus） ──
        self._dc_subscriptions: Dict[str, List[EventSubscription]] = defaultdict(list)
        self._dc_cache_max = 100
        self._dc_event_cache: Dict[str, Any] = {}
        self._dc_event_history: Dict[str, Deque[Any]] = defaultdict(
            lambda: deque(maxlen=self._dc_cache_max)
        )

        # ── 统计 ──
        self._stats = CognitiveBusStats()

        log.info("[NajaEventBus] 统一事件总线初始化完成")

    # ================================================================
    #  Dataclass 事件接口（兼容原 NajaEventBus）
    # ================================================================

    def subscribe(
        self,
        event_type_or_module: str,
        callback: Callable,
        event_types: Optional[List[CognitiveEventType]] = None,
        min_importance: float = 0.3,
        markets: Optional[Set[str]] = None,
        priority: int = 0,
    ):
        """
        统一订阅入口 — 自动识别调用方式

        用法 A（dataclass 事件，原 NajaEventBus 接口）：
            bus.subscribe('HotspotComputedEvent', callback, markets={'US','CN'}, priority=10)

        用法 B（认知信号事件）：
            bus.subscribe("ManasEngine", callback, event_types=[...], min_importance=0.3)
        """
        if event_types is not None:
            # 用法 B：认知信号订阅
            return self.subscribe_cognitive(
                module_name=event_type_or_module,
                callback=callback,
                event_types=event_types,
                min_importance=min_importance,
            )
        else:
            # 用法 A：dataclass 事件订阅
            return self._subscribe_dataclass(
                event_type=event_type_or_module,
                callback=callback,
                markets=markets,
                priority=priority,
            )

    def _subscribe_dataclass(
        self,
        event_type: str,
        callback: Callable,
        markets: Optional[Set[str]] = None,
        priority: int = 0,
    ) -> None:
        """订阅 dataclass 事件"""
        sub = EventSubscription(
            callback=callback,
            event_type=event_type,
            markets=markets or set(),
            priority=priority,
        )
        with self._lock:
            self._dc_subscriptions[event_type].append(sub)
            self._dc_subscriptions[event_type].sort(key=lambda x: x.priority, reverse=True)

        log.debug(
            f"[NajaEventBus] 订阅成功: type={event_type}, "
            f"priority={priority}, markets={markets or 'all'}"
        )

    def publish(self, event) -> int:
        """
        发布事件 — 自动识别事件类型

        - CognitiveSignalEvent → 走认知信号通道
        - 其他 dataclass → 走 dataclass 通道（按类名字符串路由）

        Returns:
            成功分发给多少个订阅者（dataclass 通道返回 int，认知通道返回 dict）
        """
        if isinstance(event, CognitiveSignalEvent):
            result = self._publish_cognitive(event)
            return sum(1 for v in result.values() if v)

        # ── dataclass 事件 ──
        event_type = type(event).__name__
        delivered = 0

        with self._lock:
            self._dc_event_cache[event_type] = event
            self._dc_event_history[event_type].append(event)
            subscriptions = list(self._dc_subscriptions.get(event_type, []))

        if not subscriptions:
            return 0

        event_market = getattr(event, 'market', None)

        for sub in subscriptions:
            if sub.markets and event_market not in sub.markets:
                continue
            try:
                sub.callback(event)
                delivered += 1
            except Exception as e:
                log.error(
                    f"[NajaEventBus] 事件处理失败: type={event_type}, error={e}"
                )

        self._stats.total_published += 1
        self._stats.total_delivered += delivered
        self._stats.by_event_type[event_type] = \
            self._stats.by_event_type.get(event_type, 0) + 1

        return delivered

    def unsubscribe(self, event_type_or_module: str, callback: Callable = None) -> bool:
        """
        取消订阅 — 自动识别

        - 如果提供 callback：按 dataclass 事件取消
        - 如果不提供 callback：按认知模块名取消
        """
        if callback is not None:
            with self._lock:
                subs = self._dc_subscriptions.get(event_type_or_module, [])
                for i, sub in enumerate(subs):
                    if sub.callback == callback:
                        subs.pop(i)
                        return True
            return False
        else:
            return self._unsubscribe_cognitive(event_type_or_module)

    def get_latest_event(self, event_type: str) -> Optional[Any]:
        """获取最近一次 dataclass 事件"""
        with self._lock:
            return self._dc_event_cache.get(event_type)

    def get_event_history(self, event_type: str, max_count: int = 10) -> List[Any]:
        """获取 dataclass 事件历史"""
        if max_count <= 0:
            return []
        with self._lock:
            history = self._dc_event_history.get(event_type)
            if not history:
                return []
            return list(history)[-max_count:]

    def clear(self, event_type: Optional[str] = None) -> None:
        """清空 dataclass 通道订阅和缓存"""
        with self._lock:
            if event_type:
                self._dc_subscriptions[event_type].clear()
                self._dc_event_cache.pop(event_type, None)
                if event_type in self._dc_event_history:
                    self._dc_event_history[event_type].clear()
            else:
                self._dc_subscriptions.clear()
                self._dc_event_history.clear()
                self._dc_event_cache.clear()

    # ================================================================
    #  认知信号事件接口
    # ================================================================

    def subscribe_cognitive(
        self,
        module_name: str,
        callback: Callable[[CognitiveSignalEvent], None],
        event_types: Optional[List[CognitiveEventType]] = None,
        min_importance: float = 0.3,
    ) -> CognitiveSubscriber:
        """订阅认知事件"""
        subscriber = CognitiveSubscriber(
            module_name=module_name,
            callback=callback,
            event_types=event_types or [],
            min_importance=min_importance,
        )

        with self._lock:
            self._cognitive_subscribers[module_name].append(subscriber)
            self._module_names.add(module_name)
            for et in subscriber.event_types:
                self._event_type_modules[et].add(module_name)

        event_type_str = [et.value for et in (event_types or [])]
        log.info(
            f"[NajaEventBus] 模块 '{module_name}' 订阅认知事件 "
            f"(event_types={event_type_str or '全部'}, min_importance={min_importance})"
        )
        return subscriber

    def _unsubscribe_cognitive(self, module_name: str) -> bool:
        """取消认知事件订阅"""
        with self._lock:
            if module_name not in self._cognitive_subscribers:
                return False
            for et, modules in self._event_type_modules.items():
                modules.discard(module_name)
            del self._cognitive_subscribers[module_name]
            self._module_names.discard(module_name)
        log.info(f"[NajaEventBus] 模块 '{module_name}' 已取消认知订阅")
        return True

    def publish_cognitive_event(
        self,
        source: str,
        event_type: CognitiveEventType,
        narratives: Optional[List[str]] = None,
        importance: float = 0.5,
        confidence: float = 0.5,
        stock_codes: Optional[List[str]] = None,
        risk_level: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, bool]:
        """发布认知事件（构造 CognitiveSignalEvent 后分发）"""
        event = CognitiveSignalEvent(
            source=source,
            event_type=event_type,
            narratives=narratives or [],
            importance=importance,
            confidence=confidence,
            stock_codes=stock_codes or [],
            risk_level=risk_level,
            metadata=metadata or {},
        )
        return self._publish_cognitive(event)

    def _publish_cognitive(self, event: CognitiveSignalEvent) -> Dict[str, bool]:
        """内部：分发认知信号事件"""
        # 去重
        if self._is_duplicate(event):
            log.debug(f"[NajaEventBus] 认知事件去重: {event}")
            return {}

        with self._lock:
            self._recent_events.append(event)
            now = time.time()
            self._recent_events = [
                e for e in self._recent_events
                if now - e.timestamp < self._dedup_window
            ]

        self._stats.total_published += 1
        self._stats.by_event_type[event.event_type.value] = \
            self._stats.by_event_type.get(event.event_type.value, 0) + 1

        results = {}
        delivered_count = 0

        with self._lock:
            subscribers_snapshot = {
                k: list(v) for k, v in self._cognitive_subscribers.items()
            }

        for module_name, subs in subscribers_snapshot.items():
            for sub in subs:
                if not sub.enabled:
                    continue
                if event.importance < sub.min_importance:
                    continue
                if sub.event_types and event.event_type not in sub.event_types:
                    continue
                try:
                    sub.callback(event)
                    results[module_name] = True
                    delivered_count += 1
                    self._stats.total_delivered += 1
                    self._stats.by_module[module_name] = \
                        self._stats.by_module.get(module_name, 0) + 1
                except Exception as e:
                    log.error(f"[NajaEventBus] 模块 '{module_name}' 认知回调失败: {e}")
                    results[module_name] = False

        if delivered_count == 0 and event.importance >= 0.7:
            self._stats.dropped += 1
            log.debug(f"[NajaEventBus] 高重要性认知事件无人接收: {event}")

        return results

    def _is_duplicate(self, event: CognitiveSignalEvent) -> bool:
        """检查认知事件是否重复"""
        now = time.time()
        for recent in self._recent_events:
            if now - recent.timestamp > self._dedup_window:
                continue
            if (
                recent.source == event.source and
                recent.event_type == event.event_type and
                set(recent.narratives) == set(event.narratives)
            ):
                return True
        return False

    # ================================================================
    #  通用工具方法
    # ================================================================

    def enable_module(self, module_name: str, enabled: bool = True):
        """启用/禁用认知模块的订阅"""
        with self._lock:
            if module_name not in self._cognitive_subscribers:
                return
            for sub in self._cognitive_subscribers[module_name]:
                sub.enabled = enabled
        log.debug(f"[NajaEventBus] 模块 '{module_name}' 已{'启用' if enabled else '禁用'}")

    def get_subscribers(self, module_name: Optional[str] = None) -> List[CognitiveSubscriber]:
        """获取认知订阅者列表"""
        with self._lock:
            if module_name:
                return list(self._cognitive_subscribers.get(module_name, []))
            return [s for subs in self._cognitive_subscribers.values() for s in subs]

    def get_stats(self) -> Dict[str, Any]:
        """获取总线统计"""
        return {
            "total_published": self._stats.total_published,
            "total_delivered": self._stats.total_delivered,
            "delivery_rate": round(
                self._stats.total_delivered / max(1, self._stats.total_published) * 100, 1
            ),
            "by_module": dict(self._stats.by_module),
            "by_event_type": dict(self._stats.by_event_type),
            "dropped": self._stats.dropped,
            "active_modules": len(self._module_names),
        }

    def list_modules(self) -> List[str]:
        """列出所有认知订阅模块"""
        return sorted(list(self._module_names))

    def reset_stats(self):
        """重置统计"""
        self._stats = CognitiveBusStats()





# ============== 单例访问 ==============

_bus: Optional[NajaEventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> NajaEventBus:
    """获取统一事件总线单例"""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = NajaEventBus()
    return _bus


def reset_event_bus():
    """重置总线（用于测试）"""
    global _bus
    if _bus is not None:
        _bus.clear()
    _bus = None
