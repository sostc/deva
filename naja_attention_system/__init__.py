"""
Naja Attention Scheduling System
自适应注意力调度机制

核心模块:
1. Global Attention - 全市场注意力计算
2. Sector Attention - 板块注意力计算
3. Weight Pool - 多对多权重池
4. Frequency Scheduler - 频率调度器
5. Strategy Allocation - 策略分配与调节
6. Dual Engine - River + PyTorch 双引擎

数据流:
snapshot → Global Attention → Sector Attention → Weight Pool → 
    Frequency Scheduler → Strategy Allocation → DataSource 调整 → 执行
"""

from .global_attention import GlobalAttentionEngine, MarketSnapshot
from .sector_attention import SectorAttentionEngine, SectorConfig
from .weight_pool import WeightPool, SymbolWeightConfig, WeightPoolView
from .frequency_scheduler import FrequencyScheduler, FrequencyLevel, FrequencyConfig, AdaptiveFrequencyController
from .strategy_allocation import (
    StrategyAllocator, StrategyRegistry, Strategy, StrategyConfig,
    StrategyParams, StrategyScope, StrategyType
)
from .dual_engine import RiverEngine, PyTorchEngine, DualEngineCoordinator, AnomalySignal, PatternSignal
from .attention_system import AttentionSystem, AttentionSystemConfig, AttentionSystemIntegration
from .noise_filter import NoiseFilter, NoiseFilterConfig, get_noise_filter

__all__ = [
    "GlobalAttentionEngine",
    "MarketSnapshot",
    "SectorAttentionEngine",
    "SectorConfig",
    "WeightPool",
    "SymbolWeightConfig",
    "WeightPoolView",
    "FrequencyScheduler",
    "FrequencyLevel",
    "FrequencyConfig",
    "AdaptiveFrequencyController",
    "StrategyAllocator",
    "StrategyRegistry",
    "Strategy",
    "StrategyConfig",
    "StrategyParams",
    "StrategyScope",
    "StrategyType",
    "RiverEngine",
    "PyTorchEngine",
    "DualEngineCoordinator",
    "AnomalySignal",
    "PatternSignal",
    "AttentionSystem",
    "AttentionSystemConfig",
    "AttentionSystemIntegration",
    "NoiseFilter",
    "NoiseFilterConfig",
    "get_noise_filter",
]