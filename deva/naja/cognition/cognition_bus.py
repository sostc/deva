"""Cognition Event Bus - 认知事件总线

基于流的认知事件总线，实现"一切皆流，无物永驻"的理念。

事件类型：
- attention_snapshot: 注意力快照事件
- news_signal: 新闻信号事件
- resonance_detected: 共振检测事件
- insight_generated: 洞察生成事件
- cognition_feedback: 认知反馈事件

使用方式：
    from .cognition_bus import cognition_bus, emit_attention, emit_news

    # 发射注意力快照
    emit_attention(snapshot)

    # 发射新闻信号
    emit_news(signal)

    # 订阅共振事件
    cognition_bus.filter(lambda x: x.get("type") == "resonance").sink(my_handler)
"""

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import time

from deva import Stream


class CognitionEventType(Enum):
    ATTENTION_SNAPSHOT = "attention_snapshot"
    NEWS_SIGNAL = "news_signal"
    RESONANCE_DETECTED = "resonance_detected"
    INSIGHT_GENERATED = "insight_generated"
    COGNITION_FEEDBACK = "cognition_feedback"
    NARRATIVE_UPDATE = "narrative_update"
    SEMANTIC_GRAPH_UPDATE = "semantic_graph_update"


@dataclass
class CognitionEvent:
    event_type: CognitionEventType
    data: Any
    timestamp: float = field(default_factory=time.time)
    source: str = "cognition_system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }


_cognition_bus_stream: Optional[Stream] = None
_cognition_bus_lock_event: bool = False


def get_cognition_bus() -> Stream:
    """获取认知事件总线单例"""
    global _cognition_bus_stream
    if _cognition_bus_stream is None:
        _cognition_bus_stream = Stream(
            name="cognition_bus",
            description="认知事件总线 - 所有认知事件流经此总线",
            cache_max_len=1000,
            cache_max_age_seconds=3600,
        )
    return _cognition_bus_stream


cognition_bus = get_cognition_bus()


def emit_cognition_event(event: CognitionEvent) -> None:
    """发射认知事件到总线"""
    cognition_bus.emit(event.to_dict())


def emit_attention_snapshot(
    block_weights: Dict[str, float],
    symbol_weights: Dict[str, float],
    high_attention_symbols: set,
    active_blocks: set,
    global_attention: float,
    activity: float,
    block_names: Dict[str, str],
    source: str = "attention_system",
) -> None:
    """发射注意力快照事件"""
    event = CognitionEvent(
        event_type=CognitionEventType.ATTENTION_SNAPSHOT,
        data={
            "block_weights": block_weights,
            "symbol_weights": symbol_weights,
            "high_attention_symbols": list(high_attention_symbols),
            "active_blocks": list(active_blocks),
            "global_attention": global_attention,
            "activity": activity,
            "block_names": block_names,
        },
        source=source,
    )
    emit_cognition_event(event)


def emit_news_signal(
    signal_data: Dict[str, Any],
    source: str = "radar",
) -> None:
    """发射新闻信号事件"""
    event = CognitionEvent(
        event_type=CognitionEventType.NEWS_SIGNAL,
        data=signal_data,
        source=source,
    )
    emit_cognition_event(event)


def emit_resonance(
    resonance_data: Dict[str, Any],
    source: str = "cross_signal",
) -> None:
    """发射共振检测事件"""
    event = CognitionEvent(
        event_type=CognitionEventType.RESONANCE_DETECTED,
        data=resonance_data,
        source=source,
    )
    emit_cognition_event(event)


def emit_insight(
    insight_data: Dict[str, Any],
    source: str = "insight_engine",
) -> None:
    """发射洞察生成事件"""
    event = CognitionEvent(
        event_type=CognitionEventType.INSIGHT_GENERATED,
        data=insight_data,
        source=source,
    )
    emit_cognition_event(event)


def emit_cognition_feedback(
    feedback_data: Dict[str, Any],
    source: str = "cognition",
) -> None:
    """发射认知反馈事件"""
    event = CognitionEvent(
        event_type=CognitionEventType.COGNITION_FEEDBACK,
        data=feedback_data,
        source=source,
    )
    emit_cognition_event(event)


def subscribe_to_event(
    event_type: CognitionEventType,
    handler: Callable[[Dict[str, Any]], None],
) -> None:
    """订阅特定类型的认知事件

    Args:
        event_type: 事件类型
        handler: 处理函数
    """
    cognition_bus.filter(lambda x: x.get("type") == event_type.value).sink(handler)


def subscribe_to_all(handler: Callable[[Dict[str, Any]], None]) -> None:
    """订阅所有认知事件"""
    cognition_bus.sink(handler)
