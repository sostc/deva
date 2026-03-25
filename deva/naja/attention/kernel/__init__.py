"""
Attention Kernel - 事件级注意力计算核心

提供：
- AttentionEvent：统一事件格式
- QueryState：全局查询状态
- Encoder：Key/Value 编码器
- AttentionHead：单头注意力
- MultiHeadAttention：多头注意力融合
- AttentionMemory：持久注意力记忆
- AttentionKernel：核心注意力中枢
"""

from .event import AttentionEvent
from .state import QueryState
from .encoder import Encoder
from .head import AttentionHead
from .multi_head import MultiHeadAttention
from .memory import AttentionMemory
from .kernel import AttentionKernel
from .heads import get_default_heads, get_regime_aware_heads

__all__ = [
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