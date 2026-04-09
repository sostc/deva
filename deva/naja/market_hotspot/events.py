"""
Market Hotspot Events - 市场热点事件定义

用于 MarketHotspotSystem 和 AttentionOS 之间的解耦通信

已迁移到 naja.events.hotspot_events，此文件保持向后兼容
"""

from deva.naja.events.hotspot_events import (
    HotspotComputedEvent,
    HotspotShiftEvent,
    MarketSnapshotEvent,
    SymbolUpdateEvent,
)

__all__ = [
    "HotspotComputedEvent",
    "HotspotShiftEvent",
    "MarketSnapshotEvent",
    "SymbolUpdateEvent",
]
