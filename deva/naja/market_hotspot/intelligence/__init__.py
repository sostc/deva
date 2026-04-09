"""
Intelligence - 智能增强模块
"""

from .predictive_engine import (
    PredictiveAttentionEngine,
    PredictionResult,
    EMAAccelerator,
    SecondOrderDifferentiator,
    MomentumPredictor
)
from .feedback_loop import (
    AttentionFeedbackLoop,
    FeedbackCollector,
    AttentionEffectivenessAnalyzer,
    BanditUpdater,
    StrategyOutcome,
    AttentionEffectiveness
)
from .budget_system import (
    AttentionBudgetSystem,
    BudgetConfig,
    BudgetLevel,
    BudgetAllocation,
    TopKBudgetAllocator,
    AdaptiveBudgetController,
    ResourceMonitor
)
from .propagation import (
    AttentionPropagation,
    PropagationEngine,
    RelationMatrix,
    SectorRelation
)
from .strategy_learner import (
    StrategyLearning,
    MarketStateDetector,
    BanditStrategySelector,
    RuleBasedStrategySelector,
    MarketState,
    StrategyPerformance,
    StrategySelection
)
from .signal_tuner import (
    SignalTuner,
    SignalRecord,
    TradeRecord,
    ParamAdjustment,
    get_signal_tuner,
    start_signal_tuner,
    stop_signal_tuner
)

__all__ = [
    "PredictiveAttentionEngine",
    "PredictionResult",
    "EMAAccelerator",
    "SecondOrderDifferentiator",
    "MomentumPredictor",
    "AttentionFeedbackLoop",
    "FeedbackCollector",
    "AttentionEffectivenessAnalyzer",
    "BanditUpdater",
    "StrategyOutcome",
    "AttentionEffectiveness",
    "AttentionBudgetSystem",
    "BudgetConfig",
    "BudgetLevel",
    "BudgetAllocation",
    "TopKBudgetAllocator",
    "AdaptiveBudgetController",
    "ResourceMonitor",
    "AttentionPropagation",
    "PropagationEngine",
    "RelationMatrix",
    "SectorRelation",
    "StrategyLearning",
    "MarketStateDetector",
    "BanditStrategySelector",
    "RuleBasedStrategySelector",
    "MarketState",
    "StrategyPerformance",
    "StrategySelection",
    "SignalTuner",
    "SignalRecord",
    "TradeRecord",
    "ParamAdjustment",
    "get_signal_tuner",
    "start_signal_tuner",
    "stop_signal_tuner",
]
