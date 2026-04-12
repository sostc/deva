"""
Naja Attention System - 注意力基础设施

这是系统的通用注意力基础设施，被市场热点系统和新闻叙事系统复用。

目录结构:
- os/              - AttentionOS 核心层（入口 + OS内核 + 策略决策）
- orchestration/   - 协调层（交易中枢 + 认知协调 + 信号执行 + 状态查询 + 流动性管理）
- tracking/        - 监控跟踪层（持仓监控 + 热点信号跟踪 + 报告生成）
- kernel/          - AttentionKernel 核心 + ManasEngine
- values/          - 价值观系统
- models/          - 数据结构
- discovery/       - 主动发现模块（盲区、叙事、信念验证）
- ui/              - UI 相关

根目录保留:
- portfolio.py     - 持仓管理
- focus_manager.py - 关注管理
- block_registry.py - 题材注册表
- attention_fusion.py - 融合层
- text_importance_scorer.py - 文本重要性评分

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
from .discovery import (
    ConvictionValidator,
    get_conviction_validator,
    BlindSpotInvestigator,
    get_blind_spot_investigator,
    NarrativeBlockLinker,
    get_narrative_block_linker,
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
from .models.output import (
    AttentionKernelOutput,
    AttentionFusionOutput,
)
# OS 核心层 (从新路径导入)
from .os import (
    OSAttentionKernel,
    StrategyDecisionMaker,
    AttentionOS,
    get_attention_os,
)
# 协调层 (从新路径导入)
from .orchestration import (
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
    # Discovery (主动发现)
    "ConvictionValidator",
    "get_conviction_validator",
    "BlindSpotInvestigator",
    "get_blind_spot_investigator",
    "NarrativeBlockLinker",
    "get_narrative_block_linker",
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
    # Models (数据结构)
    "AttentionKernelOutput",
    "AttentionFusionOutput",
    # OS 核心层
    "OSAttentionKernel",
    "StrategyDecisionMaker",
    "AttentionOS",
    "get_attention_os",
    # 协调层
    "TradingCenter",
    "get_trading_center",
]

__version__ = "3.0.0"
