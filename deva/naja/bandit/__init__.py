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
from .attribution import (
    StrategyAttribution,
    TradeAttribution,
    StrategyContribution,
    SignalQualityAnalysis,
    MarketConditionAttribution,
    get_attribution,
    record_trade_attribution,
)
from .tuner import (
    BanditTuner,
    ParameterSpace,
    TuningResult,
    get_bandit_tuner,
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
    
    # 获取各组件
    cycle = get_adaptive_cycle()
    runner = get_bandit_runner()
    listener = get_signal_listener()
    observer = get_market_observer()
    portfolio = get_virtual_portfolio()

    # 统计需要恢复的组件
    running_components = []
    if cycle._running:
        running_components.append("AdaptiveCycle")
    if runner._running:
        running_components.append("BanditAutoRunner")
    if listener._running:
        running_components.append("SignalListener")
    if observer._running:
        running_components.append("MarketDataObserver")

    if running_components:
        log.info(f"🎯 恢复 Bandit: {', '.join(running_components)}")

    # 恢复各组件（cycle 会自动触发其他组件恢复）
    if cycle._running:
        cycle._restore_running_state()
    else:
        runner.start() if runner._running else None
        listener.start() if listener._running else None
        observer.start() if observer._running else None


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
    "StrategyAttribution",
    "TradeAttribution",
    "StrategyContribution",
    "SignalQualityAnalysis",
    "MarketConditionAttribution",
    "get_attribution",
    "record_trade_attribution",
    "BanditTuner",
    "ParameterSpace",
    "TuningResult",
    "get_bandit_tuner",
]
