"""路由注册"""

import json
from pywebio.platform.tornado import webio_handler
from tornado.web import RequestHandler

from .pages import (
    main, dsadmin, signaladmin, taskadmin, strategyadmin,
    radaradmin, insightadmin, cognition_page, memory_page,
    llmadmin, banditadmin, bandit_attribution, market,
    awakening_page, dictadmin, tableadmin, runtimestateadmin,
    souladmin, configadmin, tuningadmin, system_page,
    narrative_page, narrative_lifecycle_page, merrill_clock_page,
    learningadmin, learning_list_page, learning_history_page,
    learning_detail_page, supplychain_page,
    KnowledgeActionHandler,
    _get_log_stream_page, _get_loop_audit_page,
)
from .api import HotspotHandler, HealthHandler
from .api_extensions import (
    CognitionMemoryHandler, CognitionTopicsHandler, CognitionAttentionHandler, CognitionThoughtHandler,
    MarketStateHandler, MarketHotspotDetailsHandler,
    SystemStatusHandler, SystemModulesHandler,
    RadarEventsHandler,
    BanditStatsHandler,
    KnowledgeListHandler, KnowledgeStatsHandler, KnowledgeDetailHandler, KnowledgeTradingHandler,
    DataSourceListHandler, StrategyListHandler,
    AlayaStatusHandler,
    RegistryStatusHandler, QueryStateHandler, SystemStateHandler,
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

            # === A股热点题材 ===
            cn_blocks = []
            try:
                bw = hotspot.block_hotspot.get_all_weights(filter_noise=True)
                for bid, w in sorted(bw.items(), key=lambda x: x[1], reverse=True)[:10]:
                    name = bid
                    try:
                        from deva.naja.market_hotspot.integration.history_tracker import get_history_tracker
                        ht = get_history_tracker()
                        if ht: name = ht.get_block_name(bid) or bid
                    except Exception: pass
                    cn_blocks.append({"block_id": bid, "name": name, "weight": round(w, 4)})
            except Exception: pass

            # === A股热门股票 ===
            cn_stocks = []
            try:
                sw = hotspot.weight_pool.get_all_weights(filter_noise=True)
                for sym, w in sorted(sw.items(), key=lambda x: x[1], reverse=True)[:20]:
                    name = sym
                    try:
                        from deva.naja.dictionary.blocks import BlockDictionary
                        info = BlockDictionary().get_stock_info(sym)
                        if info: name = info.get("name", sym)
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
                    us_stocks.append({"symbol": sym, "name": sym, "weight": round(w, 4), "change_pct": round(changes.get(sym, 0), 2)})
            except Exception: pass

            # === 系统报告 ===
            report = {}
            try: report = integration.get_hotspot_report() or {}
            except Exception: pass

            self.write(json.dumps({
                "cn": {"hot_blocks": cn_blocks, "hot_stocks": cn_stocks,
                       "market_hotspot": round(report.get("global_hotspot", 0), 4),
                       "market_activity": round(report.get("activity", 0), 4)},
                "us": {"hot_blocks": us_blocks, "hot_stocks": us_stocks,
                       "market_hotspot": us_hotspot, "market_activity": us_activity},
                "system_status": report.get("status", "unknown"),
                "processed_snapshots": report.get("processed_snapshots", 0),
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
    ]

    api_routes = [
        (r'/api/knowledge/action', KnowledgeActionHandler),
        (r'/api/hotspot', HotspotHandler),
        (r'/api/health', HealthHandler),
        (r'/api/cognition/memory', CognitionMemoryHandler),
        (r'/api/cognition/topics', CognitionTopicsHandler),
        (r'/api/cognition/attention', CognitionAttentionHandler),
        (r'/api/cognition/thought', CognitionThoughtHandler),
        (r'/api/market/state', MarketStateHandler),
        (r'/api/market/hotspot/details', MarketHotspotDetailsHandler),
        (r'/api/market/hotspot', MarketHotspotAPIHandler),
        (r'/api/system/status', SystemStatusHandler),
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
        # 新的数据结构 API 端点
        (r'/api/registry/status', RegistryStatusHandler),
        (r'/api/query/state', QueryStateHandler),
        (r'/api/system/state', SystemStateHandler),
        (r'/api/events/query', EventQueryHandler),
        (r'/api/events/stats', EventStatsHandler),
        (r'/api/app/container', AppContainerStatusHandler),
    ]

    return page_routes + api_routes
