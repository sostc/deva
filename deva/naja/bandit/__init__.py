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


def restore_bandit_state():
    """恢复 Bandit 所有组件的运行状态
    
    在系统启动时调用，恢复：
    1. SignalListener 运行状态
    2. MarketDataObserver 运行状态和跟踪股票
    3. BanditAutoRunner 运行状态
    4. AdaptiveCycle 运行状态
    5. VirtualPortfolio 持仓数据
    """
    import logging
    log = logging.getLogger(__name__)
    
    log.info("=== 开始恢复 Bandit 状态 ===")
    
    # 1. 获取自适应循环（会自动触发各组件的恢复）
    cycle = get_adaptive_cycle()
    
    # 2. 如果 AdaptiveCycle 之前是运行状态，启动它
    if cycle._running:
        log.info("AdaptiveCycle 之前处于运行状态，正在恢复...")
        cycle._restore_running_state()
    else:
        log.info("AdaptiveCycle 之前未运行，跳过恢复")
    
    # 3. 获取并恢复 BanditAutoRunner
    runner = get_bandit_runner()
    if runner._running:
        log.info("BanditAutoRunner 之前处于运行状态，正在启动...")
        runner.start()
    
    # 4. 获取并恢复 SignalListener
    listener = get_signal_listener()
    if listener._running:
        log.info("SignalListener 之前处于运行状态，正在启动...")
        listener.start()
    
    # 5. 获取并恢复 MarketDataObserver
    observer = get_market_observer()
    if observer._running:
        log.info("MarketDataObserver 之前处于运行状态，正在启动...")
        observer.start()
    
    log.info("=== Bandit 状态恢复完成 ===")


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
    "restore_bandit_state",
]
