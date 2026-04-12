"""
Naja Events - 统一事件系统

Naja 的所有事件总线和事件定义都在此模块下：

总线：
- NajaEventBus: dataclass 事件分发（Text/Hotspot 等结构化事件）
- CognitiveSignalBus: 认知层信号事件（叙事/共振/风险等高级信号）

事件定义：
- text_events: 文本处理相关事件
- hotspot_events: 市场热点相关事件
- cognitive_bus: 认知信号事件类型
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
from .cognitive_bus import (
    CognitiveEventType,
    CognitiveSignalEvent,
    CognitiveSubscriber,
    CognitiveBusStats,
    CognitiveSignalBus,
    get_cognitive_bus,
    reset_cognitive_bus,
)

__all__ = [
    # NajaEventBus
    "NajaEventBus",
    "EventSubscription",
    "get_event_bus",
    "reset_event_bus",
    # CognitiveSignalBus
    "CognitiveEventType",
    "CognitiveSignalEvent",
    "CognitiveSubscriber",
    "CognitiveBusStats",
    "CognitiveSignalBus",
    "get_cognitive_bus",
    "reset_cognitive_bus",
    # Text events
    "TextFetchedEvent",
    "TextFocusedEvent",
    # Hotspot events
    "HotspotComputedEvent",
    "HotspotShiftEvent",
    "MarketSnapshotEvent",
    "SymbolUpdateEvent",
]
