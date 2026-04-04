"""
Naja Attention System - 统一注意力调度系统

按功能模块组织的注意力系统架构：

core/          - 核心注意力计算引擎
processing/    - 数据预处理（噪音过滤）
scheduling/    - 频率调度和策略分配
intelligence/  - 智能增强（预测、反馈、预算、学习）
engine/        - River + PyTorch 双引擎
integration/   - 系统集成和主控制器
strategies/    - 基于注意力的交易策略
"""

from .core import (
    GlobalAttentionEngine,
    MarketSnapshot,
    SectorAttentionEngine,
    SectorConfig,
    WeightPool,
    WeightPoolView,
    SymbolWeightConfig,
)
from .processing import (
    NoiseFilter,
    NoiseFilterConfig,
    get_noise_filter,
    get_tick_noise_filter,
    TickNoiseFilterConfig,
)
from .scheduling import (
    FrequencyScheduler,
    FrequencyLevel,
    FrequencyConfig,
    AdaptiveFrequencyController,
    StrategyAllocator,
    StrategyRegistry,
    Strategy,
    StrategyConfig,
    StrategyParams,
    StrategyScope,
    StrategyType,
)
from .engine import (
    RiverEngine,
    PyTorchEngine,
    DualEngineCoordinator,
    AnomalySignal,
    PatternSignal,
)
from .intelligence import (
    PredictiveAttentionEngine,
    PredictionResult,
    EMAAccelerator,
    SecondOrderDifferentiator,
    MomentumPredictor,
    AttentionFeedbackLoop,
    FeedbackCollector,
    AttentionEffectivenessAnalyzer,
    BanditUpdater,
    StrategyOutcome,
    AttentionEffectiveness,
    AttentionBudgetSystem,
    BudgetConfig,
    BudgetLevel,
    BudgetAllocation,
    TopKBudgetAllocator,
    AdaptiveBudgetController,
    ResourceMonitor,
    AttentionPropagation,
    PropagationEngine,
    RelationMatrix,
    SectorRelation,
    StrategyLearning,
    MarketStateDetector,
    BanditStrategySelector,
    RuleBasedStrategySelector,
    MarketState,
    StrategyPerformance,
    StrategySelection,
)
from .integration import (
    AttentionSystem,
    AttentionSystemConfig,
    AttentionSystemIntegration,
    IntelligenceAugmentedSystem,
    IntelligenceConfig,
    create_intelligence_system,
    create_system,
    NajaAttentionIntegration,
    get_attention_integration,
    initialize_attention_system,
    get_attention_system,
    register_strategy_manager,
    get_strategy_manager,
    process_data_with_strategies,
    AttentionModeManager,
    get_mode_manager,
)
from .config import (
    NoiseFilterConfig,
    NajaAttentionConfig,
    load_config,
    get_intelligence_config,
    default_config,
)
from .trading_center import (
    TradingCenter,
    get_trading_center,
    FusionOutput,
    FusionResult,
    DecisionFusion,
)
from .data_processor import (
    DataProcessor,
    get_data_processor,
)
from .cognition_orchestrator import (
    CognitionOrchestrator,
    get_cognition_orchestrator,
)
from .signal_executor import (
    SignalExecutor,
    get_signal_executor,
)
from .liquidity_manager import (
    LiquidityManager,
    get_liquidity_manager,
)
from .state_querier import (
    StateQuerier,
    get_state_querier,
)

from .realtime_data_fetcher import (
    RealtimeDataFetcher,
    AsyncRealtimeDataFetcher,
    FetchConfig,
)
from .kernel import (
    AttentionEvent,
    QueryState,
    Encoder,
    AttentionHead,
    MultiHeadAttention,
    AttentionMemory,
    AttentionKernel,
    get_default_heads,
    get_regime_aware_heads,
)

__all__ = [
    # Core
    "GlobalAttentionEngine",
    "MarketSnapshot",
    "SectorAttentionEngine",
    "SectorConfig",
    "WeightPool",
    "WeightPoolView",
    "SymbolWeightConfig",
    # Processing
    "NoiseFilter",
    "NoiseFilterConfig",
    "get_noise_filter",
    "get_tick_noise_filter",
    "TickNoiseFilterConfig",
    # Scheduling
    "FrequencyScheduler",
    "FrequencyLevel",
    "FrequencyConfig",
    "AdaptiveFrequencyController",
    "StrategyAllocator",
    "StrategyRegistry",
    "Strategy",
    "StrategyConfig",
    "StrategyParams",
    "StrategyScope",
    "StrategyType",
    # Engine
    "RiverEngine",
    "PyTorchEngine",
    "DualEngineCoordinator",
    "AnomalySignal",
    "PatternSignal",
    # Intelligence
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
    # Integration
    "AttentionSystem",
    "AttentionSystemConfig",
    "AttentionSystemIntegration",
    "IntelligenceAugmentedSystem",
    "IntelligenceConfig",
    "create_intelligence_system",
    "create_system",
    "NajaAttentionIntegration",
    "get_attention_integration",
    "initialize_attention_system",
    "get_attention_system",
    "register_strategy_manager",
    "get_strategy_manager",
    "process_data_with_strategies",
    "AttentionModeManager",
    "get_mode_manager",
    # Config
    "NajaAttentionConfig",
    "load_config",
    "get_intelligence_config",
    "default_config",
    # TradingCenter (核心中枢)
    "TradingCenter",
    "get_trading_center",
    "FusionOutput",
    "FusionResult",
    "DecisionFusion",
    # Split Modules
    "DataProcessor",
    "get_data_processor",
    "CognitionOrchestrator",
    "get_cognition_orchestrator",
    "SignalExecutor",
    "get_signal_executor",
    "LiquidityManager",
    "get_liquidity_manager",
    "StateQuerier",
    "get_state_querier",
    # Realtime Fetcher
    "RealtimeDataFetcher",
    "AsyncRealtimeDataFetcher",
    "FetchConfig",
    # Kernel
    "AttentionEvent",
    "QueryState",
    "Encoder",
    "AttentionHead",
    "MultiHeadAttention",
    "AttentionMemory",
    "AttentionKernel",
    "get_default_heads",
    "get_regime_aware_heads",
]

__version__ = "3.0.0"