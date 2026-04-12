"""
数据获取配置

包含 RealtimeDataFetcher 的配置数据类和相关常量。
"""

from dataclasses import dataclass


@dataclass
class FetchConfig:
    """获取配置"""
    base_high_interval: float = 5.0
    base_medium_interval: float = 10.0
    base_low_interval: float = 60.0
    enable_market_data: bool = True
    force_trading_mode: bool = False
    playback_mode: bool = False
    playback_speed: float = 10.0


SNAPSHOT_CONFIG_KEY = "realtime_data_fetcher_snapshot"
