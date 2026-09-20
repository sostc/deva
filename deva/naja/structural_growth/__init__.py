"""Naja Structural Growth Radar - 结构性增长雷达

基于事件流、产业状态和多 Agent 验证的结构性增长发现系统。
专门寻找供需变化导致的利润跃迁与估值重估候选。

核心对象：
- IndustryState  产业状态卡（六维度 + 二阶导信号）
- Evidence       证据/反证
- 三 Agent 链：
  - DiscoveryAgent   发现者：提出利润跃迁假设
  - VerificationAgent 验证者：收集正反证据，有否决权
  - ValuationAgent   估值分析者：情景分析与预期差

本模块为纯领域逻辑，不依赖 SR() 或全局注册表。
"""

from .evidence import (
    Evidence,
    EvidenceType,
    EvidenceStatus,
    EvidenceChain,
)
from .industry_state import (
    IndustryState,
    FactorState,
    FactorTrend,
    SecondDerivativeSignals,
)
from .valuation_state import (
    ValuationPhase,
    TransitionRules,
    StateTransition,
    ValuationStateMachine,
)
from .observation_pool import ObservationPool, TrackedIndustry
from .data_adapter import IndustryDataAdapter
from .news_bridge import NewsBridge, IndustryConfig
from .industry_aggregator import IndustryAggregator, IndustryAggregate
from .financial_data_fetcher import FinancialDataFetcher, StockFinancial, get_financial_data_fetcher
from .agents.discovery_agent import DiscoveryAgent, GrowthHypothesis, HypothesisType
from .agents.verification_agent import (
    VerificationAgent,
    VerificationResult,
    VerificationVerdict,
)
from .agents.valuation_agent import (
    ValuationAgent,
    ValuationScenario,
    ValuationAnalysis,
)

__all__ = [
    # evidence
    "Evidence",
    "EvidenceType",
    "EvidenceStatus",
    "EvidenceChain",
    # industry state
    "IndustryState",
    "FactorState",
    "FactorTrend",
    "SecondDerivativeSignals",
    # valuation state machine
    "ValuationPhase",
    "TransitionRules",
    "StateTransition",
    "ValuationStateMachine",
    # observation pool
    "ObservationPool",
    "TrackedIndustry",
    # data adapter
    "IndustryDataAdapter",
    # news bridge
    "NewsBridge",
    "IndustryConfig",
    # industry aggregator
    "IndustryAggregator",
    "IndustryAggregate",
    # financial data
    "FinancialDataFetcher",
    "StockFinancial",
    "get_financial_data_fetcher",
    # agents
    "DiscoveryAgent",
    "GrowthHypothesis",
    "HypothesisType",
    "VerificationAgent",
    "VerificationResult",
    "VerificationVerdict",
    "ValuationAgent",
    "ValuationScenario",
    "ValuationAnalysis",
]
