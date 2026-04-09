"""
Market Hotspot Event Bus - 市场热点事件总线

已迁移到 naja.events.event_bus.NajaEventBus
此文件保持向后兼容

使用方式（新版）：
    from deva.naja.events import get_event_bus
    bus = get_event_bus()

使用方式（旧版，向后兼容）：
    from deva.naja.market_hotspot.event_bus import get_hotspot_event_bus
    bus = get_hotspot_event_bus()
"""

from deva.naja.events import (
    NajaEventBus as HotspotEventBus,
    get_event_bus,
)

__all__ = [
    "HotspotEventBus",
    "get_hotspot_event_bus",
]

get_hotspot_event_bus = get_event_bus
