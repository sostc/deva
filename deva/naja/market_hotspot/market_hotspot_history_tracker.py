"""
兼容性垫片 - 原 market_hotspot_history_tracker.py 已移至 tracking/ 子包

所有符号从 tracking/ 子包重新导出，保持向后兼容。
新代码请直接从 deva.naja.market_hotspot.tracking 导入。
"""

from .tracking.history_tracker import (
    MarketHotspotHistoryTracker,
    HotspotSnapshot,
    HotspotChange,
    BlockHotspotEvent,
    get_history_tracker,
)

__all__ = [
    "MarketHotspotHistoryTracker",
    "HotspotSnapshot",
    "HotspotChange",
    "BlockHotspotEvent",
    "get_history_tracker",
]
