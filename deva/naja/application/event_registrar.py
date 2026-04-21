"""
Event Subscriber Registrar

统一管理事件订阅的装配器。
将事件订阅从领域对象内部移到应用层，使领域对象更纯净。
"""

import logging
import time
from typing import Any, Optional

log = logging.getLogger(__name__)


class EventSubscriberRegistrar:
    """事件订阅装配器 - 统一管理所有事件订阅"""

    def __init__(
        self,
        attention_os: Any,
        trading_center: Any,
    ):
        self.attention_os = attention_os
        self.trading_center = trading_center
        self._registered = False

    def register_all(self) -> None:
        """注册所有事件订阅"""
        if self._registered:
            log.debug("[EventSubscriberRegistrar] 已注册，跳过")
            return

        log.info("[EventSubscriberRegistrar] 开始注册事件订阅...")

        try:
            from deva.naja.events import get_event_bus
            event_bus = get_event_bus()

            self._register_attention_os(event_bus)
            self._register_trading_center(event_bus)
            self._register_cognition_domain(event_bus)
            
            self._registered = True
            log.info("[EventSubscriberRegistrar] 事件订阅注册完成")
            
        except Exception as e:
            log.error(f"[EventSubscriberRegistrar] 事件订阅注册失败: {e}", exc_info=True)

    def _register_cognition_domain(self, event_bus) -> None:
        """注册认知领域模块的事件订阅"""
        try:
            # CrossSignalAnalyzer
            from deva.naja.cognition.analysis.cross_signal_analyzer import get_cross_signal_analyzer
            analyzer = get_cross_signal_analyzer()
            if analyzer:
                analyzer.subscribe_text_events(event_bus)
                log.info("[EventSubscriberRegistrar] CrossSignalAnalyzer 事件订阅完成")
        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] CrossSignalAnalyzer 事件订阅失败: {e}")

        try:
            # NarrativeTracker
            from deva.naja.cognition.narrative.tracker import get_narrative_tracker
            tracker = get_narrative_tracker()
            if tracker:
                tracker.subscribe_text_events(event_bus)
                tracker.subscribe_manas_state_events(event_bus)
                log.info("[EventSubscriberRegistrar] NarrativeTracker 事件订阅完成")
        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] NarrativeTracker 事件订阅失败: {e}")

        try:
            # TimingNarrativeTracker
            from deva.naja.cognition.narrative.timing import TimingNarrativeTracker
            timing_tracker = TimingNarrativeTracker()
            if timing_tracker:
                timing_tracker.subscribe_text_events(event_bus)
                log.info("[EventSubscriberRegistrar] TimingNarrativeTracker 事件订阅完成")
        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] TimingNarrativeTracker 事件订阅失败: {e}")

        try:
            # SupplyChainLinker
            from deva.naja.cognition.narrative.supply_chain_linker import get_supply_chain_linker
            linker = get_supply_chain_linker()
            if linker:
                linker.subscribe_text_events(event_bus)
                log.info("[EventSubscriberRegistrar] SupplyChainLinker 事件订阅完成")
        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] SupplyChainLinker 事件订阅失败: {e}")

    def _register_attention_os(self, event_bus) -> None:
        """注册 AttentionOS 的事件订阅"""
        if self.attention_os is None:
            return

        try:
            # HotspotComputedEvent
            event_bus.subscribe(
                'HotspotComputedEvent',
                self.attention_os._on_hotspot_computed,
                markets={'US', 'CN'},
                priority=10
            )

            # HotspotShiftEvent
            event_bus.subscribe(
                'HotspotShiftEvent',
                self.attention_os._on_hotspot_shift,
                priority=5
            )

            # TextFetchedEvent
            event_bus.subscribe(
                'TextFetchedEvent',
                self.attention_os._on_text_fetched,
                priority=10
            )

            log.info("[EventSubscriberRegistrar] AttentionOS 事件订阅完成")
            
        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] AttentionOS 事件订阅失败: {e}")

    def _register_trading_center(self, event_bus) -> None:
        """注册 TradingCenter 的事件订阅"""
        if self.trading_center is None:
            return

        try:
            from deva.naja.events import TradeDecisionEvent

            def on_strategy_signal(event):
                """处理策略信号事件"""
                try:
                    start_time = time.time_ns()
                    
                    decision = self.trading_center.process_strategy_signal_event(event)
                    processing_time_ms = (time.time_ns() - start_time) / 1_000_000
                    
                    decision_event = TradeDecisionEvent(
                        signal_event=event,
                        decision=decision["decision"],
                        approval_score=decision.get("approval_score", 0.5),
                        approved_symbol=decision.get("approved_symbol"),
                        approved_direction=decision.get("approved_direction"),
                        position_size=decision.get("position_size"),
                        entry_price=decision.get("entry_price"),
                        stop_loss_price=decision.get("stop_loss_price"),
                        take_profit_price=decision.get("take_profit_price"),
                        reason=decision.get("reason", ""),
                        subsystems_opinions=decision.get("subsystems_opinions", {}),
                        processing_time_ms=processing_time_ms,
                        metadata={
                            "processing_time_ms": processing_time_ms,
                            "original_signal": event.to_dict(),
                        }
                    )
                    
                    event_bus.publish(decision_event)
                    log.debug(f"[TradingCenter] 发布 TradeDecisionEvent: {decision_event.decision.value}")
                    
                except Exception as e:
                    log.warning(f"[TradingCenter] 处理策略信号事件失败: {e}")
            
            event_bus.subscribe("StrategySignalEvent", on_strategy_signal)
            log.info("[EventSubscriberRegistrar] TradingCenter 事件订阅完成")
            
        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] TradingCenter 事件订阅失败: {e}")
