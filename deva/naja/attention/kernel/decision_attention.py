"""
DecisionAttention - 决策型注意力

在 QK^T 层面调制注意力强度：

    Attention = softmax(α · QK^T / T) × V

维度分布：
    Q (时机) → 进入 Query 生成阶段
    K (宏观) → 进入 K 的世界权重
    α (策略准确性) → QK 相似度的放大/缩小因子
    T (仓位/风险) → softmax 的温度参数

温度 T 的作用：
    - 仓位高/风险敏感 → T 大 → 更平滑/保守
    - 仓位低/可进攻 → T 小 → 更集中/激进

α (策略准确性) 的作用：
    - 策略表现好 → α 大 → 更极端选择
    - 策略表现差 → α 小 → 更分散

================================================================================
系统集成位置
================================================================================

1. AttentionKernel (kernel.py)
   - _process_with_manas() 中使用 DecisionAttention
   - result["alpha"] *= α 进行调制

2. ManasManager (manas_manager.py)
   - 管理 DecisionAttention 的生命周期

================================================================================
使用示例
================================================================================

# 1. 独立使用
from deva.naja.attention.kernel.decision_attention import DecisionAttention

da = DecisionAttention()
scores, alpha, temp = da.modulate(raw_scores, strategy_performance=0.7)

# 2. 集成到 AttentionKernel
kernel = AttentionKernel(
    encoder, multi_head, memory,
    enable_manas=True  # ManasEngine 内部使用 DecisionAttention
)
"""

import math
from typing import Dict, Any, Optional
from deva.naja.register import SR


class DecisionAttention:
    """
    决策型注意力调制器

    用法:
        decision_attn = DecisionAttention()
        scores, alpha, temperature = decision_attn.modulate(raw_scores, strategy_performance)
    """

    def __init__(self, manas_engine=None):
        """
        初始化决策注意力

        Args:
            manas_engine: ManasEngine 实例，用于获取决策状态
        """
        self._manas = manas_engine
        self._last_alpha = 1.0
        self._last_temperature = 1.0
        self._last_strategy_performance = 0.5

    def _get_portfolio(self):
        """获取虚拟持仓"""
        try:
            return SR('virtual_portfolio')
        except ImportError:
            return None

    def _get_cash_ratio(self, portfolio) -> float:
        """获取现金比例"""
        if portfolio is None:
            return 0.5
        try:
            summary = portfolio.get_summary()
            available = summary.get('available_capital', 0)
            total = summary.get('total_capital', 1)
            return available / max(total, 1) if total > 0 else 0.5
        except:
            return 0.5

    def set_manas_engine(self, manas):
        """设置末那识引擎"""
        self._manas = manas

    def compute_temperature(self) -> float:
        """
        计算 softmax 温度 T

        T 由仓位/胆识决定：
        - 仓位高 → 风险敏感 → T 大（更平滑保守）
        - 仓位低 → 可以进攻 → T 小（更集中激进）

        Returns:
            float: 温度参数 T，范围 [0.5, 2.0]
        """
        portfolio = self._get_portfolio()
        cash_ratio = self._get_cash_ratio(portfolio)

        T = 1.0 + (1.0 - cash_ratio) * 0.8
        T = max(0.5, min(2.0, T))

        self._last_temperature = T
        return T

    def compute_alpha(self, strategy_performance: float = 0.5) -> float:
        """
        计算策略准确性缩放因子 α

        α 由策略近期表现决定：
        - 策略表现好 → α 大 → 更极端选择
        - 策略表现差 → α 小 → 更分散

        Args:
            strategy_performance: 策略近期表现 [0, 1]，默认 0.5

        Returns:
            float: α 因子，范围 [0.5, 1.5]
        """
        base_alpha = 0.5 + strategy_performance * 0.5
        self._last_alpha = base_alpha
        self._last_strategy_performance = strategy_performance
        return base_alpha

    def modulate(self, raw_scores: list, strategy_performance: float = 0.5) -> tuple:
        """
        对 QK^T 原始分数进行调制

        Args:
            raw_scores: 原始 QK^T 相似度分数列表
            strategy_performance: 策略近期表现 [0, 1]

        Returns:
            tuple: (modulated_scores, alpha, temperature)
        """
        T = self.compute_temperature()
        α = self.compute_alpha(strategy_performance)

        if not raw_scores:
            return [], α, T

        modulated_scores = [(α * score) / T for score in raw_scores]
        return modulated_scores, α, T

    def get_state(self) -> Dict[str, Any]:
        """获取决策注意力状态"""
        return {
            "alpha": self._last_alpha,
            "temperature": self._last_temperature,
            "strategy_performance": self._last_strategy_performance,
        }


class TemperatureAwareHead:
    """
    支持温度调制的 AttentionHead

    在 _softmax 方法中注入温度参数 T
    """

    def __init__(self, name: str, scorer, decision_attention: Optional[DecisionAttention] = None):
        """
        初始化温度感知头

        Args:
            name: 头的名称
            scorer: 相似度计算函数 (Q, K) -> score
            decision_attention: DecisionAttention 实例
        """
        self.name = name
        self.scorer = scorer
        self.decision_attention = decision_attention

    def compute(self, Q, events, strategy_performance: float = 0.5):
        """
        计算单头 attention 输出（支持温度调制）

        Args:
            Q: QueryState 或 query dict
            events: AttentionEvent 列表
            strategy_performance: 策略近期表现 [0, 1]

        Returns:
            加权聚合后的 dict {alpha, risk, confidence}
        """
        if not events:
            return {"alpha": 0, "risk": 0, "confidence": 0}

        scores = []
        values = []
        for e in events:
            k = e.key if e.key is not None else e.features
            v = e.value if e.value is not None else {}
            score = self.scorer(Q, k)
            scores.append(score)
            values.append(v)

        if self.decision_attention is not None:
            scores, α, T = self.decision_attention.modulate(scores, strategy_performance)
        else:
            α, T = 1.0, 1.0

        weights = self._softmax(scores, temperature=T)
        result = self._aggregate(weights, values)
        result["_alpha"] = α
        result["_temperature"] = T
        return result

    def _softmax(self, scores, temperature: float = 1.0):
        """
        Softmax 归一化（带温度参数）

        Args:
            scores: float 列表
            temperature: 温度参数 T，默认 1.0

        Returns:
            归一化后的权重列表
        """
        if not scores:
            return []
        exp_scores = [math.exp(s / temperature) for s in scores]
        total = sum(exp_scores)
        if total == 0:
            return [0] * len(scores)
        return [s / total for s in exp_scores]

    def _aggregate(self, weights, values):
        """
        加权求和

        Args:
            weights: 权重列表
            values: value dict 列表

        Returns:
            加权聚合后的 dict
        """
        result = {"alpha": 0, "risk": 0, "confidence": 0}
        for w, v in zip(weights, values):
            if not isinstance(v, dict):
                continue
            result["alpha"] += w * v.get("alpha", 0)
            result["risk"] += w * v.get("risk", 0)
            result["confidence"] += w * v.get("confidence", 0)
        return result
