"""
预定义多头配置

提供默认的四个注意力头
"""

from .attention_scorer import AttentionHead


def get_default_heads():
    """
    获取默认的四个注意力头

    Returns:
        AttentionHead 列表
    """
    return [
        AttentionHead(
            "market",
            scorer=lambda Q, K: K.get("price_change", 0)
        ),
        AttentionHead(
            "news",
            scorer=lambda Q, K: K.get("sentiment", 0)
        ),
        AttentionHead(
            "flow",
            scorer=lambda Q, K: K.get("volume_spike", 0)
        ),
        AttentionHead(
            "meta",
            scorer=lambda Q, K: K.get("historical_alpha", 0)
        )
    ]


def get_regime_aware_heads():
    """
    获取基于市场状态的注意力头

    Returns:
        AttentionHead 列表
    """
    def trend_scorer(Q, K):
        regime = Q.get("regime", "neutral") if isinstance(Q, dict) else getattr(Q, "market_regime", {}).get("type", "neutral")
        if regime == "trend":
            return K.get("momentum", 0)
        elif regime == "reversal":
            return K.get("reversal", 0)
        return K.get("breakout", 0)

    return [
        AttentionHead("trend", scorer=lambda Q, K: trend_scorer(Q, K)),
        AttentionHead("reversal", scorer=lambda Q, K: K.get("reversal", 0)),
        AttentionHead("breakout", scorer=lambda Q, K: K.get("breakout", 0)),
    ]