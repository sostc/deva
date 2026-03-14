"""Bandit 策略选择和调节模块

提供 Multi-armed Bandit 算法实现，支持策略的在线自适应选择。
与 LLM Controller 架构一致，支持相同的动作类型。

完整流程：
1. SignalListener - 监听信号流，识别股票
2. VirtualPortfolio - 虚拟持仓管理
3. MarketDataObserver - 市场数据观察
4. AdaptiveCycle - 自适应循环控制器
"""

from .optimizer import (
    BanditOptimizer,
    BanditDecision,
    StrategyReward,
    BanditAction,
    get_bandit_optimizer,
)
from .tracker import (
    BanditPositionTracker,
    get_bandit_tracker,
)
from .runner import (
    BanditAutoRunner,
    get_bandit_runner,
    ensure_bandit_auto_runner,
)
from .xiaohe_integration import (
    XiaoHeBanditIntegration,
    get_xiaohe_bandit_integration,
    enable_xiaohe_bandit,
    disable_xiaohe_bandit,
)
from .signal_listener import (
    SignalListener,
    DetectedSignal,
    get_signal_listener,
)
from .virtual_portfolio import (
    VirtualPortfolio,
    VirtualPosition,
    get_virtual_portfolio,
)
from .market_observer import (
    MarketDataObserver,
    get_market_observer,
)
from .adaptive_cycle import (
    AdaptiveCycle,
    get_adaptive_cycle,
)

__all__ = [
    "BanditOptimizer",
    "BanditDecision",
    "StrategyReward",
    "BanditAction",
    "get_bandit_optimizer",
    "BanditPositionTracker",
    "get_bandit_tracker",
    "BanditAutoRunner",
    "get_bandit_runner",
    "ensure_bandit_auto_runner",
    "XiaoHeBanditIntegration",
    "get_xiaohe_bandit_integration",
    "enable_xiaohe_bandit",
    "disable_xiaohe_bandit",
    "SignalListener",
    "DetectedSignal",
    "get_signal_listener",
    "VirtualPortfolio",
    "VirtualPosition",
    "get_virtual_portfolio",
    "MarketDataObserver",
    "get_market_observer",
    "AdaptiveCycle",
    "get_adaptive_cycle",
]
