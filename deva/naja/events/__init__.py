"""
Naja Events - 统一事件定义

按领域分组的事件定义，供 Radar、Attention、Cognition 等系统使用

子模块：
- event_bus: 统一事件总线
- text_events: 文本处理相关事件
- hotspot_events: 市场热点相关事件
"""

from .event_bus import (
    NajaEventBus,
    EventSubscription,
    get_event_bus,
    reset_event_bus,
)
from .text_events import (
    TextFetchedEvent,
    TextFocusedEvent,
)
from .hotspot_events import (
    HotspotComputedEvent,
    HotspotShiftEvent,
    MarketSnapshotEvent,
    SymbolUpdateEvent,
)

__all__ = [
    # EventBus
    "NajaEventBus",
    "EventSubscription",
    "get_event_bus",
    "reset_event_bus",
    # Text events
    "TextFetchedEvent",
    "TextFocusedEvent",
    # Hotspot events
    "HotspotComputedEvent",
    "HotspotShiftEvent",
    "MarketSnapshotEvent",
    "SymbolUpdateEvent",
]
