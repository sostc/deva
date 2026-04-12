"""
Tracking - 热点历史追踪子包

提供市场热点随时间变化的追踪能力：
- 快照记录与变化检测
- 题材轮动检测
- 热点加强/减弱事件
"""

from .history_tracker import (
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
