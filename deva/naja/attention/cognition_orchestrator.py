"""
CognitionOrchestrator - 认知协调模块

职责：
- 认知上下文获取
- 认知反馈应用
- 信号调整

从 AttentionOrchestrator 拆分出来
"""

import logging
from typing import Dict, Any, List, Optional
import pandas as pd

log = logging.getLogger(__name__)


def _lab_debug_log(msg: str):
    """调试日志"""
    log.debug(f"[CognitionOrchestrator] {msg}")


class CognitionOrchestrator:
    """
    认知协调器

    负责：
    - 获取认知系统上下文
    - 应用认知反馈到信号
    - 第一性原理思维协调
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            import threading
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._init_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        with self._init_lock:
            if getattr(self, '_initialized', False):
                return
            self._ensure_initialized()

    def _ensure_initialized(self):
        """初始化"""
        self._awakened_state = {
            "last_fp_result": None,
            "last_recalled_patterns": [],
        }
        self._initialized = True
        log.info("CognitionOrchestrator 初始化完成")

    def _get_cognition_context(self) -> Dict[str, Any]:
        """
        获取认知系统上下文（快思考）
        """
        context = {
            "narratives": [],
            "market_sentiment": "neutral",
            "market_sentiment_confidence": 0.3,
            "sector_resonances": {},
            "topic_signals": [],
            "liquidity_predictions": {},
            "global_liquidity_summary": {},
            "recent_reflections": [],
            "latest_reflection": {},
            "ai_compute_trend": None,
            "ai_positions": {},
            "attention_shift": {},
        }

        # ========== SectorNarrative (地：叙事追踪) ==========
        try:
            from deva.naja.cognition.narrative import NarrativeTracker
            tracker = NarrativeTracker()
            narrative_summary = tracker.get_summary(limit=10)
            if narrative_summary:
                context["narratives"] = [
                    {
                        "narrative": s.get("narrative", ""),
                        "stage": s.get("stage", "unknown"),
                        "attention_score": s.get("attention_score", 0.5),
                        "trend": s.get("trend", 0),
                        "keywords": s.get("keywords", []),
                    }
                    for s in narrative_summary
                ]
                log.debug(f"[Cognition] 获取 narratives: {len(context['narratives'])} 条")
        except Exception as e:
            log.debug(f"[Cognition] 获取 narratives 失败: {e}")

        # ========== LLMReflection (慢思考) ==========
        try:
            from deva.naja.cognition.insight.llm_reflection import get_llm_reflection_engine
            reflection_engine = get_llm_reflection_engine()
            if reflection_engine:
                recent_reflections = reflection_engine.get_recent_reflections(limit=3)
                if recent_reflections:
                    context["recent_reflections"] = recent_reflections
                    context["latest_reflection"] = recent_reflections[0] if recent_reflections else {}
                    log.debug(f"[Cognition] 获取 recent_reflections: {len(context['recent_reflections'])} 条")
        except Exception as e:
            log.debug(f"[Cognition] 获取 recent_reflections 失败: {e}")

        # ========== CrossSignalAnalyzer (共振检测) ==========
        try:
            from deva.naja.cognition.cross_signal_analyzer import get_cross_signal_analyzer
            analyzer = get_cross_signal_analyzer()
            if analyzer:
                sector_resonances = analyzer.get_sector_resonances()
                if sector_resonances:
                    context["sector_resonances"] = sector_resonances
                    log.debug(f"[Cognition] 获取 sector_resonances: {len(sector_resonances)} 条")
        except Exception as e:
            log.debug(f"[Cognition] 获取 sector_resonances 失败: {e}")

        # ========== AI算力趋势 ==========
        try:
            from deva.naja.cognition.keyword_registry import KeywordRegistry
            registry = KeywordRegistry()
            ai_compute_trend = registry.get_ai_compute_trend()
            if ai_compute_trend:
                context["ai_compute_trend"] = ai_compute_trend
        except Exception:
            pass

        return context

    def _get_problem_opportunity_context(self) -> Optional[Dict[str, Any]]:
        """获取问题-机会-解决者上下文"""
        try:
            from deva.naja.cognition.keyword_registry import KeywordRegistry
            registry = KeywordRegistry()
            return registry.get_problem_opportunity_context()
        except Exception:
            return None

    def _apply_cognition_to_signals(self, signals: List[Any], data: pd.DataFrame) -> List[Any]:
        """
        应用认知系统分析结果到信号

        快思考：
        1. NewsMind - 新闻情绪 → 调整置信度
        2. CrossSignalAnalyzer - 板块共振 → 调整仓位
        3. LiquidityCognition - 流动性预测 → 调整频率
        4. AI算力趋势 → 调整AI相关仓位

        慢思考：
        5. LLMReflection - 高置信度洞察 → 大幅调整
        """
        if not signals:
            return signals

        try:
            cognition_context = self._get_cognition_context()

            narratives = cognition_context.get("narratives", [])
            latest_reflection = cognition_context.get("latest_reflection", {})
            has_high_conf_insight = latest_reflection.get("confidence", 0) > 0.7

            sentiment = cognition_context.get("market_sentiment", "neutral")
            sentiment_conf = cognition_context.get("market_sentiment_confidence", 0.3)

            sector_resonances = cognition_context.get("sector_resonances", {})
            ai_compute_trend = cognition_context.get("ai_compute_trend")

            for signal in signals:
                symbol = getattr(signal, 'symbol', None) or getattr(signal, 'stock_code', None)
                if not symbol:
                    continue

                signal.metadata = signal.metadata or {}

                if sentiment != "neutral" and sentiment_conf > 0.5:
                    if sentiment == "bullish":
                        signal.confidence = min(1.0, signal.confidence + 0.05 * sentiment_conf)
                    elif sentiment == "fearful":
                        signal.confidence = max(0.0, signal.confidence - 0.08 * sentiment_conf)

                if sector_resonances:
                    symbol_sector = self._get_symbol_sector(symbol, data)
                    if symbol_sector and symbol_sector in sector_resonances:
                        resonance = sector_resonances[symbol_sector]
                        resonance_strength = resonance.get("resonance_strength", 0)
                        if resonance_strength > 0.7:
                            signal.metadata["sector_resonance"] = resonance_strength
                            signal.confidence = min(1.0, signal.confidence + 0.05)

                if ai_compute_trend and symbol in ["NVDA", "AMD", "INTC", "TSLA", "AAPL"]:
                    trend_direction = ai_compute_trend.get("trend_direction", "neutral")
                    cumulative_growth = ai_compute_trend.get("cumulative_growth", 0)
                    if trend_direction == "rising" and cumulative_growth > 1.0:
                        signal.confidence = min(1.0, signal.confidence + 0.05)

                if narratives:
                    signal.metadata["narratives"] = [
                        n.get("narrative", "") for n in narratives[:3]
                    ]

                if has_high_conf_insight:
                    signal.metadata["high_conf_cognition"] = True

            return signals

        except Exception as e:
            log.warning(f"[Cognition] 应用认知到信号失败: {e}")
            return signals

    def _get_symbol_sector(self, symbol: str, data: pd.DataFrame) -> Optional[str]:
        """获取股票所属板块"""
        try:
            if 'code' in data.columns and 'block' in data.columns:
                match = data[data['code'] == symbol]
                if not match.empty:
                    return str(match.iloc[0]['block'])
        except Exception:
            pass
        return None

    def _notify_cognition(self):
        """通知认知系统更新"""
        try:
            from deva.naja.cognition.narrative import NarrativeTracker
            tracker = NarrativeTracker()
            tracker.tick()
        except Exception as e:
            log.debug(f"[Cognition] 通知认知系统失败: {e}")

    def _trigger_llm_analysis(self):
        """触发 LLM 分析"""
        try:
            from deva.naja.cognition.insight.llm_reflection import get_llm_reflection_engine
            engine = get_llm_reflection_engine()
            if engine:
                pass
        except Exception as e:
            log.debug(f"[Cognition] 触发LLM分析失败: {e}")

    def _apply_cognition_feedback(self, feedback):
        """应用认知反馈"""
        pass

    def _record_signal_outcome(self, symbol: str, signal_type: str, entry_price: float, outcome: Optional[float] = None, success: Optional[bool] = None):
        """记录信号结果"""
        try:
            from deva.naja.cognition.insight.insight_pool import get_insight_pool
            pool = get_insight_pool()
            if pool:
                pool.record_signal_outcome(symbol, signal_type, entry_price, outcome, success)
        except Exception as e:
            log.debug(f"[Cognition] 记录信号结果失败: {e}")

    def update_awakened_state(self, fp_result=None, recalled_patterns=None):
        """更新觉醒状态"""
        if fp_result is not None:
            self._awakened_state["last_fp_result"] = fp_result
        if recalled_patterns is not None:
            self._awakened_state["last_recalled_patterns"] = recalled_patterns

    def get_awakened_state(self) -> Dict[str, Any]:
        """获取觉醒状态"""
        return self._awakened_state


_cognition_orchestrator: Optional['CognitionOrchestrator'] = None


def get_cognition_orchestrator() -> CognitionOrchestrator:
    """获取 CognitionOrchestrator 单例"""
    global _cognition_orchestrator
    if _cognition_orchestrator is None:
        _cognition_orchestrator = CognitionOrchestrator()
    return _cognition_orchestrator
