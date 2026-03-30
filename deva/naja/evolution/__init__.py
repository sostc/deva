"""
Evolution Module - 进化层

提供系统自我观察、自我学习和自我改进能力

类：
- MetaEvolution: 元进化引擎
- SelfObserver: 自我观察器
- OpportunityEngine: 主动机会创造引擎
- ActionExecutor: 行动执行器
"""

from .meta_evolution import (
    MetaEvolution,
    SelfObserver,
    ModulePerformance,
    DecisionRecord,
    EvolutionInsight,
    EvolutionPhase,
    PerformanceTrend,
    get_meta_evolution,
    initialize_meta_evolution,
)

from .opportunity_engine import (
    OpportunityEngine,
    OpportunityScanner,
    TimingOptimizer,
    OpportunityType,
    OpportunityStage,
    Opportunity,
    TimingSignal,
)

from .action_executor import (
    ActionExecutor,
    WisdomSynthesizer,
    ActionGenerator,
    ExecutionCoordinator,
    ActionType,
    ActionPriority,
    TradingAction,
    WisdomInput,
)

__all__ = [
    "MetaEvolution",
    "SelfObserver",
    "ModulePerformance",
    "DecisionRecord",
    "EvolutionInsight",
    "EvolutionPhase",
    "PerformanceTrend",
    "get_meta_evolution",
    "initialize_meta_evolution",
    "OpportunityEngine",
    "OpportunityScanner",
    "TimingOptimizer",
    "OpportunityType",
    "OpportunityStage",
    "Opportunity",
    "TimingSignal",
    "ActionExecutor",
    "WisdomSynthesizer",
    "ActionGenerator",
    "ExecutionCoordinator",
    "ActionType",
    "ActionPriority",
    "TradingAction",
    "WisdomInput",
]