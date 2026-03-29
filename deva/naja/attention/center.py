"""
Attention Orchestrator - 注意力编排器

核心职责：
1. 接收所有数据源的数据
2. 通过 AttentionKernel 计算事件级注意力
3. 协调板块/个股权重计算
4. 根据注意力动态调度策略执行
5. 提供统一的查询接口

架构：
Radar/DataSource → AttentionKernel → AttentionOrchestrator → CognitionEngine → Strategy/Bandit
"""

import time
import sys
import threading
import asyncio
import os
from typing import Dict, List, Optional, Set, Callable, Any
from collections import defaultdict
import logging


def _lab_debug_log(msg: str):
    """实验室模式调试日志"""
    if os.environ.get("NAJA_LAB_DEBUG") == "true":
        logging.getLogger(__name__).info(f"[Lab-Debug] {msg}")


import numpy as np

try:
    import pandas as pd
except Exception:
    pd = None

from .integration.extended import get_attention_integration
from .processing import get_noise_filter, NoiseFilterConfig, get_tick_noise_filter, TickNoiseFilterConfig

try:
    from deva.naja.config import get_noise_filter_config
except ImportError:
    def get_noise_filter_config():
        return {}

try:
    from deva.naja.performance import record_component_execution, ComponentType
    _PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    _PERFORMANCE_MONITORING_AVAILABLE = False

log = logging.getLogger(__name__)


class AttentionOrchestrator:
    """
    注意力编排器

    作为数据源和策略之间的中间层：
    - 数据源始终emit全量数据
    - 编排器协调 AttentionKernel 和注意力系统
    - 策略通过编排器获取数据（已过滤）

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局协调器：AttentionOrchestrator 是流式计算系统的核心协调器，负责
       接收所有数据源数据、计算注意力、协调策略执行。必须全局唯一。

    2. 状态一致性：注意力计算、市场状态、板块映射等信息需要在全系统保持一致。
       如果存在多个实例，会导致状态分裂，系统行为不可预测。

    3. 资源管理：AttentionKernel 等核心计算组件本身就是单例的，作为协调器的
       AttentionOrchestrator 也必须是单例才能正确访问这些资源。

    4. 生命周期：协调器的生命周期与系统一致，随系统启动和关闭。

    5. 这是流式计算系统的设计选择，不是过度工程。
    ================================================================================
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._init_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        pass

    def _ensure_initialized(self):
        if getattr(self, '_initialized', False):
            return
        with self._init_lock:
            if getattr(self, '_initialized', False):
                return

            self._integration = get_attention_integration()

            self._state_lock = threading.RLock()

            self._strategies: Dict[str, Dict] = {}
            self._datasources: Dict[str, Dict] = {}

            self._last_attention_update = 0
            self._attention_cache_ttl = 0.1
            self._cached_high_attention_symbols: Set[str] = set()
            self._cached_active_sectors: Set[str] = set()
            self._cached_market_time_str: str = ""

            self._sector_id_map: Dict[str, int] = {}
            self._next_sector_id = 1

            self._processed_frames = 0
            self._filtered_frames = 0
            self._noise_filtered_count = 0

            self._last_noise_log_time = 0
            self._noise_log_interval = 60

            self._init_attention_kernel()

            from .pipeline import PipelineManager, PipelineConfig
            pipeline_config = PipelineConfig(
                name="attention_pipeline",
                stop_on_error=False,
                enable_stats=True,
            )
            self._pipeline = PipelineManager(pipeline_config)

            from deva.naja.common.data_quality_gate import DataQualityGate
            self._quality_gate = DataQualityGate()

            from .pipeline import EnrichStage
            self._enrich_stage = EnrichStage(name="enrich_sector", use_direct_load=True)
            self._pipeline.add_stage(self._enrich_stage)

            from .pipeline import FilterStage
            self._filter_stage = FilterStage(
                name="filter_noise",
                min_amount=1_000_000,
                min_volume=100_000,
            )
            self._pipeline.add_stage(self._filter_stage)

            try:
                from deva.naja.cognition.cross_signal_analyzer import get_cross_signal_analyzer
                self._cross_analyzer = get_cross_signal_analyzer()
                _lab_debug_log("跨信号分析器已初始化")
            except Exception as e:
                _lab_debug_log(f"跨信号分析器初始化失败: {e}")
                self._cross_analyzer = None

            nf_config = get_noise_filter_config()

            noise_config = NoiseFilterConfig(
                min_amount=nf_config.get('min_amount', 1_000_000),
                min_volume=nf_config.get('min_volume', 100_000),
                min_price=nf_config.get('min_price', 1.0),
                blacklist=set(nf_config.get('blacklist', [])),
                whitelist=set(nf_config.get('whitelist', [])),
                dynamic_threshold=True,
                filter_b_shares=nf_config.get('filter_b_shares', True),
                filter_st=nf_config.get('filter_st', False),
            )
            self._noise_filter = get_noise_filter(noise_config) if nf_config.get('enabled', True) else None

            tick_config = TickNoiseFilterConfig(
                min_amount=nf_config.get('min_amount', 1_000_000),
                min_volume=nf_config.get('min_volume', 100_000),
                min_price=nf_config.get('min_price', 1.0),
                max_price=nf_config.get('max_price', 1000.0),
                max_price_change_pct=nf_config.get('max_price_change_pct', 20.0),
                flat_threshold=nf_config.get('flat_threshold', 0.5),
                flat_consecutive_frames=nf_config.get('flat_consecutive_frames', 10),
                wash_trading_volume_ratio=nf_config.get('wash_trading_volume_ratio', 3.0),
                wash_trading_price_change_max=nf_config.get('wash_trading_price_change_max', 0.5),
                abnormal_volatility_threshold=nf_config.get('abnormal_volatility_threshold', 10.0),
                filter_b_shares=nf_config.get('filter_b_shares', True),
                filter_st=nf_config.get('filter_st', False),
                blacklist=set(nf_config.get('blacklist', [])),
                whitelist=set(nf_config.get('whitelist', [])),
            )
            self._tick_noise_filter = get_tick_noise_filter(tick_config) if nf_config.get('enabled', True) else None
            self._tick_noise_reports = []

            self._pytorch_processing = False
            self._pytorch_thread = None
            self._start_pytorch_processor()

            self._initialized = True
            log.info("AttentionOrchestrator 初始化完成")

            self._initialize_strategies()

    def _initialize_strategies(self):
        """初始化注意力策略"""
        try:
            from deva.naja.attention.strategies import initialize_attention_strategies
            mgr = initialize_attention_strategies()
            log.info(f"注意力策略系统已初始化: {len(mgr.strategies)} 个策略, is_running={mgr.is_running}")
        except Exception as e:
            log.error(f"初始化注意力策略失败: {e}")
            import traceback
            log.error(traceback.format_exc())

    def _init_attention_kernel(self):
        """初始化 AttentionKernel 事件级注意力核心"""
        try:
            from .kernel import (
                AttentionEvent,
                QueryState,
                Encoder,
                MultiHeadAttention,
                AttentionMemory,
                AttentionKernel,
                get_default_heads,
            )

            encoder = Encoder()
            heads = get_default_heads()
            multi_head = MultiHeadAttention(heads)
            memory = AttentionMemory(decay_rate=300)

            self._attention_kernel = AttentionKernel(encoder, multi_head, memory, enable_four_dimensions=False)
            self._attention_query_state = QueryState()

            self._init_four_dimensions_manager()

            _lab_debug_log("AttentionKernel 初始化完成，四维决策框架管理器已就绪（条件触发）")
        except Exception as e:
            log.error(f"AttentionKernel 初始化失败: {e}")
            self._attention_kernel = None
            self._attention_query_state = None

    def _init_four_dimensions_manager(self):
        """初始化四维决策框架管理器"""
        try:
            from .kernel import (
                setup_four_dimensions_manager,
                TriggerConfig,
            )

            config = TriggerConfig(
                auto_enable_low_cash=True,
                auto_enable_extreme_market=True,
                low_cash_threshold=0.2,
                extreme_low_signal=0.3,
                extreme_high_signal=0.8,
            )

            self._four_dimensions_manager = setup_four_dimensions_manager(
                self._attention_kernel, config
            )

            _lab_debug_log("四维决策框架管理器初始化完成")
        except Exception as e:
            log.error(f"四维决策框架管理器初始化失败: {e}")
            self._four_dimensions_manager = None

    def get_four_dimensions_manager(self):
        """获取四维决策框架管理器"""
        return getattr(self, '_four_dimensions_manager', None)

    def get_attention_kernel(self):
        """获取 AttentionKernel 实例"""
        return self._attention_kernel

    def get_query_state(self):
        """获取 QueryState 实例"""
        return self._attention_query_state

    def _update_four_dimensions(self):
        """更新四维决策框架状态（条件触发）"""
        manager = self.get_four_dimensions_manager()
        if manager:
            manager.update()

    def _process_with_kernel(self, data, symbols, returns, volumes, prices, timestamp):
        """使用 AttentionKernel 处理市场快照数据"""
        if self._attention_kernel is None or self._attention_query_state is None:
            return None

        try:
            from .kernel import AttentionEvent

            events = []
            for i in range(len(symbols)):
                symbol = str(symbols[i]) if i < len(symbols) else f"unknown_{i}"
                price_change = float(returns[i]) if i < len(returns) else 0.0
                volume_spike = float(volumes[i]) / 1e6 if i < len(volumes) else 0.0
                sentiment = 0.5
                historical_alpha = 0.0

                event = AttentionEvent(
                    source="market",
                    data={"symbol": symbol, "price": float(prices[i]) if i < len(prices) else 0.0},
                    features={
                        "price_change": price_change,
                        "sentiment": sentiment,
                        "volume_spike": volume_spike,
                        "historical_alpha": historical_alpha,
                        "alpha": abs(price_change) * 0.5 + volume_spike * 0.3,
                        "risk": abs(price_change) * 0.8,
                        "confidence": min(1.0, volume_spike * 0.5 + abs(price_change) * 10),
                    },
                    timestamp=timestamp
                )
                events.append(event)

            if not events:
                return None

            result = self._attention_kernel.process(self._attention_query_state, events)

            _lab_debug_log(f"[Kernel] 处理 {len(events)} 个事件: alpha={result.get('alpha', 0):.4f}, confidence={result.get('confidence', 0):.4f}")

            return result

        except Exception as e:
            log.debug(f"[Kernel] 处理失败: {e}")
            return None

    @property
    def _cached_global_attention(self) -> float:
        """直接代理到 attention_system，消除缓存同步问题"""
        return self._integration.attention_system._last_global_attention

    @property
    def _cached_activity(self) -> float:
        """直接代理到 attention_system，消除缓存同步问题"""
        return self._integration.attention_system._last_activity

    def _start_pytorch_processor(self):
        """启动 PyTorch 队列处理线程"""
        if self._pytorch_processing:
            return

        self._pytorch_processing = True
        self._pytorch_thread = threading.Thread(target=self._pytorch_loop, daemon=True)
        self._pytorch_thread.start()
        log.info("PyTorch 队列处理线程已启动")

    def _pytorch_loop(self):
        """PyTorch 队列处理循环"""
        log.info("PyTorch 处理循环开始运行")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while self._pytorch_processing:
            try:
                if (self._integration.attention_system is None or
                    self._integration.attention_system.dual_engine is None):
                    time.sleep(5)
                    continue

                dual_engine = self._integration.attention_system.dual_engine
                pytorch = dual_engine.pytorch

                queue_size = len(pytorch._pending_queue)

                if queue_size > 0:
                    current_time = time.time()
                    if not hasattr(self, '_last_queue_log_time'):
                        self._last_queue_log_time = 0
                    if queue_size >= 500 and current_time - self._last_queue_log_time >= 60:
                        log.info(f"[PyTorchProcessor] 队列中有 {queue_size} 个待处理信号，开始处理...")
                        self._last_queue_log_time = current_time

                    try:
                        results = loop.run_until_complete(pytorch.process_batch())
                        if results and len(results) >= 100:
                            log.info(f"[PyTorchProcessor] 完成 {len(results)} 个推理")
                    except Exception as e:
                        log.error(f"[PyTorchProcessor] 处理失败: {e}")

                time.sleep(2)

            except Exception as e:
                log.error(f"[PyTorchProcessor] 循环错误: {e}")
                time.sleep(5)

        loop.close()
        log.info("PyTorch 处理循环已停止")

    def stop_pytorch_processor(self):
        """停止 PyTorch 队列处理"""
        self._pytorch_processing = False
        if self._pytorch_thread:
            self._pytorch_thread.join(timeout=5)

    def register_strategy(self,
                         strategy_id: str,
                         strategy_type: str,
                         callback: Callable,
                         min_attention: float = 0.0,
                         filter_by_attention: bool = True):
        """注册策略到调度中心"""
        self._strategies[strategy_id] = {
            'type': strategy_type,
            'callback': callback,
            'min_attention': min_attention,
            'filter_by_attention': filter_by_attention,
            'registered_at': time.time()
        }
        log.info(f"策略 {strategy_id} 已注册到调度中心 (类型: {strategy_type})")

    def unregister_strategy(self, strategy_id: str):
        """注销策略"""
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
            log.info(f"策略 {strategy_id} 已从调度中心注销")

    def register_datasource(self, datasource_id: str, config: Optional[Dict] = None):
        """注册数据源到调度中心"""
        self._datasources[datasource_id] = {
            'config': config or {},
            'registered_at': time.time(),
            'is_experiment': config.get('is_experiment', False) if config else False
        }
        log.info(f"数据源 {datasource_id} 已注册到调度中心")

    def unregister_datasource(self, datasource_id: str):
        """注销数据源"""
        if datasource_id in self._datasources:
            del self._datasources[datasource_id]
            log.info(f"数据源 {datasource_id} 已从调度中心注销")

    def process_datasource_data(self, datasource_id: str, data: Any) -> None:
        """处理数据源数据"""
        _lab_debug_log(f"[Center] process_datasource_data called: datasource={datasource_id}, data_type={type(data)}")

        if pd is None or not isinstance(data, pd.DataFrame):
            log.debug(f"[Center] 数据源 {datasource_id} 数据格式不正确，跳过")
            return

        start_time = time.time()
        self._processed_frames += 1

        quality_report = self._quality_gate.validate(data, context=datasource_id)
        if not quality_report.passed:
            log.error(f"[Center] 数据质量不合格: {quality_report.failed_count} 项失败")
            return
        if quality_report.warning_count > 0:
            log.info(f"[Center] 数据质量有警告: {quality_report.warning_count} 项")

        pipeline_result = self._pipeline.execute(data, context={'datasource_id': datasource_id})

        if pipeline_result.passed:
            data = pipeline_result.data
            if pipeline_result.warning:
                if self._processed_frames % 10 == 0:
                    log.warning(f"[Center] Pipeline 警告: {pipeline_result.warning}")
        else:
            log.error(f"[Center] Pipeline 执行失败: {pipeline_result.error}")
            return

        if self._processed_frames % 10 == 0:
            log.info(f"[Center] 已处理 {self._processed_frames} 帧数据, Pipeline: {pipeline_result.rows_in}→{pipeline_result.rows_out}")

        print(f"[DEBUG] About to call _dispatch_to_strategies, data rows={len(data)}")
        try:
            self._update_attention(data)
        except Exception as e:
            print(f"[ERROR] _update_attention failed: {e}")
            import traceback
            traceback.print_exc()
            return
        print(f"[DEBUG] _update_attention done, calling _dispatch_to_strategies")
        _lab_debug_log(f"[Center] _update_attention 完成, 调用 _dispatch_to_strategies")
        print(f"[DEBUG] Calling _dispatch_to_strategies now")
        self._dispatch_to_strategies(datasource_id, data)
        print(f"[DEBUG] _dispatch_to_strategies returned")

        self._update_four_dimensions()

        if _PERFORMANCE_MONITORING_AVAILABLE:
            latency = (time.time() - start_time) * 1000
            record_component_execution(
                component_id=f"attention_center_{datasource_id}",
                component_name=f"注意力调度中心: {datasource_id}",
                component_type=ComponentType.DATASOURCE,
                execution_time_ms=latency,
                success=True
            )

    def _update_attention(self, data: pd.DataFrame):
        """更新注意力系统"""
        print(f"[DEBUG] _update_attention ENTER")
        sys.stdout.flush()
        if self._integration.attention_system is None or not self._integration.attention_system._initialized:
            log.warning("注意力系统未初始化，尝试自动初始化...")
            try:
                from .integration.extended import initialize_attention_system
                from .config import load_config
                config = load_config()
                if config.enabled:
                    initialize_attention_system(config.to_attention_system_config())
                    log.warning("注意力系统自动初始化成功")
                else:
                    log.warning("注意力系统未启用 (enabled=False)，跳过")
                    return
            except Exception as e:
                log.error(f"注意力系统自动初始化失败: {e}")
                import traceback
                log.error(traceback.format_exc())
                return

        current_time = time.time()
        if current_time - self._last_attention_update < self._attention_cache_ttl:
            return

        try:
            should_log_noise = current_time - self._last_noise_log_time >= self._noise_log_interval

            if self._noise_filter:
                original_count = len(data)
                filtered_data = self._noise_filter.filter_dataframe(
                    data,
                    symbol_col='code' if 'code' in data.columns else data.index.name or 'code',
                    amount_col='amount' if 'amount' in data.columns else None,
                    volume_col='volume' if 'volume' in data.columns else None,
                    price_col='now' if 'now' in data.columns else ('close' if 'close' in data.columns else None),
                    name_col='name' if 'name' in data.columns else ('stock_name' if 'stock_name' in data.columns else None)
                )
                filtered_count = original_count - len(filtered_data)
                self._noise_filtered_count += filtered_count

                if should_log_noise:
                    log.info(f"[基础噪音过滤] 原始{original_count}条 -> 过滤后{len(filtered_data)}条 (过滤{filtered_count}条, 过滤率{filtered_count/max(original_count,1)*100:.1f}%)")

                if len(filtered_data) == 0:
                    log.warning("⚠️ 基础噪音过滤后数据为空！所有股票都被过滤了")
                    filtered_data = data
                    log.info("[回退] 使用原始数据，跳过基础噪音过滤")

                data = filtered_data

            if self._tick_noise_filter and not data.empty:
                tick_original_count = len(data)
                filtered_data, tick_reports = self._tick_noise_filter.filter_dataframe(
                    data,
                    symbol_col='code',
                    name_col='name',
                    price_col='now',
                    close_col='close',
                    volume_col='volume',
                    amount_col='amount',
                    high_col='high' if 'high' in data.columns else 'now',
                    low_col='low' if 'low' in data.columns else 'now',
                    open_col='open' if 'open' in data.columns else 'close'
                )
                tick_filtered_count = tick_original_count - len(filtered_data)

                if should_log_noise:
                    log.info(f"[Tick噪音过滤] 原始{tick_original_count}条 -> 过滤后{len(filtered_data)}条 (过滤{tick_filtered_count}条, 过滤率{tick_filtered_count/max(tick_original_count,1)*100:.1f}%)")
                    self._last_noise_log_time = current_time

                if len(filtered_data) == 0:
                    log.warning("⚠️ Tick噪音过滤后数据为空！所有股票都被过滤了")
                    filtered_data = data
                    log.info("[回退] 使用原始数据，跳过Tick噪音过滤")
                elif tick_filtered_count > 0:
                    noise_reports = [r for r in tick_reports if r.is_noise]
                    if noise_reports:
                        noise_types = {}
                        for r in noise_reports:
                            for t in r.noise_types:
                                noise_types[t.value] = noise_types.get(t.value, 0) + 1
                        log.debug(f"  噪音类型分布: {noise_types}")

                self._tick_noise_reports = tick_reports
                data = filtered_data

            if data.empty:
                log.debug("过滤后数据为空，跳过本次更新")
                return

            code_col = 'code' if 'code' in data.columns else data.index.name
            symbols = data.index.values if code_col == data.index.name else data[code_col].values

            if 'p_change' in data.columns:
                returns = data['p_change'].values
            else:
                close_values = data['close'].values
                now_values = data['now'].values
                returns = np.where(
                    close_values > 0.01,
                    (now_values - close_values) / close_values * 100,
                    0.0
                )

            returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
            returns = np.clip(returns, -50.0, 50.0)

            volumes = data['volume'].values if 'volume' in data.columns else np.ones(len(symbols)) * 1000000
            volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
            volumes = np.clip(volumes, 0, 1e15)

            prices = data['now'].values if 'now' in data.columns else data['close'].values
            prices = np.nan_to_num(prices, nan=0.0, posinf=1e6, neginf=0.0)
            prices = np.clip(prices, 0.01, 1e6)

            symbols, returns, volumes, prices, sector_ids = self._expand_for_multi_sector(
                symbols, returns, volumes, prices, data, code_col
            )

            market_time = current_time
            market_time_str = None
            if 'date' in data.columns and 'time' in data.columns:
                first_row = data.iloc[0]
                date_val = str(first_row['date'])
                time_val = str(first_row['time'])
                try:
                    from datetime import datetime
                    dt_str = f"{date_val} {time_val}"
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    market_time = dt.timestamp()
                    market_time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass

            # Update QueryState with current market context
            if self._attention_query_state is not None:
                self._attention_query_state.update_from_market(
                    symbols=symbols,
                    returns=returns,
                    volumes=volumes,
                    prices=prices,
                    timestamp=market_time,
                    sector_ids=sector_ids if 'sector' in data.columns else None,
                    sector_map=self._get_sector_map(data),
                )

                self._update_portfolio_state()

                self._update_macro_liquidity_from_scanner()

                self._update_signal_stream_query_state()

            kernel_result = self._process_with_kernel(
                data, symbols, returns, volumes, prices, market_time
            )

            if self._integration.intelligence_system is not None:
                result = self._integration.intelligence_system.process_snapshot(
                    symbols=symbols,
                    returns=returns,
                    volumes=volumes,
                    prices=prices,
                    sector_ids=sector_ids,
                    timestamp=market_time
                )
            else:
                result = self._integration.attention_system.process_snapshot(
                    symbols=symbols,
                    returns=returns,
                    volumes=volumes,
                    prices=prices,
                    sector_ids=sector_ids,
                    timestamp=market_time
                )

            if kernel_result:
                result['kernel_attention'] = kernel_result

            if self._processed_frames % 10 == 0:
                _lab_debug_log(f"process_snapshot result: global_attention={result.get('global_attention')}, sector_attention count={len(result.get('sector_attention', {}))}")

            control = self._integration.get_datasource_control()
            self._cached_high_attention_symbols = set(control.get('high_freq_symbols', []))
            active_ids = set(str(s) for s in self._integration.get_active_sectors(threshold=0.3))
            self._cached_active_sectors = set(active_ids)
            if self._sector_id_map:
                for name, sid in self._sector_id_map.items():
                    if str(sid) in active_ids:
                        self._cached_active_sectors.add(name)

            self._apply_memory_hints(data)

            attention_engine = self._integration.attention_system.global_attention
            history_size = len(attention_engine._history_buffer) if hasattr(attention_engine, '_history_buffer') else 0

            if self._processed_frames % 50 == 0:
                _lab_debug_log(f"[Attention] 注意力: {self._cached_global_attention:.3f}, "
                        f"活跃度: {self._cached_activity:.3f}, "
                        f"历史缓冲: {history_size}/{attention_engine.history_window}, "
                        f"活跃板块: {len(self._cached_active_sectors)}, "
                        f"高注意力个股: {len(self._cached_high_attention_symbols)}")

            if self._processed_frames % 100 == 0:
                dual_summary = result.get('dual_engine_summary', {})
                river_stats = dual_summary.get('river_stats', {})
                _lab_debug_log(f"[River Engine] 处理: {river_stats.get('processed_count', 0)}, "
                        f"异常: {river_stats.get('anomaly_count', 0)}, "
                        f"活跃: {river_stats.get('active_symbols', 0)}")

            try:
                from deva.naja.cognition.history_tracker import get_history_tracker
                tracker = get_history_tracker()

                sector_weights = self._integration.attention_system.sector_attention.get_all_weights()
                symbol_weights = self._integration.attention_system.weight_pool.get_all_weights()

                _lab_debug_log(f"快照记录: sector_weights count={len(sector_weights)}, symbol_weights count={len(symbol_weights)}, tracker.snapshots={len(tracker.snapshots)}")

                self._cached_high_attention_symbols.clear()
                self._cached_active_sectors.clear()

                available = set(str(s) for s in data['code'].values)
                matched = 0
                sample_matched = []
                sample_unmatched = []

                for sym, weight in symbol_weights.items():
                    sym_str = str(sym)
                    if sym_str in available:
                        self._cached_high_attention_symbols.add(sym_str)
                        matched += 1
                        if len(sample_matched) < 3:
                            sample_matched.append(sym_str)
                    else:
                        if len(sample_unmatched) < 3:
                            sample_unmatched.append((sym_str, sym_str in available))

                _lab_debug_log(f"[过滤调试] data codes: {len(available)}, symbol_weights: {len(symbol_weights)}, matched: {matched}")
                if sample_matched:
                    _lab_debug_log(f"[过滤调试] sample matched: {sample_matched}")
                if sample_unmatched:
                    _lab_debug_log(f"[过滤调试] sample unmatched: {sample_unmatched}")

                for sec, weight in sector_weights.items():
                    if weight >= 0.01:
                        self._cached_active_sectors.add(str(sec))

                if sector_weights:
                    from deva.naja.attention.processing.sector_noise_detector import get_sector_noise_detector
                    noise_detector = get_sector_noise_detector()
                    sorted_sectors = sorted(sector_weights.items(), key=lambda x: x[1], reverse=True)
                    valid_sectors = []
                    for s, w in sorted_sectors:
                        sector_name = tracker.get_sector_name(s)
                        if sector_name and sector_name != s and not noise_detector.is_noise(s, sector_name):
                            valid_sectors.append((sector_name, w))
                        if len(valid_sectors) >= 5:
                            break
                    if valid_sectors:
                        _lab_debug_log(f"SectorWeights Top5: {[(f'{n}({w:.2f})') for n, w in valid_sectors]}")

                symbol_market_data = {}
                for idx, row in data.iterrows():
                    symbol = str(row['code']) if 'code' in row else str(idx)
                    price = float(row.get('now', row.get('close', 0)))
                    change = float(row.get('p_change', 0)) if 'p_change' in row else 0.0
                    volume = float(row.get('volume', 0))
                    sector = str(row.get('sector', row.get('industry', ''))) if 'sector' in row or 'industry' in row else ''
                    if symbol:
                        symbol_market_data[symbol] = {
                            'price': price,
                            'change': change,
                            'volume': volume,
                            'sector': sector
                        }

                tracker.record_snapshot(
                    global_attention=self._cached_global_attention,
                    sector_weights=sector_weights,
                    symbol_weights=symbol_weights,
                    timestamp=market_time,
                    timestamp_str=market_time_str,
                    symbol_market_data=symbol_market_data,
                    activity=self._cached_activity
                )

                if 'sector' in data.columns or 'industry' in data.columns:
                    sector_col = 'sector' if 'sector' in data.columns else 'industry'
                    for _, row in data.iterrows():
                        sector_name = str(row.get(sector_col, '')).strip()
                        if sector_name:
                            sector_id = self._sector_id_map.get(sector_name)
                            if sector_id:
                                tracker.register_sector_name(str(sector_id), sector_name)

                if 'code' in data.columns:
                    name_col = 'name' if 'name' in data.columns else ('stock_name' if 'stock_name' in data.columns else None)
                    if name_col:
                        for _, row in data.iterrows():
                            symbol = str(row['code'])
                            name = row.get(name_col, symbol)
                            if symbol and name and name != symbol:
                                tracker.register_symbol_name(symbol, name)

            except Exception as e:
                log.debug(f"记录注意力历史失败: {e}")

            self._notify_cognition()

            self._last_attention_update = current_time

        except Exception as e:
            import traceback
            log.error(f"更新注意力系统失败: {e}")
            log.error(f"错误详情: {traceback.format_exc()}")
            try:
                log.error(f"数据形状: symbols={len(symbols)}, returns={len(returns)}, volumes={len(volumes)}, prices={len(prices)}")
                log.error(f"Returns 范围: [{np.min(returns):.2f}, {np.max(returns):.2f}]")
                log.error(f"Prices 范围: [{np.min(prices):.2f}, {np.max(prices):.2f}]")
                log.error(f"Volumes 范围: [{np.min(volumes):.2f}, {np.max(volumes):.2f}]")
            except:
                pass

    def _notify_cognition(self):
        """通知认知系统（跨信号分析器）注意力更新"""
        if not self._cross_analyzer:
            return

        try:
            from deva.naja.cognition.cross_signal_analyzer import AttentionSnapshot

            snapshot = AttentionSnapshot(
                sector_weights=self._integration.attention_system.sector_attention.get_all_weights() if self._integration.attention_system else {},
                symbol_weights=self._integration.attention_system.weight_pool.get_all_weights() if self._integration.attention_system else {},
                high_attention_symbols=self._cached_high_attention_symbols,
                active_sectors=self._cached_active_sectors,
                global_attention=self._cached_global_attention,
                activity=self._cached_activity,
                timestamp=time.time(),
                sector_names=dict(self._sector_id_map)
            )

            resonances = self._cross_analyzer.ingest_attention(snapshot)

            if resonances and self._processed_frames % 10 == 0:
                _lab_debug_log(f"[Cognition] 检测到 {len(resonances)} 个共振信号")
                for r in resonances[:3]:
                    _lab_debug_log(f"  共振: {r.sector_name} (score={r.resonance_score:.3f}, type={r.resonance_type.value})")

            if self._cross_analyzer.should_trigger_llm():
                self._trigger_llm_analysis()

        except Exception as e:
            log.debug(f"通知认知系统失败: {e}")

    def _trigger_llm_analysis(self):
        """触发LLM分析（认知系统深度分析）"""
        if not self._cross_analyzer:
            return

        try:
            recent_signals = self._cross_analyzer.get_recent_resonances(n=5)
            if not recent_signals:
                return

            prompt = self._cross_analyzer.batch_for_llm(recent_signals)
            _lab_debug_log(f"[Cognition-LLM] 准备LLM分析，信号数: {len(recent_signals)}")

            asyncio.create_task(self._async_llm_analysis(prompt, recent_signals))

        except Exception as e:
            log.debug(f"触发LLM分析失败: {e}")

    async def _async_llm_analysis(self, prompt: str, signals):
        """异步执行LLM分析"""
        try:
            from deva.naja.llm_controller import get_llm_controller
            controller = get_llm_controller()

            if controller is None:
                _lab_debug_log("[Cognition-LLM] LLM控制器未初始化")
                return

            response = await controller.chat(
                prompt=prompt,
                system="你是一个专业的金融市场分析师，擅长识别新闻和行情的共振机会。",
                temperature=0.7
            )

            if response:
                _lab_debug_log(f"[Cognition-LLM] LLM分析完成，响应长度: {len(response)}")

                feedback = self._cross_analyzer.create_feedback(
                    resonance=signals[0] if signals else None,
                    insight_text=response
                )

                self._apply_cognition_feedback(feedback)

        except Exception as e:
            log.debug(f"异步LLM分析失败: {e}")

    def _apply_cognition_feedback(self, feedback):
        """应用认知系统反馈"""
        try:
            adjustment = feedback.attention_adjustment

            if adjustment.get("increase_weight_on"):
                _lab_debug_log(f"[Cognition-Feedback] 建议提高板块权重: {adjustment['increase_weight_on']}")

            if adjustment.get("decrease_weight_on"):
                _lab_debug_log(f"[Cognition-Feedback] 建议降低板块权重: {adjustment['decrease_weight_on']}")

            _lab_debug_log(f"[Cognition-Feedback] 优先级: {feedback.priority}, 操作建议: {feedback.insight_text[:100] if feedback.insight_text else 'N/A'}...")

        except Exception as e:
            log.debug(f"应用认知反馈失败: {e}")

    def _dispatch_to_strategies(self, datasource_id: str, data: pd.DataFrame, market_time: Optional[float] = None):
        """分发数据到各策略"""
        print(f"[DEBUG] _dispatch_to_strategies ENTER: data_rows={len(data)}, cached={len(self._cached_high_attention_symbols)}")
        sys.stdout.flush()
        _lab_debug_log(f"[_dispatch_to_strategies] data行数={len(data)}, cached_symbols={len(self._cached_high_attention_symbols)}")

        if market_time is None and not data.empty:
            try:
                if 'date' in data.columns and 'time' in data.columns:
                    first_row = data.iloc[0]
                    date_val = str(first_row['date'])
                    time_val = str(first_row['time'])
                    from datetime import datetime
                    dt_str = f"{date_val} {time_val}"
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    market_time = dt.timestamp()
            except Exception:
                market_time = time.time()
        elif market_time is None:
            market_time = time.time()

        from .strategies import get_strategy_manager
        strategy_mgr = get_strategy_manager()
        if strategy_mgr is None:
            log.warning("策略管理器未初始化")
            return

        if not strategy_mgr.is_running:
            log.warning(f"策略管理器未运行 (is_running=False)")
            if strategy_mgr.strategies:
                log.info(f"尝试启动策略管理器, 策略数={len(strategy_mgr.strategies)}")
                strategy_mgr.start()

        context = {
            'global_attention': self._cached_global_attention,
            'high_attention_symbols': self._cached_high_attention_symbols,
            'active_sectors': self._cached_active_sectors,
            'datasource_id': datasource_id,
            'market_time': market_time
        }

        print(f"[DEBUG] _dispatch: calling strategy_mgr.process_data with data rows={len(data)}, context keys={list(context.keys())}")
        signals = strategy_mgr.process_data(data, context)
        print(f"[DEBUG] _dispatch: process_data returned {len(signals) if signals else 0} signals")
        if signals:
            log.info(f"🎯 注意力策略生成 {len(signals)} 个信号")
            self._execute_signals(signals)
        elif self._processed_frames % 10 == 0:
            active_count = sum(1 for c in strategy_mgr.configs.values() if c.enabled)
            log.info(f"[策略执行] 帧{self._processed_frames}: 活跃策略={active_count}, 总策略={len(strategy_mgr.strategies)}, 无信号")

    def _filter_by_attention(self, data: pd.DataFrame) -> pd.DataFrame:
        """根据注意力过滤数据，同时排除已有持仓"""
        if not self._cached_high_attention_symbols:
            return data

        held_symbols = set()
        if self._attention_query_state and self._attention_query_state.portfolio_state:
            held_symbols = set(self._attention_query_state.portfolio_state.get("held_symbols", []))

        code_column = 'code' if 'code' in data.columns else data.index.name
        if code_column == 'code':
            filtered = data[data['code'].isin(self._cached_high_attention_symbols)]
        else:
            filtered = data[data.index.isin(self._cached_high_attention_symbols)]

        if held_symbols:
            if code_column == 'code':
                filtered = filtered[~filtered['code'].isin(held_symbols)]
            else:
                filtered = filtered[~filtered.index.isin(held_symbols)]

        return filtered

    def _filter_by_sectors(self, data: pd.DataFrame) -> pd.DataFrame:
        """根据板块过滤数据"""
        if not self._cached_active_sectors:
            return data

        sector_col = None
        if 'sector' in data.columns:
            sector_col = 'sector'
        elif 'industry' in data.columns:
            sector_col = 'industry'

        if sector_col is None:
            return data

        try:
            return data[data[sector_col].astype(str).isin(self._cached_active_sectors)]
        except Exception:
            return data

    def _extract_sector_ids(self, data: pd.DataFrame) -> np.ndarray:
        """从数据中提取板块ID"""
        if 'sector_id' in data.columns:
            try:
                return data['sector_id'].fillna(0).astype(int).values
            except Exception:
                return np.zeros(len(data))

        sector_col = None
        if 'sector' in data.columns:
            sector_col = 'sector'
        elif 'industry' in data.columns:
            sector_col = 'industry'

        if sector_col is not None:
            sector_ids: List[int] = []
            for value in data[sector_col].values:
                name = str(value).strip()
                if not name:
                    sector_ids.append(0)
                    continue
                if name not in self._sector_id_map:
                    self._sector_id_map[name] = self._next_sector_id
                    self._next_sector_id += 1
                sector_ids.append(self._sector_id_map[name])
            return np.array(sector_ids, dtype=int)

        try:
            from deva.naja.attention.integration.extended import get_attention_integration
            integration = get_attention_integration()
            symbol_sector_map = getattr(integration, '_symbol_sector_map', {})
            log.info(f"[_extract_sector_ids] symbol_sector_map size={len(symbol_sector_map)}, integration id={id(integration)}")
            if not symbol_sector_map:
                log.warning(f"[_extract_sector_ids] symbol_sector_map is empty")
                return np.zeros(len(data))

            code_col = 'code' if 'code' in data.columns else data.index.name
            log.info(f"[_extract_sector_ids] code_col={code_col}, data len={len(data)}")
            sector_ids = []
            matched = 0
            sample_count = 0
            for symbol in data[code_col].values if code_col else data.index.values:
                symbol_str = str(symbol)
                sector_list = symbol_sector_map.get(symbol_str, [])
                if sample_count < 3:
                    log.info(f"[_extract_sector_ids] sample: {symbol_str} -> {sector_list}")
                    sample_count += 1
                for sector_id in sector_list:
                    if sector_id != 0:
                        matched += 1
                    sector_ids.append(sector_id if sector_id else 0)
            log.info(f"[_extract_sector_ids] matched {matched}/{len(sector_ids)} sector entries")
            return np.array(sector_ids, dtype=object)
        except Exception as e:
            import traceback
            log.error(f"[_extract_sector_ids] error: {e}")
            log.error(traceback.format_exc())
            return np.zeros(len(data))

    def _expand_for_multi_sector(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        prices: np.ndarray,
        data: pd.DataFrame,
        code_col: str
    ) -> tuple:
        """展开多板块数据，使每个股票-板块组合成为独立的一行"""
        try:
            from deva.naja.attention.integration.extended import get_attention_integration
            integration = get_attention_integration()
            symbol_sector_map = getattr(integration, '_symbol_sector_map', {})

            if not symbol_sector_map:
                sector_ids = self._extract_sector_ids(data)
                return symbols, returns, volumes, prices, sector_ids

            expanded_symbols = []
            expanded_returns = []
            expanded_volumes = []
            expanded_prices = []
            expanded_sector_ids = []

            multi_sector_count = 0
            for i, symbol in enumerate(symbols):
                symbol_str = str(symbol)
                sector_list = symbol_sector_map.get(symbol_str, [])

                if not sector_list:
                    sector_list = ['0']

                for sector_id in sector_list:
                    expanded_symbols.append(symbol_str)
                    expanded_returns.append(returns[i])
                    expanded_volumes.append(volumes[i])
                    expanded_prices.append(prices[i])
                    expanded_sector_ids.append(sector_id if sector_id else 0)
                    if len(sector_list) > 1:
                        multi_sector_count += 1

            if multi_sector_count > 0 and self._processed_frames % 10 == 0:
                log.info(f"[_expand_for_multi_sector] 多板块股票: {multi_sector_count} 条展开记录")

            return (
                np.array(expanded_symbols),
                np.array(expanded_returns),
                np.array(expanded_volumes),
                np.array(expanded_prices),
                np.array(expanded_sector_ids, dtype=object)
            )
        except Exception as e:
            log.error(f"[_expand_for_multi_sector] error: {e}")
            import traceback
            log.error(traceback.format_exc())
            sector_ids = self._extract_sector_ids(data)
            return symbols, returns, volumes, prices, sector_ids

    def _get_sector_map(self, data: pd.DataFrame) -> Dict[str, List[str]]:
        """从数据中提取 symbol -> [sectors] 的映射"""
        sector_col = None
        if 'sector' in data.columns:
            sector_col = 'sector'
        elif 'industry' in data.columns:
            sector_col = 'industry'

        if sector_col is None:
            return {}

        sector_map: Dict[str, List[str]] = {}
        try:
            code_col = 'code' if 'code' in data.columns else data.index.name
            if code_col is None:
                return {}

            for idx, row in data.iterrows():
                code = str(row[code_col]) if code_col in row else str(idx)
                sector = str(row.get(sector_col, '')).strip()
                if code and sector and sector != 'nan':
                    if code not in sector_map:
                        sector_map[code] = []
                    if sector not in sector_map[code]:
                        sector_map[code].append(sector)
        except Exception:
            pass

        return sector_map

    def _execute_signals(self, signals):
        """将信号传递给 Bandit 的 SignalListener 执行"""
        try:
            from deva.naja.signal.stream import get_signal_stream
            from deva.naja.strategy.result_store import StrategyResult
            signal_stream = get_signal_stream()

            for signal in signals:
                if signal.signal_type not in ('buy', 'sell'):
                    continue

                price = 0.0
                if signal.metadata:
                    price = float(signal.metadata.get('price', signal.metadata.get('close', 0)))

                result = StrategyResult(
                    id=f"{signal.strategy_name}_{signal.symbol}_{int(signal.timestamp*1000)}",
                    strategy_id=signal.strategy_name,
                    strategy_name=signal.strategy_name,
                    ts=signal.timestamp,
                    success=True,
                    input_preview=f"{signal.symbol}: {signal.signal_type}",
                    output_preview=f"置信度: {signal.confidence:.2f}, 得分: {signal.score:.3f}",
                    output_full={
                        'signal_type': signal.signal_type.upper(),
                        'stock_code': signal.symbol,
                        'price': price,
                        'confidence': signal.confidence,
                        'score': signal.score,
                        'reason': signal.reason,
                    },
                    process_time_ms=0,
                    error="",
                    metadata={'source': 'attention_center', 'attention_strategy': signal.strategy_name}
                )

                signal_stream.update(result, who='attention_center')

            log.info(f"[Center] 已将 {len(signals)} 个信号添加到信号流")
        except Exception as e:
            log.error(f"[Center] 添加信号到信号流失败: {e}")

    def _update_portfolio_state(self):
        """从 VirtualPortfolio 更新 QueryState 的持仓状态"""
        try:
            from deva.naja.bandit import get_virtual_portfolio
            portfolio = get_virtual_portfolio()

            summary = portfolio.get_summary()
            positions = portfolio.get_all_positions(status="OPEN")

            held_symbols = list(set(p.stock_code for p in positions))

            concentration = 0.0
            if summary['total_value'] > 0 and positions:
                max_position = max((p.market_value for p in positions), default=0)
                concentration = max_position / summary['total_value']

            exposed_sectors = list(set(p.strategy_id.split('_')[0] for p in positions if '_' in p.strategy_id))

            self._attention_query_state.update({
                "portfolio_state": {
                    "held_symbols": held_symbols,
                    "total_return": summary.get('total_return', 0),
                    "profit_loss": summary.get('total_profit_loss', 0),
                    "position_count": summary.get('position_count', 0),
                    "available_capital": summary.get('available_capital', 0),
                    "used_capital": summary.get('used_capital', 0),
                    "concentration": concentration,
                    "exposed_sectors": exposed_sectors,
                    "timestamp": time.time(),
                }
            })

            _lab_debug_log(f"[Portfolio] 持仓更新: {len(held_symbols)} 个, 收益率={summary.get('total_return', 0):.2f}%")

        except ImportError:
            pass
        except Exception as e:
            _lab_debug_log(f"[Portfolio] 更新持仓状态失败: {e}")

    def _update_macro_liquidity_from_scanner(self):
        """
        从 GlobalMarketScanner 更新宏观流动性信号，并影响各子系统

        核心逻辑：
        1. 大盘下跌（平均涨跌）= 流动性不足 → 降仓、减高频
        2. 定价检测只用于板块/个股级别判断，不用于大盘宏观
        3. 宏观流动性信号独立于定价检测
        """
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            from deva.naja.radar.global_market_scanner import LiquiditySignalType
            scanner = get_global_market_scanner()

            summary = scanner.get_market_summary()
            market_data = scanner.get_last_data()
            if not market_data:
                return

            total_change = 0.0
            count = 0
            for code, md in market_data.items():
                if md.change_pct != 0:
                    total_change += md.change_pct
                    count += 1

            avg_change = total_change / max(count, 1) if count > 0 else 0
            phase = summary.get('us_trading_phase', 'closed')

            if phase == 'trading':
                phase_factor = 1.0
            elif phase in ('pre_market', 'after_hours'):
                phase_factor = 0.7
            else:
                phase_factor = 0.4

            change_score = np.clip(-avg_change / 5.0, -1.0, 1.0)
            raw_signal = (change_score * 0.6 + (phase_factor - 0.5) * 0.4 + 1.0) / 2.0

            liquidity_status = "宽松" if raw_signal > 0.6 else ("紧张" if raw_signal < 0.4 else "中性")
            _lab_debug_log(f"[MacroLiquidity] 大盘平均涨跌={avg_change:.2f}%({liquidity_status}), 美股时段={phase}, signal={raw_signal:.3f}")

            self._attention_query_state.set_macro_liquidity_signal(raw_signal)
            self._apply_liquidity_to_sector_attention(raw_signal)
            self._apply_liquidity_to_strategy_budget(raw_signal)
            self._apply_liquidity_to_frequency(raw_signal)

        except ImportError:
            pass
        except Exception as e:
            _lab_debug_log(f"[MacroLiquidity] 更新失败: {e}")

    def _apply_liquidity_to_sector_attention(self, liquidity_signal: float):
        """
        根据宏观流动性信号调整板块注意力

        流动性紧张时：
        - 降低高波动板块的权重
        - 提高防守板块（消费、医药）的权重
        """
        try:
            if not hasattr(self, '_integration') or not self._integration.attention_system:
                return

            sector_attention = self._integration.attention_system.sector_attention
            if not hasattr(sector_attention, '_attention_scores') or not hasattr(sector_attention, '_sector_id_to_idx'):
                return

            if liquidity_signal < 0.4:
                adjustment_factor = 0.8
            elif liquidity_signal > 0.7:
                adjustment_factor = 1.1
            else:
                adjustment_factor = 1.0

            if adjustment_factor != 1.0:
                high_volatility_sectors = ["科技", "半导体", "新能源", "汽车", "有色", "煤炭", "钢铁"]
                for sector_id, idx in list(sector_attention._sector_id_to_idx.items()):
                    if not hasattr(sector_attention, '_sectors') or sector_id not in sector_attention._sectors:
                        continue
                    sector_name = sector_attention._sectors[sector_id].name if sector_attention._sectors.get(sector_id) else ""
                    for hv_sector in high_volatility_sectors:
                        if hv_sector in sector_name:
                            old_score = float(sector_attention._attention_scores[idx])
                            new_score = old_score * adjustment_factor
                            sector_attention._attention_scores[idx] = np.clip(new_score, 0.0, 1.0)
                            break

        except Exception as e:
            _lab_debug_log(f"[MacroLiquidity-Sector] 调整板块注意力失败: {e}")

    def _apply_liquidity_to_strategy_budget(self, liquidity_signal: float):
        """
        根据宏观流动性信号调整策略预算

        流动性紧张时：
        - 增加 AnomalySniper 预算（关注异常）
        - 减少 MomentumTracker 预算（减少趋势追涨）
        """
        try:
            if not hasattr(self, '_integration') or not self._integration.attention_system:
                return

            if liquidity_signal < 0.4:
                budget_adjustment = {
                    "AnomalySniper": 0.2,
                    "MomentumTracker": -0.2,
                }
            elif liquidity_signal > 0.7:
                budget_adjustment = {
                    "AnomalySniper": -0.1,
                    "MomentumTracker": 0.1,
                }
            else:
                return

            if hasattr(self._integration.attention_system, '_strategy_budget'):
                for strategy, delta in budget_adjustment.items():
                    current = self._integration.attention_system._strategy_budget.get(strategy, 0.5)
                    new_budget = max(0.1, min(0.9, current + delta))
                    self._integration.attention_system._strategy_budget[strategy] = new_budget
                    _lab_debug_log(f"[MacroLiquidity-Budget] {strategy}: {current:.2f} -> {new_budget:.2f}")

        except Exception as e:
            _lab_debug_log(f"[MacroLiquidity-Budget] 调整策略预算失败: {e}")

    def _apply_liquidity_to_frequency(self, liquidity_signal: float):
        """
        根据宏观流动性信号调整决策频率

        流动性紧张时：
        - 提高 high_freq 阈值，减少高频交易
        - 延长决策周期
        """
        try:
            if not hasattr(self, '_integration') or not self._integration.attention_system:
                return

            if liquidity_signal < 0.4:
                freq_adjustment = 1.3
            elif liquidity_signal > 0.7:
                freq_adjustment = 0.9
            else:
                freq_adjustment = 1.0

            if freq_adjustment != 1.0 and hasattr(self._integration.attention_system, '_high_freq_threshold'):
                old_threshold = self._integration.attention_system._high_freq_threshold
                new_threshold = old_threshold * freq_adjustment
                self._integration.attention_system._high_freq_threshold = new_threshold
                _lab_debug_log(f"[MacroLiquidity-Freq] high_freq_threshold: {old_threshold:.3f} -> {new_threshold:.3f}")

        except Exception as e:
            _lab_debug_log(f"[MacroLiquidity-Freq] 调整频率失败: {e}")

    def _update_signal_stream_query_state(self):
        """将 QueryState 同步到 SignalStream 用于优先级计算"""
        try:
            from deva.naja.signal.stream import get_signal_stream
            signal_stream = get_signal_stream()
            signal_stream.set_query_state(self._attention_query_state)

            _lab_debug_log(f"[SignalStream] QueryState 已同步: regime={self._attention_query_state.market_regime.get('type', 'unknown')}, risk_bias={self._attention_query_state.risk_bias:.2f}")
        except ImportError:
            pass
        except Exception as e:
            _lab_debug_log(f"[SignalStream] 同步 QueryState 失败: {e}")

    def _get_sector_weights(self) -> Dict[str, float]:
        """获取板块权重"""
        if self._integration.attention_system is None:
            return {}
        return self._integration.attention_system.sector_attention.get_all_weights()

    def _get_symbol_weights(self) -> Dict[str, float]:
        """获取个股权重"""
        if self._integration.attention_system is None:
            return {}
        return self._integration.attention_system.weight_pool.get_all_weights()

    def _apply_memory_hints(self, data: pd.DataFrame) -> None:
        """将洞察系统中的热点提示合并到注意力上下文"""
        try:
            from deva.naja.cognition.insight import get_insight_engine
        except Exception:
            return

        try:
            insight = get_insight_engine()
            hints = insight.get_attention_hints(lookback=200)
        except Exception:
            return

        weighted_symbols = hints.get("symbols") or {}
        weighted_sectors = hints.get("sectors") or {}

        if weighted_symbols:
            try:
                if 'code' in data.columns:
                    available = set(str(s) for s in data['code'].values)
                else:
                    available = set(str(s) for s in data.index.values)

                for sym, weight in weighted_symbols.items():
                    sym_str = str(sym)
                    if sym_str in available and weight >= 0.001:
                        self._cached_high_attention_symbols.add(sym_str)
            except Exception:
                pass

        if weighted_sectors:
            try:
                for sec, weight in weighted_sectors.items():
                    if weight >= 0.01:
                        self._cached_active_sectors.add(str(sec))
            except Exception:
                pass

    def get_cached_market_time(self) -> str:
        """获取缓存的市场时间字符串"""
        return self._cached_market_time_str

    def get_attention_context(self) -> Dict[str, Any]:
        """获取注意力上下文"""
        return {
            'global_attention': self._cached_global_attention,
            'high_attention_symbols': self._cached_high_attention_symbols,
            'active_sectors': self._cached_active_sectors,
            'processed_frames': self._processed_frames,
            'filtered_frames': self._filtered_frames,
            'filter_ratio': self._filtered_frames / max(self._processed_frames, 1)
        }

    def should_process_strategy(self, strategy_id: str) -> bool:
        """判断策略是否应该执行"""
        if strategy_id not in self._strategies:
            return True

        config = self._strategies[strategy_id]
        min_attention = config.get('min_attention', 0.0)

        return self._cached_global_attention >= min_attention

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        noise_stats = self._noise_filter.get_stats() if self._noise_filter else {}

        return {
            'registered_strategies': len(self._strategies),
            'registered_datasources': len(self._datasources),
            'processed_frames': self._processed_frames,
            'filtered_frames': self._filtered_frames,
            'filter_ratio': self._filtered_frames / max(self._processed_frames, 1),
            'global_attention': self._cached_global_attention,
            'high_attention_count': len(self._cached_high_attention_symbols),
            'noise_filter': noise_stats
        }


_orchestrator: Optional[AttentionOrchestrator] = None
_orchestrator_lock = threading.Lock()


def get_orchestrator() -> AttentionOrchestrator:
    """获取编排器单例"""
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = AttentionOrchestrator()
    return _orchestrator


def initialize_orchestrator() -> AttentionOrchestrator:
    """初始化编排器（强制初始化）"""
    orchestrator = get_orchestrator()
    orchestrator._ensure_initialized()
    log.info("注意力编排器已初始化")
    return orchestrator


Orchestrator = AttentionOrchestrator