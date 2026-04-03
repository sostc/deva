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
from datetime import datetime

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
    max_sectors: int = 5000
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

        # 股票名称缓存
        self._symbol_name_cache: Dict[str, str] = {}

        # 美股注意力引擎（独立于A股）
        self._us_global_attention = GlobalAttentionEngine(
            history_window=self.config.global_history_window
        )
        self._us_sector_attention = SectorAttentionEngine(
            max_sectors=self.config.max_sectors
        )
        self._us_weight_pool = WeightPool(
            max_symbols=self.config.max_symbols
        )

        # 美股缓存状态
        self._us_last_global_attention: float = 0.0
        self._us_last_activity: float = 0.0
        self._us_last_sector_attention: Dict[str, float] = {}
        self._us_last_symbol_weights: Dict[str, float] = {}
        self._us_last_symbol_snapshot: Dict[str, Dict[str, Any]] = {}
        self._us_last_snapshot_time: float = 0.0

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
            config: 获取配置，为None时使用保存的配置
        """
        import sys
        log.warning(f"[AttentionSystem] ⚠️ start_realtime_fetcher 被调用, config={config}, _initialized={self._initialized}")
        sys.stdout.flush()
        sys.stderr.flush()

        try:
            if not self._initialized:
                log.error("[AttentionSystem] 系统未初始化，无法启动实盘获取器")
                return

            if self._realtime_fetcher is not None and self._realtime_fetcher._running:
                log.warning("[AttentionSystem] 实盘获取器已在运行中")
                return

            if config is None:
                from deva.naja.attention.integration.extended import get_mode_manager
                from deva.naja.attention.realtime_data_fetcher import FetchConfig
                mode_manager = get_mode_manager()
                saved_config = mode_manager.get_fetcher_config()
                log.warning(f"[AttentionSystem] saved_config={saved_config}")
                sys.stdout.flush()
                if saved_config:
                    config = FetchConfig(**saved_config)
                    log.info(f"[AttentionSystem] 使用保存的配置: force_trading_mode={config.force_trading_mode}")
                else:
                    config = FetchConfig()
                    log.info("[AttentionSystem] 使用默认配置")

            log.warning(f"[AttentionSystem] 创建 RealtimeDataFetcher, config.force_trading_mode={config.force_trading_mode}")
            sys.stdout.flush()

            self._realtime_fetcher = RealtimeDataFetcher(self, config)
            self._realtime_fetcher.start()
            sys.stdout.flush()

            log.warning("[AttentionSystem] 实盘获取器已启动，强制激活")
            self._realtime_fetcher._activate()
            sys.stdout.flush()

            print(f"[AttentionSystem] 调用 set_data_fetcher, self._realtime_fetcher={self._realtime_fetcher}")
            sys.stdout.flush()
            from deva.naja.attention.realtime_data_fetcher import set_data_fetcher
            print(f"[AttentionSystem] set_data_fetcher imported, calling it...")
            sys.stdout.flush()
            set_data_fetcher(self._realtime_fetcher)
            print(f"[AttentionSystem] set_data_fetcher called successfully")
            sys.stdout.flush()

            log.info("[AttentionSystem] 实盘获取器启动完成")
        except Exception as e:
            log.error(f"[AttentionSystem] 启动实盘获取器失败: {e}")
            import traceback
            log.error(traceback.format_exc())
            sys.stdout.flush()
            sys.stderr.flush()

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
        from deva.naja.attention.integration.extended import get_mode_manager

        mode_manager = get_mode_manager()
        current_mode = mode_manager.get_mode() if mode_manager else 'unknown'

        log.debug(f"[AttentionSystem] process_data 被调用, mode={current_mode}, type={type(data)}, len={len(data) if hasattr(data, '__len__') else 'N/A'}")

        if isinstance(data, pd.DataFrame):
            if data.empty:
                log.debug("[AttentionSystem] 数据为空，跳过")
                return

            log.debug(f"[AttentionSystem] process_data 收到数据: {len(data)} 行, columns={list(data.columns)}, index[:5]={list(data.index[:5])}")

            if 'code' not in data.columns and data.index is not None and len(data.index) > 0:
                data = data.copy()
                data['code'] = data.index
                log.debug(f"[AttentionSystem] 从索引提取股票代码: {list(data['code'][:5])}")

            if 'change_pct' not in data.columns and 'now' in data.columns and 'close' in data.columns:
                data = data.copy()
                close_values = data['close'].replace(0, np.nan).infer_objects(copy=False)
                data['change_pct'] = (data['now'] - data['close']) / close_values * 100
                data['change_pct'] = data['change_pct'].fillna(0).infer_objects(copy=False)
                log.debug(f"[AttentionSystem] 计算 change_pct: {list(data['change_pct'][:5])}")

            name_col = 'name' if 'name' in data.columns else ('stock_name' if 'stock_name' in data.columns else None)
            symbol_col = 'code' if 'code' in data.columns else data.index.name or 'code'

            from deva.naja.common.stock_registry import get_stock_registry
            registry = get_stock_registry()

            if 'code' in data.columns:
                codes = data['code'].astype(str).values
            else:
                codes = data.index.astype(str).values if data.index is not None else []

            if name_col and name_col in data.columns:
                names = data[name_col].astype(str).values
                for code, name in zip(codes, names):
                    registry.register(code, name)
                log.debug(f"[AttentionSystem] StockRegistry 注册: {len([c for c in codes if c])} 条")
            else:
                for code in codes:
                    if code:
                        registry.register(code, code)

            self._register_symbol_names_from_dataframe(data, symbol_col, name_col)
            log.debug(f"[AttentionSystem] 注册股票名称: cache大小={len(self._symbol_name_cache)}")

            data = self._apply_noise_filter(data)

            symbols = data['code'].values if 'code' in data.columns else data.index.values if data.index is not None else []
            returns = data['change_pct'].values if 'change_pct' in data.columns else np.zeros(len(data))
            volumes = data['volume'].values if 'volume' in data.columns else np.zeros(len(data))
            prices = data['now'].values if 'now' in data.columns else np.zeros(len(data))
            sector_ids = self._extract_sector_ids_from_data(data)

            log.debug(f"[AttentionSystem] process_snapshot 调用: symbols={len(symbols)}, sector_ids={len(sector_ids)}")
            log.debug(f"[AttentionSystem] symbols[:5]={list(symbols[:5])}, returns[:5]={list(returns[:5])}")

            result = self.process_snapshot(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                sector_ids=sector_ids,
                timestamp=time.time()
            )
            log.info(f"[AttentionSystem] process_snapshot 完成: global_attention={result.get('global_attention', 'N/A'):.3f}, sector_count={len(result.get('sector_attention', {}))}")

            try:
                from deva.naja.cognition.history_tracker import get_history_tracker
                tracker = get_history_tracker()
                if tracker:
                    symbol_weights = result.get('symbol_weights', {})
                    sector_attention = result.get('sector_attention', {})
                    global_attn = result.get('global_attention', 0.5)
                    activity = result.get('activity', 0.5)

                    market_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    tracker.record_snapshot(
                        global_attention=global_attn,
                        sector_weights=sector_attention,
                        symbol_weights=symbol_weights,
                        timestamp=time.time(),
                        timestamp_str=market_time_str,
                        activity=activity
                    )
                    log.debug(f"[AttentionSystem] HistoryTracker.record_snapshot 完成, snapshots数量={len(tracker.snapshots)}")
                else:
                    log.warning(f"[AttentionSystem] HistoryTracker 未初始化")
            except Exception as e:
                log.warning(f"[AttentionSystem] 记录到HistoryTracker失败: {e}")
                import traceback
                log.warning(traceback.format_exc())
        else:
            log.debug(f"[AttentionSystem] process_data 收到非DataFrame数据: {type(data)}")

    def _apply_noise_filter(self, data: 'pd.DataFrame') -> 'pd.DataFrame':
        """对数据进行噪音过滤（B股、ST股等）"""
        try:
            from ..processing.noise_filter import NoiseFilter
            from ..processing.tick_filter import TickNoiseFilter

            nf_config = self._get_noise_filter_config()
            noise_filter = NoiseFilter(config=nf_config)

            filtered = noise_filter.filter_dataframe(
                data,
                symbol_col='code' if 'code' in data.columns else data.index.name or 'code',
                amount_col='amount' if 'amount' in data.columns else None,
                volume_col='volume' if 'volume' in data.columns else None,
                price_col='now' if 'now' in data.columns else ('close' if 'close' in data.columns else None),
                name_col='name' if 'name' in data.columns else ('stock_name' if 'stock_name' in data.columns else None)
            )

            return filtered
        except Exception as e:
            log.debug(f"[AttentionSystem] 噪音过滤失败: {e}")
            return data

    def _register_symbol_names_from_dataframe(self, data: 'pd.DataFrame', symbol_col: str, name_col: Optional[str]):
        """从DataFrame注册股票名称"""
        if name_col is None:
            return
        try:
            if name_col in data.columns:
                names = data[name_col].astype(str).values
                if 'code' in data.columns:
                    symbols = data['code'].astype(str).values
                elif data.index is not None and len(data.index) > 0:
                    symbols = data.index.astype(str).values
                else:
                    return

                for symbol, name in zip(symbols, names):
                    if symbol and name and name != symbol:
                        self._symbol_name_cache[symbol] = name
                log.debug(f"[AttentionSystem] 注册股票名称: {len([s for s,n in zip(symbols, names) if s and n and n != s])} 个")
        except Exception as e:
            log.debug(f"[AttentionSystem] 注册股票名称失败: {e}")

    def get_symbol_name(self, symbol: str) -> str:
        """获取股票名称"""
        return self._symbol_name_cache.get(symbol, symbol)

    def _extract_sector_ids_from_data(self, data: 'pd.DataFrame') -> np.ndarray:
        """从数据中提取板块ID（已过滤噪音板块）"""
        try:
            block_df = self._get_block_dataframe()
            if block_df is None or block_df.empty:
                return np.zeros(len(data))

            code_col = 'code' if 'code' in data.columns else data.index.name
            if code_col is None:
                return np.zeros(len(data))

            from deva.naja.attention.processing.sector_noise_detector import SectorNoiseDetector
            sector_noise_detector = SectorNoiseDetector()

            block_df = block_df.copy()
            block_df['code'] = block_df['code'].astype(str).str.zfill(6)

            code_to_blocks: Dict[str, List[str]] = {}
            noise_block_count = 0
            for _, row in block_df.iterrows():
                code = str(row['code'])
                block = str(row['blocks']) if pd.notna(row['blocks']) else ''
                if block and code:
                    if sector_noise_detector.is_noise(block):
                        noise_block_count += 1
                        continue
                    if code not in code_to_blocks:
                        code_to_blocks[code] = []
                    if block not in code_to_blocks[code]:
                        code_to_blocks[code].append(block)

            if noise_block_count > 0:
                log.debug(f"[AttentionSystem] 提取板块时过滤噪音板块: {noise_block_count}个")

            sector_id_map: Dict[str, int] = {}
            next_sector_id = 1
            for blocks in code_to_blocks.values():
                for block in blocks:
                    if block not in sector_id_map:
                        sector_id_map[block] = next_sector_id
                        next_sector_id += 1

            sector_ids = []
            raw_codes = data[code_col].astype(str).values
            for code in raw_codes:
                code_str = str(code)
                code_str = code_str.replace('sh', '').replace('sz', '').replace('bj', '').zfill(6)
                blocks = code_to_blocks.get(code_str, [])
                if not blocks:
                    sector_ids.append(0)
                else:
                    sector_ids.append(sector_id_map.get(blocks[0], 0))

            log.debug(f"[AttentionSystem] 提取板块ID完成: {len(sector_id_map)}个有效板块, {len(data)}只股票")
            return np.array(sector_ids, dtype=int)
        except Exception as e:
            log.debug(f"[AttentionSystem] 提取sector_ids失败: {e}")
            return np.zeros(len(data))

    def _get_block_dataframe(self):
        """获取板块数据（统一从字典获取）"""
        try:
            from deva.naja.dictionary import get_dictionary_manager
            mgr = get_dictionary_manager()
            entry = mgr.get_by_name("通达信概念板块")
            if entry:
                payload = entry.get_payload()
                if isinstance(payload, pd.DataFrame):
                    return payload
            return None
        except Exception:
            return None

    def _get_noise_filter_config(self) -> 'NoiseFilterConfig':
        """获取噪音过滤器配置"""
        try:
            from ..processing.noise_filter import NoiseFilterConfig
            from deva.naja.config import get_noise_filter_config
            nf_config = get_noise_filter_config()
            return NoiseFilterConfig(
                min_amount=nf_config.get('min_amount', 1_000_000),
                min_volume=nf_config.get('min_volume', 100_000),
                min_price=nf_config.get('min_price', 1.0),
                blacklist=set(nf_config.get('blacklist', [])),
                whitelist=set(nf_config.get('whitelist', [])),
                dynamic_threshold=nf_config.get('dynamic_threshold', True),
                filter_b_shares=nf_config.get('filter_b_shares', True),
                filter_st=nf_config.get('filter_st', False),
            )
        except Exception:
            from ..processing.noise_filter import NoiseFilterConfig
            return NoiseFilterConfig()

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
                sector_attention = self.sector_attention.update(symbols, returns, volumes, timestamp, sector_ids)
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

    def process_us_snapshot(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        prices: np.ndarray,
        sector_ids: np.ndarray,
        timestamp: float
    ) -> Dict[str, Any]:
        """
        处理美股市场快照（独立于A股的注意力计算）

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组 (%)
            volumes: 成交量数组
            prices: 价格数组
            sector_ids: 板块ID数组（板块名称）
            timestamp: 时间戳

        Returns:
            调度决策结果（包含美股专属的注意力数据）
        """
        if not self._initialized:
            log.warning("[US-Attention] 注意力系统未初始化，跳过美股处理")
            return {
                'timestamp': timestamp,
                'global_attention': 0.5,
                'sector_attention': {},
                'symbol_weights': {},
                'market': 'US',
            }

        start_time = time.time()

        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        volumes = np.clip(volumes, 0, 1e15)
        prices = np.nan_to_num(prices, nan=0.0, posinf=1e6, neginf=0.0)
        prices = np.clip(prices, 0.01, 1e6)

        snapshot = MarketSnapshot(
            symbols=symbols,
            returns=returns,
            volumes=volumes,
            prices=prices,
            sector_ids=sector_ids,
            timestamp=timestamp
        )

        print(f"[US-Attention] process_us_snapshot: symbols={len(symbols)}, returns={returns[:5] if len(returns) > 5 else returns}")

        try:
            global_attention, activity = self._us_global_attention.get_attention_and_activity(snapshot)
            self._us_global_attention.update(snapshot)
            print(f"[US-Attention] global_attention={global_attention}, activity={activity}")

            with self._cache_lock:
                self._us_last_global_attention = global_attention
                self._us_last_activity = activity

        except Exception as e:
            print(f"[US-Attention] GlobalAttention 失败: {e}")
            import traceback
            traceback.print_exc()
            log.error(f"[US-GlobalAttention] 失败: {e}")
            global_attention = 0.5
            activity = 0.5

        try:
            sector_attention = self._us_sector_attention.update(symbols, returns, volumes, timestamp, sector_ids)
            print(f"[US-Attention] sector_attention count={len(sector_attention)}")
            with self._cache_lock:
                self._us_last_sector_attention = sector_attention
        except Exception as e:
            print(f"[US-Attention] SectorAttention 失败: {e}")
            log.error(f"[US-SectorAttention] 失败: {e}")
            sector_attention = {}

        # 自动注册新的美股symbol到_weight_pool（如果尚未注册）
        for sym in symbols:
            if sym not in self._us_weight_pool._symbol_to_idx:
                sector_list = [sector_ids[i] for i, s in enumerate(symbols) if s == sym]
                self._us_weight_pool.register_symbol(sym, sector_list if sector_list else ["其他"])
                print(f"[US-Attention] 自动注册美股symbol: {sym} -> {sector_list[:3] if sector_list else ['其他']}")

        try:
            symbol_weights = self._us_weight_pool.update(symbols, returns, volumes, sector_attention, timestamp)
            print(f"[US-Attention] symbol_weights count={len(symbol_weights)}")
            with self._cache_lock:
                self._us_last_symbol_weights = symbol_weights
        except Exception as e:
            print(f"[US-Attention] WeightPool 失败: {e}")
            log.error(f"[US-WeightPool] 失败: {e}")
            symbol_weights = {}

        latency = (time.time() - start_time) * 1000

        market_state = {}
        try:
            market_state = self._us_global_attention.get_market_state()
        except Exception:
            market_state = {'attention': global_attention, 'activity': activity, 'trend': 'unknown', 'description': '状态获取失败'}

        log.debug(f"[US-Attention] 处理完成: global_attention={global_attention:.3f}, sector_count={len(sector_attention)}, symbol_count={len(symbol_weights)}, latency={latency:.1f}ms")

        try:
            snapshot = {}
            for i, sym in enumerate(symbols):
                sym_str = str(sym)
                snapshot[sym_str] = {
                    "price": float(prices[i]) if i < len(prices) else 0.0,
                    "change": float(returns[i]) if i < len(returns) else 0.0,
                    "volume": float(volumes[i]) if i < len(volumes) else 0.0,
                    "sector": str(sector_ids[i]) if i < len(sector_ids) else "",
                    "market": "US",
                }
            with self._cache_lock:
                self._us_last_symbol_snapshot = snapshot
                self._us_last_snapshot_time = timestamp
        except Exception as e:
            log.debug(f"[US-Attention] 更新美股快照失败: {e}")

        return {
            'timestamp': timestamp,
            'latency_ms': latency,
            'global_attention': global_attention,
            'activity': activity,
            'sector_attention': sector_attention,
            'symbol_weights': symbol_weights,
            'market_state': market_state,
            'market': 'US',
            'stock_count': len(symbols),
        }

    def get_us_attention_state(self) -> Dict[str, Any]:
        """获取美股注意力状态"""
        with self._cache_lock:
            return {
                'global_attention': self._us_last_global_attention,
                'activity': self._us_last_activity,
                'sector_attention': self._us_last_sector_attention.copy(),
                'symbol_weights': self._us_last_symbol_weights.copy(),
                'stock_count': len(self._us_last_symbol_weights),
            }

    def get_us_symbol_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """获取美股最新symbol快照"""
        with self._cache_lock:
            return self._us_last_symbol_snapshot.copy()

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
