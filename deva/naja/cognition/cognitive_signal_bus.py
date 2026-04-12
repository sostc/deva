"""
兼容性转发 - CognitiveSignalBus 已迁移到 events/cognitive_bus.py

新代码请直接从 deva.naja.events 导入：
    from deva.naja.events import get_cognitive_bus, CognitiveEventType
"""

# 从新位置重新导出所有公开符号
from deva.naja.events.cognitive_bus import (  # noqa: F401
    CognitiveEventType,
    CognitiveSignalEvent,
    CognitiveSubscriber,
    CognitiveBusStats,
    CognitiveSignalBus,
    get_cognitive_bus,
    reset_cognitive_bus,
)

__all__ = [
    "CognitiveEventType",
    "CognitiveSignalEvent",
    "CognitiveSubscriber",
    "CognitiveBusStats",
    "CognitiveSignalBus",
    "get_cognitive_bus",
    "reset_cognitive_bus",
]
