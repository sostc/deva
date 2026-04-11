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
)
from .runner import (
    BanditAutoRunner,
    ensure_bandit_auto_runner,
)
from .signal_listener import (
    SignalListener,
    DetectedSignal,
)
from .virtual_portfolio import (
    VirtualPortfolio,
    VirtualPosition,
)
from .market_observer import (
    MarketDataObserver,
    get_market_observer,
)
from .adaptive_cycle import (
    AdaptiveCycle,
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
from .stock_block_map import (
    StockBlockMap,
    StockMetadata,
    get_stock_block_map,
)
from .supply_chain_graph import (
    SupplyChainKnowledgeGraph,
    GraphNode,
    GraphEdge,
    NodeType,
    RelationType,
    SupplyChainAnalysis,
    get_supply_chain_graph,
)
from .tuner import (
    BanditTuner,
    ParameterSpace,
    TuningResult,
    get_bandit_tuner,
)
from .market_data_bus import (
    MarketDataBus,
    MarketQuote,
    get_market_data_bus,
)
from .fundamental_data_fetcher import (
    FundamentalDataFetcher,
    get_fundamental_data_fetcher,
)
from deva.naja.register import SR


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
    cycle = SR('adaptive_cycle')
    runner = SR('bandit_runner')
    listener = SR('signal_listener')
    observer = get_market_observer()
    portfolio = SR('virtual_portfolio')

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

    # 启动持仓价格自动更新（每次启动都运行，不依赖于之前的运行状态）
    try:
        from .portfolio_manager import get_portfolio_manager
        pm = get_portfolio_manager()
        pm.start_price_auto_update()
    except Exception as e:
        log.warning(f"启动持仓价格自动更新失败: {e}")


__all__ = [
    "BanditOptimizer",
    "BanditDecision",
    "StrategyReward",
    "BanditAction",
    "get_bandit_optimizer",
    "BanditPositionTracker",
    "BanditAutoRunner",
    "ensure_bandit_auto_runner",
    "SignalListener",
    "DetectedSignal",
    "VirtualPortfolio",
    "VirtualPosition",

    "MarketDataObserver",
    "get_market_observer",
    "AdaptiveCycle",
    "restore_bandit_state",
    "StrategyAttribution",
    "TradeAttribution",
    "StrategyContribution",
    "SignalQualityAnalysis",
    "MarketConditionAttribution",
    "get_attribution",
    "record_trade_attribution",
    "StockBlockMap",
    "StockMetadata",
    "get_stock_block_map",
    "SupplyChainKnowledgeGraph",
    "GraphNode",
    "GraphEdge",
    "NodeType",
    "RelationType",
    "SupplyChainAnalysis",
    "get_supply_chain_graph",
    "SupplyChainValuationEngine",
    "ValuationLevel",
    "ValuationResult",
    "get_supply_chain_valuation_engine",
    "BanditTuner",
    "ParameterSpace",
    "TuningResult",
    "get_bandit_tuner",
    "MarketDataBus",
    "MarketQuote",
    "get_market_data_bus",
    "FundamentalDataFetcher",
    "get_fundamental_data_fetcher",
]
