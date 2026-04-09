"""
NajaEventBus - 统一事件总线

提供事件发布/订阅机制，解耦 Naja 系统内各组件的通信

支持的事件类型：
- TextFetchedEvent, TextFocusedEvent（文本处理）
- HotspotComputedEvent, HotspotShiftEvent（市场热点）
- 其他自定义事件

使用方式：
```python
from deva.naja.events import get_event_bus, NajaEventBus

# 获取单例
bus = get_event_bus()

# 发布事件
bus.publish(TextFetchedEvent(...))

# 订阅事件
def on_text_fetched(event):
    ...

bus.subscribe('TextFetchedEvent', on_text_fetched, priority=10)
```
"""

import logging
from typing import Callable, Deque, Dict, List, Set, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque
import threading

log = logging.getLogger(__name__)


@dataclass
class EventSubscription:
    """事件订阅记录"""
    callback: Callable
    event_type: str
    markets: Set[str] = field(default_factory=set)
    priority: int = 0


class NajaEventBus:
    """
    Naja 统一事件总线

    实现发布-订阅模式，解耦各系统组件

    使用方式:
    ```python
    # 发布事件
    event_bus = get_event_bus()
    event_bus.publish(HotspotComputedEvent(...))

    # 订阅事件
    def on_hotspot_computed(event: HotspotComputedEvent):
        ...

    event_bus.subscribe('HotspotComputedEvent', on_hotspot_computed, markets={'US', 'CN'})
    ```
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._subscriptions: Dict[str, List[EventSubscription]] = defaultdict(list)
        self._lock_obj = threading.Lock()
        self._cache_max_size = 100
        self._event_cache: Dict[str, Any] = {}
        self._event_history: Dict[str, Deque[Any]] = defaultdict(
            lambda: deque(maxlen=self._cache_max_size)
        )

        self._initialized = True
        log.info("[NajaEventBus] 统一事件总线初始化完成")

    def subscribe(
        self,
        event_type: str,
        callback: Callable,
        markets: Optional[Set[str]] = None,
        priority: int = 0,
    ) -> None:
        """
        订阅事件

        Args:
            event_type: 事件类型名称（如 'HotspotComputedEvent', 'TextFetchedEvent'）
            callback: 回调函数
            markets: 过滤的市场（如 {'US', 'CN'}），None 表示不过滤
            priority: 优先级，数值越大越先执行
        """
        markets = markets or set()
        subscription = EventSubscription(
            callback=callback,
            event_type=event_type,
            markets=markets,
            priority=priority,
        )

        with self._lock_obj:
            self._subscriptions[event_type].append(subscription)
            self._subscriptions[event_type].sort(key=lambda x: x.priority, reverse=True)

        log.debug(
            f"[NajaEventBus] 订阅成功: type={event_type}, "
            f"priority={priority}, markets={markets or 'all'}"
        )

    def unsubscribe(self, event_type: str, callback: Callable) -> bool:
        """取消订阅"""
        with self._lock_obj:
            subs = self._subscriptions.get(event_type, [])
            for i, sub in enumerate(subs):
                if sub.callback == callback:
                    subs.pop(i)
                    log.debug(f"[NajaEventBus] 取消订阅: type={event_type}")
                    return True
        return False

    def publish(self, event: Any) -> int:
        """
        发布事件

        Args:
            event: 事件对象（dataclass）

        Returns:
            成功分发给多少个订阅者
        """
        event_type = type(event).__name__
        delivered = 0

        with self._lock_obj:
            self._event_cache[event_type] = event
            self._event_history[event_type].append(event)
            subscriptions = list(self._subscriptions.get(event_type, []))

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
                    f"[NajaEventBus] 事件处理失败: type={event_type}, "
                    f"error={e}"
                )

        return delivered

    def get_latest_event(self, event_type: str) -> Optional[Any]:
        """获取最近一次事件"""
        with self._lock_obj:
            return self._event_cache.get(event_type)

    def get_event_history(self, event_type: str, max_count: int = 10) -> List[Any]:
        """获取事件历史"""
        if max_count <= 0:
            return []
        with self._lock_obj:
            history = self._event_history.get(event_type)
            if not history:
                return []
            return list(history)[-max_count:]

    def clear(self, event_type: Optional[str] = None) -> None:
        """清空订阅或缓存"""
        with self._lock_obj:
            if event_type:
                self._subscriptions[event_type].clear()
                self._event_cache.pop(event_type, None)
                if event_type in self._event_history:
                    self._event_history[event_type].clear()
            else:
                self._subscriptions.clear()
                self._event_history.clear()
                self._event_cache.clear()


_bus: Optional[NajaEventBus] = None


def get_event_bus() -> NajaEventBus:
    """获取事件总线单例"""
    global _bus
    if _bus is None:
        _bus = NajaEventBus()
    return _bus


def reset_event_bus() -> None:
    """重置事件总线（主要用于测试）"""
    global _bus
    if _bus is not None:
        _bus.clear()
    _bus = None
