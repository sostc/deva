"""
Attention Kernel - 事件级注意力计算核心

提供：
- AttentionEvent：统一事件格式
- QueryState：全局查询状态
- Encoder：Key/Value 编码器
- AttentionHead：单头注意力
- MultiHeadAttention：多头注意力融合
- AttentionKernel：核心注意力中枢
- ManasEngine：末那识引擎（完整决策中枢）
- ManasManager：末那识引擎管理器
- DecisionAttention：决策型注意力调制器
- TemperatureAwareHead：支持温度调制的 AttentionHead

新增（借鉴 Transformer）：
- EventEmbedding：事件嵌入表示
- MarketFeatureEncoder：市场特征编码器
- EventSelfAttention：事件自注意力层
- FeedForwardNetwork：前馈网络层
- TransformerLikeAttentionLayer：类 Transformer 完整注意力层

新增（借鉴大模型上下文学习）：
- Demonstration：示范样本
- InContextAttentionLearner：上下文学习器
"""

from .event import AttentionEvent
from .state import QueryState
from .event_encoder import Encoder
from .attention_scorer import AttentionHead
from .multi_scorer import MultiHeadAttention
from .kernel import AttentionKernel
from .heads import get_default_heads, get_regime_aware_heads
from .manas_engine import (
    ManasEngine,
    TimingEngine,
    RegimeEngine,
    ConfidenceEngine,
    RiskEngine,
    MetaManas,
    BiasState,
    ManasOutput,
)
from .manas_manager import (
    ManasManager,
    get_manas_manager,
    setup_manas_manager,
)
from .decision_attention import DecisionAttention, TemperatureAwareHead

# 新增：借鉴 Transformer 的组件
from .embedding import EventEmbedding, MarketFeatureEncoder
from .self_attention import (
    EventSelfAttention,
    FeedForwardNetwork,
    TransformerLikeAttentionLayer,
)

# 新增：借鉴大模型上下文学习的组件
from .in_context_learner import (
    Demonstration,
    InContextAttentionLearner,
    get_in_context_learner,
    setup_in_context_learner,
)

__all__ = [
    "AttentionEvent",
    "QueryState",
    "Encoder",
    "AttentionHead",
    "MultiHeadAttention",
    "AttentionKernel",
    "get_default_heads",
    "get_regime_aware_heads",
    "ManasEngine",
    "TimingEngine",
    "RegimeEngine",
    "ConfidenceEngine",
    "RiskEngine",
    "MetaManas",
    "BiasState",
    "ManasOutput",
    "ManasManager",
    "get_manas_manager",
    "setup_manas_manager",
    "DecisionAttention",
    "TemperatureAwareHead",
    # 新增：借鉴 Transformer 的组件
    "EventEmbedding",
    "MarketFeatureEncoder",
    "EventSelfAttention",
    "FeedForwardNetwork",
    "TransformerLikeAttentionLayer",
    # 新增：借鉴大模型上下文学习的组件
    "Demonstration",
    "InContextAttentionLearner",
    "get_in_context_learner",
    "setup_in_context_learner",
]
