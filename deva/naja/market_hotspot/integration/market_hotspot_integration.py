"""
MarketHotspotIntegration - 市场热点系统集成层

将市场热点系统集成到 Naja 中：

职责:
1. 自动从 naja 数据源获取题材和个股信息
2. 初始化市场热点系统 (MarketHotspotSystem)
3. 初始化热点智能系统 (HotspotIntelligenceSystem)
4. 提供统一的单例访问接口
5. 管理模式切换 (lab/realtime)
6. 持久化状态

架构:
    MarketHotspotIntegration (本文件 - 集成层)
        │
        ├── MarketHotspotSystem (核心计算)
        │       ├── GlobalHotspotEngine
        │       ├── BlockHotspotEngine
        │       ├── WeightPool
        │       └── ...
        │
        └── HotspotIntelligenceSystem (智能增强)
                ├── HotspotLearningSystem (热点学习)
                ├── PredictiveHotspotEngine (预测)
                ├── HotspotBudgetSystem (预算)
                └── ...
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
import time
import threading
import logging

from deva import NB

from .market_hotspot_system import MarketHotspotSystem, MarketHotspotSystemConfig
from ..core import BlockConfig

from deva.naja.infra.registry.singleton_registry import SR
from deva.naja.attention.portfolio import Portfolio, StockInfo

log = logging.getLogger(__name__)


class MarketHotspotIntegration:
    """
    Naja 市场热点系统集成器

    职责：
    1. 自动从 naja 数据源获取题材和个股信息
    2. 初始化市场热点系统
    3. 拦截数据源数据进行处理
    4. 提供频率控制接口
    5. 监控和报告

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局热点集成：MarketHotspotIntegration 是全局市场热点系统集成器，
       负责协调 MarketHotspotSystem 和数据流。如果存在多个实例，会导致状态不一致。

    2. 状态一致性：热点计算状态、频率控制状态等需要在全系统保持一致。

    3. 生命周期：Integration 的生命周期与系统一致，随系统启动和关闭。

    4. 这是流式计算系统的设计选择，不是过度工程。
    ================================================================================
    """

    _instance = None
    _initialized = False
    _init_lock = threading.Lock()
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 使用锁保护 _initialized 检查，避免多线程竞态条件
        if MarketHotspotIntegration._initialized:
            return

        with MarketHotspotIntegration._init_lock:
            # 双重检查
            if MarketHotspotIntegration._initialized:
                return
            
            # 只在第一次创建时设置这些属性
            if not hasattr(self, 'hotspot_system'):
                self.hotspot_system: Optional[MarketHotspotSystem] = None
            if not hasattr(self, 'intelligence_system'):
                self.intelligence_system = None

            if not hasattr(self, 'config'):
                self.config: MarketHotspotSystemConfig = MarketHotspotSystemConfig()
            if not hasattr(self, '_running'):
                self._running = False
            if not hasattr(self, '_monitor_thread'):
                self._monitor_thread: Optional[threading.Thread] = None
            if not hasattr(self, '_check_interval'):
                self._check_interval = 5.0
            if not hasattr(self, '_symbol_block_map'):
                self._symbol_block_map: Dict[str, List[str]] = {}
            if not hasattr(self, '_blocks'):
                self._blocks: List[BlockConfig] = []
            if not hasattr(self, '_last_datasource_control'):
                self._last_datasource_control: Optional[Dict] = None
            if not hasattr(self, '_processed_snapshots'):
                self._processed_snapshots = 0
            if not hasattr(self, '_total_latency'):
                self._total_latency = 0.0

            MarketHotspotIntegration._initialized = True

    def initialize(self, config: Optional[MarketHotspotSystemConfig] = None, intelligence_config: Optional[Any] = None):
        """
        初始化市场热点系统

        自动从 naja 数据源获取题材和个股信息

        Args:
            config: v1 市场热点系统配置
            intelligence_config: 已废弃，忽略。智能增强系统默认全部启用。
        """
        # 防止重复初始化
        if hasattr(self, '_initialized_hotspot_system') and self._initialized_hotspot_system:
            log.info(f"[MarketHotspotIntegration] 已初始化，跳过")
            return self.hotspot_system
        
        log.info(f"[MarketHotspotIntegration] initialize 开始，config={config}")

        if config:
            self.config = config

        self._discover_blocks_and_symbols()

        log.info(f"[MarketHotspotIntegration] 创建 MarketHotspotSystem, config={self.config}")
        self.hotspot_system = MarketHotspotSystem(self.config)
        log.info(f"[MarketHotspotIntegration] 调用 hotspot_system.initialize()")
        self.hotspot_system.initialize(self._blocks, self._symbol_block_map)
        log.info(f"[MarketHotspotIntegration] hotspot_system.initialize 完成")

        self._register_names_to_tracker()

        self._initialize_intelligence_system()

        log.info(f"🧠 市场热点系统: 题材({len(self._blocks)}) 个股({len(self._symbol_block_map)})")
        if self.intelligence_system:
            modules = []
            if hasattr(self.intelligence_system, 'predictive_engine'):
                modules.append('Predictive')
            if hasattr(self.intelligence_system, 'hotspot_learning'):
                modules.append('Feedback')
            if hasattr(self.intelligence_system, 'budget_system'):
                modules.append('Budget')
            if hasattr(self.intelligence_system, 'propagation'):
                modules.append('Propagation')
            if hasattr(self.intelligence_system, 'strategy_learning'):
                modules.append('StrategyLearning')
            log.info(f"🧠 智能增强：{', '.join(modules)}")

        self._initialized_hotspot_system = True
        return self.hotspot_system

    def _initialize_intelligence_system(self):
        """初始化智能增强系统（默认全部启用，无需配置）"""
        try:
            from .hotspot_intelligence_system import (
                _HotspotIntelligenceSystemInternal,
                IntelligenceConfig,
            )

            self.intelligence_system = _HotspotIntelligenceSystemInternal(
                config=None,
                intelligence_config=IntelligenceConfig()
            )

            log.info("🧠 热点智能系统初始化完成")
        except Exception as e:
            import traceback
            log.error(f"智能增强系统初始化失败: {e}")
            log.error(traceback.format_exc())
            self.intelligence_system = None

    def _get_context(self, market: str):
        """
        获取指定市场的上下文

        Args:
            market: 市场标识 ('CN' 或 'US')

        Returns:
            MarketContext 对象
        """
        if not hasattr(self, 'hotspot_system') or self.hotspot_system is None:
            return None
        return self.hotspot_system._get_context(market)

    def process_us_snapshot(self, symbols, returns, volumes, prices, block_ids, timestamp):
        """
        处理美股快照数据

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组
            volumes: 成交量数组
            prices: 价格数组
            block_ids: 题材ID数组
            timestamp: 时间戳

        Returns:
            处理结果字典
        """
        if not hasattr(self, 'hotspot_system') or self.hotspot_system is None:
            return {'status': 'not_initialized'}

        try:
            return self.hotspot_system.process_snapshot(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                block_ids=block_ids,
                timestamp=timestamp,
                market='US'
            )
        except Exception as e:
            log.error(f"[MarketHotspotIntegration] process_us_snapshot 失败: {e}")
            return {'status': 'error', 'error': str(e)}

    def _register_names_to_tracker(self):
        """注册题材和个股名称到历史追踪器"""
        try:
            from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
            tracker = get_history_tracker()
            if tracker is None:
                return

            tracker.register_blocks(self._blocks)
            log.info(f"共注册 {len(self._blocks)} 个题材名称到tracker")

            try:
                db = NB("quant_snapshot_5min_window")
                if db.keys():
                    latest_key = sorted(db.keys())[-1]
                    df = db[latest_key]
                    if isinstance(df, pd.DataFrame):
                        if 'code' in df.columns and 'name' in df.columns:
                            for _, row in df.iterrows():
                                symbol = str(row['code'])
                                name = row.get('name', symbol)
                                if symbol and name and name != symbol:
                                    tracker.register_symbol_name(symbol, name)
                        elif 'code' in df.columns and 'stock_name' in df.columns:
                            for _, row in df.iterrows():
                                symbol = str(row['code'])
                                name = row.get('stock_name', symbol)
                                if symbol and name and name != symbol:
                                    tracker.register_symbol_name(symbol, name)
            except Exception as e:
                log.debug(f"从行情数据注册个股名称失败: {e}")

            log.debug(f"已注册 {len(tracker.block_names)} 个题材名称, {len(tracker.symbol_names)} 个个股名称")

        except Exception as e:
            log.debug(f"注册名称到历史追踪器失败: {e}")

    def _discover_blocks_and_symbols(self):
        """
        从 BlockDictionary 获取题材和个股
        """
        self._blocks = []
        self._symbol_block_map = {}

        try:
            self._load_blocks_from_block_dictionary()
        except Exception as e:
            log.warning(f"从 BlockDictionary 加载题材失败: {e}")
            import traceback
            log.warning(traceback.format_exc())

        try:
            self._load_symbols_from_stock_registry()
        except Exception as e:
            log.warning(f"从 StockRegistry 加载股票失败: {e}")

        log.info(f"🧠 市场热点数据: 题材({len(self._blocks)}) 个股({len(self._symbol_block_map)})")

    def _load_blocks_from_block_dictionary(self):
        """从 BlockDictionary 加载题材"""
        try:
            from deva.naja.dictionary.blocks import get_block_dictionary

            bd = get_block_dictionary()
            if not bd:
                log.warning("[BlockDictionary] 未找到 BlockDictionary 单例")
                return

            for block_id in bd._cn_blocks.keys():
                info = bd.get_block_info(block_id, 'CN')
                if not info:
                    continue

                block = BlockConfig(
                    block_id=block_id,
                    name=info.name,
                    symbols=set(info.stocks),
                    decay_half_life=300.0
                )
                self._blocks.append(block)

                for symbol in info.stocks:
                    if symbol not in self._symbol_block_map:
                        self._symbol_block_map[symbol] = []
                    self._symbol_block_map[symbol].append(block_id)

            log.info(f"[BlockDictionary] 加载完成: 题材数={len(self._blocks)}, 个股数={len(self._symbol_block_map)}")
            if len(self._blocks) > 0:
                log.info(f"[BlockDictionary] 前5个题材: {[s.name for s in self._blocks[:5]]}")

        except Exception as e:
            log.warning(f"加载 BlockDictionary 失败: {e}")
            import traceback
            log.warning(traceback.format_exc())

    def _load_symbols_from_stock_registry(self):
        """从 BlockDictionary 加载所有股票"""
        try:
            from deva.naja.dictionary.blocks import get_block_dictionary

            bd = get_block_dictionary()
            if not bd:
                log.warning("[BlockDictionary] 未找到 BlockDictionary 单例")
                return

            cn_codes = list(bd.get_all_stocks('CN'))
            us_codes = list(bd.get_all_stocks('US'))
            all_codes = cn_codes + us_codes

            if not all_codes:
                log.warning("[BlockDictionary] 股票列表为空")
                return

            log.info(f"[BlockDictionary] 加载到 {len(all_codes)} 只股票")

            for code in all_codes:
                if code not in self._symbol_block_map:
                    self._symbol_block_map[code] = []

            if not self._blocks:
                self._blocks.append(BlockConfig(block_id="默认", name="默认"))

        except Exception as e:
            log.warning(f"从 BlockDictionary 加载股票失败: {e}")
            import traceback
            log.warning(traceback.format_exc())

    def _guess_block(self, symbol: str) -> str:
        """根据股票代码猜测所属题材"""
        hash_val = hash(symbol) % len(self._blocks)
        return self._blocks[hash_val].block_id if self._blocks else "default"

    def get_datasource_control(self) -> Dict[str, Any]:
        """获取数据源控制指令"""
        if self.hotspot_system is None:
            return {}

        control = self.hotspot_system.get_datasource_control()
        self._last_datasource_control = control
        return control

    def get_frequency_for_symbol(self, symbol: str):
        """获取个股的数据频率档位"""
        if self.hotspot_system is None:
            from ..scheduling import FrequencyLevel
            return FrequencyLevel.LOW

        return self.hotspot_system.frequency_scheduler.get_symbol_level(symbol)

    def should_fetch_symbol(self, symbol: str, timestamp: Optional[float] = None) -> bool:
        """判断是否应该获取该个股的数据"""
        if self.hotspot_system is None:
            return True

        if timestamp is None:
            timestamp = time.time()

        return self.hotspot_system.frequency_scheduler.should_fetch(symbol, timestamp)

    def get_high_hotspot_symbols(self, threshold: float = 2.0) -> List[str]:
        """获取高热点个股列表"""
        if self.hotspot_system is None:
            return []

        symbols = self.hotspot_system.get_high_hotspot_symbols(threshold)
        return [s for s, _ in symbols]

    def get_active_blocks(self, threshold: float = 0.3) -> List[str]:
        """获取活跃题材列表"""
        if self.hotspot_system is None:
            return []

        return self.hotspot_system.get_active_blocks(threshold)

    def get_hotspot_report(self) -> Dict[str, Any]:
        """获取市场热点系统报告"""
        if self.hotspot_system is None:
            return {'status': 'not_initialized'}

        status = self.hotspot_system.get_system_status()
        rf = self.hotspot_system._realtime_fetcher if self.hotspot_system else None

        avg_latency = self._total_latency / max(self._processed_snapshots, 1)

        us_global = self.hotspot_system._us_last_global_hotspot
        us_activity = self.hotspot_system._us_last_activity

        cn_global = status.get('global_hotspot', 0)
        cn_activity = status.get('activity', 0)

        try:
            from deva.naja.radar.trading_clock import is_trading_time as is_cn_trading, is_us_trading_time
            is_cn = is_cn_trading()
            is_us = is_us_trading_time()

            if is_us and not is_cn:
                global_hotspot = us_global
                activity = us_activity
            elif is_cn and not is_us:
                global_hotspot = cn_global
                activity = cn_activity
            else:
                global_hotspot = (cn_global + us_global) / 2
                activity = (cn_activity + us_activity) / 2
        except Exception:
            global_hotspot = cn_global
            activity = cn_activity

        hotspot_details = {
            'global_hotspot': global_hotspot,
            'activity': activity,
            'hotspot_level': '高' if global_hotspot >= 0.6 else ('中' if global_hotspot >= 0.3 else '低'),
            'activity_level': '高' if activity >= 0.7 else ('中' if activity >= 0.15 else '低'),
            'cn_global': cn_global,
            'us_global': us_global,
            'cn_activity': cn_activity,
            'us_activity': us_activity,
        }

        report = {
            'status': 'running' if self._running else 'stopped',
            'processed_snapshots': self._processed_snapshots,
            'avg_latency_ms': avg_latency,
            'global_hotspot': global_hotspot,
            'activity': activity,
            'hotspot_details': hotspot_details,
            'frequency_summary': status.get('frequency_summary', {}),
            'strategy_summary': status.get('strategy_summary', {}),
            'dual_engine_summary': status.get('dual_engine_summary', {}),
            'realtime_fetcher': status.get('realtime_fetcher'),
            'cn_frequency': status.get('cn_frequency', {'high': 0, 'medium': 0, 'low': 0}),
        }

        return report

    def persist_state(self):
        """持久化市场热点系统状态（A股和美股）"""
        if self.hotspot_system is None:
            return

        try:
            if hasattr(self, 'intelligence_system') and self.intelligence_system:
                self.intelligence_system.persist_state()

            state = self.hotspot_system.save_state()
            db = NB('naja_hotspot_state')
            db['hotspot_system_state'] = state
            db.persist()
            log.info(f"[MarketHotspotIntegration] 市场热点系统状态已持久化")
        except Exception as e:
            log.warning(f"[MarketHotspotIntegration] 持久化市场热点系统状态失败: {e}")

    def load_state(self):
        """加载市场热点系统状态（A股和美股）"""
        if self.hotspot_system is None:
            return

        try:
            if hasattr(self, 'intelligence_system') and self.intelligence_system:
                self.intelligence_system.load_state()

            db = NB('naja_hotspot_state')
            state_key = 'hotspot_system_state' if 'hotspot_system_state' in db else 'attention_system_state'
            if state_key in db:
                state = db[state_key]
                self.hotspot_system.load_state(state)
                log.info(f"[MarketHotspotIntegration] 市场热点系统状态已恢复")
            else:
                log.info(f"[MarketHotspotIntegration] 未找到保存的市场热点系统状态")
        except Exception as e:
            log.warning(f"[MarketHotspotIntegration] 恢复市场热点系统状态失败: {e}")

    def start_monitoring(self):
        """启动监控线程"""
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self):
        """停止监控线程"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                if self._processed_snapshots % 1000 == 0 and self._processed_snapshots > 0:
                    report = self.get_hotspot_report()
                    log.debug(f"市场热点系统 状态: processed={report.get('processed_snapshots', 0)}, global={report.get('global_hotspot', 0):.3f}")

                time.sleep(self._check_interval)
            except Exception as e:
                log.error(f"监控循环错误: {e}")
                time.sleep(self._check_interval)

    def reset(self):
        """重置系统"""
        if self.hotspot_system:
            self.hotspot_system.reset()

        self._processed_snapshots = 0
        self._total_latency = 0.0


_market_hotspot_integration: Optional[MarketHotspotIntegration] = None
_integration_lock = threading.Lock()


class HotspotModeManager:
    """
    市场热点系统模式管理器 - 确保交易模式和实验模式互斥

    三种模式：
    - MODE_REALTIME: 实盘交易模式，使用 RealtimeDataFetcher 从 Sina 获取实时数据
    - MODE_LAB: 实验/回放模式，使用 ReplayScheduler 从数据库获取历史数据
    - MODE_FORCE_REALTIME: 强制实盘调试模式，忽略交易时间限制

    核心原则：
    1. 实盘和实验模式互斥
    2. 实验模式启动时自动停止实盘获取器
    3. 实验模式退出时自动恢复实盘获取器
    4. 强制实盘调试模式用于非交易时间调试
    """

    MODE_REALTIME = "realtime"
    MODE_LAB = "lab"
    MODE_FORCE_REALTIME = "force_realtime"

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
            self._mode = self.MODE_REALTIME
            self._original_fetcher_config: Optional[Dict] = None
            self._mode_history: List[Dict] = []
            self._initialized = True
            log.info("[HotspotModeManager] 模式管理器初始化完成，当前模式: realtime")

    def get_diagnostic_info(self) -> Dict[str, Any]:
        """获取诊断信息，用于调试和UI显示"""
        self._ensure_initialized()
        import os
        return {
            'current_mode': self._mode,
            'is_realtime': self._mode in (self.MODE_REALTIME, self.MODE_FORCE_REALTIME),
            'is_lab': self._mode == self.MODE_LAB,
            'is_force_realtime': self._mode == self.MODE_FORCE_REALTIME,
            'env_naaja_lab': os.environ.get('NAJA_LAB_MODE', 'not set'),
            'env_naaja_force_realtime': os.environ.get('NAJA_FORCE_REALTIME', 'not set'),
            'mode_history': self._mode_history[-5:] if self._mode_history else [],
        }

    def set_mode(self, mode: str, fetcher_config: Optional[Dict] = None):
        """
        设置当前模式

        Args:
            mode: MODE_REALTIME, MODE_LAB, 或 MODE_FORCE_REALTIME
            fetcher_config: 实验模式退出时用于恢复实盘获取器的配置
        """
        self._ensure_initialized()
        with self._lock:
            if self._mode == mode:
                log.debug(f"[HotspotModeManager] 模式未变化，仍为: {mode}")
                return

            old_mode = self._mode
            self._mode = mode
            self._mode_history.append({
                'timestamp': time.time(),
                'from': old_mode,
                'to': mode
            })
            log.info(f"[HotspotModeManager] 模式切换: {old_mode} -> {mode}")

            if mode == self.MODE_LAB:
                self._stop_realtime_fetcher_if_running()
            elif mode in (self.MODE_REALTIME, self.MODE_FORCE_REALTIME) and fetcher_config:
                self._restore_realtime_fetcher(fetcher_config)

    def get_mode(self) -> str:
        """获取当前模式"""
        self._ensure_initialized()
        return self._mode

    def is_lab_mode(self) -> bool:
        """是否实验模式"""
        self._ensure_initialized()
        return self._mode == self.MODE_LAB

    def is_realtime_mode(self) -> bool:
        """是否实盘模式（普通或强制）"""
        self._ensure_initialized()
        return self._mode in (self.MODE_REALTIME, self.MODE_FORCE_REALTIME)

    def is_force_realtime_mode(self) -> bool:
        """是否强制实盘调试模式"""
        self._ensure_initialized()
        return self._mode == self.MODE_FORCE_REALTIME

    def save_fetcher_config(self, config: Dict):
        """保存实盘获取器配置（用于后续恢复）"""
        self._original_fetcher_config = config

    def get_fetcher_config(self) -> Optional[Dict]:
        """获取保存的实盘获取器配置"""
        return self._original_fetcher_config

    def _stop_realtime_fetcher_if_running(self):
        """停止实盘获取器"""
        try:
            hotspot_sys = SR('hotspot_system')
            if hotspot_sys and hotspot_sys._realtime_fetcher:
                hotspot_sys._realtime_fetcher.stop()
                log.info("[HotspotModeManager] 已停止实盘获取器")
        except Exception as e:
            log.warning(f"[HotspotModeManager] 停止实盘获取器失败: {e}")

    def _restore_realtime_fetcher(self, config: Optional[Dict]):
        """恢复实盘获取器"""
        try:
            hotspot_sys = SR('hotspot_system')
            if hotspot_sys and config:
                from deva.naja.market_hotspot.data.fetch_config import FetchConfig
                fc = FetchConfig(**config) if config else None
                hotspot_sys.start_realtime_fetcher(fc)
                log.info("[HotspotModeManager] 已恢复实盘获取器")
        except Exception as e:
            log.warning(f"[HotspotModeManager] 恢复实盘获取器失败: {e}")

    def enter_lab_mode(self):
        """进入实验模式"""
        self.set_mode(self.MODE_LAB)

    def exit_lab_mode(self):
        """退出实验模式，恢复正常交易"""
        config = self.get_fetcher_config()
        self.set_mode(self.MODE_NORMAL, config)


def get_mode_manager() -> HotspotModeManager:
    """获取模式管理器单例"""
    from deva.naja.register import SR
    return HotspotModeManager()

def get_market_hotspot_integration() -> MarketHotspotIntegration:
    """获取 MarketHotspotIntegration 单例"""
    from deva.naja.register import SR
    return MarketHotspotIntegration()

def initialize_hotspot_system(
    config: Optional[MarketHotspotSystemConfig] = None,
    intelligence_config: Optional[dict] = None,
    force_realtime: bool = False,
    lab_mode: bool = False
) -> MarketHotspotSystem:
    """
    初始化市场热点系统

    这是主要的初始化入口，在 naja 启动时调用

    Args:
        config: 市场热点系统配置
        intelligence_config: 已废弃，忽略。智能增强系统默认全部启用。
        force_realtime: 强制实盘调试模式（忽略交易时间限制）
        lab_mode: 实验模式（使用回放数据）
    """
    log.info("[initialize_hotspot_system] 开始初始化...")

    mode_manager = get_mode_manager()

    log.info(f"[initialize_hotspot_system] 模式参数: force_realtime={force_realtime}, lab_mode={lab_mode}")

    integration = get_market_hotspot_integration()
    hotspot_system = integration.initialize(config)
    log.info(f"[initialize_hotspot_system] integration.initialize 完成, _initialized={hotspot_system._initialized}")

    log.info("[initialize_hotspot_system] 尝试加载保存的状态...")
    integration.load_state()

    integration.start_monitoring()

    if lab_mode:
        log.info("[initialize_hotspot_system] 实验模式 (lab_mode=True)，设置模式管理器...")
        mode_manager.enter_lab_mode()
        log.info("[initialize_hotspot_system] 实验模式，跳过实盘获取器启动")
    elif force_realtime:
        log.info("[initialize_hotspot_system] 强制实盘调试模式 (force_realtime=True)，忽略交易时间限制")
        mode_manager.set_mode(HotspotModeManager.MODE_FORCE_REALTIME)
        fetcher_config = {
            'base_high_interval': 5.0,
            'base_medium_interval': 10.0,
            'base_low_interval': 60.0,
            'enable_market_data': True,
            'force_trading_mode': True,
            'playback_mode': False,
            'playback_speed': 1.0,
        }
        mode_manager.save_fetcher_config(fetcher_config)
        log.info("[initialize_hotspot_system] 启动实盘获取器 (强制模式)...")
        hotspot_system.start_realtime_fetcher()
    else:
        mode_manager.set_mode(HotspotModeManager.MODE_REALTIME)
        fetcher_config = {
            'base_high_interval': 5.0,
            'base_medium_interval': 10.0,
            'base_low_interval': 60.0,
            'enable_market_data': True,
            'force_trading_mode': False,
            'playback_mode': False,
            'playback_speed': 1.0,
        }
        mode_manager.save_fetcher_config(fetcher_config)
        log.info("[initialize_hotspot_system] 启动实盘获取器 (普通模式)...")
        hotspot_system.start_realtime_fetcher()

    log.info("[initialize_hotspot_system] 初始化完成")
    return hotspot_system


_hotspot_manager = None


def register_hotspot_manager(manager):
    """注册策略管理器"""
    global _hotspot_manager
    _hotspot_manager = manager
    log.debug(f"策略管理器已注册: {manager}")


def get_hotspot_manager():
    """获取策略管理器"""
    return _hotspot_manager


def process_data_with_hotspots(data: pd.DataFrame, context: Optional[Dict] = None) -> List[Any]:
    """使用热点策略处理数据"""
    manager = get_hotspot_manager()

    if manager is None:
        return []

    try:
        signals = manager.process_data(data, context)
        return signals
    except Exception as e:
        log.error(f"策略处理数据失败: {e}")
        return []
