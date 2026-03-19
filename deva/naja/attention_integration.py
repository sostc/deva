"""
Naja Attention Scheduling System 集成模块

将注意力系统集成到 Naja 中，实现：
1. 启动时自动加载注意力系统
2. 自动从现有数据源获取板块和个股信息
3. 实时调整数据源频率
4. 动态控制策略执行
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Set
import time
import threading
import logging
from collections import defaultdict

from deva import NB

# 导入注意力系统
from naja_attention_system import (
    AttentionSystem,
    AttentionSystemConfig,
    SectorConfig,
    SectorAttentionEngine,
    FrequencyLevel
)

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
        
        self.attention_system: Optional[AttentionSystem] = None
        self.config: AttentionSystemConfig = AttentionSystemConfig()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._check_interval = 5.0  # 检查间隔（秒）
        
        # 缓存
        self._symbol_sector_map: Dict[str, List[str]] = {}
        self._sectors: List[SectorConfig] = []
        self._last_datasource_control: Optional[Dict] = None
        
        # 统计
        self._processed_snapshots = 0
        self._total_latency = 0.0
        
        self._initialized = True
        log.info("Naja Attention Integration 初始化完成")
    
    def initialize(self, config: Optional[AttentionSystemConfig] = None):
        """
        初始化注意力系统
        
        自动从 naja 数据源获取板块和个股信息
        """
        if config:
            self.config = config
        
        log.info("开始初始化 Attention System...")
        
        # 1. 自动发现板块和个股
        self._discover_sectors_and_symbols()
        
        # 2. 创建注意力系统
        self.attention_system = AttentionSystem(self.config)
        
        # 3. 初始化
        self.attention_system.initialize(self._sectors, self._symbol_sector_map)
        
        # 4. 注册板块和个股名称到历史追踪器
        self._register_names_to_tracker()
        
        log.info(f"Attention System 初始化完成:")
        log.info(f"  - 板块数量: {len(self._sectors)}")
        log.info(f"  - 个股数量: {len(self._symbol_sector_map)}")
        
        return self.attention_system
    
    def _register_names_to_tracker(self):
        """注册板块和个股名称到历史追踪器"""
        try:
            from .attention.history_tracker import get_history_tracker
            tracker = get_history_tracker()
            if tracker is None:
                return
            
            # 注册板块名称
            for sector in self._sectors:
                if sector.name:
                    tracker.register_sector_name(sector.sector_id, sector.name)
                    log.debug(f"注册板块名称: {sector.sector_id} -> {sector.name}")
            
            # 尝试从行情数据注册个股名称
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
            
            log.info(f"已注册 {len(tracker.sector_names)} 个板块名称, {len(tracker.symbol_names)} 个个股名称")
            
        except Exception as e:
            log.warning(f"注册名称到历史追踪器失败: {e}")
    
    def _discover_sectors_and_symbols(self):
        """
        自动从 naja 数据源发现板块和个股
        
        策略：
        1. 尝试从字典数据源获取板块信息
        2. 尝试从行情数据源获取个股列表
        3. 如果没有，使用默认配置
        """
        self._sectors = []
        self._symbol_sector_map = {}
        
        try:
            # 尝试从字典表获取板块信息
            self._load_sectors_from_dictionary()
        except Exception as e:
            log.warning(f"从字典加载板块失败: {e}")
        
        # 如果没有板块，使用默认配置
        if not self._sectors:
            log.info("使用默认板块配置")
            self._load_default_sectors()
        
        # 确保所有个股都有板块映射
        self._ensure_symbol_mappings()
    
    def _load_sectors_from_dictionary(self):
        """从字典数据源加载板块信息"""
        try:
            # 尝试获取行业/概念字典
            db = NB("naja_dictionaries")
            
            # 查找板块相关的字典
            for key in db.keys():
                try:
                    data = db[key]
                    if isinstance(data, pd.DataFrame):
                        # 检查是否有板块相关列
                        if 'sector' in data.columns or 'industry' in data.columns:
                            self._parse_sector_data(data)
                except:
                    continue
        except Exception as e:
            log.warning(f"加载字典数据失败: {e}")
    
    def _parse_sector_data(self, df: pd.DataFrame):
        """解析板块数据"""
        # 确定板块列名
        sector_col = None
        for col in ['sector', 'industry', 'concept', '板块', '行业']:
            if col in df.columns:
                sector_col = col
                break
        
        if not sector_col:
            return
        
        # 确定股票代码列名
        symbol_col = None
        for col in ['code', 'symbol', 'ts_code', '股票代码']:
            if col in df.columns:
                symbol_col = col
                break
        
        if not symbol_col:
            return
        
        # 按板块分组
        sector_groups = df.groupby(sector_col)[symbol_col].apply(list).to_dict()
        
        for sector_name, symbols in sector_groups.items():
            sector_id = f"sector_{len(self._sectors)}"
            sector = SectorConfig(
                sector_id=sector_id,
                name=str(sector_name),
                symbols=set(str(s) for s in symbols),
                decay_half_life=300.0
            )
            self._sectors.append(sector)
            
            # 更新个股映射
            for symbol in symbols:
                symbol_str = str(symbol)
                if symbol_str not in self._symbol_sector_map:
                    self._symbol_sector_map[symbol_str] = []
                self._symbol_sector_map[symbol_str].append(sector_id)
    
    def _load_default_sectors(self):
        """加载默认板块配置"""
        default_sectors = [
            SectorConfig(
                sector_id="tech",
                name="科技",
                symbols=set(),
                decay_half_life=300.0
            ),
            SectorConfig(
                sector_id="finance",
                name="金融",
                symbols=set(),
                decay_half_life=300.0
            ),
            SectorConfig(
                sector_id="healthcare",
                name="医疗",
                symbols=set(),
                decay_half_life=300.0
            ),
            SectorConfig(
                sector_id="energy",
                name="能源",
                symbols=set(),
                decay_half_life=300.0
            ),
            SectorConfig(
                sector_id="consumer",
                name="消费",
                symbols=set(),
                decay_half_life=300.0
            ),
        ]
        
        self._sectors = default_sectors
    
    def _ensure_symbol_mappings(self):
        """确保所有个股都有板块映射"""
        try:
            # 尝试从行情数据源获取所有个股
            db = NB("quant_snapshot_5min_window")
            if db.keys():
                # 获取最新一帧数据
                latest_key = sorted(db.keys())[-1]
                df = db[latest_key]
                
                if isinstance(df, pd.DataFrame) and 'code' in df.columns:
                    for _, row in df.iterrows():
                        symbol = str(row['code'])
                        if symbol not in self._symbol_sector_map:
                            # 根据股票代码特征分配默认板块
                            sector_id = self._guess_sector(symbol)
                            self._symbol_sector_map[symbol] = [sector_id]
                            
                            # 添加到板块配置
                            for sector in self._sectors:
                                if sector.sector_id == sector_id:
                                    sector.symbols.add(symbol)
                                    break
        except Exception as e:
            log.warning(f"确保个股映射失败: {e}")
    
    def _guess_sector(self, symbol: str) -> str:
        """根据股票代码猜测所属板块"""
        # 这里可以根据实际规则扩展
        # 例如：根据代码前缀、历史数据等
        
        # 简单的哈希分配
        hash_val = hash(symbol) % len(self._sectors)
        return self._sectors[hash_val].sector_id if self._sectors else "default"
    
    def process_market_data(self, df: pd.DataFrame, timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        处理市场数据
        
        这是核心接口，在数据源回调中调用
        
        Args:
            df: 市场数据 DataFrame
            timestamp: 时间戳（可选）
            
        Returns:
            注意力系统处理结果
        """
        if self.attention_system is None:
            return {}
        
        if timestamp is None:
            timestamp = time.time()
        
        try:
            # 提取数据
            symbols = df['code'].values if 'code' in df.columns else df.index.values
            
            # 涨跌幅
            if 'change_pct' in df.columns:
                returns = df['change_pct'].values
            elif 'pct_change' in df.columns:
                returns = df['pct_change'].values
            else:
                returns = np.zeros(len(symbols))
            
            # 成交量
            if 'volume' in df.columns:
                volumes = df['volume'].values
            else:
                volumes = np.ones(len(symbols)) * 1000000
            
            # 价格
            if 'now' in df.columns:
                prices = df['now'].values
            elif 'close' in df.columns:
                prices = df['close'].values
            else:
                prices = np.ones(len(symbols)) * 100
            
            # 板块ID
            if 'sector_id' in df.columns:
                sector_ids = df['sector_id'].values
            else:
                # 使用 symbol_sector_map 映射
                sector_ids = np.array([
                    hash(self._symbol_sector_map.get(str(s), ['default'])[0])
                    for s in symbols
                ])
            
            # 处理快照
            result = self.attention_system.process_snapshot(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                sector_ids=sector_ids,
                timestamp=timestamp
            )
            
            # 更新统计
            self._processed_snapshots += 1
            self._total_latency += result.get('latency_ms', 0)
            
            return result
            
        except Exception as e:
            log.error(f"处理市场数据失败: {e}")
            return {}
    
    def get_datasource_control(self) -> Dict[str, Any]:
        """
        获取数据源控制指令
        
        用于动态调整数据源订阅
        """
        if self.attention_system is None:
            return {}
        
        control = self.attention_system.get_datasource_control()
        self._last_datasource_control = control
        return control
    
    def get_frequency_for_symbol(self, symbol: str) -> FrequencyLevel:
        """获取个股的数据频率档位"""
        if self.attention_system is None:
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
    
    def get_active_sectors(self, threshold: float = 0.3) -> List[str]:
        """获取活跃板块列表"""
        if self.attention_system is None:
            return []
        
        return self.attention_system.get_active_sectors(threshold)
    
    def get_attention_report(self) -> Dict[str, Any]:
        """获取注意力系统报告"""
        if self.attention_system is None:
            return {'status': 'not_initialized'}
        
        status = self.attention_system.get_system_status()
        
        # 添加额外统计
        avg_latency = (
            self._total_latency / max(self._processed_snapshots, 1)
        )
        
        report = {
            'status': 'running' if self._running else 'stopped',
            'processed_snapshots': self._processed_snapshots,
            'avg_latency_ms': avg_latency,
            'global_attention': status.get('global_attention', 0),
            'frequency_summary': status.get('frequency_summary', {}),
            'strategy_summary': status.get('strategy_summary', {}),
            'dual_engine_summary': status.get('dual_engine_summary', {}),
        }
        
        return report
    
    def start_monitoring(self):
        """启动监控线程"""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        log.info("Attention System 监控已启动")
    
    def stop_monitoring(self):
        """停止监控线程"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        log.info("Attention System 监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                # 定期输出报告（每1000个快照输出一次，减少日志频率）
                if self._processed_snapshots % 1000 == 0 and self._processed_snapshots > 0:
                    report = self.get_attention_report()
                    log.info(f"Attention System 状态: processed={report.get('processed_snapshots', 0)}, global={report.get('global_attention', 0):.3f}")

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
        
        log.info("Attention System 已重置")


# 全局实例
_naja_attention_integration: Optional[NajaAttentionIntegration] = None
_integration_lock = threading.Lock()


def get_attention_integration() -> NajaAttentionIntegration:
    """获取 Attention Integration 单例"""
    global _naja_attention_integration
    if _naja_attention_integration is None:
        with _integration_lock:
            if _naja_attention_integration is None:
                _naja_attention_integration = NajaAttentionIntegration()
    return _naja_attention_integration


def initialize_attention_system(config: Optional[AttentionSystemConfig] = None) -> AttentionSystem:
    """
    初始化注意力系统
    
    这是主要的初始化入口，在 naja 启动时调用
    """
    integration = get_attention_integration()
    attention_system = integration.initialize(config)
    integration.start_monitoring()
    return attention_system


def get_attention_system() -> Optional[AttentionSystem]:
    """获取 Attention System 实例"""
    integration = get_attention_integration()
    return integration.attention_system


# 策略管理器引用
_strategy_manager = None


def register_strategy_manager(manager):
    """
    注册策略管理器
    
    由 naja_attention_strategies 调用
    """
    global _strategy_manager
    _strategy_manager = manager
    log.info(f"策略管理器已注册: {manager}")


def get_strategy_manager():
    """获取策略管理器"""
    return _strategy_manager


def process_data_with_strategies(data: pd.DataFrame, context: Optional[Dict] = None) -> List[Any]:
    """
    使用注意力策略处理数据
    
    这是策略系统的主要入口，在数据源回调中调用
    
    Args:
        data: 市场数据
        context: 可选的上下文
        
    Returns:
        策略生成的信号列表
    """
    global _strategy_manager
    
    if _strategy_manager is None:
        return []
    
    try:
        signals = _strategy_manager.process_data(data, context)
        return signals
    except Exception as e:
        log.error(f"策略处理数据失败: {e}")
        return []