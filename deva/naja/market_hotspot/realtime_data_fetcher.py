"""
兼容性垫片 - 原 realtime_data_fetcher.py 已拆分到 data/ 子包

所有符号从 data/ 子包重新导出，保持向后兼容。
新代码请直接从 deva.naja.market_hotspot.data 导入。
"""

# 从 data/ 子包重新导出所有公开符号
from .data.fetch_config import FetchConfig, SNAPSHOT_CONFIG_KEY
from .data.realtime_fetcher import RealtimeDataFetcher
from .data.async_fetcher import AsyncRealtimeDataFetcher, get_data_fetcher
from .data.sina_parser import (
    _get_sina_session,
    _close_sina_session,
    _parse_sina_response,
    _fetch_sina_batch_async,
    _get_cn_codes_from_registry,
    _fetch_all_stocks_async,
    _fetch_sina_sync,
)

__all__ = [
    "RealtimeDataFetcher",
    "AsyncRealtimeDataFetcher",
    "FetchConfig",
    "SNAPSHOT_CONFIG_KEY",
    "get_data_fetcher",
]
