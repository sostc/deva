"""
Attention Center - 注意力调度中心

统一协调数据源、策略和注意力系统之间的关系：
1. 接收所有数据源的数据
2. 计算注意力分数
3. 根据注意力动态调度策略执行
4. 提供统一的查询接口
"""

import time
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


class AttentionCenter:
    """
    注意力调度中心

    作为数据源和策略之间的中间层：
    - 数据源始终emit全量数据
    - 调度中心计算注意力
    - 策略通过调度中心获取数据（已过滤）
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
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
        log.info("AttentionCenter 初始化完成")

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

        self._update_attention(data)
        self._dispatch_to_strategies(datasource_id, data)

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

            symbols = data.index.values if 'code' not in data.columns else data['code'].values
            sector_ids = self._extract_sector_ids(data)

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

                if sector_weights:
                    sorted_sectors = sorted(sector_weights.items(), key=lambda x: x[1], reverse=True)[:5]
                    named_sectors = [(tracker.get_sector_name(s), w) for s, w in sorted_sectors]
                    _lab_debug_log(f"SectorWeights Top5: {[(f'{n}({w:.2f})') for n, w in named_sectors]}")

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

        for strategy_id, config in self._strategies.items():
            try:
                strategy_type = config['type']
                callback = config['callback']
                filter_by_attention = config['filter_by_attention']

                if not filter_by_attention:
                    callback(data)
                    continue

                if strategy_type == 'global':
                    context = {
                        'global_attention': self._cached_global_attention,
                        'datasource_id': datasource_id
                    }
                    callback(data, context)

                elif strategy_type == 'sector':
                    filtered = self._filter_by_sectors(data)
                    if not filtered.empty:
                        context = {
                            'active_sectors': self._cached_active_sectors,
                            'global_attention': self._cached_global_attention
                        }
                        callback(filtered, context)

                elif strategy_type == 'symbol':
                    filtered = self._filter_by_attention(data)
                    if not filtered.empty:
                        self._filtered_frames += 1
                        context = {
                            'high_attention_symbols': self._cached_high_attention_symbols,
                            'global_attention': self._cached_global_attention
                        }
                        callback(filtered, context)

            except Exception as e:
                log.error(f"分发数据到策略 {strategy_id} 失败: {e}")

        try:
            from .strategies import get_strategy_manager

            strategy_mgr = get_strategy_manager()

            if strategy_mgr is None:
                log.warning("策略管理器未初始化，跳过策略处理")
            elif not strategy_mgr.is_running:
                log.warning(f"策略管理器未运行 (is_running=False)，尝试启动...")
                if not strategy_mgr.strategies:
                    strategy_mgr.initialize_default_strategies()
                strategy_mgr.start()

            if strategy_mgr and strategy_mgr.is_running:
                context = {
                    'global_attention': self._cached_global_attention,
                    'activity': self._cached_activity,
                    'high_attention_symbols': self._cached_high_attention_symbols,
                    'active_sectors': self._cached_active_sectors,
                    'datasource_id': datasource_id,
                    'sector_weights': self._get_sector_weights(),
                    'symbol_weights': self._get_symbol_weights(),
                    'timestamp': market_time if market_time else time.time()
                }
                signals = strategy_mgr.process_data(data, context)
                if signals:
                    log.info(f"🎯 注意力策略生成 {len(signals)} 个信号")
                elif self._processed_frames % 50 == 0:
                    active_count = sum(1 for c in strategy_mgr.configs.values() if c.enabled)
                    log.debug(f"策略处理完成，无信号生成 (活跃策略: {active_count}, 总策略: {len(strategy_mgr.strategies)})")
        except ImportError as ie:
            log.debug(f"注意力策略模块未安装: {ie}")
        except Exception as e:
            log.error(f"分发数据到注意力策略系统失败: {e}", exc_info=True)

    def _filter_by_attention(self, data: pd.DataFrame) -> pd.DataFrame:
        """根据注意力过滤数据"""
        if not self._cached_high_attention_symbols:
            return data

        code_column = 'code' if 'code' in data.columns else data.index.name
        if code_column == 'code':
            return data[data['code'].isin(self._cached_high_attention_symbols)]
        else:
            return data[data.index.isin(self._cached_high_attention_symbols)]

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

        if sector_col is None:
            return np.zeros(len(data))

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
                    if sym_str in available and weight > 0.5:
                        self._cached_high_attention_symbols.add(sym_str)
            except Exception:
                pass

        if weighted_sectors:
            try:
                for sec, weight in weighted_sectors.items():
                    if weight > 0.5:
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


_orchestrator: Optional[AttentionCenter] = None
_orchestrator_lock = threading.Lock()


def get_orchestrator() -> AttentionCenter:
    """获取调度中心单例"""
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = AttentionCenter()
    return _orchestrator


def initialize_orchestrator() -> AttentionCenter:
    """初始化调度中心"""
    orchestrator = get_orchestrator()
    log.info("注意力调度中心已初始化")
    return orchestrator


Orchestrator = AttentionCenter