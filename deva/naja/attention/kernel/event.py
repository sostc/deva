"""
AttentionEvent - 统一事件格式

将 RadarEvent、NewsSignal、MarketSignal 等统一封装为 AttentionEvent
"""


class AttentionEvent:
    """
    统一事件格式

    属性:
        source: 事件来源 ("market" / "news" / "flow" / "meta")
        data: 原始数据
        features: 特征 dict
        timestamp: 时间戳
        key: 编码后 key
        value: 编码后 value

    流动性救援专用字段 (features 中):
        panic_level: 恐慌程度 (0-100)
        liquidity_score: 流动性得分 (0-1)
        spread_ratio: 相对价差 (当前/正常)
        event_impact: 事件影响度 (0-1)
        recovery_signal: 恢复信号强度 (0-1)
        price_destabilization_speed: 价格失稳速度
        volume_shrink_ratio: 成交量萎缩率
        fear_score: 恐惧得分 (0-100)
    """

    def __init__(self, source, data, features, timestamp):
        self.source = source
        self.data = data
        self.features = features
        self.timestamp = timestamp
        self.key = None
        self.value = None

    def __repr__(self):
        return f"AttentionEvent(source={self.source}, timestamp={self.timestamp})"

    def get_liquidity_rescue_features(self) -> dict:
        """获取流动性救援专用特征"""
        return {
            "panic_level": self.features.get("panic_level", 0),
            "liquidity_score": self.features.get("liquidity_score", 0.5),
            "spread_ratio": self.features.get("spread_ratio", 1.0),
            "event_impact": self.features.get("event_impact", 0),
            "recovery_signal": self.features.get("recovery_signal", 0),
            "price_destabilization_speed": self.features.get("price_destabilization_speed", 0),
            "volume_shrink_ratio": self.features.get("volume_shrink_ratio", 1.0),
            "fear_score": self.features.get("fear_score", 0),
        }

    def is_panic_candidate(self, panic_threshold: float = 70) -> bool:
        """是否是恐慌候选事件"""
        return self.features.get("panic_level", 0) >= panic_threshold

    def is_liquidity_crisis(self, threshold: float = 0.3) -> bool:
        """是否处于流动性危机"""
        return self.features.get("liquidity_score", 0.5) < threshold

    def has_recovery_signal(self, threshold: float = 0.6) -> bool:
        """是否有恢复信号"""
        return self.features.get("recovery_signal", 0) >= threshold