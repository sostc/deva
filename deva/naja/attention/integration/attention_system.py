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
from dataclasses import dataclass, field
import time
import asyncio
import logging
import threading

log = logging.getLogger(__name__)

from ..core import GlobalAttentionEngine, MarketSnapshot, SectorAttentionEngine, SectorConfig, WeightPool, WeightPoolView
from ..scheduling import FrequencyScheduler, FrequencyLevel, AdaptiveFrequencyController, StrategyAllocator, StrategyRegistry
from ..engine import DualEngineCoordinator
from ..realtime_data_fetcher import RealtimeDataFetcher, AsyncRealtimeDataFetcher, FetchConfig

# 性能监控支持
try:
    from deva.naja.performance import record_component_execution, ComponentType
    _PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    _PERFORMANCE_MONITORING_AVAILABLE = False


@dataclass
class AttentionSystemConfig:
    """注意力系统配置"""
    global_history_window: int = 20
    max_sectors: int = 100
    sector_decay_half_life: float = 300.0
    max_symbols: int = 5000
    low_interval: float = 60.0
    medium_interval: float = 10.0
    high_interval: float = 1.0
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


class AttentionSystem:
    """
    注意力系统主控制器

    职责:
    1. 协调所有子模块
    2. 处理市场数据快照
    3. 输出调度决策
    4. 监控性能指标

    修复内容:
    - 添加线程安全锁
    - 添加优雅降级机制（熔断器模式）
    - 各步骤独立错误处理
    """

    def __init__(self, config: Optional[AttentionSystemConfig] = None, fallback_config: Optional[FallbackConfig] = None):
        self.config = config or AttentionSystemConfig()
        self.fallback_config = fallback_config or FallbackConfig()

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

        # 实盘数据获取器
        self._realtime_fetcher: Optional[RealtimeDataFetcher] = None
        self._async_realtime_fetcher: Optional[AsyncRealtimeDataFetcher] = None

        # 状态
        self._initialized = False
        self._last_snapshot_time = 0.0
        self._processing_count = 0
        self._total_latency = 0.0

        # 缓存（带线程安全）
        self._cache_lock = threading.RLock()
        self._last_global_attention = 0.0
        self._last_activity = 0.0
        self._last_sector_attention: Dict[str, float] = {}
        self._last_symbol_weights: Dict[str, float] = {}

        # 上次有效结果（用于降级）
        self._last_valid_result: Optional[Dict[str, Any]] = None

        # 熔断器状态
        self._step_failures: Dict[str, int] = {}
        self._step_circuit_open: Dict[str, float] = {}
        self._default_results: Dict[str, Any] = {
            'global_attention': 0.5,
            'sector_attention': {},
            'symbol_weights': {},
            'frequency_levels': {},
            'strategy_allocation': {},
            'pattern_signals': [],
            'market_state': {},
        }

    def _get_step_result(self, step_name: str, fallback_data: Any) -> Tuple[bool, Any]:
        """检查熔断器状态，返回是否应该执行或使用降级结果"""
        if not self.fallback_config.enable_graceful_degradation:
            return True, None

        current_time = time.time()
        circuit_key = step_name

        if circuit_key in self._step_circuit_open:
            open_time = self._step_circuit_open[circuit_key]
            if current_time - open_time < self.fallback_config.circuit_breaker_timeout:
                return False, fallback_data
            else:
                del self._step_circuit_open[circuit_key]
                self._step_failures[circuit_key] = 0

        return True, None

    def _record_step_success(self, step_name: str):
        """记录步骤成功，重置失败计数"""
        with self._cache_lock:
            self._step_failures[step_name] = 0
            if step_name in self._step_circuit_open:
                del self._step_circuit_open[step_name]

    def _record_step_failure(self, step_name: str):
        """记录步骤失败，触发熔断"""
        with self._cache_lock:
            self._step_failures[step_name] = self._step_failures.get(step_name, 0) + 1
            if self._step_failures[step_name] >= self.fallback_config.max_consecutive_failures:
                self._step_circuit_open[step_name] = time.time()
                log.warning(f"[AttentionSystem] 熔断器开启: {step_name}, 持续 {self.fallback_config.circuit_breaker_timeout}s")
    
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

    def start_realtime_fetcher(self, config: Optional[FetchConfig] = None):
        """
        启动实盘数据获取器

        根据注意力权重动态获取实盘数据:
        - 高注意力 symbol: 每秒获取
        - 中注意力 symbol: 每10秒获取
        - 低注意力 symbol: 每60秒获取

        Args:
            config: 获取配置，为None时使用默认配置
        """
        if not self._initialized:
            log.error("[AttentionSystem] 系统未初始化，无法启动实盘获取器")
            return

        if self._realtime_fetcher is not None and self._realtime_fetcher._running:
            log.warning("[AttentionSystem] 实盘获取器已在运行中")
            return

        config = config or FetchConfig()
        self._realtime_fetcher = RealtimeDataFetcher(self, config)
        self._realtime_fetcher.start()

        log.info("[AttentionSystem] 实盘获取器已启动")

    def stop_realtime_fetcher(self):
        """停止实盘数据获取器"""
        if self._realtime_fetcher:
            self._realtime_fetcher.stop()
            self._realtime_fetcher = None
            log.info("[AttentionSystem] 实盘获取器已停止")

    async def start_async_realtime_fetcher(self, config: Optional[FetchConfig] = None):
        """
        启动异步实盘数据获取器

        Args:
            config: 获取配置，为None时使用默认配置
        """
        if not self._initialized:
            log.error("[AttentionSystem] 系统未初始化，无法启动异步实盘获取器")
            return

        if self._async_realtime_fetcher is not None and self._async_realtime_fetcher._running:
            log.warning("[AttentionSystem] 异步实盘获取器已在运行中")
            return

        config = config or FetchConfig()
        self._async_realtime_fetcher = AsyncRealtimeDataFetcher(self, config)
        await self._async_realtime_fetcher.start()

        log.info("[AttentionSystem] 异步实盘获取器已启动")

    async def stop_async_realtime_fetcher(self):
        """停止异步实盘数据获取器"""
        if self._async_realtime_fetcher:
            await self._async_realtime_fetcher.stop()
            self._async_realtime_fetcher = None
            log.info("[AttentionSystem] 异步实盘获取器已停止")

    def process_data(self, data):
        """
        处理外部数据（用于实盘获取器推送数据）

        Args:
            data: DataFrame 或 dict，包含 code, now, change_pct, volume 等字段
        """
        import pandas as pd

        if isinstance(data, pd.DataFrame):
            if data.empty:
                return

            symbols = data['code'].values if 'code' in data.columns else []
            returns = data['change_pct'].values if 'change_pct' in data.columns else np.zeros(len(data))
            volumes = data['volume'].values if 'volume' in data.columns else np.zeros(len(data))
            prices = data['now'].values if 'now' in data.columns else np.zeros(len(data))

            self.process_snapshot(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                sector_ids=np.array([''] * len(symbols)),
                timestamp=time.time()
            )

    def _get_fallback_for_step(self, step_name: str) -> Any:
        """获取步骤的降级数据"""
        fallbacks = {
            'global_attention': lambda: (0.5, 0.5),
            'sector_attention': lambda: {},
            'symbol_weights': lambda: {},
            'frequency_levels': lambda: {},
            'strategy_allocation': lambda: self.strategy_allocator.get_allocation_summary() if hasattr(self.strategy_allocator, 'get_allocation_summary') else {},
            'pattern_signals': lambda: [],
            'market_state': lambda: {'attention': 0.5, 'activity': 0.5, 'trend': 'degraded', 'description': '降级模式运行'},
        }
        fallback_fn = fallbacks.get(step_name, lambda: None)
        return fallback_fn()

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
        处理市场快照（带优雅降级和线程安全）

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
        result = {
            'timestamp': timestamp,
            'latency_ms': 0.0,
            'global_attention': 0.5,
            'sector_attention': {},
            'symbol_weights': {},
            'frequency_levels': {},
            'strategy_allocation': {},
            'pattern_signals': [],
            'market_state': {},
            'dual_engine_summary': {},
            'degraded': False,
            'degraded_steps': [],
        }

        global_attention = 0.5
        activity = 0.5
        sector_attention = {}
        symbol_weights = {}
        frequency_levels = {}

        should_execute, fallback = self._get_step_result('global_attention', (0.5, 0.5))
        if should_execute:
            try:
                snapshot = MarketSnapshot(
                    symbols=symbols,
                    returns=returns,
                    volumes=volumes,
                    prices=prices,
                    sector_ids=sector_ids,
                    timestamp=timestamp
                )
                global_attention, activity = self.global_attention.get_attention_and_activity(snapshot)
                self.global_attention.update(snapshot)
                self._record_step_success('global_attention')
            except Exception as e:
                log.error(f"[Step 1 GlobalAttention] 失败: {e}")
                self._record_step_failure('global_attention')
                fallback_attn, fallback_act = fallback if fallback else (0.5, 0.5)
                global_attention = fallback_attn
                activity = fallback_act
                result['degraded'] = True
                result['degraded_steps'].append('global_attention')
        else:
            log.warning(f"[Step 1 GlobalAttention] 熔断器开启，使用降级值")
            fallback_attn, fallback_act = fallback if fallback else (0.5, 0.5)
            global_attention = fallback_attn
            activity = fallback_act
            result['degraded'] = True
            result['degraded_steps'].append('global_attention')

        with self._cache_lock:
            self._last_global_attention = global_attention
            self._last_activity = activity

        should_execute, fallback = self._get_step_result('sector_attention', {})
        if should_execute:
            try:
                sector_attention = self.sector_attention.update(symbols, returns, volumes, timestamp)
                self._record_step_success('sector_attention')
            except Exception as e:
                log.error(f"[Step 2 SectorAttention] 失败: {e}")
                self._record_step_failure('sector_attention')
                sector_attention = fallback if fallback else {}
                result['degraded'] = True
                result['degraded_steps'].append('sector_attention')
        else:
            log.warning(f"[Step 2 SectorAttention] 熔断器开启，使用降级值")
            sector_attention = fallback if fallback else {}
            result['degraded'] = True
            result['degraded_steps'].append('sector_attention')

        with self._cache_lock:
            self._last_sector_attention = sector_attention

        should_execute, fallback = self._get_step_result('symbol_weights', {})
        if should_execute:
            try:
                symbol_weights = self.weight_pool.update(symbols, returns, volumes, sector_attention, timestamp)
                self._record_step_success('symbol_weights')
            except Exception as e:
                log.error(f"[Step 3 WeightPool] 失败: {e}")
                self._record_step_failure('symbol_weights')
                symbol_weights = fallback if fallback else {}
                result['degraded'] = True
                result['degraded_steps'].append('symbol_weights')
        else:
            log.warning(f"[Step 3 WeightPool] 熔断器开启，使用降级值")
            symbol_weights = fallback if fallback else {}
            result['degraded'] = True
            result['degraded_steps'].append('symbol_weights')

        with self._cache_lock:
            self._last_symbol_weights = symbol_weights

        should_execute, fallback = self._get_step_result('frequency_scheduler', {})
        if should_execute:
            try:
                freq_config = self.frequency_controller.adapt(global_attention, timestamp)
                self.frequency_scheduler.config = freq_config
                frequency_levels = self.frequency_scheduler.schedule(symbol_weights, timestamp)
                self._record_step_success('frequency_scheduler')
            except Exception as e:
                log.error(f"[Step 4 FrequencyScheduler] 失败: {e}")
                self._record_step_failure('frequency_scheduler')
                frequency_levels = fallback if fallback else {}
                result['degraded'] = True
                result['degraded_steps'].append('frequency_scheduler')
        else:
            log.warning(f"[Step 4 FrequencyScheduler] 熔断器开启，使用降级值")
            frequency_levels = fallback if fallback else {}
            result['degraded'] = True
            result['degraded_steps'].append('frequency_scheduler')

        should_execute, fallback = self._get_step_result('strategy_allocation', {})
        if should_execute:
            try:
                strategy_allocation = self.strategy_allocator.allocate(
                    global_attention, sector_attention, symbol_weights, timestamp
                )
                self._record_step_success('strategy_allocation')
            except Exception as e:
                log.error(f"[Step 5 StrategyAllocation] 失败: {e}")
                self._record_step_failure('strategy_allocation')
                strategy_allocation = fallback if fallback else {}
                result['degraded'] = True
                result['degraded_steps'].append('strategy_allocation')
        else:
            log.warning(f"[Step 5 StrategyAllocation] 熔断器开启，使用降级值")
            strategy_allocation = fallback if fallback else {}
            result['degraded'] = True
            result['degraded_steps'].append('strategy_allocation')

        pattern_signals = []
        should_execute, fallback = self._get_step_result('dual_engine', [])
        if should_execute:
            try:
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
                self._record_step_success('dual_engine')
            except Exception as e:
                log.error(f"[Step 6 DualEngine] 失败: {e}")
                self._record_step_failure('dual_engine')
                pattern_signals = fallback if fallback else []
                result['degraded'] = True
                result['degraded_steps'].append('dual_engine')
        else:
            log.warning(f"[Step 6 DualEngine] 熔断器开启，使用降级值")
            pattern_signals = fallback if fallback else []
            result['degraded'] = True
            result['degraded_steps'].append('dual_engine')

        latency = (time.time() - start_time) * 1000

        with self._cache_lock:
            self._total_latency += latency
            self._processing_count += 1
            self._last_snapshot_time = timestamp

        dual_engine_summary = self.dual_engine.get_trigger_summary()

        market_state = {}
        try:
            market_state = self.global_attention.get_market_state()
        except Exception:
            market_state = {'attention': global_attention, 'activity': activity, 'trend': 'unknown', 'description': '状态获取失败'}

        if not result['degraded'] and self.fallback_config.return_last_valid_result:
            result['degraded'] = False
            result['degraded_steps'] = []

        final_result = {
            'timestamp': timestamp,
            'latency_ms': latency,
            'global_attention': global_attention,
            'sector_attention': sector_attention,
            'symbol_weights': symbol_weights,
            'frequency_levels': frequency_levels,
            'strategy_allocation': strategy_allocation,
            'pattern_signals': pattern_signals,
            'market_state': market_state,
            'dual_engine_summary': dual_engine_summary,
            'degraded': result['degraded'],
            'degraded_steps': result['degraded_steps'],
        }

        if not result['degraded']:
            with self._cache_lock:
                self._last_valid_result = final_result

        if _PERFORMANCE_MONITORING_AVAILABLE:
            record_component_execution(
                component_id="attention_system",
                component_name="注意力系统",
                component_type=ComponentType.STRATEGY,
                execution_time_ms=latency,
                success=not result['degraded']
            )

        return final_result
    
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

        fetcher_status = None
        if self._realtime_fetcher:
            fetcher_status = self._realtime_fetcher.get_stats()

        return {
            'initialized': self._initialized,
            'processing_count': self._processing_count,
            'avg_latency_ms': avg_latency,
            'last_snapshot_time': self._last_snapshot_time,
            'global_attention': self._last_global_attention,
            'activity': self._last_activity,
            'frequency_summary': self.frequency_scheduler.get_schedule_summary(),
            'strategy_summary': self.strategy_allocator.get_allocation_summary(),
            'dual_engine_summary': self.dual_engine.get_trigger_summary(),
            'realtime_fetcher': fetcher_status
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

        with self._cache_lock:
            self._processing_count = 0
            self._total_latency = 0.0
            self._last_global_attention = 0.0
            self._last_sector_attention.clear()
            self._last_symbol_weights.clear()
            self._last_valid_result = None

        self._step_failures.clear()
        self._step_circuit_open.clear()


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