"""
CognitionIngestion - Radar → Cognition 统一数据流入口

📋 职责：
    将 Radar 层产生的各类事件统一接收，分发到 Cognition 层的对应处理器。
    消除 Radar 层直接调用多个 Cognition 子模块的耦合。

🔄 数据流：
    RadarEngine
        ↓ ingest_radar_events()
    CognitionIngestion
        ├→ InsightPool.ingest_hotspot_event()      (雷达信号 → 洞察池)
        ├→ CognitiveSignalBus.publish()            (全球市场事件 → 总线)
        └→ LiquidityCognition.ingest()             (降级路径)

使用方式：
    from deva.naja.cognition.ingestion import get_cognition_ingestion

    ingestion = get_cognition_ingestion()
    ingestion.ingest_radar_events(events)
    ingestion.ingest_market_alert(event)
"""

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_instance: Optional["CognitionIngestion"] = None


class CognitionIngestion:
    """Radar → Cognition 统一入口"""

    def __init__(self):
        self._insight_pool = None
        self._cognitive_bus = None
        self._liquidity_cognition = None

    # ------------------------------------------------------------------
    #  公共 API
    # ------------------------------------------------------------------

    def ingest_radar_events(self, events: List[Any]) -> None:
        """
        接收雷达事件列表，分发到 InsightPool

        Args:
            events: RadarEvent 列表（需要有 to_insight_signal() 方法）
        """
        if not events:
            return

        pool = self._get_insight_pool()
        if pool is None:
            return

        for event in events:
            try:
                signal = event.to_insight_signal()
                pool.ingest_hotspot_event(signal)
            except Exception:
                continue

    def ingest_market_alert(self, event: Any) -> None:
        """
        接收全球市场事件，发布到 CognitiveSignalBus

        Args:
            event: RadarEvent（需要有 payload 属性）
        """
        try:
            from .cognitive_signal_bus import get_cognitive_bus, CognitiveEventType

            bus = get_cognitive_bus()
            payload = event.payload if hasattr(event, "payload") else event

            metadata = {
                "market_id": payload.get("market_id", ""),
                "current": payload.get("current", 0),
                "change_pct": payload.get("change_pct", 0),
                "volume": payload.get("volume", 0),
                "is_abnormal": payload.get("is_abnormal", False),
                "name": payload.get("name", ""),
            }

            bus.publish_cognitive_event(
                source="RadarEngine",
                event_type=CognitiveEventType.GLOBAL_MARKET_EVENT,
                narratives=[f"全球市场:{metadata.get('market_id', '')}"],
                importance=0.7 if metadata.get("is_abnormal") else 0.5,
                metadata=metadata,
            )
            log.debug(f"[Ingestion] 全球市场事件已发布: {metadata.get('market_id')}")

        except ImportError:
            log.debug("[Ingestion] CognitiveSignalBus 未导入，降级为直接调用")
            self._ingest_market_alert_legacy(event)
        except Exception as e:
            log.debug(f"[Ingestion] 发布全球市场事件失败: {e}")

    def ingest_news(self, news_data: Dict[str, Any]) -> None:
        """
        接收新闻事件（预留接口）

        Args:
            news_data: 新闻数据字典
        """
        # 目前新闻通过 TextProcessingPipeline → TextSignalBus 流转
        # 此接口预留给未来统一入口使用
        pass

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------

    def _get_insight_pool(self):
        """懒加载 InsightPool"""
        if self._insight_pool is None:
            try:
                from deva.naja.common.singleton_registry import SR
                self._insight_pool = SR("insight_pool")
            except Exception:
                pass
        return self._insight_pool

    def _ingest_market_alert_legacy(self, event: Any) -> None:
        """降级路径：直接调用 LiquidityCognition"""
        try:
            from .liquidity import get_liquidity_cognition

            cognition = get_liquidity_cognition()
            payload = event.payload if hasattr(event, "payload") else event

            event_dict = {
                "market_id": payload.get("market_id", ""),
                "current": payload.get("current", 0),
                "change_pct": payload.get("change_pct", 0),
                "volume": payload.get("volume", 0),
                "is_abnormal": payload.get("is_abnormal", False),
                "name": payload.get("name", ""),
            }
            cognition.ingest_global_market_event(event_dict)
            log.debug(f"[Ingestion/Legacy] 事件已发送: {event_dict.get('market_id')}")
        except ImportError:
            log.debug("[Ingestion/Legacy] LiquidityCognition 未导入")
        except Exception as e:
            log.debug(f"[Ingestion/Legacy] 发送失败: {e}")


def get_cognition_ingestion() -> CognitionIngestion:
    """获取 CognitionIngestion 单例"""
    global _instance
    if _instance is None:
        _instance = CognitionIngestion()
    return _instance
