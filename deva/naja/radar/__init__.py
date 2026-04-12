"""Radar Engine - 市场感知层 (Perception Layer)

职责：
- 市场数据获取：新闻、行情、全球市场数据
- 异常模式检测：Pattern/Drift/Anomaly/BlockAnomaly
- 事件分发：将感知结果发送到认知系统

感知层是系统的"眼睛"，负责从外部世界获取信息，
检测其中值得关注的异常模式，并通知认知系统进行理解。
"""

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
    USTradingClock,
    us_trading_clock_signal,
    is_us_trading_time,
    is_us_market_closed,
    USTRADING_CLOCK_STREAM,
)
# openrouter_monitor 已迁移到 cognition 层，保留向后兼容转发
from deva.naja.cognition.openrouter_monitor import (
    get_openrouter_trend,
    get_openrouter_full_data,
    refresh_openrouter_data,
    scheduled_openrouter_check,
    TREND_TABLE,
)
from .global_market_scanner import (
    GlobalMarketScanner,
    MarketAlert,
    MarketVolatilityTracker,
    ScanConfig,
    get_global_market_scanner,
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
    "USTradingClock",

    "us_trading_clock_signal",
    "is_us_trading_time",
    "is_us_market_closed",
    "USTRADING_CLOCK_STREAM",
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
