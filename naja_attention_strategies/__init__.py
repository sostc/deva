"""
Naja Attention-Based Strategies

基于注意力系统的策略集，特点：
1. 只在市场活跃时执行
2. 只关注高注意力股票
3. 动态调整策略参数
4. 分层处理：全局 -> 板块 -> 个股

策略列表：
- GlobalMarketSentinel: 全局市场状态监控
- SectorRotationHunter: 板块轮动捕捉
- MomentumSurgeTracker: 动量突破追踪
- AnomalyPatternSniper: 异常模式狙击
- SmartMoneyFlowDetector: 聪明资金流向检测

使用方法：
    from naja_attention_strategies import setup_attention_strategies
    manager = setup_attention_strategies()
"""

from .base import AttentionStrategyBase, Signal
from .global_sentinel import GlobalMarketSentinel
from .sector_hunter import SectorRotationHunter
from .momentum_tracker import MomentumSurgeTracker
from .anomaly_sniper import AnomalyPatternSniper
from .smart_money_detector import SmartMoneyFlowDetector
from .strategy_manager import (
    AttentionStrategyManager,
    StrategyConfig,
    get_strategy_manager,
    initialize_attention_strategies
)
from .config import (
    StrategySettings,
    AttentionStrategyConfig,
    ConfigManager,
    get_config_manager
)

__all__ = [
    # 基类
    "AttentionStrategyBase",
    "Signal",
    # 策略
    "GlobalMarketSentinel",
    "SectorRotationHunter",
    "MomentumSurgeTracker",
    "AnomalyPatternSniper",
    "SmartMoneyFlowDetector",
    # 管理器
    "AttentionStrategyManager",
    "StrategyConfig",
    "get_strategy_manager",
    "initialize_attention_strategies",
    # 配置
    "StrategySettings",
    "AttentionStrategyConfig",
    "ConfigManager",
    "get_config_manager",
    # 快捷函数
    "setup_attention_strategies",
]

__version__ = "1.0.0"


def setup_attention_strategies():
    """
    快速设置注意力策略系统
    
    在 naja 启动脚本中调用：
    
    ```python
    from naja_attention_strategies import setup_attention_strategies
    manager = setup_attention_strategies()
    ```
    
    这将：
    1. 加载配置
    2. 初始化所有策略
    3. 启动策略管理器
    4. 注册到注意力系统
    """
    # 加载配置
    config_manager = get_config_manager()
    
    # 初始化策略
    manager = initialize_attention_strategies()
    
    return manager
