"""
AttentionHead - 单头注意力

实现标准的 attention 计算：score -> softmax -> weighted sum
"""

import math


class AttentionHead:
    """
    单头注意力

    属性:
        name: 头的名称
        scorer: 相似度计算函数 (Q, K) -> score
    """

    def __init__(self, name, scorer):
        """
        初始化注意力头

        Args:
            name: 头的名称
            scorer: (Q, K) -> score 的函数
        """
        self.name = name
        self.scorer = scorer

    def compute(self, Q, events):
        """
        计算单头 attention 输出

        Args:
            Q: QueryState 或 query dict
            events: AttentionEvent 列表

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

        weights = self._softmax(scores)
        return self._aggregate(weights, values)

    def _softmax(self, scores):
        """
        Softmax 归一化

        Args:
            scores: float 列表

        Returns:
            归一化后的权重列表
        """
        if not scores:
            return []
        exp_scores = [math.exp(s) for s in scores]
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