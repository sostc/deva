"""
Naja Events - 统一事件系统

所有事件总线和事件定义都在此模块下：

总线（已合并为一个 CognitiveSignalBus / NajaEventBus）：
- get_event_bus() / get_cognitive_bus() → 同一个实例
- 支持 dataclass 事件（Text/Hotspot 等）和认知信号事件

事件定义：
- text_events: 文本处理相关事件
- hotspot_events: 市场热点相关事件
- cognitive_bus: 认知信号事件类型
"""

from .cognitive_bus import (
    # 统一总线类
    CognitiveSignalBus,
    NajaEventBus,          # CognitiveSignalBus 的别名
    EventSubscription,
    # 认知事件
    CognitiveEventType,
    CognitiveSignalEvent,
    CognitiveSubscriber,
    CognitiveBusStats,
    # 单例访问
    get_event_bus,
    get_cognitive_bus,
    reset_event_bus,
    reset_cognitive_bus,
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
    # 统一总线
    "CognitiveSignalBus",
    "NajaEventBus",
    "EventSubscription",
    "get_event_bus",
    "get_cognitive_bus",
    "reset_event_bus",
    "reset_cognitive_bus",
    # 认知事件
    "CognitiveEventType",
    "CognitiveSignalEvent",
    "CognitiveSubscriber",
    "CognitiveBusStats",
    # Text events
    "TextFetchedEvent",
    "TextFocusedEvent",
    # Hotspot events
    "HotspotComputedEvent",
    "HotspotShiftEvent",
    "MarketSnapshotEvent",
    "SymbolUpdateEvent",
]
