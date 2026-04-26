"""Attention 系统 REST API 端点"""

import json
from tornado.web import RequestHandler


def _safe_get(singleton_name, attr=None):
    """安全获取单例实例，失败返回 None"""
    try:
        from deva.naja.register import SR
        
        sr_name_map = {
            'hotspot_signal_tracker': 'hotspot_signal_tracker',
            'focus_manager': 'focus_manager',
            'liquidity_manager': 'liquidity_manager',
            'position_monitor': 'position_monitor',
            'report_generator': 'report_generator',
            'blind_spot_investigator': 'blind_spot_investigator',
            'attention_fusion': 'attention_fusion',
            'conviction_validator': 'conviction_validator',
            'narrative_block_linker': 'narrative_block_linker',
        }
        
        if singleton_name in sr_name_map:
            obj = SR(sr_name_map[singleton_name])
            if obj is None:
                return None
            if attr:
                return getattr(obj, attr, None)
            return obj
        
        from deva.naja.application import get_app_container
        container = get_app_container()
        if not container:
            return None
        
        name_map = {
            'trading_center': 'trading_center',
            'attention_os': 'attention_os',
            'cognition_engine': 'cognition_engine',
            'bandit_runner': 'bandit_runner',
            'virtual_portfolio': 'virtual_portfolio',
            'insight_pool': 'insight_pool',
            'trading_clock': 'trading_clock',
        }
        
        attr_name = name_map.get(singleton_name)
        if not attr_name or not hasattr(container, attr_name):
            return None
        
        obj = getattr(container, attr_name)
        if obj is None:
            import logging
            logging.getLogger(__name__).warning(f"Container.{attr_name} returned None")
            return None
        if attr:
            return getattr(obj, attr, None)
        return obj
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"_safe_get('{singleton_name}') failed: {e}")
        return None


def _to_dict(obj):
    """将对象转为可序列化的字典"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(i) for i in obj]
    if hasattr(obj, '__dict__'):
        return _to_dict(obj.__dict__)
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()
    return obj


def _success(data):
    return {"success": True, "data": data}


def _error(msg):
    return {"success": False, "error": msg}


# ============================================================
# P0 - 核心决策
# ============================================================

class ManasStateHandler(RequestHandler):
    """末那识引擎状态"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            # 使用 get_manas_manager() 确保自动启用
            from deva.naja.attention.kernel.manas_manager import get_manas_manager
            manager = get_manas_manager()
            if manager is None:
                self.write(json.dumps(_error("manas_manager 未初始化"), ensure_ascii=False))
                return
            # 确保启用
            if not manager.is_enabled():
                manager.set_enabled(True)
            state = manager.get_state()
            self.write(json.dumps(_success(_to_dict(state)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class HarmonyHandler(RequestHandler):
    """注意力和谐度"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            tc = _safe_get('trading_center')
            if tc is None:
                self.write(json.dumps(_error("trading_center 未初始化"), ensure_ascii=False))
                return
            harmony = tc.get_harmony() if hasattr(tc, 'get_harmony') else None
            self.write(json.dumps(_success(_to_dict(harmony)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class DecisionHandler(RequestHandler):
    """交易决策"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            tc = _safe_get('trading_center')
            if tc is None:
                self.write(json.dumps(_error("trading_center 未初始化"), ensure_ascii=False))
                return
            # 获取最新输出
            output = None
            if hasattr(tc, 'get_latest_output'):
                output = tc.get_latest_output()
            elif hasattr(tc, '_last_output'):
                output = tc._last_output
            if output is None:
                self.write(json.dumps(_success({"message": "暂无决策数据，等待下一个市场周期"}), ensure_ascii=False))
                return
            self.write(json.dumps(_success(_to_dict(output)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class ConvictionHandler(RequestHandler):
    """信念验证"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            cv = _safe_get('conviction_validator')
            if cv is None:
                self.write(json.dumps(_error("conviction_validator 未初始化"), ensure_ascii=False))
                return
            # 返回最后一次验证结果
            result = None
            if hasattr(cv, 'get_last_result'):
                result = cv.get_last_result()
            elif hasattr(cv, '_last_result'):
                result = cv._last_result
            if result:
                self.write(json.dumps(_success(_to_dict(result)), ensure_ascii=False))
            else:
                self.write(json.dumps(_success({"message": "暂无验证数据"}), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class ConvictionTimingHandler(RequestHandler):
    """时机信号"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            cv = _safe_get('conviction_validator')
            if cv is None:
                self.write(json.dumps(_error("conviction_validator 未初始化"), ensure_ascii=False))
                return
            timing = cv.get_timing_signal() if hasattr(cv, 'get_timing_signal') else None
            if timing:
                self.write(json.dumps(_success({"signal": timing[0], "confidence": timing[1]}), ensure_ascii=False))
            else:
                self.write(json.dumps(_success({"signal": "unknown", "confidence": 0}), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class ConvictionShouldAddHandler(RequestHandler):
    """是否应该加仓"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            cv = _safe_get('conviction_validator')
            if cv is None:
                self.write(json.dumps(_error("conviction_validator 未初始化"), ensure_ascii=False))
                return
            result = cv.should_add_position() if hasattr(cv, 'should_add_position') else None
            if result:
                self.write(json.dumps(_success({"should_add": result[0], "reason": result[1]}), ensure_ascii=False))
            else:
                self.write(json.dumps(_success({"should_add": False, "reason": "无数据"}), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


# ============================================================
# P1 - 持仓与跟踪
# ============================================================

class PortfolioSummaryHandler(RequestHandler):
    """持仓汇总"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            p = _safe_get('portfolio')
            if p is None:
                self.write(json.dumps(_error("portfolio 未初始化"), ensure_ascii=False))
                return
            summary = p.get_summary() if hasattr(p, 'get_summary') else None
            self.write(json.dumps(_success(_to_dict(summary)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class PositionMetricsHandler(RequestHandler):
    """持仓指标"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            pm = _safe_get('position_monitor')
            if pm is None:
                self.write(json.dumps(_error("position_monitor 未初始化"), ensure_ascii=False))
                return
            metrics = pm.get_all_metrics() if hasattr(pm, 'get_all_metrics') else []
            self.write(json.dumps(_success(_to_dict(metrics)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class TrackingHotspotHandler(RequestHandler):
    """热点信号跟踪"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            hst = _safe_get('hotspot_signal_tracker')
            if hst is None:
                self.write(json.dumps(_error("hotspot_signal_tracker 未初始化"), ensure_ascii=False))
                return
            tracked = hst.get_all_tracked() if hasattr(hst, 'get_all_tracked') else []
            self.write(json.dumps(_success(_to_dict(tracked)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class TrackingStatsHandler(RequestHandler):
    """跟踪统计"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            hst = _safe_get('hotspot_signal_tracker')
            if hst is None:
                self.write(json.dumps(_error("hotspot_signal_tracker 未初始化"), ensure_ascii=False))
                return
            stats = hst.get_stats() if hasattr(hst, 'get_stats') else {}
            self.write(json.dumps(_success(_to_dict(stats)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


# ============================================================
# P2 - 发现与融合
# ============================================================

class BlindSpotsHandler(RequestHandler):
    """盲区发现"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            bsi = _safe_get('blind_spot_investigator')
            if bsi is None:
                self.write(json.dumps(_error("blind_spot_investigator 未初始化"), ensure_ascii=False))
                return
            # 获取所有已知的盲区
            result = {}
            if hasattr(bsi, 'get_all_results'):
                result = bsi.get_all_results()
            elif hasattr(bsi, '_investigation_cache'):
                result = bsi._investigation_cache
            else:
                result = {"message": "暂无盲区数据，等待系统发现"}
            self.write(json.dumps(_success(_to_dict(result)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class FusionHandler(RequestHandler):
    """注意力融合"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            af = _safe_get('attention_fusion')
            if af is None:
                self.write(json.dumps(_error("attention_fusion 未初始化"), ensure_ascii=False))
                return
            # 获取最后一次融合结果
            result = None
            if hasattr(af, 'get_last_result'):
                result = af.get_last_result()
            elif hasattr(af, '_last_result'):
                result = af._last_result
            if result:
                self.write(json.dumps(_success(_to_dict(result)), ensure_ascii=False))
            else:
                self.write(json.dumps(_success({"message": "暂无融合数据"}), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class FocusHandler(RequestHandler):
    """关注焦点"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            fm = _safe_get('focus_manager')
            if fm is None:
                self.write(json.dumps(_error("focus_manager 未初始化"), ensure_ascii=False))
                return
            summary = fm.get_summary() if hasattr(fm, 'get_summary') else {}
            self.write(json.dumps(_success(_to_dict(summary)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class NarrativeBlockMatrixHandler(RequestHandler):
    """叙事-题材关联矩阵"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            nbl = _safe_get('narrative_block_linker')
            if nbl is None:
                self.write(json.dumps(_error("narrative_block_linker 未初始化"), ensure_ascii=False))
                return
            matrix = nbl.get_block_narrative_matrix() if hasattr(nbl, 'get_block_narrative_matrix') else {}
            self.write(json.dumps(_success(_to_dict(matrix)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


# ============================================================
# P3 - 状态与报告
# ============================================================

class AttentionReportHandler(RequestHandler):
    """注意力系统报告"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            rg = _safe_get('report_generator')
            if rg is None:
                self.write(json.dumps(_error("report_generator 未初始化"), ensure_ascii=False))
                return
            report = rg.get_current_report() if hasattr(rg, 'get_current_report') else {}
            self.write(json.dumps(_success(_to_dict(report)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class LabStatusHandler(RequestHandler):
    """实验室状态"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            tc = _safe_get('trading_center')
            if tc is None:
                self.write(json.dumps(_error("trading_center 未初始化"), ensure_ascii=False))
                return
            status = {}
            if hasattr(tc, 'get_stats'):
                status = tc.get_stats()
            elif hasattr(tc, 'get_attention_context'):
                status = tc.get_attention_context()
            self.write(json.dumps(_success(_to_dict(status)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class LiquidityHandler(RequestHandler):
    """流动性状态"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            lm = _safe_get('liquidity_manager')
            if lm is None:
                self.write(json.dumps(_error("liquidity_manager 未初始化"), ensure_ascii=False))
                return
            state = lm.get_portfolio_state() if hasattr(lm, 'get_portfolio_state') else {}
            self.write(json.dumps(_success(_to_dict(state)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class StrategyTopSymbolsHandler(RequestHandler):
    """策略权重最高股票"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            aos = _safe_get('attention_os')
            if aos is None:
                self.write(json.dumps(_error("attention_os 未初始化"), ensure_ascii=False))
                return
            sdm = aos.strategy_decision_maker if hasattr(aos, 'strategy_decision_maker') else None
            if sdm is None:
                self.write(json.dumps(_error("strategy_decision_maker 未初始化"), ensure_ascii=False))
                return
            n = int(self.get_argument("n", 20))
            symbols = sdm.get_top_symbols(n) if hasattr(sdm, 'get_top_symbols') else []
            self.write(json.dumps(_success(_to_dict(symbols)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class StrategyTopBlocksHandler(RequestHandler):
    """策略权重最高题材"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            aos = _safe_get('attention_os')
            if aos is None:
                self.write(json.dumps(_error("attention_os 未初始化"), ensure_ascii=False))
                return
            sdm = aos.strategy_decision_maker if hasattr(aos, 'strategy_decision_maker') else None
            if sdm is None:
                self.write(json.dumps(_error("strategy_decision_maker 未初始化"), ensure_ascii=False))
                return
            n = int(self.get_argument("n", 10))
            blocks = sdm.get_top_blocks(n) if hasattr(sdm, 'get_top_blocks') else []
            self.write(json.dumps(_success(_to_dict(blocks)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))


class AttentionContextHandler(RequestHandler):
    """注意力上下文（综合）"""

    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")

    def get(self):
        try:
            tc = _safe_get('trading_center')
            if tc is None:
                self.write(json.dumps(_error("trading_center 未初始化"), ensure_ascii=False))
                return
            ctx = tc.get_attention_context() if hasattr(tc, 'get_attention_context') else {}
            self.write(json.dumps(_success(_to_dict(ctx)), ensure_ascii=False))
        except Exception as e:
            self.write(json.dumps(_error(str(e)), ensure_ascii=False))
