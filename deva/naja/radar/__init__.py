"""Radar Engine - 市场感知层 (Perception Layer)

职责：
- 市场数据获取：新闻、行情、全球市场数据
- 异常模式检测：Pattern/Drift/Anomaly/BlockAnomaly
- 事件分发：将感知结果发送到认知系统

感知层是系统的"眼睛"，负责从外部世界获取信息，
检测其中值得关注的异常模式，并通知认知系统进行理解。
"""

import importlib

from .engine import (
    RadarEngine,
    RadarEvent,
    RadarThread,
    get_radar_engine,
    _get_frequency_label,
    RADAR_EVENTS_TABLE,
    RADAR_THREAD_TABLE,
)
from .news_fetcher import (
    RadarNewsFetcher,
    RadarNewsProcessor,
    NewsItem,
    NewsTopicCluster,
)
from .trading_clock import (
    TradingClock,
    trading_clock_signal,
    is_trading_time,
    is_market_closed,
    TRADING_CLOCK_STREAM,
    us_trading_clock_signal,
    is_us_trading_time,
    is_us_market_closed,
    USTRADING_CLOCK_STREAM,
    get_global_trading_status,
)
# openrouter_monitor 已迁移到 cognition 层，保留向后兼容转发
from deva.naja.cognition.openrouter_monitor import (
    get_openrouter_trend,
    get_openrouter_full_data,
    refresh_openrouter_data,
    scheduled_openrouter_check,
    TREND_TABLE,
)
from .global_market_config import (
    MarketSessionManager,
    MarketStatus,
    MarketType,
    MarketInfo,
    MarketSession,
    GLOBAL_MARKET_CONFIGS,
    get_market_config,
    get_all_market_ids,
)

from .senses import (
    ProphetSense,
    ProphetSignal,
    PresageType,
    MomentumPrecipice,
    SentimentTransitionSense,
    FlowTasteSense,
    VolatilitySurfaceSense,
    RealtimeTaste,
    TasteSignal,
    PreTasteSense,
    PreTasteResult,
)

_volatility_surface_sense: VolatilitySurfaceSense = None


def get_volatility_surface_sense() -> VolatilitySurfaceSense:
    """获取 VolatilitySurfaceSense 单例"""
    global _volatility_surface_sense
    if _volatility_surface_sense is None:
        _volatility_surface_sense = VolatilitySurfaceSense()
    return _volatility_surface_sense


from deva.naja.register import SR

__all__ = [
    "RadarEngine",
    "RadarEvent",
    "get_radar_engine",
    "RadarNewsFetcher",
    "RadarNewsProcessor",
    "NewsItem",
    "NewsTopicCluster",
    "TradingClock",

    "trading_clock_signal",
    "is_trading_time",
    "is_market_closed",
    "TRADING_CLOCK_STREAM",

    "us_trading_clock_signal",
    "is_us_trading_time",
    "is_us_market_closed",
    "USTRADING_CLOCK_STREAM",
    "get_global_trading_status",
    "get_openrouter_trend",
    "get_openrouter_full_data",
    "refresh_openrouter_data",
    "scheduled_openrouter_check",
    "TREND_TABLE",
    "GlobalMarketScanner",
    "MarketAlert",
    "MarketVolatilityTracker",
    "ScanConfig",
    "get_global_market_scanner",
    "MarketSessionManager",
    "MarketStatus",
    "MarketType",
    "MarketInfo",
    "MarketSession",
    "GLOBAL_MARKET_CONFIGS",

    "get_market_config",
    "get_all_market_ids",
    # senses 子模块
    "ProphetSense",
    "ProphetSignal",
    "PresageType",
    "MomentumPrecipice",
    "SentimentTransitionSense",
    "FlowTasteSense",
    "VolatilitySurfaceSense",
    "RealtimeTaste",
    "TasteSignal",
    "PreTasteSense",
    "PreTasteResult",
]


# ---------------------------------------------------------------------------
# global_market_scanner 惰性导出（PEP 562）
# ---------------------------------------------------------------------------
# 该子模块在模块级 import 了 market_hotspot.data.global_market_futures，而后者又在
# 模块中途反向 import deva.naja.bandit.stock_block_map，于是形成环：
#   global_market_futures → bandit → radar → global_market_scanner → global_market_futures
# 全新解释器下 `import deva.naja.market_hotspot.data` 会因此直接 ImportError。
# radar 其余 eager 成员并不依赖 global_market_scanner，故改为按需加载以断开此环。
# `from deva.naja.radar import GlobalMarketScanner` 仍照常可用。
_LAZY_EXPORTS = {
    "GlobalMarketScanner": ".global_market_scanner",
    "MarketAlert": ".global_market_scanner",
    "MarketVolatilityTracker": ".global_market_scanner",
    "ScanConfig": ".global_market_scanner",
    "get_global_market_scanner": ".global_market_scanner",
}


def __getattr__(name):
    """PEP 562：惰性解析 global_market_scanner 的重导出。"""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path, __name__)
    value = getattr(module, name)
    globals()[name] = value  # 缓存，后续访问不再进入 __getattr__
    return value
