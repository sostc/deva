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
]
