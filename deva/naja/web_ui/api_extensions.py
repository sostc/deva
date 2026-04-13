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
        return SR('cognition_engine')
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
        return SR('bandit_runner')
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
        return SR('awakened_alaya')
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


class MarketStateHandler(RequestHandler):
    """市场状态 API 端点"""

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
        """获取市场状态"""
        try:
            integration = _get_market_hotspot_integration()
            if not integration or not integration.hotspot_system:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "市场热点系统未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            market_state = integration.hotspot_system.global_hotspot.get_market_state()
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": market_state
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


class MarketHotspotDetailsHandler(RequestHandler):
    """市场热点详情 API 端点"""

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
        """获取市场热点详情"""
        try:
            integration = _get_market_hotspot_integration()
            if not integration or not integration.hotspot_system:
                result = {
                    "timestamp": time.time(),
                    "success": False,
                    "error": "市场热点系统未初始化"
                }
                self.write(json.dumps(result, ensure_ascii=False))
                return

            # 这里需要获取市场快照数据
            # 暂时返回空数据结构
            result = {
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": True,
                "data": {
                    "message": "市场热点详情功能待实现"
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


class SystemStatusHandler(RequestHandler):
    """系统状态 API 端点"""

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
        """获取系统状态"""
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
