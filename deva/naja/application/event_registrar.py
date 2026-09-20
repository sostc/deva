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
            self._register_market_hotspot_push(event_bus)
            self._register_radar_news_push(event_bus)
            self._register_structural_growth(event_bus)
            
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
                # 注入依赖
                from deva.naja.application import get_app_container
                container = get_app_container()
                if container:
                    analyzer.set_insight_pool(container.insight_pool)
                
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

    def _register_market_hotspot_push(self, event_bus) -> None:
        """注册市场热点前端推送。"""
        try:
            from deva.naja.market_hotspot.push_center import get_push_center

            push_center = get_push_center()

            def _name_for_symbol(symbol: str) -> str:
                try:
                    from deva.naja.dictionary.blocks import get_stock_name
                    return get_stock_name(symbol)
                except Exception:
                    return symbol

            def on_hotspot_computed(event):
                try:
                    block_hotspot = getattr(event, "block_hotspot", {}) or {}
                    symbol_weights = getattr(event, "symbol_weights", {}) or {}
                    hot_blocks = [
                        {"block_id": str(bid), "name": str(bid), "weight": float(weight)}
                        for bid, weight in sorted(block_hotspot.items(), key=lambda item: item[1], reverse=True)[:10]
                    ]
                    hot_stocks = [
                        {"symbol": str(symbol), "name": _name_for_symbol(str(symbol)), "weight": float(weight)}
                        for symbol, weight in sorted(symbol_weights.items(), key=lambda item: item[1], reverse=True)[:20]
                    ]

                    push_center.push_dict({
                        "timestamp": getattr(event, "timestamp", time.time()),
                        "market": getattr(event, "market", "CN"),
                        "global_hotspot": float(getattr(event, "global_hotspot", 0.0) or 0.0),
                        "activity": float(getattr(event, "activity", 0.0) or 0.0),
                        "hot_blocks": hot_blocks,
                        "hot_stocks": hot_stocks,
                        "block_changes": [],
                        "stock_changes": [],
                        "raw_snapshot": event.to_dict() if hasattr(event, "to_dict") else {},
                    })
                except Exception as exc:
                    log.warning(f"[EventSubscriberRegistrar] 市场热点推送失败: {exc}")

            event_bus.subscribe(
                'HotspotComputedEvent',
                on_hotspot_computed,
                markets={'US', 'CN'},
                priority=1,
            )
            log.info("[EventSubscriberRegistrar] MarketHotspotPushCenter 事件订阅完成")

        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] MarketHotspotPushCenter 事件订阅失败: {e}")

    def _register_trading_center(self, event_bus) -> None:
        """注册 TradingCenter 的事件订阅"""
        if self.trading_center is None:
            return

        try:
            from deva.naja.events import TradeDecisionEvent, get_trading_bus

            trading_bus = get_trading_bus()

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

                    trading_bus.publish(decision_event)
                    log.debug(f"[TradingCenter] 发布 TradeDecisionEvent: {decision_event.decision.value}")

                except Exception as e:
                    log.warning(f"[TradingCenter] 处理策略信号事件失败: {e}")

            trading_bus.subscribe("StrategySignalEvent", on_strategy_signal)
            log.info("[EventSubscriberRegistrar] TradingCenter 事件订阅完成（使用交易总线）")

        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] TradingCenter 事件订阅失败: {e}")

    def _register_radar_news_push(self, event_bus) -> None:
        """注册雷达新闻前端推送。"""
        try:
            from deva.naja.radar.push_center import get_news_push_center

            push_center = get_news_push_center()

            def on_text_focused(event):
                try:
                    source = getattr(event, "source", "")
                    if source != "radar_news":
                        return

                    push_center.push_news(event)
                    log.debug(f"[EventSubscriberRegistrar] 雷达新闻已推送: {getattr(event, 'title', '')[:30]}")

                except Exception as exc:
                    log.warning(f"[EventSubscriberRegistrar] 雷达新闻推送失败: {exc}")

            event_bus.subscribe(
                'TextFocusedEvent',
                on_text_focused,
                priority=1,
            )
            log.info("[EventSubscriberRegistrar] RadarNewsPushCenter 事件订阅完成")

        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] RadarNewsPushCenter 事件订阅失败: {e}")

    def _register_structural_growth(self, event_bus) -> None:
        """注册结构性增长雷达的新闻事件订阅。

        将 TextFocusedEvent 匹配到观察池中的行业，作为证据喂入。
        """
        try:
            from deva.naja.application import get_app_container
            container = get_app_container()
            if container is None:
                return

            pool = container.structural_growth_pool
            from deva.naja.structural_growth.news_bridge import NewsBridge, IndustryConfig

            # 默认行业配置（美股为主，中英双语关键词）
            default_configs = [
                IndustryConfig(industry_id="ai_chips", name="AI芯片",
                               keywords=["NVDA", "英伟达", "AMD", "GPU", "AI芯片", "AI accelerator",
                                         "H100", "H200", "B200", "GB200", "data center GPU", "AI算力芯片"]),
                IndustryConfig(industry_id="ai_foundry", name="晶圆代工",
                               keywords=["TSMC", "台积电", "Intel foundry", "代工", "晶圆代工",
                                         "3nm", "2nm", "制程", "process node", "wafer"]),
                IndustryConfig(industry_id="semiconductor_equipment", name="半导体设备",
                               keywords=["ASML", "光刻机", "lithography", "Applied Materials",
                                         "Lam Research", "KLA", "半导体设备", "semiconductor equipment",
                                         "etch", "deposition", "inspection"]),
                IndustryConfig(industry_id="hbm", name="高带宽存储",
                               keywords=["HBM", "高带宽内存", "HBM3", "HBM3E", "SK海力士",
                                         "Micron", "美光", "memory chip", "DRAM", "storage"]),
                IndustryConfig(industry_id="cloud_infra", name="云计算/数据中心",
                               keywords=["Azure", "AWS", "GCP", "cloud", "云计算", "数据中心",
                                         "data center", "hyperscaler", "Microsoft cloud",
                                         "Google Cloud", "Amazon Web Services"]),
                IndustryConfig(industry_id="ai_software", name="AI软件/应用",
                               keywords=["Palantir", "Snowflake", "Salesforce", "MongoDB",
                                         "AI software", "AI应用", "LLM", "generative AI",
                                         "AI platform", "machine learning platform"]),
                IndustryConfig(industry_id="ai_power", name="AI电力/散热",
                               keywords=["AI电力", "数据中心用电", "算力电力", "AI用电",
                                         "data center energy", "nuclear power", "数据中心能源",
                                         "GE Vernova", "Vistra", "Constellation",
                                         "数据中心散热", "data center cooling"]),
                IndustryConfig(industry_id="energy_storage", name="储能",
                               keywords=["储能", "锂电池", "动力电池", "储能系统",
                                         "battery storage", "lithium battery", "Tesla energy",
                                         "Enphase", "grid storage", "电化学储能"]),
                IndustryConfig(industry_id="cybersecurity", name="网络安全",
                               keywords=["cybersecurity", "网络安全", "Palo Alto",
                                         "CrowdStrike", "Fortinet", "Zscaler",
                                         "data breach", " ransomware", "zero trust",
                                         "endpoint security", "cloud security"]),
                IndustryConfig(industry_id="robotics", name="机器人/自动化",
                               keywords=["robotics", "机器人", "Optimus", "Tesla robot",
                                         "Intuitive Surgical", "surgical robot",
                                         "automation", "工业机器人", "humanoid robot"]),
                IndustryConfig(industry_id="ai_networking", name="AI网络",
                               keywords=["Arista", "data center networking", "数据中心网络",
                                         "Broadcom networking", "AI networking",
                                         "Ethernet", "光模块", "optical module",
                                         "switch chip", "交换芯片"]),
            ]
            bridge = NewsBridge(pool=pool, industry_configs=default_configs)

            def on_text_focused(event):
                try:
                    bridge.on_text_event(
                        text=getattr(event, "text", ""),
                        title=getattr(event, "title", ""),
                        source=getattr(event, "source", ""),
                        sentiment=getattr(event, "sentiment", 0.5),
                        topics=getattr(event, "topics", []),
                        timestamp=getattr(event, "timestamp", None),
                    )
                except Exception as exc:
                    log.debug(f"[EventSubscriberRegistrar] StructuralGrowth 新闻处理失败: {exc}")

            event_bus.subscribe(
                'TextFocusedEvent',
                on_text_focused,
                priority=5,
            )
            log.info("[EventSubscriberRegistrar] StructuralGrowth 新闻订阅完成")

        except Exception as e:
            log.warning(f"[EventSubscriberRegistrar] StructuralGrowth 事件订阅失败: {e}")

