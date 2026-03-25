"""
AttentionKernel - 核心注意力中枢

协调 Encoder、MultiHeadAttention 和 AttentionMemory
"""


class AttentionKernel:
    """
    核心注意力中枢

    属性:
        encoder: Encoder 实例
        multi_head: MultiHeadAttention 实例
        memory: AttentionMemory 实例
    """

    def __init__(self, encoder, multi_head, memory):
        """
        初始化注意力中枢

        Args:
            encoder: Encoder 实例
            multi_head: MultiHeadAttention 实例
            memory: AttentionMemory 实例
        """
        self.encoder = encoder
        self.multi_head = multi_head
        self.memory = memory

    def process(self, Q, raw_events):
        """
        处理事件列表

        Args:
            Q: QueryState
            raw_events: AttentionEvent 列表

        Returns:
            attention 结果 dict
        """
        if not raw_events:
            return {"alpha": 0, "risk": 0, "confidence": 0}

        events = []
        for e in raw_events:
            e.key = self.encoder.encode_key(e)
            e.value = self.encoder.encode_value(e)
            events.append(e)

        result = self.multi_head.compute(Q, events)

        for e in events:
            self.memory.update(e, result["confidence"])

        return result

    def process_with_feedback(self, Q, raw_events, feedback):
        """
        带反馈的处理流程

        Args:
            Q: QueryState
            raw_events: AttentionEvent 列表
            feedback: 反馈 dict，包含 reward 等

        Returns:
            attention 结果 dict
        """
        result = self.process(Q, raw_events)

        if "reward" in feedback:
            for e in raw_events:
                self.memory.reinforce(e, feedback["reward"])

        Q.update(feedback)

        return result