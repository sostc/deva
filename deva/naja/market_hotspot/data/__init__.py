"""
Hotspot Data - 热点系统数据模块

提供数据获取与计算功能:
- 全球市场数据获取 (GlobalMarketAPI)
- Sina 行情解析与获取 (sina_parser)
- 实盘数据获取器 (RealtimeDataFetcher)
- 异步数据获取器 (AsyncRealtimeDataFetcher)
- 获取配置 (FetchConfig)
"""

from deva.naja.market_hotspot.data.global_market_futures import (
    GlobalMarketAPI,
    MarketData,
    get_global_market_api,
    fetch_global_market_data,
    MARKET_ID_TO_CODE,
)

from .fetch_config import FetchConfig, SNAPSHOT_CONFIG_KEY
from .realtime_fetcher import RealtimeDataFetcher
from .async_fetcher import AsyncRealtimeDataFetcher, get_data_fetcher

__all__ = [
    # 全球市场
    "GlobalMarketAPI",
    "MarketData",
    "get_global_market_api",
    "fetch_global_market_data",
    "MARKET_ID_TO_CODE",
    # 实盘获取
    "RealtimeDataFetcher",
    "AsyncRealtimeDataFetcher",
    "FetchConfig",
    "SNAPSHOT_CONFIG_KEY",
    "get_data_fetcher",
]
