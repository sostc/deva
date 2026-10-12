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

⚠️ 本包的重导出是**惰性**的（PEP 562），见 `_LAZY_EXPORTS`。
这样 `import ...kernel.manas_engine` 不会因为 `__init__` 而拉起
embedding / self_attention / in_context_learner（它们依赖 numpy），
更不会拉起上层 attention.os / orchestration。
"""

from __future__ import annotations

import importlib


# ---------------------------------------------------------------------------
# 包级重导出 → 按需加载（PEP 562）
# ---------------------------------------------------------------------------
# 同 `deva/naja/__init__.py` 与 `deva/naja/attention/__init__.py` 的改造。
# 这里额外隔开的是 numpy 系模块（embedding / self_attention / in_context_learner）：
# 只要 ManasEngine 的用户用不到「事件嵌入 / 自注意力 / 上下文学习」这几块，
# 就不该为它们付 numpy 的导入成本。
_LAZY_EXPORTS = {
    "AttentionEvent": ".event",
    "QueryState": ".state",
    "Encoder": ".event_encoder",
    "AttentionHead": ".attention_scorer",
    "MultiHeadAttention": ".multi_scorer",
    "AttentionKernel": ".kernel",
    "get_default_heads": ".heads",
    "get_regime_aware_heads": ".heads",
    # manas 家族
    "ManasConfig": ".manas_config",
    "RollingWindow": ".manas_config",
    "ManasEngine": ".manas_engine",
    "TimingEngine": ".manas_engine",
    "RegimeEngine": ".manas_engine",
    "ConfidenceEngine": ".manas_engine",
    "RiskEngine": ".manas_engine",
    "MetaManas": ".manas_engine",
    "BiasState": ".manas_engine",
    "ManasOutput": ".manas_engine",
    "CognitiveState": ".manas_engine",
    "ManasManager": ".manas_manager",
    "get_manas_manager": ".manas_manager",
    "DecisionAttention": ".decision_attention",
    "TemperatureAwareHead": ".decision_attention",
    # 借鉴 Transformer
    "EventEmbedding": ".embedding",
    "MarketFeatureEncoder": ".embedding",
    "EventSelfAttention": ".self_attention",
    "FeedForwardNetwork": ".self_attention",
    "TransformerLikeAttentionLayer": ".self_attention",
    # 借鉴大模型上下文学习
    "Demonstration": ".in_context_learner",
    "InContextAttentionLearner": ".in_context_learner",
    "get_in_context_learner": ".in_context_learner",
    "setup_in_context_learner": ".in_context_learner",
}

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
    "ManasConfig",
    "RollingWindow",
    "CognitiveState",
    "TimingEngine",
    "RegimeEngine",
    "ConfidenceEngine",
    "RiskEngine",
    "MetaManas",
    "BiasState",
    "ManasOutput",
    "ManasManager",
    "get_manas_manager",
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
