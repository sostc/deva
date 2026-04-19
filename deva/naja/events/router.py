from __future__ import annotations

from typing import Any, Dict, Type

from .cognitive_events import (
    CognitiveInsightEvent,
    NarrativeStateEvent,
    LiquiditySignalEvent,
    MerrillClockEvent,
)
from .hotspot_events import HotspotComputedEvent, HotspotShiftEvent, MarketSnapshotEvent, SymbolUpdateEvent
from .text_events import TextFetchedEvent, TextFocusedEvent
from .trading_events import StrategySignalEvent, TradeDecisionEvent


COGNITIVE_EVENT_CLASSES = (
    TextFetchedEvent,
    TextFocusedEvent,
    HotspotComputedEvent,
    HotspotShiftEvent,
    MarketSnapshotEvent,
    SymbolUpdateEvent,
    CognitiveInsightEvent,
    NarrativeStateEvent,
    LiquiditySignalEvent,
    MerrillClockEvent,
)

TRADING_EVENT_CLASSES = (
    StrategySignalEvent,
    TradeDecisionEvent,
)

EVENT_BUS_MAP: Dict[Type[Any], str] = {
    **{cls: "cognitive" for cls in COGNITIVE_EVENT_CLASSES},
    **{cls: "trading" for cls in TRADING_EVENT_CLASSES},
}


def resolve_event_bus_type(event_or_type: Any) -> str:
    event_type = event_or_type if isinstance(event_or_type, type) else type(event_or_type)
    if event_type in EVENT_BUS_MAP:
        return EVENT_BUS_MAP[event_type]
    raise ValueError(f"未注册的事件类型: {getattr(event_type, '__name__', event_type)}")
