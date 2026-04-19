from deva.naja.events.cognitive_events import CognitiveInsightEvent
from deva.naja.events.router import resolve_event_bus_type
from deva.naja.events.trading_events import (
    DecisionResult,
    SignalDirection,
    StrategySignalEvent,
    TradeDecisionEvent,
)


def test_resolve_trading_signal_event_bus():
    event = StrategySignalEvent(
        symbol="000001",
        direction=SignalDirection.BUY,
        confidence=0.8,
        strategy_name="demo",
        signal_type="momentum",
        current_price=10.0,
        price_change_pct=2.0,
    )
    assert resolve_event_bus_type(event) == "trading"


def test_resolve_trade_decision_event_bus():
    signal_event = StrategySignalEvent(
        symbol="000001",
        direction=SignalDirection.BUY,
        confidence=0.8,
        strategy_name="demo",
        signal_type="momentum",
        current_price=10.0,
        price_change_pct=2.0,
    )
    event = TradeDecisionEvent(
        signal_event=signal_event,
        decision=DecisionResult.APPROVED,
        approval_score=0.9,
    )
    assert resolve_event_bus_type(event) == "trading"


def test_resolve_cognitive_event_bus():
    event = CognitiveInsightEvent(
        insights=[{"theme": "demo"}],
        confidence=0.7,
        timestamp=0.0,
    )
    assert resolve_event_bus_type(event) == "cognitive"
