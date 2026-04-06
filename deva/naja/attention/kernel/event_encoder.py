"""
Encoder - Key/Value 编码器

将 AttentionEvent 编码为可计算的 key 和 value
"""


class Encoder:
    """
    Key/Value 编码器

    提供事件到 Q/K/V 的投影
    """

    def __init__(self, key_proj=None, value_proj=None):
        """
        初始化编码器

        Args:
            key_proj: 可选的 key 投影函数
            value_proj: 可选的 value 投影函数
        """
        self.key_proj = key_proj
        self.value_proj = value_proj

    def encode_key(self, event):
        """
        编码 key

        Args:
            event: AttentionEvent

        Returns:
            编码后的 key
        """
        if self.key_proj:
            return self.key_proj(event.features)
        return event.features

    def encode_value(self, event):
        """
        编码 value

        Args:
            event: AttentionEvent

        Returns:
            编码后的 value dict
        """
        if self.value_proj:
            return self.value_proj(event.features)
        return {
            "alpha": event.features.get("alpha", 0),
            "risk": event.features.get("risk", 0),
            "confidence": event.features.get("confidence", 0),
            "action": event.features.get("action", None)
        }

    def project_query(self, state):
        """
        投影 Query 状态

        Args:
            state: QueryState

        Returns:
            投影后的 query dict
        """
        return {
            "focus": state.attention_focus,
            "risk": state.risk_bias,
            "regime": state.market_regime.get("type", "neutral")
        }