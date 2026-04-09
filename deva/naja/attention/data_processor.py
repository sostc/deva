"""
DataProcessor - 数据处理模块

职责：
- 数据源数据处理
- 字典转 DataFrame
- 噪音过滤
- 注意力更新

从 AttentionOrchestrator 拆分出来
"""

import time
import logging
from typing import Dict, Any, Optional, List, Set
import pandas as pd
import numpy as np

try:
    from deva.naja.config import get_noise_filter_config
except ImportError:
    def get_noise_filter_config():
        return {}

from .processing import get_noise_filter, NoiseFilterConfig, get_tick_noise_filter, TickNoiseFilterConfig
from .integration.extended import get_market_hotspot_integration

log = logging.getLogger(__name__)


def _lab_debug_log(msg: str):
    """调试日志"""
    log.debug(f"[DataProcessor] {msg}")


class DataProcessor:
    """
    数据处理中心

    负责：
    - 接收数据源数据
    - 转换为统一格式
    - 噪音过滤
    - 更新注意力系统
    """

    _instance = None
    _lock = None

    def __new__(cls):
        if cls._instance is None:
            import threading
            cls._lock = threading.Lock()
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._init_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        with self._init_lock:
            if getattr(self, '_initialized', False):
                return
            self._ensure_initialized()

    def _ensure_initialized(self):
        """初始化"""
        self._integration = get_market_hotspot_integration()

        self._state_lock = __import__('threading').RLock()

        self._last_attention_update = 0
        self._attention_cache_ttl = 0.1
        self._cached_high_attention_symbols: Set[str] = set()
        self._cached_active_blocks: Set[str] = set()
        self._cached_market_time_str: str = ""

        self._block_id_map: Dict[str, int] = {}
        self._next_block_id = 1

        self._processed_frames = 0
        self._filtered_frames = 0
        self._noise_filtered_count = 0

        self._last_noise_log_time = 0
        self._noise_log_interval = 60

        self._attention_errors = {"kernel": 0, "update": 0, "pytorch": 0, "strategy_dispatch": 0}
        self._total_updates = 0

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
        self._enrich_stage = EnrichStage(name="enrich_block", use_direct_load=True)
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
        log.info("DataProcessor 初始化完成")

    def _start_pytorch_processor(self):
        """启动 PyTorch 队列处理"""
        import threading
        self._pytorch_processing = True
        self._pytorch_thread = threading.Thread(target=self._pytorch_loop, daemon=True)
        self._pytorch_thread.start()

    def _pytorch_loop(self):
        """PyTorch 处理循环"""
        import time
        while self._pytorch_processing:
            time.sleep(1)

    def stop_pytorch_processor(self):
        """停止 PyTorch 队列处理"""
        self._pytorch_processing = False
        if self._pytorch_thread:
            self._pytorch_thread.join(timeout=5)

    def process_datasource_data(self, datasource_id: str, data: Any) -> None:
        """处理数据源数据"""
        _lab_debug_log(f"[DataProcessor] process_datasource_data called: datasource={datasource_id}, data_type={type(data)}")

        if isinstance(data, dict):
            data = self._convert_dict_to_dataframe(data)
            if data is None:
                log.debug(f"[DataProcessor] 数据源 {datasource_id} 无法将 dict 转换为 DataFrame，跳过")
                return

        if data is None or (hasattr(data, 'empty') and data.empty):
            return

        self._update_attention(data)

        self._dispatch_to_strategies(datasource_id, data)

        self._processed_frames += 1

    def _convert_dict_to_dataframe(self, data: dict) -> Optional[pd.DataFrame]:
        """将 dict 格式的市场数据转换为 DataFrame"""
        try:
            if 'symbols' not in data:
                return None

            symbols = data.get('symbols', {})
            if not symbols:
                return None

            rows = []
            market_info = data.get('market', {})
            timestamp = data.get('timestamp', '')

            for code, info in symbols.items():
                row = {
                    'code': code,
                    'now': info.get('price', 0),
                    'change_pct': info.get('change', 0) * 100 if isinstance(info.get('change'), (int, float)) else 0,
                    'volume': market_info.get('volume', 0),
                    'date': timestamp[:10] if timestamp else '',
                    'time': timestamp[11:19] if timestamp else '',
                }
                rows.append(row)

            if not rows:
                return None

            df = pd.DataFrame(rows)
            log.debug(f"[DataProcessor] 将 dict 转换为 DataFrame 成功: {len(df)} 行")
            return df

        except Exception as e:
            log.warning(f"[DataProcessor] dict 转 DataFrame 失败: {e}")
            return None

    def _update_attention(self, data: pd.DataFrame):
        """更新注意力系统"""
        log.debug("[DEBUG] _update_attention ENTER")
        self._total_updates += 1

        attention_sys = self._integration.hotspot_system
        is_init = attention_sys is not None and getattr(attention_sys, '_initialized', False)
        if not is_init:
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
                self._attention_errors["update"] += 1
                log.error(f"[DataProcessor] 注意力系统自动初始化失败 (累计{self._attention_errors['update']}次): {e}")
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

            symbols, returns, volumes, prices, block_ids = self._expand_for_multi_block(
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

            self._last_attention_update = current_time

        except Exception as e:
            self._attention_errors["update"] += 1
            log.error(f"[DataProcessor] 注意力更新失败 (累计{self._attention_errors['update']}次): {e}")
            import traceback
            log.error(traceback.format_exc())

    def _expand_for_multi_block(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        prices: np.ndarray,
        data: pd.DataFrame,
        code_col: str
    ) -> tuple:
        """多题材扩展"""
        block_map = self._get_block_map(data)

        expanded_symbols = []
        expanded_returns = []
        expanded_volumes = []
        expanded_prices = []
        expanded_block_ids = []

        for i, code in enumerate(symbols):
            code_str = str(code)
            symbol_blocks = block_map.get(code_str, [])

            if not symbol_blocks:
                expanded_symbols.append(code_str)
                expanded_returns.append(returns[i] if i < len(returns) else 0.0)
                expanded_volumes.append(volumes[i] if i < len(volumes) else 0.0)
                expanded_prices.append(prices[i] if i < len(prices) else 0.0)
                expanded_block_ids.append(0)
            else:
                for block in symbol_blocks:
                    if block not in self._block_id_map:
                        self._block_id_map[block] = self._next_block_id
                        self._next_block_id += 1

                    expanded_symbols.append(code_str)
                    expanded_returns.append(returns[i] if i < len(returns) else 0.0)
                    expanded_volumes.append(volumes[i] if i < len(volumes) else 0.0)
                    expanded_prices.append(prices[i] if i < len(prices) else 0.0)
                    expanded_block_ids.append(self._block_id_map[block])

        return (
            np.array(expanded_symbols),
            np.array(expanded_returns),
            np.array(expanded_volumes),
            np.array(expanded_prices),
            np.array(expanded_block_ids)
        )

    def _get_block_map(self, data: pd.DataFrame) -> Dict[str, List[str]]:
        """获取题材映射"""
        block_map: Dict[str, List[str]] = {}

        try:
            if 'block' in data.columns or 'block' in data.columns:
                for _, row in data.iterrows():
                    code = str(row.get('code', ''))
                    block = str(row.get('block', row.get('block', 'unknown')))
                    if code and block and block != 'nan':
                        if code not in block_map:
                            block_map[code] = []
                        if block not in block_map[code]:
                            block_map[code].append(block)
        except Exception:
            pass

        return block_map

    def _filter_by_attention(self, data: pd.DataFrame) -> pd.DataFrame:
        """按注意力过滤"""
        if self._cached_high_attention_symbols:
            code_col = 'code' if 'code' in data.columns else data.index.name
            if code_col in data.columns:
                return data[data[code_col].isin(self._cached_high_attention_symbols)]
        return data

    def _filter_by_blocks(self, data: pd.DataFrame) -> pd.DataFrame:
        """按活跃题材过滤"""
        if not self._cached_active_blocks:
            return data
        if 'block' in data.columns:
            return data[data['block'].isin(self._cached_active_blocks)]
        return data

    def _dispatch_to_strategies(self, datasource_id: str, data: pd.DataFrame, market_time: Optional[float] = None):
        """分发到策略"""
        try:
            if not hasattr(self, '_strategies') or not self._strategies:
                return

            for strategy_id, strategy_info in self._strategies.items():
                if not self.should_process_strategy(strategy_id):
                    continue

                callback = strategy_info.get('callback')
                if not callback:
                    continue

                try:
                    if market_time:
                        callback(data, market_time)
                    else:
                        callback(data)
                except Exception as e:
                    self._attention_errors["strategy_dispatch"] += 1
                    log.error(f"[DataProcessor] 策略 {strategy_id} 分发失败 (累计{self._attention_errors['strategy_dispatch']}次): {e}")
        except Exception as e:
            log.error(f"[DataProcessor] _dispatch_to_strategies 失败: {e}")

    def should_process_strategy(self, strategy_id: str) -> bool:
        """判断是否处理策略"""
        return True

    def register_strategy(self,
                         strategy_id: str,
                         strategy_type: str,
                         callback,
                         min_attention: float = 0.0,
                         filter_by_attention: bool = True):
        """注册策略"""
        if not hasattr(self, '_strategies'):
            self._strategies: Dict[str, Dict] = {}
        self._strategies[strategy_id] = {
            'type': strategy_type,
            'callback': callback,
            'min_attention': min_attention,
            'filter_by_attention': filter_by_attention,
            'registered_at': time.time()
        }
        log.info(f"策略 {strategy_id} 已注册到 DataProcessor (类型: {strategy_type})")

    def unregister_strategy(self, strategy_id: str):
        """注销策略"""
        if hasattr(self, '_strategies') and strategy_id in self._strategies:
            del self._strategies[strategy_id]
            log.info(f"策略 {strategy_id} 已从 DataProcessor 注销")

    def register_datasource(self, datasource_id: str) -> None:
        """注册数据源"""
        if not hasattr(self, '_datasources'):
            self._datasources: Dict[str, Dict] = {}
        self._datasources[datasource_id] = {
            'registered_at': time.time(),
        }
        log.info(f"数据源 {datasource_id} 已注册到 DataProcessor")

    def unregister_datasource(self, datasource_id: str) -> None:
        """注销数据源"""
        if hasattr(self, '_datasources') and datasource_id in self._datasources:
            del self._datasources[datasource_id]
            log.info(f"数据源 {datasource_id} 已从 DataProcessor 注销")

    def get_cached_market_time(self) -> str:
        """获取缓存的市场时间"""
        return self._cached_market_time_str

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "processed_frames": getattr(self, '_processed_frames', 0),
            "filtered_frames": getattr(self, '_filtered_frames', 0),
            "noise_filtered_count": getattr(self, '_noise_filtered_count', 0),
            "total_updates": getattr(self, '_total_updates', 0),
            "attention_errors": getattr(self, '_attention_errors', {}),
            "high_attention_symbols_count": len(getattr(self, '_cached_high_attention_symbols', set())),
            "active_blocks_count": len(getattr(self, '_cached_active_blocks', set())),
        }


_data_processor: Optional['DataProcessor'] = None


def get_data_processor() -> DataProcessor:
    """获取 DataProcessor 单例"""
    global _data_processor
    if _data_processor is None:
        _data_processor = DataProcessor()
    return _data_processor
