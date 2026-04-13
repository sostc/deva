"""
市场热点系统 - 主控制器

整合所有模块，提供统一的市场热点调度接口

数据流:
snapshot → Global Hotspot → Block Hotspot → Weight Pool →
    Frequency Scheduler → Strategy Allocation → Dual Engine →
    DataSource Control
"""

from ..data.realtime_fetcher import RealtimeDataFetcher
from ..data.async_fetcher import AsyncRealtimeDataFetcher
from ..data.fetch_config import FetchConfig
from ..engine import DualEngineCoordinator
from ..scheduling import FrequencyScheduler, FrequencyLevel, AdaptiveFrequencyController, StrategyAllocator, StrategyRegistry
from ..core import GlobalHotspotEngine, MarketSnapshot, BlockHotspotEngine, BlockConfig, WeightPool, WeightPoolView, MarketContext
from .system_config import MarketHotspotSystemConfig, StepResult, FallbackConfig
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
import time
import asyncio
import logging
import threading
from datetime import datetime
from deva.naja.register import SR

log = logging.getLogger(__name__)


# 性能监控支持
try:
    from deva.naja.infra.observability.performance_monitor import record_component_execution, ComponentType
    _PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    _PERFORMANCE_MONITORING_AVAILABLE = False


class MarketHotspotSystem:
    """
    市场热点系统核心

    职责:
    1. 协调所有子模块计算热点
    2. 处理市场数据快照
    3. 输出调度决策
    4. 监控性能指标

    注意: 本类是核心计算单元，不涉及系统集成。
    集成逻辑由 MarketHotspotIntegration (market_hotspot_integration.py) 处理。
    """

    def __init__(self, config: Optional[MarketHotspotSystemConfig] = None, fallback_config: Optional[FallbackConfig] = None):
        self.config = config or MarketHotspotSystemConfig()
        self.fallback_config = fallback_config or FallbackConfig()

        # 双市场上下文（完整隔离）
        self._cn_context = MarketContext(
            market='CN',
            max_symbols=self.config.max_symbols,
            max_blocks=self.config.max_blocks,
            global_history_window=self.config.global_history_window,
        )
        self._us_context = MarketContext(
            market='US',
            max_symbols=self.config.max_symbols,
            max_blocks=self.config.max_blocks,
            global_history_window=self.config.global_history_window,
        )
        self._current_market = 'CN'

        # 兼容旧字段（指向 A 股上下文）
        self.global_hotspot = self._cn_context.global_hotspot
        self.block_hotspot = self._cn_context.block_engine
        self.weight_pool = self._cn_context.weight_pool
        self.frequency_scheduler = self._cn_context.frequency_scheduler
        self.frequency_controller = self._cn_context.frequency_controller
        self.strategy_allocator = self._cn_context.strategy_allocator
        self.dual_engine = self._cn_context.dual_engine

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
        self._last_global_hotspot = 0.0
        self._last_activity = 0.0
        self._last_block_hotspot: Dict[str, float] = {}
        self._last_symbol_weights: Dict[str, float] = {}

        # 股票名称缓存
        self._symbol_name_cache: Dict[str, str] = {}

        # 美股热点引擎（保持兼容旧字段）
        self._us_global_hotspot = self._us_context.global_hotspot
        self._us_block_hotspot = self._us_context.block_engine
        self._us_weight_pool = self._us_context.weight_pool

        # 美股缓存状态
        self._us_last_global_hotspot: float = 0.0
        self._us_last_activity: float = 0.0
        self._us_last_block_hotspot: Dict[str, float] = {}
        self._us_last_symbol_weights: Dict[str, float] = {}
        self._us_last_symbol_snapshot: Dict[str, Dict[str, Any]] = {}
        self._us_last_snapshot_time: float = 0.0

        # 美股题材变化追踪（用于检测显著变化）
        self._us_prev_block_hotspot: Dict[str, float] = {}
        self._us_block_change_threshold: float = 0.1  # 调低阈值以捕获更多变化

        # 美股期货指数缓存（用于UI展示）
        self._us_futures_cache: Dict[str, float] = {}
        self._us_futures_cache_time: float = 0.0
        self._us_futures_cache_ttl: float = 60.0  # 缓存60秒

        # A股指数缓存（用于UI展示）
        self._cn_index_cache: Dict[str, float] = {}
        self._cn_index_cache_time: float = 0.0
        self._cn_index_cache_ttl: float = 60.0  # 缓存60秒

        # 上次有效结果（用于降级）
        self._last_valid_result: Optional[Dict[str, Any]] = None

        # 熔断器状态
        self._step_failures: Dict[str, int] = {}
        self._step_circuit_open: Dict[str, float] = {}
        self._default_results: Dict[str, Any] = {
            'global_hotspot': 0.5,
            'block_hotspot': {},
            'symbol_weights': {},
            'frequency_levels': {},
            'strategy_allocation': {},
            'pattern_signals': [],
            'market_state': {},
        }

        # 注册指数符号到频率调度器（指数始终为高频）
        self._register_index_symbols()

    INDEX_SYMBOLS = ['CN_SH', 'CN_HS300', 'CN_CHINEXT', 'US_NQ', 'US_ES', 'US_YM']

    def _register_index_symbols(self):
        """注册指数符号到频率调度器，指数权重固定为最高"""
        if self._cn_context is None or self._us_context is None:
            log.warning("[MarketHotspotSystem] _register_index_symbols: context 未初始化")
            return
        for symbol in self.INDEX_SYMBOLS:
            if symbol.startswith('CN_'):
                self._cn_context.frequency_scheduler.register_protected_symbol(symbol)
            elif symbol.startswith('US_'):
                self._us_context.frequency_scheduler.register_protected_symbol(symbol)
        log.info(f"[MarketHotspotSystem] 注册指数符号完成: {self.INDEX_SYMBOLS}")

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
                log.warning(f"[MarketHotspotSystem] 熔断器开启: {step_name}, 持续 {self.fallback_config.circuit_breaker_timeout}s")

    def initialize(
        self,
        blocks: List[BlockConfig],
        symbol_block_map: Dict[str, List[str]]
    ):
        """
        初始化系统

        Args:
            blocks: 题材配置列表
            symbol_block_map: symbol -> blocks 映射
        """
        log.info(f"[MarketHotspotSystem] 初始化: 收到 {len(blocks)} 个题材, {len(symbol_block_map)} 个个股")

        # 注册题材
        for config in blocks:
            self.block_hotspot.register_block(config)

        log.info(f"[MarketHotspotSystem] 已注册 {len(self.block_hotspot._blocks)} 个题材到 block_hotspot")
        log.info(f"[MarketHotspotSystem] 题材列表: {[c.name for c in list(self.block_hotspot._blocks.values())[:10]]}")

        # 注册个股
        for symbol, block_ids in symbol_block_map.items():
            self.weight_pool.register_symbol(symbol, block_ids)
            self.frequency_scheduler.register_symbol(symbol)
            self.dual_engine.river.register_symbol(symbol)

        log.info(f"[MarketHotspotSystem] 已注册 {len(symbol_block_map)} 个个股")

        self._initialized = True

    def start_realtime_fetcher(self, config: Optional[FetchConfig] = None):
        """启动实盘数据获取器"""
        try:
            if not self._initialized:
                log.error("[MarketHotspotSystem] 系统未初始化，无法启动实盘获取器")
                return

            if self._realtime_fetcher is not None and self._realtime_fetcher._running:
                log.warning("[MarketHotspotSystem] 实盘获取器已在运行中")
                return

            if config is None:
                from deva.naja.market_hotspot.integration.market_hotspot_integration import get_mode_manager
                from deva.naja.market_hotspot.data.fetch_config import FetchConfig
                mode_manager = get_mode_manager()
                saved_config = mode_manager.get_fetcher_config()
                if saved_config:
                    config = FetchConfig(**saved_config)
                else:
                    config = FetchConfig()

            from deva.naja.market_hotspot.data.realtime_fetcher import RealtimeDataFetcher
            fetcher = RealtimeDataFetcher(self, config)
            fetcher.start()
            fetcher._activate()

            self._realtime_fetcher = fetcher
            log.info("[MarketHotspotSystem] 实盘获取器启动完成")
        except Exception as e:
            log.error(f"[MarketHotspotSystem] 启动实盘获取器失败: {e}")
            import traceback
            traceback.print_exc()

    def stop_realtime_fetcher(self):
        """停止实盘数据获取器"""
        if self._realtime_fetcher:
            self._realtime_fetcher.stop()
            self._realtime_fetcher = None
            log.info("[MarketHotspotSystem] 实盘获取器已停止")

    async def start_async_realtime_fetcher(self, config: Optional[FetchConfig] = None):
        """
        启动异步实盘数据获取器

        Args:
            config: 获取配置，为None时使用默认配置
        """
        if not self._initialized:
            log.error("[MarketHotspotSystem] 系统未初始化，无法启动异步实盘获取器")
            return

        if self._async_realtime_fetcher is not None and self._async_realtime_fetcher._running:
            log.warning("[MarketHotspotSystem] 异步实盘获取器已在运行中")
            return

        config = config or FetchConfig()
        self._async_realtime_fetcher = AsyncRealtimeDataFetcher(self, config)
        await self._async_realtime_fetcher.start()

        log.info("[MarketHotspotSystem] 异步实盘获取器已启动")

    async def stop_async_realtime_fetcher(self):
        """停止异步实盘数据获取器"""
        if self._async_realtime_fetcher:
            await self._async_realtime_fetcher.stop()
            self._async_realtime_fetcher = None
            log.info("[MarketHotspotSystem] 异步实盘获取器已停止")

    def process_data(self, data, market: Optional[str] = None):
        """
        处理外部数据（用于实盘获取器推送数据）

        Args:
            data: DataFrame 或 dict，包含 code, now, change_pct, volume 等字段
            market: 市场标识 ('CN' 或 'US')，如果为 None 则自动检测
        """
        import pandas as pd
        from deva.naja.market_hotspot.integration.market_hotspot_integration import get_mode_manager

        mode_manager = get_mode_manager()
        current_mode = mode_manager.get_mode() if mode_manager else 'unknown'

        log.debug(f"[MarketHotspotSystem] process_data 被调用, mode={current_mode}, type={type(data)}, len={len(data) if hasattr(data, '__len__') else 'N/A'}")

        if isinstance(data, pd.DataFrame):
            if data.empty:
                log.debug("[MarketHotspotSystem] 数据为空，跳过")
                return

            # 自动检测市场
            if market is None:
                market = self._detect_market_from_data(data)

            log.debug(f"[MarketHotspotSystem] 检测到市场: {market}, 数据行数: {len(data)}")

            log.debug(f"[MarketHotspotSystem] process_data 收到数据: {len(data)} 行, columns={list(data.columns)}, index[:5]={list(data.index[:5])}")

            if 'code' not in data.columns and data.index is not None and len(data.index) > 0:
                data = data.copy()
                data['code'] = data.index
                log.debug(f"[MarketHotspotSystem] 从索引提取股票代码: {list(data['code'][:5])}")

            if 'change_pct' not in data.columns and 'now' in data.columns and 'close' in data.columns:
                data = data.copy()
                close_values = data['close'].replace(0, np.nan).infer_objects(copy=False)
                data['change_pct'] = (data['now'] - data['close']) / close_values * 100
                data['change_pct'] = data['change_pct'].fillna(0).infer_objects(copy=False)
                log.debug(f"[MarketHotspotSystem] 计算 change_pct: {list(data['change_pct'][:5])}")

            name_col = 'name' if 'name' in data.columns else (
                'stock_name' if 'stock_name' in data.columns else None)
            symbol_col = 'code' if 'code' in data.columns else data.index.name or 'code'

            self._register_symbol_names_from_dataframe(data, symbol_col, name_col)
            log.debug(f"[MarketHotspotSystem] 注册股票名称: cache大小={len(self._symbol_name_cache)}")

            data = self._apply_noise_filter(data)

            symbols = data['code'].values if 'code' in data.columns else data.index.values if data.index is not None else []
            returns = data['change_pct'].values if 'change_pct' in data.columns else np.zeros(
                len(data))
            volumes = data['volume'].values if 'volume' in data.columns else np.zeros(len(data))
            prices = data['now'].values if 'now' in data.columns else np.zeros(len(data))

            if market == 'US' and 'block' in data.columns:
                block_ids = data['block'].values

                symbols_list = data.index.values
                blocks_list = data['blocks'].values if 'blocks' in data.columns else block_ids

                us_weight_pool = self._get_context('US').weight_pool
                log.debug(f"[MarketHotspotSystem] 美股注册: symbols={list(symbols_list[:5])}, weight_pool={id(us_weight_pool)}")

                for sym, blk_list in zip(symbols_list, blocks_list):
                    if isinstance(blk_list, str):
                        blk_list = [blk_list] if blk_list else []
                    elif hasattr(blk_list, 'tolist'):
                        blk_list = blk_list.tolist()
                    elif not isinstance(blk_list, list):
                        blk_list = []
                    try:
                        us_weight_pool.register_symbol(str(sym), blk_list)
                    except Exception as e:
                        log.debug(f"注册symbol失败: {sym}, {e}")
            else:
                block_ids = self._extract_block_ids_from_data(data)

            log.debug(f"[MarketHotspotSystem] process_snapshot 调用: market={market}, symbols={len(symbols)}, block_ids={len(block_ids)}")
            log.debug(f"[MarketHotspotSystem] symbols[:5]={list(symbols[:5])}, returns[:5]={list(returns[:5])}")

            result = self.process_snapshot(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                block_ids=block_ids,
                timestamp=time.time(),
                market=market
            )
            log.debug(f"[MarketHotspotSystem] process_snapshot 完成: global_hotspot={result.get('global_hotspot', 'N/A'):.3f}, block_count={len(result.get('block_hotspot', {}))}, symbol_weights_count={len(result.get('symbol_weights', {}))}")

            try:
                from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
                tracker = get_history_tracker()
                if tracker:
                    symbol_weights = result.get('symbol_weights', {})
                    block_hotspot = result.get('block_hotspot', {})
                    global_attn = result.get('global_hotspot', 0.5)
                    activity = result.get('activity', 0.5)

                    market_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    tracker.record_snapshot(
                        global_hotspot=global_attn,
                        block_weights=block_hotspot,
                        symbol_weights=symbol_weights,
                        timestamp=time.time(),
                        timestamp_str=market_time_str,
                        activity=activity
                    )
                    log.debug(f"[MarketHotspotSystem] HistoryTracker.record_snapshot 完成, snapshots数量={len(tracker.snapshots)}")
                else:
                    log.warning(f"[MarketHotspotSystem] HistoryTracker 未初始化")
            except Exception as e:
                log.warning(f"[MarketHotspotSystem] 记录到HistoryTracker失败: {e}")
                import traceback
                log.warning(traceback.format_exc())
        else:
            log.debug(f"[MarketHotspotSystem] process_data 收到非DataFrame数据: {type(data)}")

    def _apply_noise_filter(self, data: 'pd.DataFrame') -> 'pd.DataFrame':
        """对数据进行噪音过滤（B股、ST股等）"""
        try:
            from ..processing.noise_filter import NoiseFilter, NoiseFilterConfig

            if not hasattr(self, '_noise_filter') or self._noise_filter is None:
                nf_config = self._get_noise_filter_config()
                self._noise_filter = NoiseFilter(config=nf_config)

            filtered = self._noise_filter.filter_dataframe(
                data,
                symbol_col='code' if 'code' in data.columns else data.index.name or 'code',
                amount_col='amount' if 'amount' in data.columns else None,
                volume_col='volume' if 'volume' in data.columns else None,
                price_col='now' if 'now' in data.columns else (
                    'close' if 'close' in data.columns else None),
                name_col='name' if 'name' in data.columns else (
                    'stock_name' if 'stock_name' in data.columns else None)
            )

            return filtered
        except Exception as e:
            log.debug(f"[MarketHotspotSystem] 噪音过滤失败: {e}")
            return data

    @property
    def noise_filter(self):
        """获取噪音过滤器实例（供 UI 层使用）"""
        if not hasattr(self, '_noise_filter') or self._noise_filter is None:
            nf_config = self._get_noise_filter_config()
            self._noise_filter = NoiseFilter(config=nf_config)
        return self._noise_filter

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
                log.debug(f"[MarketHotspotSystem] 注册股票名称: {len([s for s,n in zip(symbols, names) if s and n and n != s])} 个")
        except Exception as e:
            log.debug(f"[MarketHotspotSystem] 注册股票名称失败: {e}")

    def get_symbol_name(self, symbol: str) -> str:
        """获取股票名称"""
        return self._symbol_name_cache.get(symbol, symbol)

    def _extract_block_ids_from_data(self, data: 'pd.DataFrame') -> np.ndarray:
        """从数据中提取题材ID（使用 BlockDictionary）"""
        try:
            from deva.naja.dictionary.blocks import get_block_dictionary
            from deva.naja.market_hotspot.processing.block_noise_detector import BlockNoiseDetector

            bd = get_block_dictionary()
            block_noise_detector = BlockNoiseDetector()

            code_col = 'code' if 'code' in data.columns else data.index.name
            if code_col is None:
                return np.zeros(len(data))

            raw_codes = data[code_col].astype(str).values
            stock_to_blocks = bd._cn_stock_to_blocks

            block_id_map: Dict[str, int] = {}
            next_block_id = 1

            for code in raw_codes:
                code_str = str(code).replace('sh', '').replace('sz', '').replace('bj', '').zfill(6)
                blocks = stock_to_blocks.get(code_str, set())

                filtered_blocks = []
                for block in blocks:
                    if block_noise_detector.is_block_noise(block):
                        continue
                    filtered_blocks.append(block)
                    if block not in block_id_map:
                        block_id_map[block] = next_block_id
                        next_block_id += 1

            block_ids = []
            for code in raw_codes:
                code_str = str(code).replace('sh', '').replace('sz', '').replace('bj', '').zfill(6)
                blocks = stock_to_blocks.get(code_str, set())
                block_id = 0
                for block in blocks:
                    if not block_noise_detector.is_block_noise(block):
                        block_id = block_id_map.get(block, 0)
                        break
                block_ids.append(block_id)

            log.debug(f"[MarketHotspotSystem] 提取题材ID完成: {len(block_id_map)}个有效题材, {len(data)}只股票")
            return np.array(block_ids, dtype=int)
        except Exception as e:
            log.debug(f"[MarketHotspotSystem] 提取block_ids失败: {e}")
            import traceback
            log.debug(traceback.format_exc())
            return np.zeros(len(data))

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
            'global_hotspot': lambda: (0.5, 0.5),
            'block_hotspot': lambda: {},
            'symbol_weights': lambda: {},
            'frequency_levels': lambda: {},
            'strategy_allocation': lambda: self.strategy_allocator.get_allocation_summary() if hasattr(self.strategy_allocator, 'get_allocation_summary') else {},
            'pattern_signals': lambda: [],
            'market_state': lambda: {'hotspot': 0.5, 'activity': 0.5, 'trend': 'degraded', 'description': '降级模式运行'},
        }
        fallback_fn = fallbacks.get(step_name, lambda: None)
        return fallback_fn()

    def _detect_market_from_data(self, data: 'pd.DataFrame') -> str:
        """
        从数据中检测市场标识

        检测逻辑:
        1. 如果有 'market' 列，使用该列的值
        2. 如果有 'code' 列，检查代码前缀:
           - 'gb_' 开头 -> US
           - 'sh', 'sz', 'bj' 开头 -> CN
        3. 默认返回 'CN'
        """
        try:
            # 方法1: 检查是否有 market 列
            if 'market' in data.columns:
                markets = data['market'].dropna().unique()
                if len(markets) > 0:
                    market = str(markets[0]).upper()
                    if market in ('US', 'CN'):
                        return market

            # 方法2: 检查代码前缀
            if 'code' in data.columns:
                codes = data['code'].dropna().astype(str).head(10).values
                us_count = sum(1 for c in codes if c.startswith('gb_'))
                cn_count = sum(1 for c in codes if c.startswith(('sh', 'sz', 'bj')))
                if us_count > cn_count:
                    return 'US'
                elif cn_count > 0:
                    return 'CN'

            return 'CN'
        except Exception as e:
            log.debug(f"[MarketHotspotSystem] 市场检测失败: {e}")
            return 'CN'

    def _get_context(self, market: str) -> 'MarketContext':
        """获取市场对应的上下文"""
        return self._cn_context if market == 'CN' else self._us_context

    def _get_block_engine(self, market: str) -> 'BlockHotspotEngine':
        """获取市场对应的题材引擎"""
        return self._get_context(market).block_engine

    def _get_weight_pool(self, market: str) -> 'WeightPool':
        """获取市场对应的权重池"""
        return self._get_context(market).weight_pool

    def _get_frequency_scheduler(self, market: str) -> 'FrequencyScheduler':
        """获取市场对应的频率调度器"""
        return self._get_context(market).frequency_scheduler

    def process_snapshot(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        prices: np.ndarray,
        block_ids: np.ndarray,
        timestamp: float,
        market: str = 'CN'
    ) -> Dict[str, Any]:
        """
        处理市场快照（带优雅降级和线程安全，支持双市场）

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组 (%)
            volumes: 成交量数组
            prices: 价格数组
            block_ids: 题材ID数组
            timestamp: 时间戳
            market: 市场标识 ('CN' 或 'US')

        Returns:
            调度决策结果
        """
        if not self._initialized:
            raise RuntimeError("MarketHotspotSystem not initialized. Call initialize() first.")

        start_time = time.time()

        # 根据市场获取对应的引擎
        ctx = self._get_context(market)
        block_engine = ctx.block_engine
        weight_pool = ctx.weight_pool
        frequency_scheduler = ctx.frequency_scheduler
        frequency_controller = ctx.frequency_controller
        global_hotspot_engine = ctx.global_hotspot
        strategy_allocator = ctx.strategy_allocator
        dual_engine = ctx.dual_engine

        result = {
            'timestamp': timestamp,
            'market': market,
            'latency_ms': 0.0,
            'global_hotspot': 0.5,
            'block_hotspot': {},
            'symbol_weights': {},
            'frequency_levels': {},
            'strategy_allocation': {},
            'pattern_signals': [],
            'market_state': {},
            'dual_engine_summary': {},
            'degraded': False,
            'degraded_steps': [],
        }

        global_hotspot = 0.5
        activity = 0.5
        block_hotspot = {}
        symbol_weights = {}
        frequency_levels = {}

        should_execute, fallback = self._get_step_result('global_hotspot', (0.5, 0.5))
        if should_execute:
            try:
                snapshot = MarketSnapshot(
                    symbols=symbols,
                    returns=returns,
                    volumes=volumes,
                    prices=prices,
                    block_ids=block_ids,
                    timestamp=timestamp
                )
                global_hotspot, activity = global_hotspot_engine.get_hotspot_and_activity(snapshot)
                global_hotspot_engine.update(snapshot)
                self._record_step_success('global_hotspot')
            except Exception as e:
                log.error(f"[Step 1 GlobalHotspot] 失败: {e}")
                self._record_step_failure('global_hotspot')
                fallback_attn, fallback_act = fallback if fallback else (0.5, 0.5)
                global_hotspot = fallback_attn
                activity = fallback_act
                result['degraded'] = True
                result['degraded_steps'].append('global_hotspot')
        else:
            log.warning(f"[Step 1 GlobalHotspot] 熔断器开启，使用降级值")
            fallback_attn, fallback_act = fallback if fallback else (0.5, 0.5)
            global_hotspot = fallback_attn
            activity = fallback_act
            result['degraded'] = True
            result['degraded_steps'].append('global_hotspot')

        with self._cache_lock:
            if market == 'US':
                self._us_last_global_hotspot = global_hotspot
                self._us_last_activity = activity
            else:
                self._last_global_hotspot = global_hotspot
                self._last_activity = activity

        should_execute, fallback = self._get_step_result('block_hotspot', {})
        if should_execute:
            try:
                block_hotspot = block_engine.update(
                    symbols, returns, volumes, timestamp, block_ids)
                self._record_step_success('block_hotspot')
            except Exception as e:
                log.error(f"[Step 2 BlockHotspot] 失败: {e}")
                self._record_step_failure('block_hotspot')
                block_hotspot = fallback if fallback else {}
                result['degraded'] = True
                result['degraded_steps'].append('block_hotspot')
        else:
            log.warning(f"[Step 2 BlockHotspot] 熔断器开启，使用降级值")
            block_hotspot = fallback if fallback else {}
            result['degraded'] = True
            result['degraded_steps'].append('block_hotspot')

        with self._cache_lock:
            if market == 'US':
                self._us_last_block_hotspot = block_hotspot
            else:
                self._last_block_hotspot = block_hotspot

        should_execute, fallback = self._get_step_result('symbol_weights', {})
        if should_execute:
            try:
                symbol_weights = weight_pool.update(
                    symbols, returns, volumes, block_hotspot, timestamp)
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
            if market == 'US':
                self._us_last_symbol_weights = symbol_weights
            else:
                self._last_symbol_weights = symbol_weights

        should_execute, fallback = self._get_step_result('frequency_scheduler', {})
        if should_execute:
            try:
                freq_config = frequency_controller.adapt(global_hotspot, timestamp)
                frequency_scheduler.config = freq_config
                frequency_levels = frequency_scheduler.schedule(symbol_weights, timestamp)
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
                strategy_allocation = strategy_allocator.allocate(
                    global_hotspot, block_hotspot, symbol_weights, timestamp
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
                    pattern = dual_engine.process_tick(
                        symbol=symbol_str,
                        price=float(prices[i]),
                        volume=float(volumes[i]),
                        global_hotspot=global_hotspot,
                        block_hotspot=block_hotspot,
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

        dual_engine_summary = dual_engine.get_trigger_summary()

        market_state = {}
        try:
            market_state = global_hotspot_engine.get_market_state()
        except Exception:
            market_state = {'hotspot': global_hotspot, 'activity': activity,
                            'trend': 'unknown', 'description': '状态获取失败'}

        if not result['degraded'] and self.fallback_config.return_last_valid_result:
            result['degraded'] = False
            result['degraded_steps'] = []

        final_result = {
            'timestamp': timestamp,
            'market': market,
            'latency_ms': latency,
            'global_hotspot': global_hotspot,
            'block_hotspot': block_hotspot,
            'symbol_weights': symbol_weights,
            'frequency_levels': frequency_levels,
            'strategy_allocation': strategy_allocation,
            'pattern_signals': pattern_signals,
            'market_state': market_state,
            'dual_engine_summary': dual_engine_summary,
            'degraded': result['degraded'],
            'degraded_steps': result['degraded_steps'],
        }

        if market == 'US':
            try:
                snapshot = {}
                for i, sym in enumerate(symbols):
                    sym_str = str(sym)
                    snapshot[sym_str] = {
                        "price": float(prices[i]) if i < len(prices) else 0.0,
                        "change": float(returns[i]) if i < len(returns) else 0.0,
                        "volume": float(volumes[i]) if i < len(volumes) else 0.0,
                        "block": str(block_ids[i]) if i < len(block_ids) else "",
                        "market": "US",
                    }
                with self._cache_lock:
                    self._us_last_symbol_snapshot = snapshot
                    self._us_last_snapshot_time = timestamp
            except Exception as e:
                log.debug(f"[US-Hotspot] 更新美股快照失败: {e}")

        if not result['degraded']:
            with self._cache_lock:
                self._last_valid_result = final_result

        if _PERFORMANCE_MONITORING_AVAILABLE:
            record_component_execution(
                component_id="hotspot_system",
                component_name="市场热点系统",
                component_type=ComponentType.STRATEGY,
                execution_time_ms=latency,
                success=not result['degraded']
            )

        self._publish_hotspot_event(market, global_hotspot, activity,
                                    block_hotspot, symbol_weights, symbols)

        return final_result

    def process_us_snapshot(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        prices: np.ndarray,
        block_ids: np.ndarray,
        timestamp: float
    ) -> Dict[str, Any]:
        """
        处理美股市场快照（独立于A股的热点计算）

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组 (%)
            volumes: 成交量数组
            prices: 价格数组
            block_ids: 题材ID数组（题材名称）
            timestamp: 时间戳

        Returns:
            调度决策结果（包含美股专属的热点数据）
        """
        if not self._initialized:
            log.warning("[US-Hotspot] 市场热点系统未初始化，跳过美股处理")
            return {
                'timestamp': timestamp,
                'global_hotspot': 0.5,
                'block_hotspot': {},
                'symbol_weights': {},
                'market': 'US',
            }

        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        volumes = np.clip(volumes, 0, 1e15)
        prices = np.nan_to_num(prices, nan=0.0, posinf=1e6, neginf=0.0)
        prices = np.clip(prices, 0.01, 1e6)
        log.debug(f"[US-Hotspot] process_us_snapshot: symbols={len(symbols)}, returns={returns[:5] if len(returns) > 5 else returns}")

        result = self.process_snapshot(
            symbols=symbols,
            returns=returns,
            volumes=volumes,
            prices=prices,
            block_ids=block_ids,
            timestamp=timestamp,
            market='US',
        )

        block_hotspot = result.get('block_hotspot', {})
        if block_hotspot:
            self._push_cross_market_block_changes(block_hotspot)

        return result

    def _push_cross_market_block_changes(self, current_block_hotspot: Dict[str, float]):
        """检测美股题材显著变化并推送到跨市场记忆"""
        if not current_block_hotspot:
            return

        block_changes = {}
        for block, weight in current_block_hotspot.items():
            prev_weight = self._us_prev_block_hotspot.get(block, 0.0)
            change = weight - prev_weight

            if change >= self._us_block_change_threshold:
                block_changes[block] = change
                log.info(f"[CrossMarket] 检测到美股题材显著变化: {block} {prev_weight:.3f} → {weight:.3f} (变化: {change:+.3f})")

        if block_changes:
            try:
                from deva.naja.knowledge.alaya.awakened_alaya import AwakenedAlaya
                alaya = AwakenedAlaya()
                if hasattr(alaya, 'cross_market_memory') and alaya.cross_market_memory:
                    pushed = alaya.cross_market_memory.push_block_change(block_changes)
                    if pushed:
                        log.info(f"[CrossMarket] 成功推送 {len(pushed)} 个A股预测")
            except Exception as e:
                log.warning(f"[CrossMarket] 推送跨市场题材变化失败: {e}")

        self._us_prev_block_hotspot = current_block_hotspot.copy()

    def get_cn_hotspot_state(self) -> Dict[str, Any]:
        """获取A股热点状态"""
        with self._cache_lock:
            return {
                'hotspot': self._last_global_hotspot,
                'activity': self._last_activity,
                'block_hotspot': self._last_block_hotspot.copy(),
                'symbol_weights': self._last_symbol_weights.copy(),
            }

    def get_us_hotspot_state(self) -> Dict[str, Any]:
        """获取美股热点状态"""
        with self._cache_lock:
            symbol_changes = {
                sym: data.get("change", 0.0)
                for sym, data in self._us_last_symbol_snapshot.items()
            }
            current_time = time.time()
            if current_time - self._us_futures_cache_time > self._us_futures_cache_ttl:
                self._update_us_futures_cache_no_lock()
            futures = self._us_futures_cache.copy()
            sw = self._us_last_symbol_weights.copy()
            log.debug(f"[MHS-get_us] _us_last_symbol_weights count={len(sw)}, sample={list(sw.items())[:3] if sw else 'empty'}")
            return {
                'global_hotspot': self._us_last_global_hotspot,
                'activity': self._us_last_activity,
                'block_hotspot': self._us_last_block_hotspot.copy(),
                'symbol_weights': sw,
                'symbol_changes': symbol_changes,
                'stock_count': len(sw),
                'futures_indices': futures,
            }

    def get_us_symbol_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """获取美股最新symbol快照"""
        with self._cache_lock:
            return self._us_last_symbol_snapshot.copy()

    def _update_us_futures_cache_no_lock(self):
        """内部方法：更新美股期货指数缓存（不带锁，需在持有锁时调用）"""
        try:
            import urllib.request
            url = "https://hq.sinajs.cn/list=hf_NQ,hf_ES,hf_YM"
            headers = {
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0"
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read().decode('gbk', errors='replace')

            for line in data.split('\n'):
                if 'hq_str_hf_NQ' in line and '"' in line:
                    fields = line.split('"')[1].split(',')
                    if len(fields) > 9:
                        try:
                            cur, prev = float(fields[0]), float(fields[8])
                            self._us_futures_cache['NQ'] = round(
                                (cur - prev) / prev * 100, 2) if prev else 0
                        except:
                            pass
                elif 'hq_str_hf_ES' in line and '"' in line:
                    fields = line.split('"')[1].split(',')
                    if len(fields) > 9:
                        try:
                            cur, prev = float(fields[0]), float(fields[8])
                            self._us_futures_cache['ES'] = round(
                                (cur - prev) / prev * 100, 2) if prev else 0
                        except:
                            pass
                elif 'hq_str_hf_YM' in line and '"' in line:
                    fields = line.split('"')[1].split(',')
                    if len(fields) > 9:
                        try:
                            cur, prev = float(fields[0]), float(fields[8])
                            self._us_futures_cache['YM'] = round(
                                (cur - prev) / prev * 100, 2) if prev else 0
                        except:
                            pass

            self._us_futures_cache_time = time.time()
        except Exception as e:
            log.debug(f"[MarketHotspotSystem] 更新期货缓存失败: {e}")

    def get_us_futures_indices(self) -> Dict[str, float]:
        """获取美股期货指数缓存"""
        with self._cache_lock:
            return self._us_futures_cache.copy()

    def get_cn_indices(self) -> Dict[str, float]:
        """获取A股指数缓存"""
        with self._cache_lock:
            current_time = time.time()
            if current_time - self._cn_index_cache_time > self._cn_index_cache_ttl:
                self._update_cn_index_cache_no_lock()
            return self._cn_index_cache.copy()

    def _update_cn_index_cache_no_lock(self):
        """内部方法：更新A股指数缓存（不带锁，需在持有锁时调用）"""
        try:
            import urllib.request
            url = "https://hq.sinajs.cn/list=sh000001,s_sh000300,sz399006"
            headers = {
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0"
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read().decode('gbk', errors='replace')

            for line in data.split('\n'):
                if 'hq_str_sh000001' in line and '"' in line:
                    fields = line.split('"')[1].split(',')
                    if len(fields) > 2:
                        try:
                            cur, prev = float(fields[1]), float(fields[2])
                            self._cn_index_cache['SH'] = round(
                                (cur - prev) / prev * 100, 2) if prev else 0
                        except:
                            pass
                elif 'hq_str_s_sh000300' in line and '"' in line:
                    fields = line.split('"')[1].split(',')
                    if len(fields) > 3:
                        try:
                            self._cn_index_cache['HS300'] = float(fields[3])
                        except:
                            pass
                elif 'hq_str_sz399006' in line and '"' in line:
                    fields = line.split('"')[1].split(',')
                    if len(fields) > 2:
                        try:
                            cur, prev = float(fields[1]), float(fields[2])
                            self._cn_index_cache['CHINEXT'] = round(
                                (cur - prev) / prev * 100, 2) if prev else 0
                        except:
                            pass

            self._cn_index_cache_time = time.time()
        except Exception as e:
            log.debug(f"[MarketHotspotSystem] 更新A股指数缓存失败: {e}")

    async def process_pytorch_batch(self) -> List[Any]:
        """处理 PyTorch 批量推理"""
        return await self.dual_engine.process_pytorch_batch()

    def get_symbols_for_frequency(self, level: FrequencyLevel, market: str = 'CN') -> List[str]:
        """获取指定频率档位的所有个股"""
        return self._get_context(market).frequency_scheduler.get_symbols_by_level(level)

    def get_high_hotspot_symbols(self, threshold: float = 2.0) -> List[Tuple[str, float]]:
        """获取高热点个股"""
        view = WeightPoolView(self.weight_pool)
        return view.get_high_hotspot_symbols(threshold)

    def get_active_blocks(self, threshold: float = 0.3) -> List[str]:
        """获取活跃题材"""
        return self.block_hotspot.get_active_blocks(threshold)

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        avg_latency = (
            self._total_latency / max(self._processing_count, 1)
        )

        fetcher_status = None
        if self._realtime_fetcher:
            fetcher_status = self._realtime_fetcher.get_stats()
        else:
            from deva.naja.market_hotspot.data.async_fetcher import get_data_fetcher
            singleton_fetcher = get_data_fetcher()
            if singleton_fetcher:
                fetcher_status = singleton_fetcher.get_stats()

        cn_high = cn_med = cn_low = 0
        us_high = us_med = us_low = 0

        cn_fs = self._cn_context.frequency_scheduler
        us_fs = self._us_context.frequency_scheduler

        for symbol in cn_fs._symbol_to_idx.keys():
            level = cn_fs.get_symbol_level(symbol)
            if level.value == 2:
                cn_high += 1
            elif level.value == 1:
                cn_med += 1
            else:
                cn_low += 1

        for symbol in us_fs._symbol_to_idx.keys():
            level = us_fs.get_symbol_level(symbol)
            if level.value == 2:
                us_high += 1
            elif level.value == 1:
                us_med += 1
            else:
                us_low += 1

        return {
            'initialized': self._initialized,
            'processing_count': self._processing_count,
            'avg_latency_ms': avg_latency,
            'last_snapshot_time': self._last_snapshot_time,
            'global_hotspot': self._last_global_hotspot,
            'activity': self._last_activity,
            'frequency_summary': cn_fs.get_schedule_summary(),
            'strategy_summary': self._cn_context.strategy_allocator.get_allocation_summary(),
            'dual_engine_summary': self._cn_context.dual_engine.get_trigger_summary(),
            'realtime_fetcher': fetcher_status,
            'cn_frequency': {'high': cn_high, 'medium': cn_med, 'low': cn_low},
            'us_frequency': {'high': us_high, 'medium': us_med, 'low': us_low},
        }

    def get_datasource_control(self, market: str = 'CN') -> Dict[str, Any]:
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
        ctx = self._get_context(market)
        fs = ctx.frequency_scheduler
        high_freq = fs.get_symbols_by_level(FrequencyLevel.HIGH)
        medium_freq = fs.get_symbols_by_level(FrequencyLevel.MEDIUM)
        low_freq = fs.get_symbols_by_level(FrequencyLevel.LOW)

        config = fs.config

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
        self._cn_context.global_hotspot.reset()
        self._cn_context.block_engine.reset()
        self._cn_context.weight_pool.reset()
        self._cn_context.frequency_scheduler.reset()
        self._cn_context.strategy_allocator.reset()
        self._cn_context.dual_engine.reset()

        self._us_context.global_hotspot.reset()
        self._us_context.block_engine.reset()
        self._us_context.weight_pool.reset()
        self._us_context.frequency_scheduler.reset()
        self._us_context.strategy_allocator.reset()
        self._us_context.dual_engine.reset()

        with self._cache_lock:
            self._processing_count = 0
            self._total_latency = 0.0
            self._last_global_hotspot = 0.0
            self._last_block_hotspot.clear()
            self._last_symbol_weights.clear()
            self._last_valid_result = None

        self._step_failures.clear()
        self._step_circuit_open.clear()

    def _publish_hotspot_event(
        self,
        market: str,
        global_hotspot: float,
        activity: float,
        block_hotspot: Dict[str, float],
        symbol_weights: Dict[str, float],
        symbols: np.ndarray
    ):
        """发布热点计算完成事件到事件总线"""
        try:
            from deva.naja.events import get_event_bus, HotspotComputedEvent
            event_bus = get_event_bus()
            event = HotspotComputedEvent(
                market=market,
                timestamp=time.time(),
                global_hotspot=global_hotspot,
                activity=activity,
                block_hotspot=block_hotspot,
                symbol_weights=symbol_weights,
                symbols=list(symbols) if symbols is not None else []
            )
            event_bus.publish(event)
        except Exception as e:
            log.debug(f"[MarketHotspotSystem] 发布热点事件失败: {e}")

    def save_state(self) -> Dict[str, Any]:
        """保存市场热点系统状态用于持久化（包含A股和美股）"""
        return {
            'cn_context': self._cn_context.save_state(),
            'us_context': self._us_context.save_state(),
            'us_last_global_hotspot': self._us_last_global_hotspot,
            'us_last_activity': self._us_last_activity,
            'us_last_block_hotspot': self._us_last_block_hotspot,
            'us_last_symbol_weights': self._us_last_symbol_weights,
            'us_last_snapshot_time': self._us_last_snapshot_time,
        }

    def load_state(self, state: Dict[str, Any]) -> bool:
        """从持久化状态恢复市场热点系统"""
        try:
            if not state:
                return False

            if 'cn_context' in state or 'us_context' in state:
                if 'cn_context' in state:
                    self._cn_context = MarketContext.load_state(state.get('cn_context', {}))
                if 'us_context' in state:
                    self._us_context = MarketContext.load_state(state.get('us_context', {}))
                # 重新对齐兼容字段
                self.global_hotspot = self._cn_context.global_hotspot
                self.block_hotspot = self._cn_context.block_engine
                self.weight_pool = self._cn_context.weight_pool
                self.frequency_scheduler = self._cn_context.frequency_scheduler
                self.frequency_controller = self._cn_context.frequency_controller
                self.strategy_allocator = self._cn_context.strategy_allocator
                self.dual_engine = self._cn_context.dual_engine
                self._us_global_hotspot = self._us_context.global_hotspot
                self._us_block_hotspot = self._us_context.block_engine
                self._us_weight_pool = self._us_context.weight_pool
            else:
                # 兼容旧结构
                self.global_hotspot.load_state(state.get('global_hotspot', {}))
                self.block_hotspot.load_state(state.get('block_hotspot', {}))
                self.weight_pool.load_state(state.get('weight_pool', {}))
                self.frequency_scheduler.load_state(state.get('frequency_scheduler', {}))
                self._us_global_hotspot.load_state(state.get('us_global_hotspot', {}))
                self._us_block_hotspot.load_state(state.get('us_block_hotspot', {}))
                self._us_weight_pool.load_state(state.get('us_weight_pool', {}))

            self._us_last_global_hotspot = state.get('us_last_global_hotspot', 0.0)
            self._us_last_activity = state.get('us_last_activity', 0.0)
            self._us_last_block_hotspot = state.get('us_last_block_hotspot', {})
            self._us_last_symbol_weights = state.get('us_last_symbol_weights', {})
            self._us_last_snapshot_time = state.get('us_last_snapshot_time', 0.0)

            log.info("[MarketHotspotSystem] 状态恢复完成")
            return True
        except Exception as e:
            log.warning(f"[MarketHotspotSystem] load_state 失败: {e}")
            return False



# MarketHotspotSystemIntegration 已移至 system_integration.py
