"""
Hotspot Events - 市场热点相关事件

用于 MarketHotspotSystem 和 AttentionOS、Cognition 之间的通信
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import time


@dataclass
class HotspotComputedEvent:
    """
    热点计算完成事件

    当 MarketHotspotSystem 完成一次热点计算后发布此事件
    AttentionOS 订阅此事件来结合自己的持仓和策略做决策
    QueryStateUpdater 使用其中的真实市场数据更新 QueryState
    """
    market: str
    timestamp: float
    global_hotspot: float
    activity: float
    block_hotspot: Dict[str, float] = field(default_factory=dict)
    symbol_weights: Dict[str, float] = field(default_factory=dict)
    symbols: List[str] = field(default_factory=list)

    # 真实市场数据（用于下游系统如 QueryState 更新）
    prices: List[float] = field(default_factory=list)
    returns: List[float] = field(default_factory=list)
    volumes: List[float] = field(default_factory=list)

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'market': self.market,
            'timestamp': self.timestamp,
            'datetime': self.datetime.isoformat(),
            'global_hotspot': self.global_hotspot,
            'activity': self.activity,
            'block_hotspot': self.block_hotspot,
            'symbol_weights': self.symbol_weights,
            'symbol_count': len(self.symbols),
        }


@dataclass
class MarketSnapshotEvent:
    """
    市场快照事件
    """
    market: str
    timestamp: float
    global_hotspot: float
    activity: float
    block_weights: Dict[str, float] = field(default_factory=dict)
    symbol_weights: Dict[str, float] = field(default_factory=dict)
    market_state: str = "unknown"

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)

    @property
    def market_time_str(self) -> str:
        return self.datetime.strftime("%H:%M:%S")


@dataclass
class SymbolUpdateEvent:
    """
    个股更新事件
    """
    market: str
    symbol: str
    timestamp: float
    weight: float
    block: Optional[str] = None
    change: Optional[float] = None


@dataclass
class HotspotShiftEvent:
    """
    热点转移事件

    当市场热点发生显著转移时发布（如全局热点转移、题材集中度变化、市场状态变化等）
    AttentionOS 接收此事件后决定是否发送到 InsightPool
    """
    event_type: str  # global_hotspot_shift, block_concentration_shift, market_state_shift, block_hotspot_change, symbol_hotspot_change
    timestamp: float
    market: str = ""
    title: str = ""
    content: str = ""
    score: float = 0.0
    symbol: str = ""
    block: str = ""
    market_time: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    old_value: Optional[float] = None
    new_value: Optional[float] = None

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)


@dataclass
class GlobalMarketDataEvent:
    """
    全局市场数据事件

    当GlobalMarketScanner获取到全局市场数据后发布此事件
    QueryStateUpdater接收此事件并更新QueryState
    """
    symbols: List[str]
    returns: List[float]
    volumes: List[float]
    prices: List[float]
    timestamp: float
    market: str = ""
    source: str = "global_market_scanner"

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'market': self.market,
            'timestamp': self.timestamp,
            'datetime': self.datetime.isoformat(),
            'symbol_count': len(self.symbols),
            'source': self.source
        }
