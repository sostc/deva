"""
MarketContext - 市场上下文

每个市场(CN/US)独立的完整上下文，包含:
- FrequencyScheduler
- WeightPool
- BlockHotspotEngine

设计原则:
- 完全隔离，不同市场之间不共享任何数据
- 独立持久化
- 独立计算
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import numpy as np

from deva.naja.market_hotspot.scheduling.frequency_scheduler import (
    FrequencyScheduler,
    FrequencyConfig,
    FrequencyLevel
)
from deva.naja.market_hotspot.scheduling.frequency_scheduler import AdaptiveFrequencyController
from deva.naja.market_hotspot.scheduling.strategy_allocator import StrategyAllocator
from deva.naja.market_hotspot.core.weight_pool import (
    WeightPool,
    SymbolWeightConfig
)
from deva.naja.market_hotspot.core.block_engine import (
    BlockHotspotEngine,
    BlockConfig
)
from deva.naja.market_hotspot.core.global_hotspot_engine import GlobalHotspotEngine
from deva.naja.market_hotspot.engine.dual_engine import DualEngineCoordinator


@dataclass
class MarketContext:
    """
    单个市场的完整上下文

    Attributes:
        market: 市场标识 ('CN' 或 'US')
        frequency_scheduler: 频率调度器
        weight_pool: 权重池
        block_engine: 题材热点引擎
        last_update_time: 最后更新时间
        is_active: 是否活跃
    """
    market: str
    max_symbols: int = 5000
    max_blocks: int = 5000
    global_history_window: int = 20

    frequency_scheduler: FrequencyScheduler = field(init=False)
    frequency_controller: AdaptiveFrequencyController = field(init=False)
    weight_pool: WeightPool = field(init=False)
    block_engine: BlockHotspotEngine = field(init=False)
    global_hotspot: GlobalHotspotEngine = field(init=False)
    strategy_allocator: StrategyAllocator = field(init=False)
    dual_engine: DualEngineCoordinator = field(init=False)
    last_update_time: float = 0.0
    is_active: bool = False

    def __post_init__(self):
        self.frequency_scheduler = FrequencyScheduler(max_symbols=self.max_symbols)
        self.frequency_controller = AdaptiveFrequencyController()
        self.weight_pool = WeightPool(max_symbols=self.max_symbols)
        self.block_engine = BlockHotspotEngine(max_blocks=self.max_blocks)
        self.global_hotspot = GlobalHotspotEngine(history_window=self.global_history_window)
        self.strategy_allocator = StrategyAllocator()
        self.dual_engine = DualEngineCoordinator()

    def activate(self):
        """激活市场"""
        self.is_active = True

    def deactivate(self):
        """停用市场（不清理数据）"""
        self.is_active = False

    def get_symbol_weights(self) -> Dict[str, float]:
        """获取所有股票的权重"""
        return self.weight_pool.get_weights()

    def get_block_hotspot(self) -> Dict[str, float]:
        """获取所有题材的热点"""
        return self.block_engine.get_all_weights()

    def get_frequency_levels(self) -> Dict[str, FrequencyLevel]:
        """获取所有股票当前的频率档位"""
        return self.frequency_scheduler.get_all_levels()

    def get_summary(self) -> Dict[str, Any]:
        """获取市场摘要"""
        return {
            'market': self.market,
            'is_active': self.is_active,
            'last_update': self.last_update_time,
            'symbol_count': len(self.frequency_scheduler._symbol_to_idx),
            'block_count': len(self.block_engine._blocks),
            'symbol_weights': len(self.weight_pool._symbol_to_idx),
        }

    def save_state(self) -> Dict[str, Any]:
        """保存状态用于持久化"""
        return {
            'market': self.market,
            'is_active': self.is_active,
            'last_update_time': self.last_update_time,
            'frequency_scheduler': self.frequency_scheduler.save_state(),
            'frequency_controller': {},
            'weight_pool': self.weight_pool.save_state(),
            'block_engine': self.block_engine.save_state(),
            'global_hotspot': self.global_hotspot.save_state(),
            'strategy_allocator': self.strategy_allocator.get_allocation_summary() if hasattr(self.strategy_allocator, 'get_allocation_summary') else {},
            'dual_engine': self.dual_engine.get_trigger_summary() if hasattr(self.dual_engine, 'get_trigger_summary') else {},
        }

    @classmethod
    def load_state(cls, state: Dict[str, Any]) -> 'MarketContext':
        """从持久化状态恢复"""
        market = state.get('market', 'CN')
        ctx = cls(market=market)

        ctx.is_active = state.get('is_active', False)
        ctx.last_update_time = state.get('last_update_time', 0.0)

        if 'frequency_scheduler' in state:
            ctx.frequency_scheduler.load_state(state['frequency_scheduler'])
        if 'weight_pool' in state:
            ctx.weight_pool.load_state(state['weight_pool'])
        if 'block_engine' in state:
            ctx.block_engine.load_state(state['block_engine'])
        if 'global_hotspot' in state:
            ctx.global_hotspot.load_state(state['global_hotspot'])

        return ctx
