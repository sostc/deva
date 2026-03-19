"""
注意力调度中心 (Attention Orchestrator)

统一协调数据源、策略和注意力系统之间的关系：
1. 接收所有数据源的数据
2. 计算注意力分数
3. 根据注意力动态调度策略执行
4. 提供统一的查询接口
"""

import time
import threading
import asyncio
from typing import Dict, List, Optional, Set, Callable, Any
from collections import defaultdict
import logging

import numpy as np

try:
    import pandas as pd
except Exception:
    pd = None

from .attention_integration import get_attention_integration
from naja_attention_system import get_noise_filter, NoiseFilterConfig
from naja_attention_system.tick_noise_filter import get_tick_noise_filter, TickNoiseFilterConfig
from .config import get_noise_filter_config

# 性能监控支持
try:
    from deva.naja.performance import record_component_execution, ComponentType
    _PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    _PERFORMANCE_MONITORING_AVAILABLE = False

log = logging.getLogger(__name__)


class AttentionOrchestrator:
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
        
        # 策略注册表
        self._strategies: Dict[str, Dict] = {}  # strategy_id -> config
        
        # 数据源注册表
        self._datasources: Dict[str, Dict] = {}  # datasource_id -> config
        
        # 缓存
        self._last_attention_update = 0
        self._attention_cache_ttl = 1.0  # 1秒缓存
        self._cached_high_attention_symbols: Set[str] = set()
        self._cached_active_sectors: Set[str] = set()
        self._cached_global_attention = 0.5
        
        # 统计
        self._processed_frames = 0
        self._filtered_frames = 0
        
        # 日志频率控制
        self._last_noise_log_time = 0
        self._noise_log_interval = 60  # 每60秒打印一次噪音过滤日志
        
        # 从 naja 配置表加载噪音过滤配置
        nf_config = get_noise_filter_config()
        
        # 基础噪音过滤器
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
        self._noise_filtered_count = 0
        
        # Tick级别噪音过滤器（增强版）
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
        
        # PyTorch 队列处理线程
        self._pytorch_processing = False
        self._pytorch_thread = None
        self._start_pytorch_processor()
        
        self._initialized = True
        log.info("AttentionOrchestrator 初始化完成")
    
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
        
        # 创建事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self._pytorch_processing:
            try:
                # 检查注意力系统是否初始化
                if (self._integration.attention_system is None or 
                    self._integration.attention_system.dual_engine is None):
                    time.sleep(5)
                    continue
                
                dual_engine = self._integration.attention_system.dual_engine
                pytorch = dual_engine.pytorch
                
                # 检查队列长度
                queue_size = len(pytorch._pending_queue)
                
                if queue_size > 0:
                    # 只在队列较大时打印日志，避免频繁输出
                    if queue_size >= 100:
                        log.info(f"[PyTorchProcessor] 队列中有 {queue_size} 个待处理信号，开始处理...")
                    
                    # 运行异步处理
                    try:
                        results = loop.run_until_complete(pytorch.process_batch())
                        if results and len(results) >= 100:
                            log.info(f"[PyTorchProcessor] 完成 {len(results)} 个推理")
                            # 这里可以添加结果处理逻辑
                    except Exception as e:
                        log.error(f"[PyTorchProcessor] 处理失败: {e}")
                
                # 每2秒检查一次队列
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
                         strategy_type: str,  # 'global' | 'sector' | 'symbol'
                         callback: Callable,
                         min_attention: float = 0.0,
                         filter_by_attention: bool = True):
        """
        注册策略到调度中心
        
        Args:
            strategy_id: 策略ID
            strategy_type: 策略类型
                - 'global': 全市场策略，接收全量数据
                - 'sector': 板块策略，只接收活跃板块数据
                - 'symbol': 个股策略，只接收高注意力个股
            callback: 数据回调函数
            min_attention: 最小注意力阈值
            filter_by_attention: 是否根据注意力过滤数据
        """
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
        """
        注册数据源到调度中心
        
        Args:
            datasource_id: 数据源ID
            config: 数据源配置
        """
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
        """
        处理数据源数据

        这是核心方法，数据源emit数据时调用
        """
        if pd is None or not isinstance(data, pd.DataFrame):
            log.debug(f"[Orchestrator] 数据源 {datasource_id} 数据格式不正确，跳过")
            return

        start_time = time.time()
        self._processed_frames += 1

        # 每10帧输出一次日志
        if self._processed_frames % 10 == 0:
            log.info(f"[Orchestrator] 已处理 {self._processed_frames} 帧数据，当前数据源: {datasource_id}")
            log.info(f"[Orchestrator] 数据形状: {data.shape}, 列: {list(data.columns)}")

        # 更新注意力系统
        self._update_attention(data)

        # 分发数据到各策略
        self._dispatch_to_strategies(datasource_id, data)

        # 记录性能监控
        if _PERFORMANCE_MONITORING_AVAILABLE:
            latency = (time.time() - start_time) * 1000
            record_component_execution(
                component_id=f"attention_orchestrator_{datasource_id}",
                component_name=f"注意力调度中心: {datasource_id}",
                component_type=ComponentType.DATASOURCE,
                execution_time_ms=latency,
                success=True
            )
    
    def _update_attention(self, data: pd.DataFrame):
        """更新注意力系统"""
        if self._integration.attention_system is None:
            return
        
        # 检查缓存
        current_time = time.time()
        if current_time - self._last_attention_update < self._attention_cache_ttl:
            return
        
        try:
            # 检查是否需要打印日志（控制频率）
            should_log_noise = current_time - self._last_noise_log_time >= self._noise_log_interval
            
            # ===== 基础噪音过滤 =====
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
                
                # 控制日志频率，每60秒打印一次
                if should_log_noise:
                    log.info(f"[基础噪音过滤] 原始{original_count}条 -> 过滤后{len(filtered_data)}条 (过滤{filtered_count}条, 过滤率{filtered_count/max(original_count,1)*100:.1f}%)")
                
                if len(filtered_data) == 0:
                    log.warning("⚠️ 基础噪音过滤后数据为空！所有股票都被过滤了")
                    # 不过滤，使用原始数据
                    filtered_data = data
                    log.info("[回退] 使用原始数据，跳过基础噪音过滤")
                
                data = filtered_data
            
            # ===== Tick级别增强噪音过滤 =====
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
                
                # 控制日志频率
                if should_log_noise:
                    log.info(f"[Tick噪音过滤] 原始{tick_original_count}条 -> 过滤后{len(filtered_data)}条 (过滤{tick_filtered_count}条, 过滤率{tick_filtered_count/max(tick_original_count,1)*100:.1f}%)")
                    self._last_noise_log_time = current_time
                
                if len(filtered_data) == 0:
                    log.warning("⚠️ Tick噪音过滤后数据为空！所有股票都被过滤了")
                    # 不过滤，使用原始数据
                    filtered_data = data
                    log.info("[回退] 使用原始数据，跳过Tick噪音过滤")
                elif tick_filtered_count > 0:
                    # 记录详细报告（用于调试）
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
            
            # 提取必要字段
            symbols = data.index.values if 'code' not in data.columns else data['code'].values
            
            returns = data['p_change'].values if 'p_change' in data.columns else \
                     (data['now'].values - data['close'].values) / data['close'].values * 100
            
            volumes = data['volume'].values if 'volume' in data.columns else np.ones(len(symbols)) * 1000000
            prices = data['now'].values if 'now' in data.columns else data['close'].values
            
            # 提取行情数据时间（优先使用数据中的时间）
            market_time = current_time
            market_time_str = None
            if 'date' in data.columns and 'time' in data.columns:
                # 使用第一行的时间作为代表
                first_row = data.iloc[0]
                date_val = str(first_row['date'])
                time_val = str(first_row['time'])
                try:
                    from datetime import datetime
                    # 尝试解析日期时间
                    dt_str = f"{date_val} {time_val}"
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    market_time = dt.timestamp()
                    market_time_str = dt.strftime("%H:%M:%S")
                except:
                    pass
            
            # 更新注意力系统
            result = self._integration.attention_system.process_snapshot(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                sector_ids=np.zeros(len(symbols)),  # 简化处理
                timestamp=market_time
            )
            
            # 更新缓存
            control = self._integration.get_datasource_control()
            self._cached_high_attention_symbols = set(control.get('high_freq_symbols', []))
            self._cached_active_sectors = set(self._integration.get_active_sectors(threshold=0.3))
            self._cached_global_attention = self._integration.attention_system._last_global_attention
            
            # 每100帧输出一次 River Engine 统计（用于调试）
            if self._processed_frames % 100 == 0:
                dual_summary = result.get('dual_engine_summary', {})
                river_stats = dual_summary.get('river_stats', {})
                log.info(f"[River Engine] 处理: {river_stats.get('processed_count', 0)}, "
                        f"异常: {river_stats.get('anomaly_count', 0)}, "
                        f"活跃: {river_stats.get('active_symbols', 0)}")
            
            # 记录到历史追踪器
            try:
                from .attention.history_tracker import get_history_tracker
                tracker = get_history_tracker()
                
                # 获取板块和个股权重
                sector_weights = self._integration.attention_system.sector_attention.get_all_weights()
                symbol_weights = self._integration.attention_system.weight_pool.get_all_weights()
                
                tracker.record_snapshot(
                    global_attention=self._cached_global_attention,
                    sector_weights=sector_weights,
                    symbol_weights=symbol_weights,
                    timestamp=market_time,
                    timestamp_str=market_time_str
                )
                
                # 注册股票名称（如果数据中有）
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
            
            self._last_attention_update = current_time
            
        except Exception as e:
            import traceback
            log.error(f"更新注意力系统失败: {e}")
            log.debug(f"错误详情: {traceback.format_exc()}")
    
    def _dispatch_to_strategies(self, datasource_id: str, data: pd.DataFrame):
        """分发数据到各策略"""
        # 1. 分发到旧版策略（回调方式）
        for strategy_id, config in self._strategies.items():
            try:
                strategy_type = config['type']
                callback = config['callback']
                filter_by_attention = config['filter_by_attention']
                
                if not filter_by_attention:
                    # 不过滤，传递全量数据
                    callback(data)
                    continue
                
                # 根据策略类型过滤数据
                if strategy_type == 'global':
                    # 全市场策略：传递全量数据 + 注意力上下文
                    context = {
                        'global_attention': self._cached_global_attention,
                        'datasource_id': datasource_id
                    }
                    callback(data, context)
                    
                elif strategy_type == 'sector':
                    # 板块策略：只传递活跃板块的数据
                    filtered = self._filter_by_sectors(data)
                    if not filtered.empty:
                        context = {
                            'active_sectors': self._cached_active_sectors,
                            'global_attention': self._cached_global_attention
                        }
                        callback(filtered, context)
                    
                elif strategy_type == 'symbol':
                    # 个股策略：只传递高注意力个股
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
        
        # 2. 分发到新版注意力策略系统
        try:
            # 直接从 naja_attention_strategies 获取策略管理器
            from naja_attention_strategies import get_strategy_manager
            
            strategy_mgr = get_strategy_manager()
            
            # 检查策略管理器状态
            if strategy_mgr is None:
                log.warning("策略管理器未初始化，跳过策略处理")
            elif not strategy_mgr.is_running:
                log.warning(f"策略管理器未运行 (is_running=False)，尝试启动...")
                # 自动启动策略管理器
                if not strategy_mgr.strategies:
                    strategy_mgr.initialize_default_strategies()
                strategy_mgr.start()
            
            if strategy_mgr and strategy_mgr.is_running:
                context = {
                    'global_attention': self._cached_global_attention,
                    'high_attention_symbols': self._cached_high_attention_symbols,
                    'active_sectors': self._cached_active_sectors,
                    'datasource_id': datasource_id,
                    'sector_weights': self._get_sector_weights(),
                    'symbol_weights': self._get_symbol_weights()
                }
                signals = strategy_mgr.process_data(data, context)
                if signals:
                    log.info(f"🎯 注意力策略生成 {len(signals)} 个信号")
                elif self._processed_frames % 50 == 0:
                    # 每50帧输出一次调试信息
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
        # 这里简化处理，实际应该根据股票所属板块过滤
        # 暂时返回全量数据
        return data
    
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


# 全局实例
_orchestrator: Optional[AttentionOrchestrator] = None
_orchestrator_lock = threading.Lock()


def get_orchestrator() -> AttentionOrchestrator:
    """获取调度中心单例"""
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = AttentionOrchestrator()
    return _orchestrator


def initialize_orchestrator() -> AttentionOrchestrator:
    """
    初始化调度中心
    
    这是主要的初始化入口，在 naja 启动时调用
    """
    orchestrator = get_orchestrator()
    log.info("注意力调度中心已初始化")
    return orchestrator
