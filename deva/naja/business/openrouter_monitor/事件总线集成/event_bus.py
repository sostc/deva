"""
OpenRouter 监控 - 事件总线集成

与认知事件总线和交易事件总线集成，处理事件的订阅和发布
"""

from typing import Dict, Optional


class OpenRouterEventBus:
    """OpenRouter 事件总线集成"""

    def __init__(self):
        self.cognitive_bus = None
        self.trading_bus = None
        self._initialize_buses()

    def _initialize_buses(self):
        """初始化事件总线"""
        try:
            from deva.naja.events.cognitive_event_bus import CognitiveEventBus
            from deva.naja.events.trading_event_bus import TradingEventBus
            
            self.cognitive_bus = CognitiveEventBus()
            self.trading_bus = TradingEventBus()
        except Exception as e:
            print(f"[OpenRouter EventBus] 初始化事件总线失败: {e}")

    def publish_cognitive_event(self, event_type: str, data: Dict):
        """发布认知事件

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if self.cognitive_bus:
            try:
                self.cognitive_bus.publish(event_type, data)
                print(f"[OpenRouter EventBus] 发布认知事件: {event_type}")
            except Exception as e:
                print(f"[OpenRouter EventBus] 发布认知事件失败: {e}")

    def publish_trading_event(self, event_type: str, data: Dict):
        """发布交易事件

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if self.trading_bus:
            try:
                self.trading_bus.publish(event_type, data)
                print(f"[OpenRouter EventBus] 发布交易事件: {event_type}")
            except Exception as e:
                print(f"[OpenRouter EventBus] 发布交易事件失败: {e}")

    def publish_ai_compute_trend(self, trend_data: Dict):
        """发布 AI 算力趋势事件

        Args:
            trend_data: 趋势分析结果
        """
        if not trend_data:
            return

        # 发布到认知事件总线
        cognitive_event = {
            "signal_type": "ai_compute_trend",
            "trend_data": trend_data,
            "timestamp": trend_data.get("latest_date", ""),
            "alert_level": trend_data.get("alert_level", "normal")
        }
        self.publish_cognitive_event("ai_compute_trend", cognitive_event)

        # 发布到交易事件总线
        if trend_data.get("alert_level") in ["warning", "critical"]:
            trading_event = {
                "signal_type": "ai_compute_alert",
                "trend_data": trend_data,
                "recommendation": trend_data.get("recommendation", ""),
                "alert_level": trend_data.get("alert_level", "normal")
            }
            self.publish_trading_event("ai_compute_alert", trading_event)
