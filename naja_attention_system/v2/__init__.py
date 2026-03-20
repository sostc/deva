"""
Naja Attention System v2.0

新增模块:
- Module 7: Predictive Attention Engine (预测注意力)
- Module 8: Attention Feedback Loop (注意力反馈)
- Module 9: Attention Budget System (注意力预算)
- Module 10: Attention Propagation (注意力扩散)
- Module 11: Strategy Learning (策略选择学习)

升级目标:
从 Reactive System (响应式) → Adaptive System (自适应)
"""

from .predictive_attention import (
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

from .strategy_learning import (
    StrategyLearning,
    MarketStateDetector,
    BanditStrategySelector,
    RuleBasedStrategySelector,
    MarketState,
    StrategyPerformance,
    StrategySelection
)

from .integration import (
    V2EnhancedAttentionSystem,
    V2Config,
    create_v2_system,
    migrate_from_v1
)


__all__ = [
    # Module 7
    'PredictiveAttentionEngine',
    'PredictionResult',
    'EMAAccelerator',
    'SecondOrderDifferentiator',
    'MomentumPredictor',
    
    # Module 8
    'AttentionFeedbackLoop',
    'FeedbackCollector',
    'AttentionEffectivenessAnalyzer',
    'BanditUpdater',
    'StrategyOutcome',
    'AttentionEffectiveness',
    
    # Module 9
    'AttentionBudgetSystem',
    'BudgetConfig',
    'BudgetLevel',
    'BudgetAllocation',
    'TopKBudgetAllocator',
    'AdaptiveBudgetController',
    'ResourceMonitor',
    
    # Module 10
    'AttentionPropagation',
    'PropagationEngine',
    'RelationMatrix',
    'SectorRelation',
    
    # Module 11
    'StrategyLearning',
    'MarketStateDetector',
    'BanditStrategySelector',
    'RuleBasedStrategySelector',
    'MarketState',
    'StrategyPerformance',
    'StrategySelection',
    
    # Integration
    'V2EnhancedAttentionSystem',
    'V2Config',
    'create_v2_system',
    'migrate_from_v1'
]


__version__ = '2.0.0'
