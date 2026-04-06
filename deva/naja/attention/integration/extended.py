"""
Naja Attention System Extended Integration - Naja注意力系统扩展集成

将注意力系统集成到 Naja 中：

职责:
1. 自动从 naja 数据源获取板块和个股信息
2. 初始化注意力系统
3. 提供统一的单例访问接口
4. 管理字典数据加载
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
import time
import threading
import logging

from deva import NB

from .attention_system import AttentionSystem, AttentionSystemConfig
from ..core import BlockConfig as SectorConfig

log = logging.getLogger(__name__)


class NajaAttentionIntegration:
    """
    Naja 注意力系统集成器

    职责：
    1. 自动从 naja 数据源获取板块和个股信息
    2. 初始化注意力系统
    3. 拦截数据源数据进行处理
    4. 提供频率控制接口
    5. 监控和报告

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局注意力集成：NajaAttentionIntegration 是全局注意力系统集成器，
       负责协调 AttentionSystem 和数据流。如果存在多个实例，会导致状态不一致。

    2. 状态一致性：注意力计算状态、频率控制状态等需要在全系统保持一致。

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
        if NajaAttentionIntegration._initialized:
            return
        
        with NajaAttentionIntegration._init_lock:
            # 双重检查
            if NajaAttentionIntegration._initialized:
                return
            
            # 只在第一次创建时设置这些属性
            if not hasattr(self, 'attention_system'):
                self.attention_system: Optional[AttentionSystem] = None
            if not hasattr(self, 'intelligence_system'):
                self.intelligence_system = None
            if not hasattr(self, 'intelligence_config'):
                self.intelligence_config = None
            if not hasattr(self, 'config'):
                self.config: AttentionSystemConfig = AttentionSystemConfig()
            if not hasattr(self, '_running'):
                self._running = False
            if not hasattr(self, '_monitor_thread'):
                self._monitor_thread: Optional[threading.Thread] = None
            if not hasattr(self, '_check_interval'):
                self._check_interval = 5.0
            if not hasattr(self, '_symbol_block_map'):
                self._symbol_block_map: Dict[str, List[str]] = {}
            if not hasattr(self, '_sectors'):
                self._sectors: List[SectorConfig] = []
            if not hasattr(self, '_last_datasource_control'):
                self._last_datasource_control: Optional[Dict] = None
            if not hasattr(self, '_processed_snapshots'):
                self._processed_snapshots = 0
            if not hasattr(self, '_total_latency'):
                self._total_latency = 0.0

            NajaAttentionIntegration._initialized = True

    def initialize(self, config: Optional[AttentionSystemConfig] = None, intelligence_config: Optional[Any] = None):
        """
        初始化注意力系统

        自动从 naja 数据源获取板块和个股信息

        Args:
            config: v1 注意力系统配置
            intelligence_config: 智能增强系统配置
        """
        # 防止重复初始化
        if hasattr(self, '_initialized_attention_system') and self._initialized_attention_system:
            log.info(f"[NajaAttentionIntegration] 已初始化，跳过")
            return self.attention_system
        
        log.info(f"[NajaAttentionIntegration] initialize 开始，config={config}")

        if config:
            self.config = config

        self.intelligence_config = intelligence_config

        self._discover_sectors_and_symbols()

        log.info(f"[NajaAttentionIntegration] 创建 AttentionSystem, config={self.config}")
        self.attention_system = AttentionSystem(self.config)
        log.info(f"[NajaAttentionIntegration] 调用 attention_system.initialize()")
        self.attention_system.initialize(self._sectors, self._symbol_block_map)
        log.info(f"[NajaAttentionIntegration] attention_system.initialize 完成")

        self._register_names_to_tracker()

        self._initialize_intelligence_system()

        log.info(f"🧠 注意力系统: 板块({len(self._sectors)}) 个股({len(self._symbol_block_map)})")
        if self.intelligence_system:
            modules = []
            if hasattr(self.intelligence_system, 'predictive_engine'):
                modules.append('Predictive')
            if hasattr(self.intelligence_system, 'feedback_loop'):
                modules.append('Feedback')
            if hasattr(self.intelligence_system, 'budget_system'):
                modules.append('Budget')
            if hasattr(self.intelligence_system, 'propagation'):
                modules.append('Propagation')
            if hasattr(self.intelligence_system, 'strategy_learning'):
                modules.append('StrategyLearning')
            log.info(f"🧠 智能增强：{', '.join(modules)}")

        self._initialized_attention_system = True
        return self.attention_system

    def _initialize_intelligence_system(self):
        """初始化智能增强系统"""
        if self.intelligence_config is None:
            return

        try:
            from .integration import (
                _IntelligenceAugmentedSystemInternal,
                IntelligenceConfig,
            )

            if isinstance(self.intelligence_config, dict):
                ic = IntelligenceConfig(
                    enable_predictive=self.intelligence_config.get('enable_predictive', True),
                    enable_feedback=self.intelligence_config.get('enable_feedback', True),
                    enable_budget=self.intelligence_config.get('enable_budget', True),
                    enable_propagation=self.intelligence_config.get('enable_propagation', True),
                    enable_strategy_learning=self.intelligence_config.get('enable_strategy_learning', True)
                )
            else:
                ic = self.intelligence_config

            self.intelligence_system = _IntelligenceAugmentedSystemInternal(
                config=None,
                intelligence_config=ic
            )

            log.info("🧠 智能增强系统初始化完成")
        except Exception as e:
            import traceback
            log.error(f"智能增强系统初始化失败: {e}")
            log.error(traceback.format_exc())
            self.intelligence_system = None

    def _register_names_to_tracker(self):
        """注册板块和个股名称到历史追踪器"""
        try:
            from deva.naja.cognition.history_tracker import get_history_tracker
            tracker = get_history_tracker()
            if tracker is None:
                return

            tracker.register_sectors(self._sectors)
            log.info(f"共注册 {len(self._sectors)} 个板块名称到tracker")

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

            log.debug(f"已注册 {len(tracker.block_names)} 个板块名称, {len(tracker.symbol_names)} 个个股名称")

        except Exception as e:
            log.debug(f"注册名称到历史追踪器失败: {e}")

    def _discover_sectors_and_symbols(self):
        """
        自动从 naja 数据源发现板块和个股

        策略：
        1. 尝试从字典数据源获取板块信息
        2. 尝试从行情数据源获取个股列表
        3. 如果没有，使用默认配置
        """
        self._sectors = []
        self._symbol_block_map = {}

        try:
            self._load_sectors_from_dictionary()
        except Exception as e:
            log.warning(f"从字典加载板块失败: {e}")

        if not self._sectors:
            self._load_default_sectors()

        self._ensure_symbol_mappings()

    def _load_sectors_from_dictionary(self):
        """从字典数据源加载板块信息"""
        try:
            from deva.naja.dictionary import get_dictionary_manager
            mgr = get_dictionary_manager()

            entry = mgr.get_by_name("通达信概念板块")
            if entry:
                data = entry.get_payload()
                if isinstance(data, pd.DataFrame):
                    log.info(f"[Dictionary] ✅ 找到通达信板块数据, columns={list(data.columns)}, rows={len(data)}")
                    self._parse_sector_data(data)
                else:
                    log.warning(f"[Dictionary] 通达信板块数据不是DataFrame: {type(data)}")
            else:
                log.warning(f"[Dictionary] 未找到'通达信概念板块'字典")

            log.info(f"[Dictionary] 加载完成: 板块数={len(self._sectors)}")
            if len(self._sectors) > 0:
                log.info(f"[Dictionary] 前5个板块: {[s.name for s in self._sectors[:5]]}")
        except Exception as e:
            log.warning(f"加载字典数据失败: {e}")
            import traceback
            log.warning(traceback.format_exc())

    def _parse_sector_data(self, df: pd.DataFrame):
        """解析板块数据"""
        sector_col = None
        for col in ['blocks', 'block', 'sector', 'industry', 'concept', '板块', '行业']:
            if col in df.columns:
                sector_col = col
                break

        if not sector_col:
            log.warning(f"[Dictionary] 未找到板块列，可用列: {list(df.columns)}")
            return

        symbol_col = None
        for col in ['code', 'symbol', 'ts_code', 'stock_code', '股票代码']:
            if col in df.columns:
                symbol_col = col
                break

        if not symbol_col:
            log.warning(f"[Dictionary] 未找到股票代码列，可用列: {list(df.columns)}")
            return

        log.info(f"[Dictionary] 解析板块数据: sector_col={sector_col}, symbol_col={symbol_col}, 行数={len(df)}")

        def _should_skip_sector_name(name: str) -> bool:
            name_str = str(name).strip()
            if not name_str:
                return True
            return ("B股" in name_str) or ("含B股" in name_str)

        skipped_sectors = 0

        if '|' in str(df[sector_col].iloc[0] if len(df) > 0 else ''):
            log.info(f"[Dictionary] 使用多值板块解析模式")

            for _, row in df.iterrows():
                code = str(row[symbol_col])
                blocks_str = str(row[sector_col])
                blocks = blocks_str.split('|') if '|' in blocks_str else [blocks_str]

                for block_name in blocks:
                    block_name = block_name.strip()
                    if not block_name:
                        continue
                    if _should_skip_sector_name(block_name):
                        skipped_sectors += 1
                        continue

                    import hashlib
                    block_id = f"block_{int(hashlib.md5(block_name.encode()).hexdigest()[:8], 16) % 100000}"

                    existing_sector = None
                    for s in self._sectors:
                        if s.name == block_name:
                            existing_sector = s
                            break

                    if existing_sector:
                        existing_sector.symbols.add(code)
                        self._symbol_block_map.setdefault(code, []).append(existing_sector.block_id)
                    else:
                        sector = SectorConfig(
                            block_id=block_id,
                            name=block_name,
                            symbols={code},
                            decay_half_life=300.0
                        )
                        self._sectors.append(sector)
                        self._symbol_block_map.setdefault(code, []).append(block_id)

            log.info(f"[Dictionary] 多值解析完成: 板块数={len(self._sectors)}, 个股数={len(self._symbol_block_map)}")
        else:
            sector_groups = df.groupby(sector_col)[symbol_col].apply(list).to_dict()

            for sector_name, symbols in sector_groups.items():
                if _should_skip_sector_name(sector_name):
                    skipped_sectors += 1
                    continue
                block_id = f"sector_{len(self._sectors)}"
                sector = SectorConfig(
                    block_id=block_id,
                    name=str(sector_name),
                    symbols=set(str(s) for s in symbols),
                    decay_half_life=300.0
                )
                self._sectors.append(sector)

                for symbol in symbols:
                    symbol_str = str(symbol)
                    if symbol_str not in self._symbol_block_map:
                        self._symbol_block_map[symbol_str] = []
                    self._symbol_block_map[symbol_str].append(block_id)

        if skipped_sectors > 0:
            log.info(f"[Dictionary] 过滤板块完成: 跳过 {skipped_sectors} 个含B股相关板块")

    def _load_default_sectors(self):
        """加载默认板块配置"""
        default_sectors = [
            SectorConfig(block_id="tech", name="科技", symbols=set(), decay_half_life=300.0),
            SectorConfig(block_id="finance", name="金融", symbols=set(), decay_half_life=300.0),
            SectorConfig(block_id="healthcare", name="医疗", symbols=set(), decay_half_life=300.0),
            SectorConfig(block_id="energy", name="能源", symbols=set(), decay_half_life=300.0),
            SectorConfig(block_id="consumer", name="消费", symbols=set(), decay_half_life=300.0),
        ]

        self._sectors = default_sectors

    def _ensure_symbol_mappings(self):
        """确保所有个股都有板块映射"""
        try:
            db = NB("quant_snapshot_5min_window")
            keys = list(db.keys())
            log.debug(f"[_ensure_symbol_mappings] 数据库键数量: {len(keys)}")

            if keys:
                latest_key = sorted(keys)[-1]
                df = db[latest_key]
                log.debug(f"[_ensure_symbol_mappings] 最新键: {latest_key}, 类型: {type(df)}")

                if isinstance(df, pd.DataFrame) and 'code' in df.columns:
                    log.debug(f"[_ensure_symbol_mappings] DataFrame 行数: {len(df)}, 列: {list(df.columns)}")
                    for _, row in df.iterrows():
                        symbol = str(row['code'])
                        if symbol not in self._symbol_block_map:
                            block_id = self._guess_sector(symbol)
                            self._symbol_block_map[symbol] = [block_id]

                            for sector in self._sectors:
                                if sector.block_id == block_id:
                                    sector.symbols.add(symbol)
                                    break
                    log.debug(f"[_ensure_symbol_mappings] 完成后个股映射数: {len(self._symbol_block_map)}")
                else:
                    log.debug(f"[_ensure_symbol_mappings] 数据不是DataFrame或没有code列")
            else:
                log.debug(f"[_ensure_symbol_mappings] 数据库为空")
        except Exception as e:
            log.warning(f"确保个股映射失败: {e}")
            import traceback
            log.warning(traceback.format_exc())

    def _guess_sector(self, symbol: str) -> str:
        """根据股票代码猜测所属板块"""
        hash_val = hash(symbol) % len(self._sectors)
        return self._sectors[hash_val].block_id if self._sectors else "default"

    def get_datasource_control(self) -> Dict[str, Any]:
        """获取数据源控制指令"""
        if self.attention_system is None:
            return {}

        control = self.attention_system.get_datasource_control()
        self._last_datasource_control = control
        return control

    def get_frequency_for_symbol(self, symbol: str):
        """获取个股的数据频率档位"""
        if self.attention_system is None:
            from ..scheduling import FrequencyLevel
            return FrequencyLevel.LOW

        return self.attention_system.frequency_scheduler.get_symbol_level(symbol)

    def should_fetch_symbol(self, symbol: str, timestamp: Optional[float] = None) -> bool:
        """判断是否应该获取该个股的数据"""
        if self.attention_system is None:
            return True

        if timestamp is None:
            timestamp = time.time()

        return self.attention_system.frequency_scheduler.should_fetch(symbol, timestamp)

    def get_high_attention_symbols(self, threshold: float = 2.0) -> List[str]:
        """获取高注意力个股列表"""
        if self.attention_system is None:
            return []

        symbols = self.attention_system.get_high_attention_symbols(threshold)
        return [s for s, _ in symbols]

    def get_active_blocks(self, threshold: float = 0.3) -> List[str]:
        """获取活跃板块列表"""
        if self.attention_system is None:
            return []

        return self.attention_system.get_active_blocks(threshold)

    def get_attention_report(self) -> Dict[str, Any]:
        """获取注意力系统报告"""
        if self.attention_system is None:
            return {'status': 'not_initialized'}

        status = self.attention_system.get_system_status()

        avg_latency = self._total_latency / max(self._processed_snapshots, 1)

        us_global = self.attention_system._us_last_global_attention
        us_activity = self.attention_system._us_last_activity

        cn_global = status.get('global_attention', 0)
        cn_activity = status.get('activity', 0)

        try:
            from deva.naja.radar.trading_clock import is_trading_time as is_cn_trading, is_us_trading_time
            is_cn = is_cn_trading()
            is_us = is_us_trading_time()

            if is_us and not is_cn:
                global_attention = us_global
                activity = us_activity
            elif is_cn and not is_us:
                global_attention = cn_global
                activity = cn_activity
            else:
                global_attention = (cn_global + us_global) / 2
                activity = (cn_activity + us_activity) / 2
        except Exception:
            global_attention = cn_global
            activity = cn_activity

        attention_details = {
            'global_attention': global_attention,
            'activity': activity,
            'attention_level': '高' if global_attention >= 0.6 else ('中' if global_attention >= 0.3 else '低'),
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
            'global_attention': global_attention,
            'activity': activity,
            'attention_details': attention_details,
            'frequency_summary': status.get('frequency_summary', {}),
            'strategy_summary': status.get('strategy_summary', {}),
            'dual_engine_summary': status.get('dual_engine_summary', {}),
            'realtime_fetcher': status.get('realtime_fetcher'),
        }

        return report

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
                    report = self.get_attention_report()
                    log.debug(f"Attention System 状态: processed={report.get('processed_snapshots', 0)}, global={report.get('global_attention', 0):.3f}")

                time.sleep(self._check_interval)
            except Exception as e:
                log.error(f"监控循环错误: {e}")
                time.sleep(self._check_interval)

    def reset(self):
        """重置系统"""
        if self.attention_system:
            self.attention_system.reset()

        self._processed_snapshots = 0
        self._total_latency = 0.0


_naja_attention_integration: Optional[NajaAttentionIntegration] = None
_integration_lock = threading.Lock()


class AttentionModeManager:
    """
    注意力系统模式管理器 - 确保交易模式和实验模式互斥

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
            log.info("[AttentionModeManager] 模式管理器初始化完成，当前模式: realtime")

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
                log.debug(f"[AttentionModeManager] 模式未变化，仍为: {mode}")
                return

            old_mode = self._mode
            self._mode = mode
            self._mode_history.append({
                'timestamp': time.time(),
                'from': old_mode,
                'to': mode
            })
            log.info(f"[AttentionModeManager] 模式切换: {old_mode} -> {mode}")

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
            attention_system = get_attention_system()
            if attention_system and attention_system._realtime_fetcher:
                attention_system._realtime_fetcher.stop()
                log.info("[AttentionModeManager] 已停止实盘获取器")
        except Exception as e:
            log.warning(f"[AttentionModeManager] 停止实盘获取器失败: {e}")

    def _restore_realtime_fetcher(self, config: Optional[Dict]):
        """恢复实盘获取器"""
        try:
            attention_system = get_attention_system()
            if attention_system and config:
                from deva.naja.attention.realtime_data_fetcher import FetchConfig
                fc = FetchConfig(**config) if config else None
                attention_system.start_realtime_fetcher(fc)
                log.info("[AttentionModeManager] 已恢复实盘获取器")
        except Exception as e:
            log.warning(f"[AttentionModeManager] 恢复实盘获取器失败: {e}")

    def enter_lab_mode(self):
        """进入实验模式"""
        self.set_mode(self.MODE_LAB)

    def exit_lab_mode(self):
        """退出实验模式，恢复正常交易"""
        config = self.get_fetcher_config()
        self.set_mode(self.MODE_NORMAL, config)


def get_mode_manager() -> AttentionModeManager:
    """获取模式管理器单例"""
    return AttentionModeManager()


def get_attention_integration() -> NajaAttentionIntegration:
    """获取 Attention Integration 单例"""
    return NajaAttentionIntegration()


def initialize_attention_system(
    config: Optional[AttentionSystemConfig] = None,
    intelligence_config: Optional[dict] = None
) -> AttentionSystem:
    """
    初始化注意力系统

    这是主要的初始化入口，在 naja 启动时调用

    环境变量模式检测优先级：
    1. NAJA_LAB_MODE=1 -> 实验模式
    2. NAJA_FORCE_REALTIME=1 -> 强制实盘调试模式
    3. 默认 -> 普通实盘模式

    Args:
        config: 注意力系统配置
        intelligence_config: 智能增强系统配置
    """
    import os

    log.info("[initialize_attention_system] 开始初始化...")

    mode_manager = get_mode_manager()

    is_lab_mode = os.environ.get('NAJA_LAB_MODE') == '1'
    is_force_realtime = os.environ.get('NAJA_FORCE_REALTIME') == '1'

    log.info(f"[initialize_attention_system] 模式检测: NAJA_LAB_MODE={'1' if is_lab_mode else 'not set'}, NAJA_FORCE_REALTIME={'1' if is_force_realtime else 'not set'}")

    integration = get_attention_integration()
    attention_system = integration.initialize(config, intelligence_config=intelligence_config)
    log.info(f"[initialize_attention_system] integration.initialize 完成, _initialized={attention_system._initialized}")
    integration.start_monitoring()

    if is_lab_mode:
        log.info("[initialize_attention_system] 检测到实验模式 (NAJA_LAB_MODE=1)，设置模式管理器...")
        mode_manager.enter_lab_mode()
        log.info("[initialize_attention_system] 实验模式，跳过实盘获取器启动")
    elif is_force_realtime:
        log.info("[initialize_attention_system] ⚠️ 强制实盘调试模式 (NAJA_FORCE_REALTIME=1)，忽略交易时间限制")
        mode_manager.set_mode(AttentionModeManager.MODE_FORCE_REALTIME)
        fetcher_config = {
            'base_high_interval': 1.0,
            'base_medium_interval': 10.0,
            'base_low_interval': 60.0,
            'enable_market_data': True,
            'force_trading_mode': True,
            'playback_mode': False,
            'playback_speed': 1.0,
        }
        mode_manager.save_fetcher_config(fetcher_config)
        log.info("[initialize_attention_system] 启动实盘获取器 (强制模式)...")
        attention_system.start_realtime_fetcher()
    else:
        mode_manager.set_mode(AttentionModeManager.MODE_REALTIME)
        fetcher_config = {
            'base_high_interval': 1.0,
            'base_medium_interval': 10.0,
            'base_low_interval': 60.0,
            'enable_market_data': True,
            'force_trading_mode': False,
            'playback_mode': False,
            'playback_speed': 1.0,
        }
        mode_manager.save_fetcher_config(fetcher_config)
        log.info("[initialize_attention_system] 启动实盘获取器 (普通模式)...")
        attention_system.start_realtime_fetcher()

    log.info("[initialize_attention_system] 初始化完成")
    return attention_system


def get_attention_system() -> Optional[AttentionSystem]:
    """获取 Attention System 实例"""
    integration = get_attention_integration()
    return integration.attention_system


_strategy_manager = None


def register_strategy_manager(manager):
    """注册策略管理器"""
    global _strategy_manager
    _strategy_manager = manager
    log.debug(f"策略管理器已注册: {manager}")


def get_strategy_manager():
    """获取策略管理器"""
    return _strategy_manager


def process_data_with_strategies(data: pd.DataFrame, context: Optional[Dict] = None) -> List[Any]:
    """使用注意力策略处理数据"""
    global _strategy_manager

    if _strategy_manager is None:
        return []

    try:
        signals = _strategy_manager.process_data(data, context)
        return signals
    except Exception as e:
        log.error(f"策略处理数据失败: {e}")
        return []
