"""
Attention System - 主控制器

整合所有模块，提供统一的注意力调度接口

数据流:
snapshot → Global Attention → Sector Attention → Weight Pool →
    Frequency Scheduler → Strategy Allocation → Dual Engine →
    DataSource Control
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass
import time
import asyncio
import logging

log = logging.getLogger(__name__)

from ..core import GlobalAttentionEngine, MarketSnapshot, SectorAttentionEngine, SectorConfig, WeightPool, WeightPoolView
from ..scheduling import FrequencyScheduler, FrequencyLevel, AdaptiveFrequencyController, StrategyAllocator, StrategyRegistry
from ..engine import DualEngineCoordinator

# 性能监控支持
try:
    from deva.naja.performance import record_component_execution, ComponentType
    _PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    _PERFORMANCE_MONITORING_AVAILABLE = False


@dataclass
class AttentionSystemConfig:
    """注意力系统配置"""
    # 全局注意力
    global_history_window: int = 20
    
    # 板块注意力
    max_sectors: int = 100
    sector_decay_half_life: float = 300.0
    
    # 权重池
    max_symbols: int = 5000
    
    # 频率调度
    low_interval: float = 60.0
    medium_interval: float = 10.0
    high_interval: float = 1.0
    
    # 双引擎
    river_history_window: int = 20
    pytorch_max_concurrent: int = 10


class AttentionSystem:
    """
    注意力系统主控制器
    
    职责:
    1. 协调所有子模块
    2. 处理市场数据快照
    3. 输出调度决策
    4. 监控性能指标
    """
    
    def __init__(self, config: Optional[AttentionSystemConfig] = None):
        self.config = config or AttentionSystemConfig()
        
        # 初始化子模块
        self.global_attention = GlobalAttentionEngine(
            history_window=self.config.global_history_window
        )
        
        self.sector_attention = SectorAttentionEngine(
            max_sectors=self.config.max_sectors
        )
        
        self.weight_pool = WeightPool(
            max_symbols=self.config.max_symbols
        )
        
        self.frequency_scheduler = FrequencyScheduler(
            max_symbols=self.config.max_symbols
        )
        
        self.frequency_controller = AdaptiveFrequencyController()
        
        self.strategy_allocator = StrategyAllocator()
        
        self.dual_engine = DualEngineCoordinator()
        
        # 状态
        self._initialized = False
        self._last_snapshot_time = 0.0
        self._processing_count = 0
        self._total_latency = 0.0
        
        # 缓存
        self._last_global_attention = 0.0
        self._last_activity = 0.0  # 市场活跃度
        self._last_sector_attention: Dict[str, float] = {}
        self._last_symbol_weights: Dict[str, float] = {}
    
    def initialize(
        self,
        sectors: List[SectorConfig],
        symbol_sector_map: Dict[str, List[str]]
    ):
        """
        初始化系统

        Args:
            sectors: 板块配置列表
            symbol_sector_map: symbol -> sectors 映射
        """
        log.info(f"[AttentionSystem] 初始化: 收到 {len(sectors)} 个板块, {len(symbol_sector_map)} 个个股")

        # 注册板块
        for sector in sectors:
            self.sector_attention.register_sector(sector)

        log.info(f"[AttentionSystem] 已注册 {len(self.sector_attention._sectors)} 个板块到 sector_attention")
        log.info(f"[AttentionSystem] 板块列表: {[s.name for s in list(self.sector_attention._sectors.values())[:10]]}")

        # 注册个股
        for symbol, sector_ids in symbol_sector_map.items():
            self.weight_pool.register_symbol(symbol, sector_ids)
            self.frequency_scheduler.register_symbol(symbol)
            self.dual_engine.river.register_symbol(symbol)

        log.info(f"[AttentionSystem] 已注册 {len(symbol_sector_map)} 个个股")

        self._initialized = True
    
    def process_snapshot(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        prices: np.ndarray,
        sector_ids: np.ndarray,
        timestamp: float
    ) -> Dict[str, Any]:
        """
        处理市场快照
        
        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组 (%)
            volumes: 成交量数组
            prices: 价格数组
            sector_ids: 板块ID数组
            timestamp: 时间戳
            
        Returns:
            调度决策结果
        """
        if not self._initialized:
            raise RuntimeError("AttentionSystem not initialized. Call initialize() first.")
        
        start_time = time.time()

        try:
            # Step 1: Global Attention
            snapshot = MarketSnapshot(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                sector_ids=sector_ids,
                timestamp=timestamp
            )
            global_attention, activity = self.global_attention.get_attention_and_activity(snapshot)
            self.global_attention.update(snapshot)  # 保持历史更新
            self._last_global_attention = global_attention
            self._last_activity = activity
        except Exception as e:
            import traceback
            log.error(f"[Step 1 GlobalAttention] 失败: {e}")
            log.error(traceback.format_exc())
            raise

        try:
            # Step 2: Sector Attention
            sector_attention = self.sector_attention.update(
                symbols, returns, volumes, timestamp
            )
            self._last_sector_attention = sector_attention
        except Exception as e:
            import traceback
            log.error(f"[Step 2 SectorAttention] 失败: {e}")
            log.error(traceback.format_exc())
            raise

        try:
            # Step 3: Weight Pool
            symbol_weights = self.weight_pool.update(
                symbols, returns, volumes, sector_attention, timestamp
            )
            self._last_symbol_weights = symbol_weights
        except Exception as e:
            import traceback
            log.error(f"[Step 3 WeightPool] 失败: {e}")
            log.error(traceback.format_exc())
            raise

        try:
            # Step 4: Frequency Scheduler
            # 根据 global_attention 调整频率配置
            freq_config = self.frequency_controller.adapt(global_attention, timestamp)
            self.frequency_scheduler.config = freq_config

            frequency_levels = self.frequency_scheduler.schedule(
                symbol_weights, timestamp
            )
        except Exception as e:
            import traceback
            log.error(f"[Step 4 FrequencyScheduler] 失败: {e}")
            log.error(traceback.format_exc())
            raise

        try:
            # Step 5: Strategy Allocation
            strategy_allocation = self.strategy_allocator.allocate(
                global_attention,
                sector_attention,
                symbol_weights,
                timestamp
            )
        except Exception as e:
            import traceback
            log.error(f"[Step 5 StrategyAllocation] 失败: {e}")
            log.error(traceback.format_exc())
            raise

        try:
            # Step 6: Dual Engine (处理每个 tick)
            pattern_signals = []
            for i, symbol in enumerate(symbols):
                symbol_str = str(symbol)
                weight = symbol_weights.get(symbol_str, 1.0)

                pattern = self.dual_engine.process_tick(
                    symbol=symbol_str,
                    price=float(prices[i]),
                    volume=float(volumes[i]),
                    global_attention=global_attention,
                    sector_attention=sector_attention,
                    symbol_weight=weight,
                    timestamp=timestamp
                )

                if pattern:
                    pattern_signals.append(pattern)
        except Exception as e:
            import traceback
            log.error(f"[Step 6 DualEngine] 失败: {e}")
            log.error(traceback.format_exc())
            raise
        
        # 计算延迟
        latency = (time.time() - start_time) * 1000  # ms
        self._total_latency += latency
        self._processing_count += 1
        self._last_snapshot_time = timestamp

        # 获取 Dual Engine 统计
        dual_engine_summary = self.dual_engine.get_trigger_summary()

        # 记录性能监控
        if _PERFORMANCE_MONITORING_AVAILABLE:
            record_component_execution(
                component_id="attention_system",
                component_name="注意力系统",
                component_type=ComponentType.STRATEGY,
                execution_time_ms=latency,
                success=True
            )

        return {
            'timestamp': timestamp,
            'latency_ms': latency,
            'global_attention': global_attention,
            'sector_attention': sector_attention,
            'symbol_weights': symbol_weights,
            'frequency_levels': frequency_levels,
            'strategy_allocation': strategy_allocation,
            'pattern_signals': pattern_signals,
            'market_state': self.global_attention.get_market_state(),
            'dual_engine_summary': dual_engine_summary
        }
    
    async def process_pytorch_batch(self) -> List[Any]:
        """处理 PyTorch 批量推理"""
        return await self.dual_engine.process_pytorch_batch()
    
    def get_symbols_for_frequency(self, level: FrequencyLevel) -> List[str]:
        """获取指定频率档位的所有个股"""
        return self.frequency_scheduler.get_symbols_by_level(level)
    
    def get_high_attention_symbols(self, threshold: float = 2.0) -> List[Tuple[str, float]]:
        """获取高注意力个股"""
        view = WeightPoolView(self.weight_pool)
        return view.get_high_attention_symbols(threshold)
    
    def get_active_sectors(self, threshold: float = 0.3) -> List[str]:
        """获取活跃板块"""
        return self.sector_attention.get_active_sectors(threshold)
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        avg_latency = (
            self._total_latency / max(self._processing_count, 1)
        )
        
        return {
            'initialized': self._initialized,
            'processing_count': self._processing_count,
            'avg_latency_ms': avg_latency,
            'last_snapshot_time': self._last_snapshot_time,
            'global_attention': self._last_global_attention,
            'activity': self._last_activity,
            'frequency_summary': self.frequency_scheduler.get_schedule_summary(),
            'strategy_summary': self.strategy_allocator.get_allocation_summary(),
            'dual_engine_summary': self.dual_engine.get_trigger_summary()
        }
    
    def get_datasource_control(self) -> Dict[str, Any]:
        """
        获取数据源控制指令
        
        Returns:
            {
                'high_freq_symbols': [...],
                'medium_freq_symbols': [...],
                'low_freq_symbols': [...],
                'intervals': {
                    'high': 1.0,
                    'medium': 10.0,
                    'low': 60.0
                }
            }
        """
        high_freq = self.frequency_scheduler.get_symbols_by_level(FrequencyLevel.HIGH)
        medium_freq = self.frequency_scheduler.get_symbols_by_level(FrequencyLevel.MEDIUM)
        low_freq = self.frequency_scheduler.get_symbols_by_level(FrequencyLevel.LOW)
        
        config = self.frequency_scheduler.config
        
        return {
            'high_freq_symbols': high_freq,
            'medium_freq_symbols': medium_freq,
            'low_freq_symbols': low_freq,
            'intervals': {
                'high': config.high_interval,
                'medium': config.medium_interval,
                'low': config.low_interval
            },
            'timestamp': time.time()
        }
    
    def reset(self):
        """重置系统"""
        self.global_attention.reset()
        self.sector_attention.reset()
        self.weight_pool.reset()
        self.frequency_scheduler.reset()
        self.strategy_allocator.reset()
        self.dual_engine.reset()
        
        self._processing_count = 0
        self._total_latency = 0.0
        self._last_global_attention = 0.0
        self._last_sector_attention.clear()
        self._last_symbol_weights.clear()


class AttentionSystemIntegration:
    """
    与 Naja 系统的集成层
    
    提供与现有 DataSource 和 Strategy 的集成接口
    """
    
    def __init__(self, attention_system: AttentionSystem):
        self.attention_system = attention_system
        self._datasource_callbacks: List[Callable] = []
        self._strategy_callbacks: List[Callable] = []
    
    def on_datasource_data(self, data: Dict[str, Any]):
        """
        处理数据源数据
        
        将数据源数据转换为快照格式并处理
        """
        # 解析数据源数据
        # 假设 data 包含: symbols, returns, volumes, prices, sector_ids, timestamp
        
        snapshot_data = self._parse_datasource_data(data)
        
        if snapshot_data:
            result = self.attention_system.process_snapshot(**snapshot_data)
            
            # 通知注册的回调
            for callback in self._datasource_callbacks:
                try:
                    callback(result)
                except Exception as e:
                    pass
    
    def _parse_datasource_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析数据源数据为快照格式"""
        try:
            return {
                'symbols': np.array(data['symbols']),
                'returns': np.array(data['returns']),
                'volumes': np.array(data['volumes']),
                'prices': np.array(data['prices']),
                'sector_ids': np.array(data.get('sector_ids', [])),
                'timestamp': data.get('timestamp', time.time())
            }
        except Exception as e:
            return None
    
    def register_datasource_callback(self, callback: Callable):
        """注册数据源回调"""
        self._datasource_callbacks.append(callback)
    
    def register_strategy_callback(self, callback: Callable):
        """注册策略回调"""
        self._strategy_callbacks.append(callback)
    
    def get_datasource_config(self) -> Dict[str, Any]:
        """
        获取数据源配置
        
        用于动态调整数据源订阅
        """
        return self.attention_system.get_datasource_control()
    
    def should_process_strategy(self, strategy_id: str) -> bool:
        """判断是否应该处理指定策略"""
        active_strategies = self.attention_system.strategy_allocator.get_active_strategies()
        return strategy_id in active_strategies