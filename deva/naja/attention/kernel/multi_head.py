"""
MultiHeadAttention - 多头注意力融合

并行计算多个 AttentionHead 并融合结果
"""


class MultiHeadAttention:
    """
    多头注意力

    属性:
        heads: AttentionHead 列表
        output_mode: "merge" 或 "concat"
    """

    def __init__(self, heads, output_mode="merge"):
        """
        初始化多头注意力

        Args:
            heads: AttentionHead 列表
            output_mode: "merge"（相加）或 "concat"（拼接）
        """
        self.heads = heads
        self.output_mode = output_mode

    def compute(self, Q, events):
        """
        计算多头 attention 输出

        Args:
            Q: QueryState 或 query dict
            events: AttentionEvent 列表

        Returns:
            融合后的 dict
        """
        outputs = []
        for head in self.heads:
            out = head.compute(Q, events)
            outputs.append(out)

        if self.output_mode == "concat":
            return self._concat(outputs)
        return self._merge(outputs)

    def _merge(self, outputs):
        """
        简单相加融合

        Args:
            outputs: 结果 dict 列表

        Returns:
            融合后的 dict
        """
        final = {"alpha": 0, "risk": 0, "confidence": 0}
        for o in outputs:
            final["alpha"] += o["alpha"]
            final["risk"] += o["risk"]
            final["confidence"] += o["confidence"]
        return final

    def _concat(self, outputs):
        """
        拼接融合

        Args:
            outputs: 结果 dict 列表

        Returns:
            {"head_outputs": [...]} 包含所有头的输出
        """
        return {"head_outputs": outputs}