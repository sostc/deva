"""
LLM Reflection Engine - 慢思考模块

深度反思引擎，定期从各认知模块收集数据进行深度分析。
与快思考模块（NewsMind、CrossSignalAnalyzer等）不同，慢思考：
- 定期执行（不是实时）
- 使用 LLM 进行深度分析
- 包含迭代反思（对比上次结论）
- 结合持仓情况进行战略思考

Usage:
    from deva.naja.cognition.insight.llm_reflection import get_llm_reflection_engine
    engine = get_llm_reflection_engine()
    engine.trigger_reflection()
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from deva import NB

from ...config import get_llm_config


LLM_REFLECTION_TABLE = "naja_llm_reflections"


@dataclass
class Reflection:
    id: str
    ts: float
    theme: str
    summary: str
    signals_count: int
    narratives: List[str] = field(default_factory=list)
    symbols: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)
    confidence: float = 0.5
    actionability: float = 0.5
    novelty: float = 0.5
    liquidity_structure: str = ""
    source: str = "llm_reflection"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "theme": self.theme,
            "summary": self.summary,
            "signals_count": self.signals_count,
            "narratives": self.narratives,
            "symbols": self.symbols,
            "blocks": self.blocks,
            "confidence": self.confidence,
            "actionability": self.confidence,
            "novelty": self.novelty,
            "liquidity_structure": self.liquidity_structure,
            "source": self.source,
        }


class LLMReflectionEngine:
    """LLM 反思引擎 - 定期调用 LLM 生成深度洞察

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局 LLM 反思：LLMReflectionEngine 是全局 LLM 反思引擎，所有
       LLM 反思操作都通过这个实例。如果存在多个实例，可能导致调用冲突。

    2. 状态一致性：反思历史、LLM 调用状态等需要在全系统保持一致。

    3. 生命周期：Engine 的生命周期与系统一致，随系统启动和关闭。

    4. 这是系统 LLM 反思的设计选择，不是过度工程。
    ================================================================================
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._db = NB(LLM_REFLECTION_TABLE)
        cfg = get_llm_config()

        self._enabled = bool(cfg.get("reflection_enabled", True))
        self._interval_seconds = float(cfg.get("reflection_interval_seconds", 3600))
        self._min_signals = int(cfg.get("reflection_min_signals", 5))
        self._max_signals = int(cfg.get("reflection_max_signals", 50))

        self._last_run_ts = time.time()
        self._last_success_ts = 0.0
        self._reflections_count = 0
        self._running_reflections: List[Reflection] = []

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        if self._enabled:
            self._start_timer_thread()
            self._subscribe_trading_clock()

        self._initialized = True

    def _subscribe_trading_clock(self) -> None:
        """订阅交易时钟，收盘后延迟触发反思"""
        from ...radar.trading_clock import TRADING_CLOCK_STREAM
        try:
            TRADING_CLOCK_STREAM.sink(self._on_trading_clock_event)
            import logging
            log = logging.getLogger(__name__)
            log.info("[LLMReflection] 已订阅交易时钟信号")
        except Exception:
            pass

    def _on_trading_clock_event(self, event: Dict[str, Any]) -> None:
        """处理交易时钟事件，收盘后延迟触发"""
        import logging
        log = logging.getLogger(__name__)

        if not isinstance(event, dict):
            return

        phase = event.get("phase")
        if phase != "closed":
            return

        log.info("[LLMReflection] 检测到收盘信号，延迟5分钟后启动反思...")

        def delayed_reflection():
            import time
            time.sleep(300)
            log.info("[LLMReflection] 延迟结束，开始每日反思...")
            self.run_daily_reflection()

        threading.Thread(target=delayed_reflection, daemon=True, name="post_market_reflection").start()

    def _start_timer_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._timer_loop,
            daemon=True,
            name="llm_reflection_timer",
        )
        self._thread.start()

    def _timer_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            if now - self._last_run_ts >= self._interval_seconds:
                self._run_reflection()

            self._stop_event.wait(min(30, self._interval_seconds))

    def _run_reflection(self, min_signals: int = None) -> Optional[Reflection]:
        import logging
        log = logging.getLogger(__name__)

        now = time.time()
        self._last_run_ts = now

        signals = self._collect_signals()
        portfolio = self._collect_portfolio()

        required = min_signals if min_signals is not None else self._min_signals
        if len(signals) < required:
            log.warning(f"[LLMReflection] 信号不足: 当前{len(signals)}条, 需要{required}条")
            return None

        narratives = self._collect_narratives()
        themes = self._extract_themes(signals)
        symbols = self._extract_symbols(signals)
        blocks = self._extract_blocks(signals)

        log.info(f"[LLMReflection] 开始反思: {len(signals)}个信号, {len(narratives)}个叙事, {len(themes)}个主题, 持仓{portfolio.get('count', 0)}只")
        try:
            result = self._call_llm(signals, narratives, themes, portfolio)
        except Exception as e:
            log.error(f"[LLMReflection] LLM 调用失败: {e}", exc_info=True)
            return None

        if not result:
            log.warning("[LLMReflection] LLM 返回空结果")
            return None

        log.info(f"[LLMReflection] 反思生成成功: {result.get('theme', 'N/A')}")

        reflection = Reflection(
            id=f"refl_{int(now * 1000)}",
            ts=now,
            theme=result.get("theme", "市场反思"),
            summary=result.get("summary", ""),
            signals_count=len(signals),
            narratives=narratives[:5],
            symbols=symbols[:10],
            blocks=blocks[:5],
            confidence=float(result.get("confidence", 0.5)),
            actionability=float(result.get("actionability", 0.5)),
            novelty=float(result.get("novelty", 0.5)),
            liquidity_structure=result.get("liquidity_structure", ""),
            source="llm_reflection",
        )

        self._save_reflection(reflection)
        self._last_success_ts = now
        self._reflections_count += 1

        self._emit_to_insight(reflection)

        # 反思完成后推送到钉钉
        self._push_reflection_to_dtalk(reflection, signals)

        # 同步推送到微信
        self._push_reflection_to_weixin(reflection)

        return reflection

    def _push_reflection_to_dtalk(self, reflection, signals: List[Dict[str, Any]]) -> None:
        """将 LLM 反思结果推送到钉钉"""
        try:
            from deva.endpoints import Dtalk

            # 构建消息内容
            theme = reflection.theme
            summary = reflection.summary
            
            # 如果 summary 是列表，转为字符串
            if isinstance(summary, list):
                summary_text = "；".join([str(s) for s in summary if s])
            else:
                summary_text = str(summary) if summary else "暂无"

            # 获取关键信号
            signal_parts = []
            for sig in signals[:5]:
                sig_theme = sig.get('theme', '')
                if sig_theme:
                    signal_parts.append(sig_theme)
            
            signals_text = "\n".join([f"- {s}" for s in signal_parts]) if signal_parts else "无"

            # 获取持仓信息
            portfolio = self._collect_portfolio()
            portfolio_text = portfolio.get('summary', '无持仓数据')

            # 构建 Markdown 消息
            markdown = f"""## 🤖 LLM 每日反思

**主题**: {theme}

**核心结论**:
{summary_text}

**持仓状态**: {portfolio_text}

**关键信号**:
{signals_text}

---
_反思生成时间: {datetime.fromtimestamp(reflection.ts).strftime('%Y-%m-%d %H:%M:%S')}_
"""

            dtalk_msg = f"@md@LLM每日反思|{markdown}"
            dtalk = Dtalk()
            dtalk.send(dtalk_msg)
            log.info(f"[LLMReflection] 反思已推送到钉钉: {theme}")

        except Exception as e:
            log.warning(f"[LLMReflection] 推送反思到钉钉失败: {e}")

    def _push_reflection_to_weixin(self, reflection) -> None:
        """将 LLM 反思结果推送到微信"""
        try:
            from .weixin_notifier import get_weixin_notifier

            notifier = get_weixin_notifier()
            if not notifier:
                return

            theme = reflection.theme
            summary = reflection.summary

            # summary 可能是列表，转为字符串
            if isinstance(summary, list):
                summary_text = "；".join([str(s) for s in summary if s])
            else:
                summary_text = str(summary) if summary else "暂无"

            # 持仓信息
            portfolio = self._collect_portfolio()
            portfolio_text = portfolio.get("summary", "无持仓数据")

            # 流动性结构
            liquidity = getattr(reflection, "liquidity_structure", "") or ""

            # 时间
            ts_str = datetime.fromtimestamp(reflection.ts).strftime("%Y-%m-%d %H:%M")

            text = (
                f"🤖 LLM 每日反思 | {ts_str}\n\n"
                f"📌 主题：{theme}\n\n"
                f"💡 结论：\n{summary_text}\n\n"
                f"💼 持仓：{portfolio_text}\n\n"
                f"💧 流动性：{liquidity if liquidity else '暂无判断'}"
            )

            notifier.send(text)
            import logging
            log = logging.getLogger(__name__)
            log.info(f"[LLMReflection] 反思已推送到微信")

        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.warning(f"[LLMReflection] 推送反思到微信失败: {e}")

    def _emit_liquidity_signal(self, now_ts: float) -> None:
        """将流动性结构作为独立信号推送到 InsightPool"""
        try:
            engine = SR('cognition_engine')
            tracker = engine._news_mind.narrative_tracker
            if not tracker:
                return
            liquidity = tracker.get_liquidity_structure()

            quadrants = liquidity.get("quadrants", {})
            active_quadrants = [name for name, data in quadrants.items() if data.get("stage") in ("高潮", "扩散")]

            if not active_quadrants:
                return

            themes_list = []
            for name, data in quadrants.items():
                if data.get("stage") != "无数据":
                    themes_list.append(f"{data.get('icon', '')}{name}:{data.get('stage', '')}")

            liquidity_summary = liquidity.get("conclusion", "")
            summary_text = f"美林时钟四象限: {' | '.join(themes_list)}。{liquidity_summary}"

            signal_data = {
                "theme": f"流动性结构: {', '.join(active_quadrants[:2])}",
                "summary": summary_text,
                "symbols": [],
                "blocks": ["macro", "liquidity"],
                "confidence": 0.8,
                "actionability": 0.7,
                "system_hotspot": 0.9,
                "novelty": 0.5,
                "source": "liquidity_structure",
                "signal_type": "liquidity_structure",
                "payload": {
                    "quadrants": quadrants,
                    "conclusion": liquidity.get("conclusion", ""),
                    "timestamp": liquidity.get("timestamp", now_ts),
                },
            }

            pool = SR('insight_pool')
            pool.ingest_hotspot_event(signal_data)
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.warning(f"[LLMReflection] 推送流动性信号失败: {e}")

    def _collect_signals(self) -> List[Dict[str, Any]]:
        """直接收集各认知模块的信号，不再依赖 InsightPool"""
        signals = []

        signals.extend(self._collect_narrative_signals())

        signals.extend(self._collect_tiandao_minxin_signals())

        signals.extend(self._collect_market_analysis_signals())

        signals.extend(self._collect_liquidity_signals())

        signals.extend(self._collect_attention_signals())

        signals.extend(self._collect_cross_signal_signals())

        signals.extend(self._collect_ai_compute_signals())

        signals.extend(self._collect_trade_feedback())

        signals.extend(self._collect_market_analysis_from_nt())

        signals.extend(self._collect_wisdom_signals())

        signals.extend(self._collect_merrill_clock_signals())

        return signals

    def run_daily_reflection(self, force_refresh: bool = False) -> Optional[Reflection]:
        """每日反思统一入口

        Args:
            force_refresh: 是否强制重新生成市场分析
                          - False (默认): 有现有分析就用，不重新生成
                          - True: 清空后重新生成

        自动流程：盘后任务 → 市场分析 → 反思
        手动流程：
        - force_refresh=False: 有市场分析 → 直接反思
        - force_refresh=True: 清空+重新生成分析，再反思
        """
        import logging
        log = logging.getLogger(__name__)

        log.info("[LLMReflection] 开始每日反思流程...")

        if force_refresh:
            log.info("[LLMReflection] 强制重新生成市场分析...")
            self._clear_market_analysis()
            market_analysis_result = self._generate_market_analysis()
            if not market_analysis_result:
                log.warning("[LLMReflection] 市场分析重新生成失败")
        else:
            market_analysis = self._collect_market_analysis_from_nt()
            if not market_analysis:
                log.info("[LLMReflection] 暂无市场分析，开始生成...")
                market_analysis_result = self._generate_market_analysis()
                if not market_analysis_result:
                    log.warning("[LLMReflection] 市场分析生成失败，继续使用现有数据")

        log.info("[LLMReflection] 触发LLM反思...")
        return self.trigger_now(min_signals=1)

    def _clear_market_analysis(self) -> None:
        """清空市场分析缓存"""
        try:
            from deva.naja.cognition.narrative import NarrativeTracker
            db = NarrativeTracker._get_market_analysis_db()
            db.pop("latest", None)
        except Exception:
            pass

    def _generate_market_analysis(self) -> bool:
        """生成市场分析"""
        try:
            engine = SR('cognition_engine')
            if not engine:
                return False
            tracker = engine._news_mind.narrative_tracker
            if not tracker:
                return False
            result = tracker.analyze_market_full()
            return result.get("step1_full_market", {}).get("success", False)
        except Exception:
            return False

    def _collect_market_analysis_from_nt(self) -> List[Dict[str, Any]]:
        """从 NarrativeTracker 获取全市场深度分析结果"""
        try:
            engine = SR('cognition_engine')
            tracker = engine._news_mind.narrative_tracker
            if not tracker:
                return []

            db = tracker._get_market_analysis_db()
            full_analysis = db.get("full_analysis", {})

            signals = []

            step1 = full_analysis.get("step1_full_market", {})
            if step1.get("success"):
                top_movers = step1.get("top_movers", {})
                gainers = top_movers.get("gainers", [])
                if gainers:
                    best = gainers[0]
                    signals.append({
                        "source": "market_analysis",
                        "signal_type": "market_rally",
                        "theme": f"市场领涨: {best['name']} {best['change_pct']:+.2f}%",
                        "summary": f"全市场{step1.get('stock_count')}只股票，{best['name']}领涨",
                        "score": min(1.0, abs(best['change_pct']) / 5.0),
                    })

                anomaly = step1.get("anomaly_result", {})
                if anomaly.get("anomaly_stocks"):
                    top_anomaly = anomaly["anomaly_stocks"][0]
                    signals.append({
                        "source": "market_analysis",
                        "signal_type": "anomaly",
                        "theme": f"异常波动: {top_anomaly['name']} (score={top_anomaly['score']:.3f})",
                        "summary": f"River异常检测: {top_anomaly['name']}波动异常",
                        "score": top_anomaly.get("score", 0.5),
                    })

            step2 = full_analysis.get("step2_focused", {})
            if step2.get("success"):
                holdings = step2.get("holding_analysis", {}).get("holdings", [])
                for h in holdings:
                    pnl_pct = h.get("return_pct", 0)
                    score = min(1.0, abs(pnl_pct) / 20.0)
                    signals.append({
                        "source": "market_analysis",
                        "signal_type": "holding",
                        "theme": f"持仓: {h['symbol']} {pnl_pct:+.2f}%",
                        "summary": f"{h['name']}盈亏${h.get('profit_loss', 0):+.2f}",
                        "score": score,
                    })

            return signals
        except Exception:
            return []

    def _collect_narrative_signals(self) -> List[Dict[str, Any]]:
        """从 NarrativeTracker 获取叙事信号"""
        try:
            engine = SR('cognition_engine')
            report = engine.get_memory_report()
            narratives = report.get("narratives", {})
            summary = narratives.get("summary", [])
            signals = []
            for n in summary:
                narrative = n.get("narrative", "")
                if narrative:
                    signals.append({
                        "source": "narrative_tracker",
                        "signal_type": "narrative",
                        "theme": f"叙事: {narrative}",
                        "summary": f"阶段={n.get('stage', '')}, 趋势={n.get('trend', 0):+.1%}",
                        "stage": n.get("stage", ""),
                        "trend": n.get("trend", 0),
                        "attention_score": n.get("attention_score", 0),
                        "score": n.get("attention_score", 0),
                    })
            return signals
        except Exception:
            return []

    def _collect_tiandao_minxin_signals(self) -> List[Dict[str, Any]]:
        """从 NarrativeTracker 获取天道/民心信号 - '遵循天道，驾驭民心'"""
        try:
            engine = SR('cognition_engine')
            tracker = engine._news_mind.narrative_tracker
            if not tracker:
                return []

            summary = tracker.get_value_market_summary()
            trading_signal = tracker.get_trading_signal()

            signals = []

            value_score = summary.get("value_score", 0)
            market_narrative_score = summary.get("market_narrative_score", 0)
            recommendation = summary.get("recommendation", "WATCH")

            if value_score > 0:
                signals.append({
                    "source": "tiandao_minxin",
                    "signal_type": "value_score",
                    "theme": f"价值评分(天道): {value_score:.0%}",
                    "summary": summary.get("reason", ""),
                    "score": value_score,
                    "recommendation": recommendation,
                })

            if market_narrative_score > 0:
                signals.append({
                    "source": "tiandao_minxin",
                    "signal_type": "market_narrative_score",
                    "theme": f"市场叙事评分(民心): {market_narrative_score:.0%}",
                    "summary": summary.get("market_opportunity", ""),
                    "score": market_narrative_score,
                })

            signal = trading_signal.get("signal", "WATCH")
            if signal in ("OVERSOLD", "OVERBOUGHT"):
                signals.append({
                    "source": "tiandao_minxin",
                    "signal_type": "trading_signal",
                    "theme": f"交易信号: {signal}",
                    "summary": trading_signal.get("action", ""),
                    "score": 0.8,
                })

            return signals
        except Exception:
            return []

    def _collect_market_analysis_signals(self) -> List[Dict[str, Any]]:
        """收集市场分析模块的信号：波动率、风险、流动性预测等"""
        signals = []

        signals.extend(self._collect_volatility_signals())

        signals.extend(self._collect_risk_signals())

        signals.extend(self._collect_liquidity_prediction_signals())

        signals.extend(self._collect_first_principles_signals())

        return signals

    def _collect_volatility_signals(self) -> List[Dict[str, Any]]:
        """从 VolatilitySurfaceSense 获取波动率信号"""
        try:
            from ...senses.volatility_surface import get_volatility_surface_sense
            vs = get_volatility_surface_sense()
            if not vs:
                return []
            alerts = vs.get_recent_alerts(limit=5)
            signals = []
            for alert in alerts:
                signals.append({
                    "source": "volatility_surface",
                    "signal_type": alert.signal.value,
                    "theme": f"波动率: {alert.signal.value}",
                    "summary": alert.description[:80] if alert.description else "",
                    "opportunity": alert.opportunity,
                    "intensity": alert.intensity,
                    "confidence": alert.confidence,
                    "score": alert.intensity * alert.confidence,
                })
            return signals
        except Exception:
            return []

    def _collect_risk_signals(self) -> List[Dict[str, Any]]:
        """从 RiskManager 获取风险信号"""
        try:
            from ...risk.risk_manager import get_risk_manager
            rm = get_risk_manager()
            if not rm:
                return []
            alert_summary = rm.get_alert_summary()
            signals = []
            for alert in alert_summary.get("alerts", [])[:5]:
                signals.append({
                    "source": "risk_manager",
                    "signal_type": alert.get("type", "risk"),
                    "theme": f"风险: {alert.get('type', 'unknown')}",
                    "summary": alert.get("message", "")[:80],
                    "severity": alert.get("severity", 0.5),
                    "score": alert.get("severity", 0.5),
                })
            return signals
        except Exception:
            return []

    def _collect_liquidity_prediction_signals(self) -> List[Dict[str, Any]]:
        """从 LiquidityCognition 获取流动性预测信号"""
        try:
            from ..liquidity.liquidity_cognition import get_liquidity_cognition
            lc = get_liquidity_cognition()
            if not lc:
                return []
            predictions = lc.get_active_predictions()
            signals = []
            for pred in predictions[:5]:
                signals.append({
                    "source": "liquidity_prediction",
                    "signal_type": "prediction",
                    "theme": f"预测: {pred.from_market} → {pred.to_market}",
                    "summary": f"{pred.direction} {pred.probability:.0%} ({pred.status.value})",
                    "probability": pred.probability,
                    "status": pred.status.value,
                    "score": pred.probability * 0.8,
                })
            return signals
        except Exception:
            return []

    def _collect_first_principles_signals(self) -> List[Dict[str, Any]]:
        """从 FirstPrinciplesMind 获取第一性原理分析信号"""
        try:
            from ...cognition.first_principles_mind import get_first_principles_mind
            fpm = get_first_principles_mind()
            if not fpm:
                return []
            signals = []

            causality = fpm.get_causality_summary()
            for chain in causality.get("causal_chains", [])[:3]:
                signals.append({
                    "source": "first_principles",
                    "signal_type": "causality",
                    "theme": f"因果: {chain.get('cause', '')[:30]} → {chain.get('effect', '')[:30]}",
                    "summary": chain.get("narrative", "")[:80],
                    "confidence": chain.get("confidence", 0.5),
                    "score": chain.get("confidence", 0.5),
                })

            contradiction = fpm.get_contradiction_summary()
            for c in contradiction.get("contradictions", [])[:3]:
                signals.append({
                    "source": "first_principles",
                    "signal_type": "contradiction",
                    "theme": f"矛盾: {c.get('type', '')}",
                    "summary": c.get("description", "")[:80],
                    "severity": c.get("severity", 0.5),
                    "score": c.get("severity", 0.5),
                })

            return signals
        except Exception:
            return []

    def _collect_liquidity_signals(self) -> List[Dict[str, Any]]:
        """从 LiquidityCognition 获取流动性洞察"""
        from ..liquidity.liquidity_cognition import get_liquidity_cognition
        try:
            lc = get_liquidity_cognition()
            if not lc:
                return []
            insights = lc.get_recent_insights(limit=5)
            signals = []
            for insight in insights:
                if isinstance(insight, dict):
                    signals.append({
                        "source": "liquidity_cognition",
                        "signal_type": insight.get("insight_type", "liquidity"),
                        "theme": f"流动性: {insight.get('narrative', '')}",
                        "summary": f"{insight.get('source_market', '')} → {insight.get('target_markets', [])}",
                        "confidence": insight.get("propagation_probability", 0.5),
                        "severity": insight.get("severity", 0.5),
                        "score": insight.get("severity", 0.5),
                    })
            return signals
        except Exception:
            return []

    def _collect_attention_signals(self) -> List[Dict[str, Any]]:
        """从 MarketHotspotHistoryTracker 获取注意力转移信号"""
        from deva.naja.market_hotspot.market_hotspot_history_tracker import get_history_tracker
        try:
            tracker = get_history_tracker()
            if not tracker:
                return []
            report = tracker.get_hotspot_shift_report(emit_to_insight=False)
            if not report.get("has_shift"):
                return []
            signals = []
            for block, name in report.get("added_blocks", report.get("added_blocks", [])):
                signals.append({
                    "source": "attention_history",
                    "signal_type": "attention_rising",
                    "theme": f"注意力上升: {name}",
                    "summary": "题材进入热门",
                    "block": block,
                    "score": 0.7,
                })
            for block, name in report.get("removed_blocks", report.get("removed_blocks", [])):
                signals.append({
                    "source": "attention_history",
                    "signal_type": "attention_falling",
                    "theme": f"注意力下降: {name}",
                    "summary": "题材退出热门",
                    "block": block,
                    "score": 0.6,
                })
            return signals
        except Exception:
            return []

    def _collect_cross_signal_signals(self) -> List[Dict[str, Any]]:
        """从 CrossSignalAnalyzer 获取共振信号"""
        from ..cross_signal_analyzer import get_cross_signal_analyzer
        try:
            analyzer = get_cross_signal_analyzer()
            if not analyzer:
                return []
            resonances = analyzer.get_recent_resonances(n=5)
            signals = []
            for r in resonances:
                if isinstance(r, dict):
                    signals.append({
                        "source": "cross_signal",
                        "signal_type": r.get("resonance_type", "共振"),
                        "theme": f"共振: {r.get('block_name', '')}",
                        "summary": f"共振强度={r.get('resonance_score', 0):.2f}",
                        "resonance_score": r.get("resonance_score", 0),
                        "score": r.get("resonance_score", 0) * 0.8,
                    })
            return signals
        except Exception:
            return []

    def _collect_ai_compute_signals(self) -> List[Dict[str, Any]]:
        """从 OpenRouterMonitor 获取 AI算力趋势"""
        try:
            from ...cognition.openrouter_monitor import get_ai_compute_trend
            trend = get_ai_compute_trend()
            if not trend:
                return []
            return [{
                "source": "ai_compute",
                "signal_type": "ai_compute_trend",
                "theme": f"AI算力: {trend.get('trend_direction', 'unknown')}",
                "summary": f"累计增长={trend.get('cumulative_growth', 0):.1%}, 本周={trend.get('weekly_growth', 0):+.1%}",
                "cumulative_growth": trend.get("cumulative_growth", 0),
                "trend_direction": trend.get("trend_direction", "unknown"),
                "score": trend.get("base_strength", 0.5),
            }]
        except Exception:
            return []

    def _collect_trade_feedback(self) -> List[Dict[str, Any]]:
        """获取交易反馈信号"""
        try:
            from deva.naja.attention.trading_center import get_trading_center
            tc = get_trading_center()
            os = tc.get_attention_os()
            scheduler = os.market_scheduler
            recent_symbols = list(scheduler._symbol_weights.keys())[:5]
            signals = []
            for sym in recent_symbols:
                signals.append({
                    "source": "trade_feedback",
                    "signal_type": "trade",
                    "theme": f"交易: {sym}",
                    "summary": "",
                    "success": True,
                    "score": 0.5,
                })
            return signals
        except Exception:
            return []

    def _collect_wisdom_signals(self) -> List[Dict[str, Any]]:
        """收集 WisdomRetriever 的检索效果信号，用于优化知识库检索"""
        try:
            from ...wisdom.wisdom_retriever import WisdomRetriever

            retriever = WisdomRetriever()
            stats = retriever.get_stats()

            signals = []

            trigger_count = stats.get("trigger_count", 0)
            if trigger_count > 0:
                last_query = stats.get("last_query", "")
                last_snippet = stats.get("last_best_snippet", "")
                last_focus = stats.get("last_focus", "")
                last_bias = stats.get("last_bias", "")
                last_time = stats.get("last_trigger_time")

                signals.append({
                    "source": "wisdom_retriever",
                    "signal_type": "wisdom_retrieval",
                    "theme": f"知识检索: {last_focus}/{last_bias}",
                    "summary": f"触发{trigger_count}次 | 查询:'{last_query}' | 片段:{last_snippet[:50]}..." if last_snippet else f"触发{trigger_count}次 | 查询:'{last_query}'",
                    "trigger_count": trigger_count,
                    "last_query": last_query,
                    "last_focus": last_focus,
                    "last_bias": last_bias,
                    "last_time": last_time,
                    "score": min(1.0, trigger_count / 10.0),
                })

                return signals
            return []
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.debug(f"[LLMReflection] 收集 wisdom 信号失败: {e}")
            return []

    def _collect_merrill_clock_signals(self) -> List[Dict[str, Any]]:
        """收集美林时钟的真实周期数据"""
        try:
            from deva.naja.cognition.merrill_clock import (
                get_merrill_phase_display,
                get_merrill_macro_signal,
                get_merrill_clock_engine,
                MerrillClockPhase,
            )

            clock = get_merrill_clock_engine()
            signal = clock.get_current_signal()

            if not signal:
                return []

            phase_name = get_merrill_phase_display(signal.phase)
            macro_signal = get_merrill_macro_signal(
                phase=signal.phase,
                confidence=signal.confidence,
            )

            # 阶段 emoji
            phase_emoji = {
                MerrillClockPhase.RECOVERY: "🌱",
                MerrillClockPhase.OVERHEAT: "🔥",
                MerrillClockPhase.STAGFLATION: "⚠️",
                MerrillClockPhase.RECESSION: "🥶",
            }.get(signal.phase, "❓")

            # 资产配置排名
            asset_ranking = " > ".join(signal.asset_ranking) if signal.asset_ranking else "无数据"

            return [{
                "source": "merrill_clock",
                "signal_type": "merrill_clock_phase",
                "theme": f"美林时钟: {phase_name}",
                "summary": "{} 当前周期：{}（置信度{}%）\n增长评分: {:.2f} | 通胀评分: {:.2f}\nManas宏观信号: {:.2f} | 资产配置: {}".format(
                    phase_emoji, phase_name, int(signal.confidence * 100),
                    signal.growth_score, signal.inflation_score,
                    macro_signal, asset_ranking
                ),
                "phase": signal.phase.value,
                "phase_name": phase_name,
                "confidence": signal.confidence,
                "growth_score": signal.growth_score,
                "inflation_score": signal.inflation_score,
                "macro_signal": macro_signal,
                "asset_ranking": signal.asset_ranking,
                "score": signal.confidence,
                "ts": time.time(),
            }]
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.warning(f"[LLMReflection] 收集美林时钟信号失败: {e}", exc_info=True)
            return []

    def _collect_portfolio(self) -> Dict[str, Any]:
        """收集当前持仓信息"""
        try:
            from ...bandit.portfolio_manager import get_portfolio_manager
            pm = get_portfolio_manager()
            if not pm:
                return {"positions": [], "summary": "无持仓系统"}

            us_portfolio = pm.get_us_portfolio("default")
            if not us_portfolio:
                return {"positions": [], "summary": "无美股持仓"}

            open_positions = us_portfolio.get_all_positions("OPEN")
            if not open_positions:
                return {"positions": [], "summary": "无持仓"}

            positions = []
            total_pnl = 0
            for pos in open_positions:
                pnl = pos.profit_loss or 0
                total_pnl += pnl
                positions.append({
                    "symbol": pos.stock_code,
                    "name": pos.stock_name,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "profit_loss": pnl,
                    "return_pct": pos.return_pct or 0,
                })

            return {
                "positions": positions,
                "count": len(positions),
                "total_profit_loss": total_pnl,
                "summary": f"持仓{len(positions)}只, 总盈亏={total_pnl:+.2f}"
            }
        except Exception:
            return {"positions": [], "summary": "获取持仓失败"}

    def _collect_narratives(self) -> List[Dict[str, Any]]:
        """收集叙事数据，包含趋势和阶段信息"""

        try:
            engine = SR('cognition_engine')
            report = engine.get_memory_report()
            narratives = report.get("narratives", {})
            summary = narratives.get("summary", [])
            result = []
            for n in summary:
                narrative = n.get("narrative", "")
                if narrative:
                    result.append({
                        "narrative": narrative,
                        "stage": n.get("stage", "萌芽"),
                        "trend": n.get("trend", 0),
                        "attention_score": n.get("attention_score", 0),
                        "recent_count": n.get("recent_count", 0),
                    })
            return result
        except Exception:
            return []

    def _extract_themes(self, signals: List[Dict[str, Any]]) -> List[str]:
        themes = []
        for sig in signals:
            theme = sig.get("theme", "")
            if theme and theme not in themes:
                themes.append(theme)
        return themes[:10]

    def _extract_symbols(self, signals: List[Dict[str, Any]]) -> List[str]:
        symbols = set()
        for sig in signals:
            for s in sig.get("symbols", []):
                symbols.add(str(s))
        return list(symbols)[:20]

    def _extract_blocks(self, signals: List[Dict[str, Any]]) -> List[str]:
        blocks = set()
        for sig in signals:
            for b in sig.get("blocks", []) or sig.get("blocks", []):
                blocks.add(str(b))
        return list(blocks)[:10]

    def _categorize_signals(self, signals: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
        """按来源分类信号"""
        categories = {
            "radar": [],      # 雷达事件 (pattern, drift, anomaly, block_anomaly, news_topic)
            "attention": [],  # 注意力事件 (global_attention_shift, market_state_shift, block_hotspot等)
            "cross_signal": [],  # 共振信号
            "feedback": [],   # 实验反馈 (experiment_feedback_summary, bandit_learning_analysis)
            "effectiveness": [],  # 有效性分析 (effective_pattern, ineffective_pattern)
            "llm_reflection": [],  # 之前的反思
            "liquidity_structure": [],  # 流动性结构信号
            "wisdom": [],     # 知识库检索信号
            "other": []       # 其他
        }

        radar_types = {'pattern', 'drift', 'anomaly', 'block_anomaly', 'news_topic'}
        attention_types = {'global_attention_shift', 'market_activity_shift', 'block_concentration_shift', 'block_concentration_shift',
                          'block_hotspot', 'symbol_attention_change', 'market_state_shift'}
        feedback_types = {'experiment_feedback_summary', 'bandit_learning_analysis'}
        effectiveness_types = {'effective_pattern', 'ineffective_pattern'}
        liquidity_types = {'liquidity_structure'}
        wisdom_types = {'wisdom_retrieval'}

        for sig in signals:
            source = sig.get('source', '')
            signal_type = sig.get('signal_type', '')

            if signal_type in liquidity_types or source == 'liquidity_structure':
                categories['liquidity_structure'].append(sig)
            elif source == 'wisdom_retriever' or signal_type in wisdom_types:
                categories['wisdom'].append(sig)
            elif source in ('market', 'radar', 'radar_news') or signal_type in radar_types:
                categories['radar'].append(sig)
            elif source == 'cross_signal' or 'resonance' in signal_type:
                categories['cross_signal'].append(sig)
            elif source == 'attention' or signal_type in attention_types:
                categories['attention'].append(sig)
            elif source == 'feedback_experiment' or signal_type in feedback_types:
                categories['feedback'].append(sig)
            elif source == 'attention_effectiveness' or signal_type in effectiveness_types:
                categories['effectiveness'].append(sig)
            elif source.startswith('llm_reflection') or signal_type == 'llm_reflection':
                categories['llm_reflection'].append(sig)
            else:
                categories['other'].append(sig)

        for cat in categories:
            categories[cat].sort(key=lambda x: x.get('ts', x.get('timestamp', 0)), reverse=True)

        return categories

    @staticmethod
    def _format_ts(ts: float) -> str:
        """格式化时间戳为可读时间"""
        from datetime import datetime
        if not ts:
            return ""
        dt = datetime.fromtimestamp(ts)
        now = datetime.now()
        diff = (now - dt).total_seconds()
        if diff < 60:
            return "刚刚"
        elif diff < 3600:
            return f"{int(diff // 60)}分钟前"
        elif diff < 86400:
            return f"{int(diff // 3600)}小时前"
        else:
            return dt.strftime("%m-%d %H:%M")

    def _format_signal_for_prompt(self, sig: Dict[str, Any], max_len: int = 80) -> str:
        """格式化单个信号为可读文本"""
        ts = sig.get('ts', sig.get('timestamp', 0))
        time_str = self._format_ts(ts)

        theme = sig.get('theme', '-')[:35]
        summary = sig.get('summary', '')
        if isinstance(summary, dict):
            summary = str(summary)[:max_len]
        elif isinstance(summary, str) and summary.startswith('{'):
            try:
                import ast
                parsed = ast.literal_eval(summary)
                if isinstance(parsed, dict):
                    parts = [f"{k}={v}" for k, v in list(parsed.items())[:3] if isinstance(v, (int, float, str)) and len(str(v)) < 30]
                    summary = ' | '.join(parts) if parts else str(parsed)[:max_len]
                else:
                    summary = str(summary)[:max_len]
            except Exception:
                summary = summary[:max_len]
        else:
            summary = str(summary)[:max_len] if summary else ''

        source = sig.get('source', '')
        signal_type = sig.get('signal_type', '')
        score = sig.get('system_attention', sig.get('score', 0))

        time_prefix = f"[{time_str}]" if time_str else ""
        return f"{time_prefix}[{source}/{signal_type}]({score:.2f}) {theme}: {summary}"

    async def _call_llm_async(
        self,
        signals: List[Dict[str, Any]],
        narratives: List[Dict[str, Any]],
        themes: List[str],
        portfolio: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        cfg = get_llm_config()

        recent_reflections = self.get_recent_reflections(limit=1)
        last_reflection = recent_reflections[0] if recent_reflections else None

        prompt = self._build_reflection_prompt(signals, narratives, themes, portfolio, last_reflection)
        import logging
        log = logging.getLogger(__name__)
        log.info(f"[LLMReflection] Prompt长度: {len(prompt)} 字符, 上次反思: {'有' if last_reflection else '无'}")

        try:
            from deva.llm import GPT
            model_type = cfg.get("model_type", "deepseek")
            gpt = GPT(model_type=model_type)
            log.info(f"[LLMReflection] 使用模型: {model_type}, API配置: base_url={gpt.base_url}, model={gpt.model}")
            response = await gpt.async_query(prompt)
        except Exception as e:
            log.error(f"[LLMReflection] LLM调用异常: {e}")
            raise RuntimeError(f"LLM 调用失败: {e}") from e

        return self._parse_llm_response(response)

    def _call_llm(self, signals, narratives, themes, portfolio) -> Optional[Dict[str, Any]]:
        import logging
        log = logging.getLogger(__name__)
        try:
            import asyncio
            import concurrent.futures

            async def call_async():
                return await self._call_llm_async(signals, narratives, themes, portfolio)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                def run_in_new_loop():
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(call_async())
                        finally:
                            new_loop.close()
                    except Exception as e:
                        log.error(f"[LLMReflection] ThreadPool中的LLM调用失败: {e}")
                        return None

                future = executor.submit(run_in_new_loop)
                result = future.result(timeout=120)
                if result is None:
                    return None
                return result
        except Exception as e:
            log.error(f"[LLMReflection] Sync call failed: {e}", exc_info=True)
            return None

    def _build_reflection_prompt(
        self,
        signals: List[Dict[str, Any]],
        narratives: List[Dict[str, Any]],
        themes: List[str],
        portfolio: Dict[str, Any],
        last_reflection: Optional[Dict[str, Any]] = None,
    ) -> str:
        categorized = self._categorize_signals(signals)

        def _format_time_line(signals_list: List[Dict], max_items: int = 8) -> str:
            if not signals_list:
                return "暂无"
            lines = []
            for s in signals_list[:max_items]:
                ts = s.get('ts', s.get('timestamp', 0))
                time_str = self._format_ts(ts)
                signal_type = s.get('signal_type', '')
                theme = s.get('theme', '-')[:25]
                score = s.get('system_attention', s.get('score', 0))
                lines.append(f"{time_str} | {signal_type} | {theme} | 分数{score:.2f}")
            return "\n".join(lines)

        radar_text = _format_time_line(categorized['radar'], 6)
        attention_text = _format_time_line(categorized['attention'], 6)
        cross_text = _format_time_line(categorized['cross_signal'], 4)
        feedback_text = _format_time_line(categorized.get('feedback', []), 3)
        effectiveness_text = _format_time_line(categorized.get('effectiveness', []), 3)
        liquidity_signals = _format_time_line(categorized.get('liquidity_structure', []), 3)
        other_text = _format_time_line(categorized.get('other', []), 4)

        def _format_narrative(n: Dict[str, Any]) -> str:
            narrative = n.get('narrative', '-')
            stage = n.get('stage', '萌芽')
            trend = n.get('trend', 0)
            ts = n.get('last_updated', 0)
            time_str = self._format_ts(ts) if ts else ""
            trend_icon = "📈" if trend > 0.3 else "📉" if trend < -0.3 else "➡️"
            trend_str = f"{trend:+.1%}" if isinstance(trend, float) else str(trend)
            time_prefix = f"[{time_str}]" if time_str else ""
            return f"{time_prefix}{narrative} [{stage}{trend_icon}{trend_str}]"

        narratives_text = "\n".join([_format_narrative(n) for n in narratives[:8]]) if narratives else "暂无叙事数据"

        narratives_active = [n for n in narratives if n.get('stage') in ('高潮', '扩散')] if narratives else []
        narratives_fading = [n for n in narratives if n.get('stage') in ('消退', '萌芽')] if narratives else []

        themes_text = "\n".join([f"- {t}" for t in themes[:10]]) if themes else "暂无主题"

        total_signals = len(signals)
        earliest_ts = min([s.get('ts', s.get('timestamp', 0)) for s in signals] or [0])
        latest_ts = max([s.get('ts', s.get('timestamp', 0)) for s in signals] or [0])
        time_range = f"{self._format_ts(earliest_ts)} ~ {self._format_ts(latest_ts)}" if earliest_ts and latest_ts else "时间范围未知"

        last_reflection_section = ""
        if last_reflection:
            last_theme = last_reflection.get('theme', '未知')
            last_summary = last_reflection.get('summary', '无')
            last_liquidity = last_reflection.get('liquidity_structure', '未知')
            last_confidence = last_reflection.get('confidence', 0)
            last_ts = last_reflection.get('ts', 0)
            last_time_str = self._format_ts(last_ts) if last_ts else "未知时间"
            last_reflection_section = f"""## 📝 上次反思结论（{last_time_str}）
**主题**: {last_theme}
**流动性结构**: {last_liquidity}
**反思内容**: {last_summary[:300]}...
**置信度**: {last_confidence:.0%}

请重点思考：
1. 上述结论与当前新数据是否吻合？
2. 如果有新变化，是偶然波动还是趋势转折？
3. 如果没有新变化，当前叙事是否得到强化？
4. 流动性结构判断是否需要调整？
"""
        else:
            last_reflection_section = "## 📝 上次反思结论\n暂无历史反思，这是首次反思。"

        def _format_portfolio(p: Dict[str, Any]) -> str:
            positions = p.get('positions', [])
            if not positions:
                return "当前无持仓"
            lines = []
            for pos in positions:
                symbol = pos.get('symbol', '')
                name = pos.get('name', '')
                ret_pct = pos.get('return_pct', 0)
                pnl = pos.get('profit_loss', 0)
                ret_icon = "📈" if ret_pct >= 0 else "📉"
                lines.append(f"{ret_icon}{symbol}({name}): {ret_pct:+.1%} ({pnl:+.2f})")
            return "\n".join(lines)

        portfolio_section = f"""## 💼 当前持仓情况
{_format_portfolio(portfolio)}

请结合持仓情况思考：
1. 当前市场信号对持仓有何影响？
2. 是否需要调整持仓？
3. 持仓盈亏是否影响决策心态？
""" if portfolio.get('positions') else "## 💼 当前持仓情况\n暂无持仓信息"

        return f"""你是资深金融市场分析师。请基于多源异构数据进行深度市场反思。

## ⏱️ 数据时间范围
数据覆盖: {time_range}
总信号数: {total_signals}

{last_reflection_section}

{portfolio_section}

## 💰 流动性结构分析（美林时钟四象限）
{liquidity_signals if liquidity_signals and liquidity_signals != "暂无" else "暂无流动性信号"}

请根据流动性信号判断当前流动性结构：
- 股票市场活跃 → 资金风险偏好高，经济复苏期
- 债券市场活跃 → 资金避险，经济可能衰退
- 大宗商品活跃 → 通胀预期，经济过热
- 现金与货币活跃 + 流动性紧张 → 资金观望，紧张情绪

## 📊 叙事变化趋势（按时间排序）
{narratives_text}
### 重点叙事
{" | ".join([f"{n['narrative']}({n['stage']})" for n in narratives_active[:3]]) if narratives_active else "无明显活跃叙事"}
{" | ".join([f"{n['narrative']}({n['stage']})" for n in narratives_fading[:3]]) if narratives_fading else "无消退叙事"}

## 📡 雷达事件（市场异常检测）
{radar_text}

## 👁️ 注意力事件（市场关注度变化）
{attention_text}

## 🔄 共振信号（新闻与注意力共振）
{cross_text}

## 📊 实验反馈（注意力系统学习结果）
{feedback_text}

## ✅ 有效性分析（哪些模式有效/无效）
{effectiveness_text}

## 📋 其他信号
{other_text}

## 核心主题
{themes_text}

## 反思要求

**迭代分析思路**：
1. 先回顾上次反思的结论，判断当前新数据是否验证/否定/补充了旧结论
2. 如果上次结论被验证 → 分析强化因素，关注是否有新变化
3. 如果上次结论被否定 → 找出转折点，理解变化原因
4. 如果上次结论被补充 → 识别新维度，理解叙事演进
5. 结合持仓情况，判断当前策略是否需要调整

请生成深度市场反思，要求：
1. **迭代性**：明确说明当前数据如何验证/否定/补充了上次的结论
2. 重点分析叙事变化趋势，判断哪些叙事正在升温/消退
3. 重点分析流动性结构（美林时钟四象限），判断资金流向
4. 结合时间线，分析事件发生的先后顺序和因果关系
5. 结合雷达异常和注意力事件，验证叙事变化的真实性
6. 评估共振信号与叙事趋势的匹配度
7. 结合实验反馈和有效性分析，判断当前策略的有效性
8. **结合持仓情况**，给出持仓调整建议
9. 给出形势判断（2-3句话，包含流动性结构结论）和可执行建议

仅返回 JSON 格式：
{{
    "theme": "反思主题（一句话，精炼，包含流动性结构判断）",
    "summary": "深度反思内容（150-300字，包含流动性结构分析、叙事趋势判断、与上次结论的迭代关系、持仓分析和可执行建议）",
    "confidence": 0.0-1.0（判断置信度，基于信号数量和质量），
    "actionability": 0.0-1.0（可执行性，结论是否可直接指导行动），
    "novelty": 0.0-1.0（新颖程度，相比历史反思是否有新发现），
    "liquidity_structure": "当前流动性结构判断（如：股市>债券>商品，资金风险偏好回升）",
    "iteration": "与上次结论的关系（验证/否定/补充/无新数据）",
    "上次结论回顾": "简要回顾上次反思的核心结论，用于对比",
    "portfolio_advice": "持仓调整建议（如：持有/加仓/减仓/止损，具体到个股）"
}}

只返回 JSON，不要其他内容。"""

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        if not response:
            return None

        try:
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                for i, line in enumerate(lines):
                    if line.strip().startswith("```"):
                        lines[i] = ""
                    elif i > 0 and lines[i - 1].strip().startswith("```"):
                        lines[i] = ""
                response = "\n".join(lines).strip()

            for marker in ["```json", "```JSON", "```"]:
                if marker in response:
                    parts = response.split(marker)
                    for part in parts:
                        part = part.strip()
                        if part.startswith("{") or part.startswith("["):
                            response = part
                            break

            data = json.loads(response)
            if not isinstance(data, dict):
                return None

            return {
                "theme": str(data.get("theme", "市场反思")),
                "summary": str(data.get("summary", "")),
                "confidence": float(data.get("confidence", 0.5)),
                "actionability": float(data.get("actionability", 0.5)),
                "novelty": float(data.get("novelty", 0.5)),
                "liquidity_structure": str(data.get("liquidity_structure", "")),
                "iteration": str(data.get("iteration", "")),
                "上次结论回顾": str(data.get("上次结论回顾", "")),
            }
        except json.JSONDecodeError as e:
            log.warning(f"[LLMReflection] JSON 解析失败: {e}, response: {response[:200]}")
            return None

    def _save_reflection(self, reflection: Reflection) -> None:
        try:
            self._db[reflection.id] = reflection.to_dict()
        except Exception:
            pass

    def _emit_to_insight(self, reflection: Reflection) -> None:

        try:
            pool = SR('insight_pool')
            insight_data = {
                "theme": reflection.theme,
                "summary": reflection.summary,
                "symbols": reflection.symbols,
                "blocks": reflection.blocks,
                "confidence": reflection.confidence,
                "actionability": reflection.actionability,
                "system_attention": reflection.novelty,
                "novelty": reflection.novelty,
                "liquidity_structure": reflection.liquidity_structure,
                "source": f"llm_reflection:{reflection.id}",
                "signal_type": "llm_reflection",
                "payload": reflection.to_dict(),
            }
            pool.ingest_hotspot_event(insight_data)
        except Exception as e:
            log.error(f"[LLMReflection] 推送到洞察池失败: {e}")

    def trigger_now(self, min_signals: int = 1) -> Optional[Reflection]:
        """手动触发一次反思

        Args:
            min_signals: 最少需要的信号数，默认1（手动触发时降低要求）
        """
        return self._run_reflection(min_signals=min_signals)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "interval_seconds": self._interval_seconds,
            "last_run_ts": self._last_run_ts,
            "last_success_ts": self._last_success_ts,
            "reflections_count": self._reflections_count,
            "pending_signals": len(self._collect_signals()),
        }

    def get_recent_reflections(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            items = list(self._db.items())
            items.sort(key=lambda x: float(x[1].get("ts", 0)) if isinstance(x[1], dict) else 0, reverse=True)
            return [item[1] for item in items[:limit] if isinstance(item[1], dict)]
        except Exception:
            return []

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)


_llm_reflection_engine: Optional[LLMReflectionEngine] = None
_llm_reflection_lock = threading.Lock()


def get_llm_reflection_engine() -> LLMReflectionEngine:
    from deva.naja.register import SR
    return SR('llm_reflection_engine')
