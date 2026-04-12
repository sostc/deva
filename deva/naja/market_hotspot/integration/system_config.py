"""
市场热点系统配置数据类

从 market_hotspot_system.py 中抽出的配置和结果数据类。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketHotspotSystemConfig:
    """市场热点系统配置"""
    global_history_window: int = 20
    max_blocks: int = 5000
    block_decay_half_life: float = 300.0
    max_symbols: int = 5000
    low_interval: float = 60.0
    medium_interval: float = 10.0
    high_interval: float = 5.0
    river_history_window: int = 20
    pytorch_max_concurrent: int = 10


@dataclass
class StepResult:
    """Pipeline步骤结果（用于优雅降级）"""
    success: bool
    data: Any = None
    error: str = ""
    using_fallback: bool = False


@dataclass
class FallbackConfig:
    """降级配置"""
    enable_graceful_degradation: bool = True
    max_consecutive_failures: int = 3
    circuit_breaker_timeout: float = 5.0
    return_last_valid_result: bool = True
