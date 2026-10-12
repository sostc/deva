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

⚠️ 本包的重导出是**惰性**的（PEP 562），见下方 `_LAZY_EXPORTS` 注释。
"""

from __future__ import annotations

import importlib

__version__ = "3.0.0"


# ---------------------------------------------------------------------------
# 包级重导出 → 按需加载（PEP 562）
# ---------------------------------------------------------------------------
# 原先这些重导出是 **eager** 的（直接 `from .os` / `from .orchestration` 取名字），
# 于是任何 `import deva.naja.attention.*` 都会传递性拉起整个交易/认知域。
# 实测 `import deva.naja.attention.kernel.manas_engine` 需 **3.4s / 3158 个模块**，
# 其中 10 个是 `TradingCenter` / `AttentionOS` / `orchestration.*` 这类重模块——
# 而 ManasEngine 本体只依赖 stdlib + manas_config，一个都不需要。
#
# manas 现已可脱离交易域单独使用（公共门面 `deva.naja.manas`），加载期不该再
# 为「用得着的名字以外的东西」买单。故把重导出全部改为惰性：第一次访问
# `deva.naja.attention.<Name>` 时才导入对应子模块并缓存。
# `from deva.naja.attention import <Name>` 同样可用（Python 会回调 __getattr__）。
#
# 与 `deva/naja/__init__.py` 的同类改造同构——那边解决的是 signal/radar/tasks
# 拖着 pywebio/pandas/bokeh 约 1.1s 的问题，这里是同一个病。
_LAZY_EXPORTS = {
    # Kernel（注意力原语；全部只依赖 stdlib / numpy）
    "AttentionEvent": ".kernel",
    "QueryState": ".kernel",
    "Encoder": ".kernel",
    "AttentionHead": ".kernel",
    "MultiHeadAttention": ".kernel",
    "AttentionKernel": ".kernel",
    "get_default_heads": ".kernel",
    "get_regime_aware_heads": ".kernel",
    "EventEmbedding": ".kernel",
    "MarketFeatureEncoder": ".kernel",
    "EventSelfAttention": ".kernel",
    "FeedForwardNetwork": ".kernel",
    "TransformerLikeAttentionLayer": ".kernel",
    "Demonstration": ".kernel",
    "InContextAttentionLearner": ".kernel",
    "get_in_context_learner": ".kernel",
    "setup_in_context_learner": ".kernel",
    # ManasEngine（决策中枢）——指向叶子模块，避免多一跳
    "ManasEngine": ".kernel.manas_engine",
    # Portfolio（持仓管理）
    "Portfolio": ".portfolio",
    "StockInfo": ".portfolio",
    # Discovery（主动发现）
    "ConvictionValidator": ".discovery",
    "get_conviction_validator": ".discovery",
    "BlindSpotInvestigator": ".discovery",
    "get_blind_spot_investigator": ".discovery",
    "NarrativeBlockLinker": ".discovery",
    "get_narrative_block_linker": ".discovery",
    # FocusManager（关注管理）
    "AttentionFocusManager": ".focus_manager",
    "get_attention_focus_manager": ".focus_manager",
    # BlockRegistry（题材注册表）
    "BlockRegistry": ".block_registry",
    "get_block_registry": ".block_registry",
    "BlockDescriptor": ".block_registry",
    # AttentionFusion（融合层）
    "AttentionFusion": ".attention_fusion",
    "get_attention_fusion": ".attention_fusion",
    "FusionSignal": ".attention_fusion",
    "FullFusionResult": ".attention_fusion",
    # Models（数据结构）
    "AttentionKernelOutput": ".models.output",
    "AttentionFusionOutput": ".models.output",
    # OS 核心层
    "OSAttentionKernel": ".os",
    "StrategyDecisionMaker": ".os",
    "AttentionOS": ".os",
    "get_attention_os": ".os",
    # 协调层
    "TradingCenter": ".orchestration",
    "get_trading_center": ".orchestration",
}

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


def __getattr__(name):
    """PEP 562：惰性解析被重导出的名字。"""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = importlib.import_module(module_path, __name__)
    value = getattr(module, name)
    globals()[name] = value  # 缓存，后续访问不再进入 __getattr__
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
