"""
Attention Data - 热点系统数据计算模块

提供数据计算功能:
- 全球市场数据获取 (GlobalMarketAPI)
"""

from deva.naja.market_hotspot.data.global_market_futures import (
    GlobalMarketAPI,
    MarketData,
    get_global_market_api,
    fetch_global_market_data,
    MARKET_ID_TO_CODE,
)

__all__ = [
    "GlobalMarketAPI",
    "MarketData",
    "get_global_market_api",
    "fetch_global_market_data",
    "MARKET_ID_TO_CODE",
]
