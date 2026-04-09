"""
Naja Attention System - 注意力基础设施

这是系统的通用注意力基础设施，被市场热点系统和新闻叙事系统复用。

基础设施层:
- os/           - AttentionOS 统一入口
- kernel/       - AttentionKernel 核心 + ManasEngine
- values/       - 价值观系统
- portfolio.py  - 持仓管理
- conviction_validator.py - 信念验证
- focus_manager.py - 关注管理
- block_registry.py - 题材注册表

市场热点系统已移动到: market_hotspot/
"""

from .kernel import (
    AttentionEvent,
    QueryState,
    Encoder,
    AttentionHead,
    MultiHeadAttention,
    AttentionKernel,
    get_default_heads,
    get_regime_aware_heads,
)
from .kernel.manas_engine import (
    ManasEngine,
)
from .portfolio import (
    Portfolio,
    StockInfo,
)
from .conviction_validator import (
    ConvictionValidator,
    get_conviction_validator,
)
from .focus_manager import (
    AttentionFocusManager,
    get_attention_focus_manager,
)
from .block_registry import (
    BlockRegistry,
    get_block_registry,
    BlockDescriptor,
)
from .attention_fusion import (
    AttentionFusion,
    get_attention_fusion,
    FusionSignal,
    FullFusionResult,
)
from .attention_os import (
    AttentionOS,
    get_attention_os,
    AttentionKernelOutput,
    AttentionFusionOutput,
)
from .trading_center import (
    TradingCenter,
    get_trading_center,
)

__all__ = [
    # Kernel (通用注意力计算)
    "AttentionEvent",
    "QueryState",
    "Encoder",
    "AttentionHead",
    "MultiHeadAttention",
    "AttentionKernel",
    "get_default_heads",
    "get_regime_aware_heads",
    # ManasEngine (决策中枢)
    "ManasEngine",
    # Portfolio (持仓管理)
    "Portfolio",
    "StockInfo",
    # ConvictionValidator (信念验证)
    "ConvictionValidator",
    "get_conviction_validator",
    # FocusManager (关注管理)
    "AttentionFocusManager",
    "get_attention_focus_manager",
    # BlockRegistry (题材注册表)
    "BlockRegistry",
    "get_block_registry",
    "BlockDescriptor",
    # AttentionFusion (融合层)
    "AttentionFusion",
    "get_attention_fusion",
    "FusionSignal",
    "FullFusionResult",
    # AttentionOS (统一入口)
    "AttentionOS",
    "get_attention_os",
    "AttentionKernelOutput",
    "AttentionFusionOutput",
    # TradingCenter (交易中枢)
    "TradingCenter",
    "get_trading_center",
]

__version__ = "3.0.0"
