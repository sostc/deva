"""Naja API 端点扩展

提供系统各模块的 JSON API 端点
"""

import json
import time
from typing import Dict, Any, Optional, List
from tornado.web import RequestHandler

from deva.naja.register import SR


def _get_cognition_engine():
    """获取认知引擎"""
    try:
        from deva.naja.application import get_app_container
        container = get_app_container()
        return container.cognition_engine if container else None
    except Exception:
        return None


def _get_market_hotspot_integration():
    """获取热点系统集成"""
    try:
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        return get_market_hotspot_integration()
    except Exception:
        return None


def _get_system_monitor():
    """获取系统监控器"""
    try:
        from deva.naja.infra.observability.system_monitor import SystemMonitor
        return SystemMonitor()
    except Exception:
        return None


def _get_radar_engine():
    """获取雷达引擎"""
    try:
        from deva.naja.radar import get_radar_engine
        return get_radar_engine()
    except Exception:
        return None


def _get_bandit_runner():
    """获取 Bandit 运行器"""
    try:
        from deva.naja.application import get_app_container
        container = get_app_container()
        return container.bandit_runner if container else None
    except Exception:
        return None


def _get_datasource_manager():
    """获取数据源管理器"""
    try:
        from deva.naja.datasource import get_datasource_manager
        return get_datasource_manager()
    except Exception:
        return None


def _get_strategy_manager():
    """获取策略管理器"""
    try:
        from deva.naja.strategy import get_strategy_manager
        return get_strategy_manager()
    except Exception:
        return None


def _get_trading_center():
    """获取交易中心"""
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        return get_trading_center()
    except Exception:
        return None


def _get_awakened_alaya():
    """获取觉醒的阿那亚"""
    try:
        from deva.naja.application import get_app_container
        container = get_app_container()
        return container.awakened_alaya if container else None
    except Exception:
        return None


class CognitionMemoryHandler(RequestHandler):
    """认知系统记忆报告 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取认知系统记忆报告"""
        try:
            engine = _get_cognition_engine()
            if not engine:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "认知引擎未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            report = engine.get_memory_report()
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": report
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class CognitionTopicsHandler(RequestHandler):
    """认知系统主题信号 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取认知系统主题信号"""
        try:
            engine = _get_cognition_engine()
            if not engine:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "认知引擎未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            lookback = int(self.get_argument('lookback', 50))
            signals = engine.get_topic_signals(lookback=lookback)
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": signals
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class CognitionAttentionHandler(RequestHandler):
    """认知系统注意力提示 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取认知系统注意力提示"""
        try:
            engine = _get_cognition_engine()
            if not engine:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "认知引擎未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            lookback = int(self.get_argument('lookback', 200))
            hints = engine.get_attention_hints(lookback=lookback)
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": hints
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class CognitionThoughtHandler(RequestHandler):
    """认知系统思想报告 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取认知系统思想报告"""
        try:
            engine = _get_cognition_engine()
            if not engine:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "认知引擎未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            report = engine._news_mind.generate_thought_report()
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": {
                    "report": report
                }
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class SystemRuntimeHandler(RequestHandler):
    """系统运行时监控 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取系统运行时监控数据"""
        try:
            monitor = _get_system_monitor()
            if not monitor:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "系统监控器未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            status = monitor.get_overall_status()
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": status
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class SystemModulesHandler(RequestHandler):
    """系统模块状态 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取系统模块状态"""
        try:
            monitor = _get_system_monitor()
            if not monitor:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "系统监控器未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            modules = monitor.get_all_health()
            modules_data = [module.to_dict() for module in modules]
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": {
                    "modules": modules_data
                }
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class RadarEventsHandler(RequestHandler):
    """雷达事件 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取雷达事件"""
        try:
            radar = _get_radar_engine()
            if not radar:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "雷达引擎未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            events = radar.get_recent_events()
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": {
                    "events": events
                }
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class BanditStatsHandler(RequestHandler):
    """Bandit 决策统计 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取 Bandit 决策统计"""
        try:
            bandit = _get_bandit_runner()
            if not bandit:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "Bandit 运行器未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            stats = {
                "running": bandit._running,
                "enabled": bandit._enabled,
                "force_mode": bandit._force_mode,
                "current_phase": bandit._current_phase,
                "previous_phase": bandit._previous_phase,
                "select_interval": bandit._select_interval,
                "adjust_interval": bandit._adjust_interval,
            }
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": stats
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class KnowledgeListHandler(RequestHandler):
    """知识库列表 API — 最近学到的因果知识"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        try:
            from deva.naja.knowledge import get_knowledge_store
            store = get_knowledge_store()

            # 参数
            status = self.get_argument("status", None)
            category = self.get_argument("category", None)
            limit = int(self.get_argument("limit", "20"))
            offset = int(self.get_argument("offset", "0"))

            entries = store.get_all()

            # 按状态筛选
            if status:
                entries = [e for e in entries if e.status == status]

            # 按分类筛选
            if category:
                entries = [e for e in entries if e.category == category]

            # 按时间降序
            entries.sort(key=lambda e: e.extracted_at, reverse=True)

            total = len(entries)
            entries = entries[offset:offset + limit]

            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "entries": [
                        {
                            "id": e.id,
                            "cause": e.cause,
                            "effect": e.effect,
                            "confidence": e.adjusted_confidence,
                            "source": e.source,
                            "original_title": e.original_title,
                            "extracted_at": e.extracted_at,
                            "category": e.category,
                            "status": e.status,
                            "evidence_count": e.evidence_count,
                            "quality_score": e.quality_score,
                            "mechanism": e.mechanism,
                            "timeframe": e.timeframe,
                            "last_updated": e.last_updated,
                        }
                        for e in entries
                    ],
                },
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


class KnowledgeStatsHandler(RequestHandler):
    """知识库统计 API"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        try:
            from deva.naja.knowledge import get_knowledge_store
            store = get_knowledge_store()
            stats = store.get_stats()

            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": stats,
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


class KnowledgeDetailHandler(RequestHandler):
    """知识条目详情 API"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        try:
            entry_id = self.get_argument("id", "")
            if not entry_id:
                self.write(json.dumps({"success": False, "error": "缺少 id 参数"}, ensure_ascii=False))
                return

            from deva.naja.knowledge import get_knowledge_store
            store = get_knowledge_store()
            entry = store.get(entry_id)

            if not entry:
                self.write(json.dumps({"success": False, "error": f"未找到知识条目: {entry_id}"}, ensure_ascii=False))
                return

            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": {
                    "id": entry.id,
                    "cause": entry.cause,
                    "effect": entry.effect,
                    "confidence": entry.adjusted_confidence,
                    "base_confidence": entry.base_confidence,
                    "source": entry.source,
                    "original_title": entry.original_title,
                    "extracted_at": entry.extracted_at,
                    "category": entry.category,
                    "status": entry.status,
                    "evidence_count": entry.evidence_count,
                    "quality_score": entry.quality_score,
                    "mechanism": entry.mechanism,
                    "timeframe": entry.timeframe,
                    "last_updated": entry.last_updated,
                    "last_seen": entry.last_seen,
                    "manual_override": entry.manual_override,
                    "manual_note": entry.manual_note,
                },
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


class KnowledgeTradingHandler(RequestHandler):
    """可用于交易决策的知识 API"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        try:
            from deva.naja.knowledge import get_knowledge_store
            store = get_knowledge_store()
            data = store.get_for_trading()

            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": data,
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))


class DataSourceListHandler(RequestHandler):
    """数据源列表 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取数据源列表"""
        try:
            manager = _get_datasource_manager()
            if not manager:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "数据源管理器未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            stats = manager.get_stats()
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": stats
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class StrategyListHandler(RequestHandler):
    """策略列表 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取策略列表"""
        try:
            manager = _get_strategy_manager()
            if not manager:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "策略管理器未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            stats = manager.get_stats()
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": stats
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class AlayaStatusHandler(RequestHandler):
    """阿那亚觉醒状态 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取阿那亚觉醒状态"""
        try:
            alaya = _get_awakened_alaya()
            if not alaya:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "阿那亚未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            stats = alaya.get_stats()
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": stats
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class RegistryStatusHandler(RequestHandler):
    """单例注册表状态 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取单例注册表状态"""
        try:
            from deva.naja.infra.registry.singleton_registry import get_registry_status
            registry_status = get_registry_status()
            
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": registry_status
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class QueryStateHandler(RequestHandler):
    """查询状态 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取查询状态"""
        try:
            from deva.naja.register import SR
            query_state = SR('query_state')
            
            if not query_state:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "查询状态未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return
            
            summary = query_state.get_summary()
            
            # 补充完整的状态数据
            full_data = {
                "summary": summary,
                "market_regime": query_state.market_regime,
                "attention_focus": query_state.attention_focus,
                "risk_bias": query_state.risk_bias,
                "macro_liquidity_signal": query_state.macro_liquidity_signal,
                "narrative_state": query_state.narrative_state,
                "cognitive_insights": query_state.cognitive_insights,
                "liquidity_state": query_state.liquidity_state,
                "economic_cycle": query_state.economic_cycle,
                "active_value_type": query_state.active_value_type,
                "last_decision_reason": query_state.last_decision_reason,
            }
            
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": full_data
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class SystemPersistentStateHandler(RequestHandler):
    """系统持久化状态 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取系统持久化状态快照"""
        try:
            from deva.naja.register import SR
            system_state_manager = SR('system_state_manager')
            
            if not system_state_manager:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "系统状态管理器未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return
            
            state_summary = system_state_manager.get_state_summary()
            
            # 补充完整状态数据
            full_data = {
                "summary": state_summary,
                "state": system_state_manager._state
            }
            
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": full_data
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class EventQueryHandler(RequestHandler):
    """事件查询 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """查询事件"""
        try:
            from deva.naja.events.query_interface import get_event_query, EventQuery, QueryCondition
            event_query = get_event_query()
            
            if not event_query:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "事件查询接口未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return
            
            # 获取查询参数
            event_type = self.get_argument('event_type', None)
            symbol = self.get_argument('symbol', None)
            direction = self.get_argument('direction', None)
            min_confidence = self.get_argument('min_confidence', None)
            max_confidence = self.get_argument('max_confidence', None)
            start_time = self.get_argument('start_time', None)
            end_time = self.get_argument('end_time', None)
            limit = int(self.get_argument('limit', 100))
            offset = int(self.get_argument('offset', 0))
            
            # 构建查询条件
            condition = QueryCondition(
                event_type=event_type,
                symbol=symbol,
                direction=direction,
                min_confidence=float(min_confidence) if min_confidence else None,
                max_confidence=float(max_confidence) if max_confidence else None,
                start_time=float(start_time) if start_time else None,
                end_time=float(end_time) if end_time else None,
                limit=limit,
                offset=offset
            )
            
            # 执行查询
            events = event_query.query_events(condition)
            
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": {
                    "events": events,
                    "count": len(events),
                    "query": condition.to_dict()
                }
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class EventStatsHandler(RequestHandler):
    """事件统计 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取事件统计"""
        try:
            from deva.naja.events.query_interface import get_event_query
            event_query = get_event_query()
            
            if not event_query:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "事件查询接口未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return
            
            event_type = self.get_argument('event_type', 'StrategySignalEvent')
            days = int(self.get_argument('days', 30))
            
            stats = event_query.get_stats(event_type, days)
            
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": {
                    "event_type": event_type,
                    "days": days,
                    "stats": {
                        "total_events": stats.total_events,
                        "buy_signals": stats.buy_signals,
                        "sell_signals": stats.sell_signals,
                        "avg_confidence": stats.avg_confidence,
                        "max_confidence": stats.max_confidence,
                        "min_confidence": stats.min_confidence,
                        "timeline": stats.timeline
                    }
                }
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))


class AppContainerStatusHandler(RequestHandler):
    """应用容器状态 API 端点"""

    def set_default_headers(self):
        """设置默认响应头"""
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        """处理OPTIONS请求"""
        self.set_status(204)
        self.finish()

    def get(self):
        """获取应用容器状态"""
        try:
            from deva.naja.application.container import get_app_container
            container = get_app_container()
            
            if not container:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "应用容器未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return
            
            startup_report = container.startup_report()
            
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": {
                    "startup_report": startup_report,
                    "components_assembled": container._components_assembled
                }
            }
            self.write(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            error_result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            self.set_status(500)
            self.write(json.dumps(error_result, ensure_ascii=False))
