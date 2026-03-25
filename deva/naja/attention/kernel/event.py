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