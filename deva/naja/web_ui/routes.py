"""路由注册"""

import json
import time
from pywebio.platform.tornado import webio_handler
from tornado.web import RequestHandler

from .pages import (
    main, dsadmin, signaladmin, taskadmin, strategyadmin,
    radaradmin, insightadmin, cognition_page, memory_page,
    llmadmin, banditadmin, bandit_attribution, market,
    awakening_page, dictadmin, tableadmin, runtimestateadmin,
    souladmin, configadmin, tuningadmin, system_page, health_page,
    narrative_page, narrative_lifecycle_page, merrill_clock_page,
    learningadmin, learning_list_page, learning_history_page,
    learning_detail_page, supplychain_page, api_explorer, devtools_page,
    KnowledgeActionHandler,
    _get_log_stream_page, _get_loop_audit_page,
)
from .api import HealthHandler
from .api_extensions import (
    CognitionMemoryHandler, CognitionTopicsHandler, CognitionAttentionHandler, CognitionThoughtHandler,
    SystemModulesHandler,
    RadarEventsHandler,
    BanditStatsHandler,
    KnowledgeListHandler, KnowledgeStatsHandler, KnowledgeDetailHandler, KnowledgeTradingHandler,
    DataSourceListHandler, StrategyListHandler,
    AlayaStatusHandler,
    RegistryStatusHandler, QueryStateHandler, SystemRuntimeHandler, SystemPersistentStateHandler,
    EventQueryHandler, EventStatsHandler, AppContainerStatusHandler
)
from deva.naja.cognition.ui import cognition_glossary_page
from .attention_api import (
    ManasStateHandler, HarmonyHandler, DecisionHandler,
    ConvictionHandler, ConvictionTimingHandler, ConvictionShouldAddHandler,
    PortfolioSummaryHandler, PositionMetricsHandler,
    TrackingHotspotHandler, TrackingStatsHandler,
    BlindSpotsHandler, FusionHandler, FocusHandler, NarrativeBlockMatrixHandler,
    AttentionReportHandler, LabStatusHandler, LiquidityHandler,
    StrategyTopSymbolsHandler, StrategyTopBlocksHandler, AttentionContextHandler,
)


class MarketHotspotAPIHandler(RequestHandler):
    """市场热点 JSON API — A股+美股双市场"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            from deva.naja.market_hotspot.integration.market_hotspot_integration import get_market_hotspot_integration
            integration = get_market_hotspot_integration()
            if not integration or not hasattr(integration, 'hotspot_system'):
                self.write(json.dumps({"error": "hotspot_system not initialized"}, ensure_ascii=False))
                return

            hotspot = integration.hotspot_system

            # === A股热点题材（直接从 CN context 获取）===
            cn_blocks = []
            try:
                cn_block_engine = hotspot._cn_context.block_engine
                bw = cn_block_engine.get_all_weights(filter_noise=True)
                for bid, w in sorted(bw.items(), key=lambda x: x[1], reverse=True)[:10]:
                    name = bid
                    try:
                        from deva.naja.market_hotspot.integration.history_tracker import get_history_tracker
                        ht = get_history_tracker()
                        if ht: name = ht.get_block_name(bid) or bid
                    except Exception: pass
                    cn_blocks.append({"block_id": bid, "name": name, "weight": round(w, 4)})
            except Exception: pass

            # === A股热门股票（直接从 CN context 获取）===
            cn_stocks = []
            try:
                cn_weight_pool = hotspot._cn_context.weight_pool
                sw = cn_weight_pool.get_all_weights(filter_noise=True)
                for sym, w in sorted(sw.items(), key=lambda x: x[1], reverse=True)[:20]:
                    name = sym
                    try:
                        from deva.naja.dictionary.blocks import get_stock_name
                        name = get_stock_name(sym)
                    except Exception: pass
                    cn_stocks.append({"symbol": sym, "name": name, "weight": round(w, 4)})
            except Exception: pass

            # === 美股热点 ===
            us_blocks, us_stocks, us_hotspot, us_activity = [], [], 0.0, 0.0
            try:
                us_state = hotspot.get_us_hotspot_state()
                us_hotspot = round(us_state.get("global_hotspot", 0), 4)
                us_activity = round(us_state.get("activity", 0), 4)
                for bid, w in sorted(us_state.get("block_hotspot", {}).items(), key=lambda x: x[1], reverse=True)[:10]:
                    us_blocks.append({"block_id": bid, "name": bid, "weight": round(w, 4)})
                changes = us_state.get("symbol_changes", {})
                for sym, w in sorted(us_state.get("symbol_weights", {}).items(), key=lambda x: x[1], reverse=True)[:20]:
                    try:
                        from deva.naja.dictionary.blocks import get_stock_name
                        name = get_stock_name(sym)
                    except Exception:
                        name = sym
                    us_stocks.append({"symbol": sym, "name": name, "weight": round(w, 4), "change_pct": round(changes.get(sym, 0), 2)})
            except Exception: pass

            # === A股指数 ===
            cn_indices = {"SH": None, "HS300": None, "CHINEXT": None}
            try:
                cn_idx = hotspot.get_cn_indices()
                cn_indices["SH"] = cn_idx.get("SH")
                cn_indices["HS300"] = cn_idx.get("HS300")
                cn_indices["CHINEXT"] = cn_idx.get("CHINEXT")
            except Exception: pass

            # === 美股期货 ===
            us_futures = {"NQ": None, "ES": None, "YM": None}
            try:
                futures = hotspot.get_us_futures_indices()
                us_futures["NQ"] = futures.get("NQ")
                us_futures["ES"] = futures.get("ES")
                us_futures["YM"] = futures.get("YM")
            except Exception: pass

            # === 美股涨跌分布 ===
            us_market_summary = {"up_count": 0, "down_count": 0, "flat_count": 0, "stock_count": 0}
            try:
                from deva.naja.market_hotspot.ui_components.us_market import get_us_market_summary
                summary = get_us_market_summary()
                if summary:
                    us_market_summary["up_count"] = summary.get("up_count", 0)
                    us_market_summary["down_count"] = summary.get("down_count", 0)
                    us_market_summary["flat_count"] = summary.get("flat_count", 0)
                    us_market_summary["stock_count"] = summary.get("stock_count", 0)
            except Exception: pass

            # === 系统报告 ===
            report = {}
            try: report = integration.get_hotspot_report() or {}
            except Exception: pass

            # === 市场状态 ===
            market_state = {"state": "unknown", "description": "等待数据...", "global_hotspot": 0}
            try:
                from deva.naja.market_hotspot.integration.history_tracker import get_history_tracker
                tracker = get_history_tracker()
                if tracker:
                    state_info = tracker.get_market_state_info()
                    market_state["state"] = state_info.get("state", "unknown")
                    market_state["description"] = state_info.get("description", "等待数据...")
                    market_state["global_hotspot"] = state_info.get("global_hotspot", 0)
            except Exception: pass

            # === 处理帧数统计 ===
            stats = {"processed_frames": 0, "filtered_frames": 0}
            try:
                from deva.naja.attention.orchestration.trading_center import get_trading_center
                orchestrator = get_trading_center()
                if orchestrator:
                    s = orchestrator.get_stats()
                    stats["processed_frames"] = s.get("processed_frames", 0)
                    stats["filtered_frames"] = s.get("filtered_frames", 0)
            except Exception: pass

            # === 热点变化记录 ===
            recent_changes = []
            try:
                from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
                tracker = get_history_tracker()
                if tracker:
                    changes = tracker.get_recent_changes(n=20)
                    for change in changes:
                        recent_changes.append({
                            "timestamp": change.timestamp,
                            "time": time.strftime("%H:%M:%S", time.localtime(change.timestamp)),
                            "change_type": change.change_type,
                            "item_id": change.item_id,
                            "item_name": change.item_name or change.item_id,
                            "old_weight": round(change.old_weight, 4) if hasattr(change, 'old_weight') and change.old_weight else 0,
                            "new_weight": round(change.new_weight, 4) if hasattr(change, 'new_weight') and change.new_weight else 0,
                            "change_percent": round(change.change_percent, 1) if hasattr(change, 'change_percent') and change.change_percent else 0,
                            "price": round(change.price, 2) if hasattr(change, 'price') and change.price else None,
                            "price_change": round(change.price_change, 2) if hasattr(change, 'price_change') and change.price_change else 0,
                            "volume": change.volume if hasattr(change, 'volume') and change.volume else None,
                            "block": change.block if hasattr(change, 'block') and change.block else None,
                        })
            except Exception: pass

            # === 热点转移报告 ===
            shift_report = {"has_shift": False}
            try:
                from deva.naja.market_hotspot.ui_components.common import get_hotspot_shift_report
                shift = get_hotspot_shift_report()
                if shift:
                    shift_report = shift
            except Exception: pass

            self.write(json.dumps({
                "cn": {
                    "hot_blocks": cn_blocks,
                    "hot_stocks": cn_stocks,
                    "market_hotspot": round(report.get("global_hotspot", 0), 4),
                    "market_activity": round(report.get("activity", 0), 4),
                    "indices": cn_indices,
                },
                "us": {
                    "hot_blocks": us_blocks,
                    "hot_stocks": us_stocks,
                    "market_hotspot": us_hotspot,
                    "market_activity": us_activity,
                    "futures": us_futures,
                    "market_summary": us_market_summary,
                },
                "market_state": market_state,
                "stats": stats,
                "system_status": report.get("status", "unknown"),
                "processed_snapshots": report.get("processed_snapshots", 0),
                "recent_changes": recent_changes,
                "shift_report": shift_report,
            }, ensure_ascii=False, indent=2))
        except Exception as e:
            self.set_status(500)
            import traceback; traceback.print_exc()
            self.write(json.dumps({"error": str(e)}, ensure_ascii=False))


def create_handlers(cdn: str = None):
    """创建路由处理器"""
    cdn_url = cdn or 'https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/'

    page_routes = [
        (r'/', webio_handler(main, cdn=cdn_url)),
        (r'/cognition', webio_handler(cognition_page, cdn=cdn_url)),
        (r'/cognition_glossary', webio_handler(cognition_glossary_page, cdn=cdn_url)),
        (r'/memory', webio_handler(memory_page, cdn=cdn_url)),
        (r'/insight', webio_handler(insightadmin, cdn=cdn_url)),
        (r'/system', webio_handler(system_page, cdn=cdn_url)),
        (r'/health', webio_handler(health_page, cdn=cdn_url)),
        (r'/performance', webio_handler(system_page, cdn=cdn_url)),
        (r'/signaladmin', webio_handler(signaladmin, cdn=cdn_url)),
        (r'/dsadmin', webio_handler(dsadmin, cdn=cdn_url)),
        (r'/taskadmin', webio_handler(taskadmin, cdn=cdn_url)),
        (r'/strategyadmin', webio_handler(strategyadmin, cdn=cdn_url)),
        (r'/radaradmin', webio_handler(radaradmin, cdn=cdn_url)),
        (r'/llmadmin', webio_handler(llmadmin, cdn=cdn_url)),
        (r'/banditadmin', webio_handler(banditadmin, cdn=cdn_url)),
        (r'/bandit_attribution', webio_handler(bandit_attribution, cdn=cdn_url)),
        (r'/market', webio_handler(market, cdn=cdn_url)),
        (r'/awakening', webio_handler(awakening_page, cdn=cdn_url)),
        (r'/dictadmin', webio_handler(dictadmin, cdn=cdn_url)),
        (r'/tableadmin', webio_handler(tableadmin, cdn=cdn_url)),
        (r'/runtime_state', webio_handler(runtimestateadmin, cdn=cdn_url)),
        (r'/configadmin', webio_handler(configadmin, cdn=cdn_url)),
        (r'/souladmin', webio_handler(souladmin, cdn=cdn_url)),
        (r'/logstream', webio_handler(lambda: _get_log_stream_page()(), cdn=cdn_url)),
        (r'/tuningadmin', webio_handler(tuningadmin, cdn=cdn_url)),
        (r'/supplychain', webio_handler(supplychain_page, cdn=cdn_url)),
        (r'/narrative', webio_handler(narrative_page, cdn=cdn_url)),
        (r'/narrative_lifecycle', webio_handler(narrative_lifecycle_page, cdn=cdn_url)),
        (r'/merrill_clock', webio_handler(merrill_clock_page, cdn=cdn_url)),
        (r'/loop_audit', webio_handler(lambda: _get_loop_audit_page()(), cdn=cdn_url)),
        (r'/learning', webio_handler(learningadmin, cdn=cdn_url)),
        (r'/learning/list', webio_handler(learning_list_page, cdn=cdn_url)),
        (r'/learning/history', webio_handler(learning_history_page, cdn=cdn_url)),
        (r'/learning/detail', webio_handler(learning_detail_page, cdn=cdn_url)),
        (r'/api_explorer', webio_handler(api_explorer, cdn=cdn_url)),
        (r'/devtools', webio_handler(devtools_page, cdn=cdn_url)),
    ]

    api_routes = [
        (r'/api/knowledge/action', KnowledgeActionHandler),
        (r'/api/health', HealthHandler),
        (r'/api/cognition/memory', CognitionMemoryHandler),
        (r'/api/cognition/topics', CognitionTopicsHandler),
        (r'/api/cognition/attention', CognitionAttentionHandler),
        (r'/api/cognition/thought', CognitionThoughtHandler),
        (r'/api/market/hotspot', MarketHotspotAPIHandler),
        (r'/api/system/runtime', SystemRuntimeHandler),
        (r'/api/system/modules', SystemModulesHandler),
        (r'/api/radar/events', RadarEventsHandler),
        (r'/api/bandit/stats', BanditStatsHandler),
        (r'/api/knowledge/list', KnowledgeListHandler),
        (r'/api/knowledge/stats', KnowledgeStatsHandler),
        (r'/api/knowledge/detail', KnowledgeDetailHandler),
        (r'/api/knowledge/trading', KnowledgeTradingHandler),
        (r'/api/datasource/list', DataSourceListHandler),
        (r'/api/strategy/list', StrategyListHandler),
        (r'/api/alaya/status', AlayaStatusHandler),
        (r'/api/attention/manas/state', ManasStateHandler),
        (r'/api/attention/harmony', HarmonyHandler),
        (r'/api/attention/decision', DecisionHandler),
        (r'/api/attention/conviction', ConvictionHandler),
        (r'/api/attention/conviction/timing', ConvictionTimingHandler),
        (r'/api/attention/conviction/should-add', ConvictionShouldAddHandler),
        (r'/api/attention/portfolio/summary', PortfolioSummaryHandler),
        (r'/api/attention/position/metrics', PositionMetricsHandler),
        (r'/api/attention/tracking/hotspot', TrackingHotspotHandler),
        (r'/api/attention/tracking/stats', TrackingStatsHandler),
        (r'/api/attention/blind-spots', BlindSpotsHandler),
        (r'/api/attention/fusion', FusionHandler),
        (r'/api/attention/focus', FocusHandler),
        (r'/api/attention/narrative-block-matrix', NarrativeBlockMatrixHandler),
        (r'/api/attention/report', AttentionReportHandler),
        (r'/api/attention/lab/status', LabStatusHandler),
        (r'/api/attention/liquidity', LiquidityHandler),
        (r'/api/attention/strategy/top-symbols', StrategyTopSymbolsHandler),
        (r'/api/attention/strategy/top-blocks', StrategyTopBlocksHandler),
        (r'/api/attention/context', AttentionContextHandler),
        (r'/api/registry/status', RegistryStatusHandler),
        (r'/api/query/state', QueryStateHandler),
        (r'/api/system/persistent', SystemPersistentStateHandler),
        (r'/api/events/query', EventQueryHandler),
        (r'/api/events/stats', EventStatsHandler),
        (r'/api/app/container', AppContainerStatusHandler),
    ]

    return page_routes + api_routes
