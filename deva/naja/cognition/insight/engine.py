"""InsightPool - 认知系统/洞察池/事件存储

别名/关键词: 洞察池、事件存储、insight、insight pool

Insight engine for user-facing attention."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from deva import NB


INSIGHT_POOL_TABLE = "naja_insight_pool"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


@dataclass
class Insight:
    id: str
    ts: float
    theme: str
    summary: str
    symbols: List[str] = field(default_factory=list)
    sectors: List[str] = field(default_factory=list)
    system_attention: float = 0.5
    confidence: float = 0.5
    actionability: float = 0.5
    novelty: float = 0.5
    user_score: float = 0.5
    source: str = ""
    signal_type: str = ""
    count: int = 1
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "theme": self.theme,
            "summary": self.summary,
            "symbols": self.symbols,
            "sectors": self.sectors,
            "system_attention": self.system_attention,
            "confidence": self.confidence,
            "actionability": self.actionability,
            "novelty": self.novelty,
            "user_score": self.user_score,
            "source": self.source,
            "signal_type": self.signal_type,
            "count": self.count,
            "payload": self.payload,
        }

    def get_summary_text(self, max_len: int = 100) -> str:
        """获取易读的 summary 文本，用于 UI 展示"""
        if not self.summary:
            return self.theme

        if isinstance(self.summary, dict):
            return self._format_dict_for_display(self.summary, max_len)

        text = str(self.summary)
        if text.startswith("{") and text.endswith("}"):
            try:
                import ast
                parsed = ast.literal_eval(text)
                if isinstance(parsed, dict):
                    return self._format_dict_for_display(parsed, max_len)
            except Exception:
                pass

        if len(text) > max_len:
            return text[:max_len].rstrip() + "…"
        return text

    @staticmethod
    def _format_dict_for_display(d: Dict[str, Any], max_len: int = 100) -> str:
        """将字典格式化为易读的展示文本"""
        parts = []
        for key, value in d.items():
            if key in ("signals", "events", "items", "data", "results"):
                if isinstance(value, list) and len(value) > 0:
                    parts.append(f"{len(value)}条{key}")
                continue
            if isinstance(value, str) and 0 < len(value) < 60:
                parts.append(value)
            elif isinstance(value, (int, float)) and abs(value) < 10000:
                parts.append(f"{key}={value}")
            elif isinstance(value, bool):
                parts.append(f"{key}={'是' if value else '否'}")
        if parts:
            result = " | ".join(parts[:4])
            if len(result) > max_len:
                return result[:max_len].rstrip() + "…"
            return result
        if d:
            first_val = next((str(v) for v in d.values() if v), "")
            if first_val and len(first_val) < max_len:
                return first_val
        return str(d)[:max_len].rstrip() + "…" if len(str(d)) > max_len else str(d)


class InsightBuilder:
    """Build candidate insights from strategy results or attention events."""

    def build_from_result(self, result: Any) -> Optional[Dict[str, Any]]:
        if result is None:
            return None

        output = getattr(result, "output_full", None)
        if output is None:
            output = getattr(result, "output_preview", None)
        if output is None:
            return None

        strategy_name = str(getattr(result, "strategy_name", "")) or "strategy"
        metadata = getattr(result, "metadata", {}) or {}

        theme = self._extract_theme(output, strategy_name)
        if not theme:
            return None

        summary = self._extract_summary(output, strategy_name)
        symbols = self._extract_symbols_from_output(output)
        sectors = self._extract_sectors(output)
        confidence = self._extract_confidence(output)
        actionability = self._extract_actionability(output)
        system_attention = self._extract_system_attention(output, metadata)
        signal_type = str(output.get("signal_type", "")) if isinstance(output, dict) else ""

        return {
            "theme": theme,
            "summary": summary,
            "symbols": symbols,
            "sectors": sectors,
            "confidence": confidence,
            "actionability": actionability,
            "system_attention": system_attention,
            "source": f"strategy:{strategy_name}",
            "signal_type": signal_type,
            "payload": output if isinstance(output, dict) else {"output": output},
        }

    def build_from_attention_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not event:
            return None

        signal_type = str(event.get("signal_type") or event.get("type", "attention"))
        payload = event.get("payload", {}) or {}
        raw_data = event.get("raw_data", {})

        theme = str(event.get("theme") or event.get("title") or "")
        if not theme or theme == "None":
            theme = self._extract_theme_from_signal(event, signal_type, payload, raw_data)

        summary_raw = event.get("content") or event.get("summary") or event.get("message") or ""
        if isinstance(summary_raw, dict):
            summary_raw = self._format_dict_for_display(summary_raw, 200)
        if not summary_raw or summary_raw == "None":
            summary_raw = self._extract_summary_from_signal(event, signal_type, payload, raw_data)
        summary = str(summary_raw) if not isinstance(summary_raw, str) else summary_raw

        symbols = self._extract_symbols(event, payload)
        event_for_extract = {"sectors": event.get("sectors"), "sector": payload.get("sector"), "板块": payload.get("板块")}
        sectors = self._extract_sectors(event_for_extract)
        system_attention = _clamp(_safe_float(event.get("score", event.get("system_attention", 0.6))))
        confidence = _clamp(_safe_float(event.get("confidence", 0.6)))
        actionability = _clamp(_safe_float(event.get("actionability", 0.4)))
        novelty = _clamp(_safe_float(event.get("novelty", None)))

        if signal_type.startswith("topic_"):
            theme = self._extract_topic_signal_info(event, signal_type, payload, raw_data)
        elif signal_type.startswith("narrative_"):
            theme = self._extract_narrative_signal_info(event, signal_type, payload, raw_data)
        elif signal_type == "attention_shift":
            theme = self._extract_attention_shift_info(event, payload, raw_data)
        elif signal_type in ("sector_hotspot", "sector_anomaly"):
            theme = self._extract_sector_signal_info(event, signal_type, payload, raw_data)

        if len(summary) < 15 and theme:
            summary = theme

        merged_payload = {**event}
        if raw_data:
            merged_payload.update(raw_data)

        return {
            "theme": theme,
            "summary": summary,
            "symbols": symbols,
            "sectors": sectors,
            "confidence": confidence,
            "actionability": actionability,
            "system_attention": system_attention,
            "novelty": novelty,
            "source": event.get("source", "attention"),
            "signal_type": signal_type,
            "payload": merged_payload,
        }

    def _extract_theme_from_signal(self, event: Dict[str, Any], signal_type: str, payload: Dict, raw_data: Dict) -> str:
        """从信号中提取主题"""
        if signal_type.startswith("topic_"):
            topic_name = payload.get("topic_name", "") or raw_data.get("topic_name", "")
            if topic_name and topic_name != "UNKNOWN":
                return f"📊 {topic_name}"
        elif signal_type.startswith("narrative_"):
            narrative = payload.get("narrative", "") or raw_data.get("narrative", "")
            if narrative:
                return f"🌊 {narrative}"
        return f"📡 {signal_type}"

    def _extract_summary_from_signal(self, event: Dict[str, Any], signal_type: str, payload: Dict, raw_data: Dict) -> str:
        """从信号中提取摘要"""
        message = event.get("message", "")
        if message and message != "None":
            return message

        signal_labels = {
            "topic_emerge": "新话题出现",
            "topic_grow": "话题快速增长",
            "topic_fade": "话题逐渐消退",
            "topic_high_attention": "话题获得高度关注",
            "topic_trend_shift": "话题趋势发生转变",
            "narrative_drift": "叙事漂移检测",
            "attention_shift": "注意力发生转移",
            "sector_hotspot": "板块成为热点",
            "sector_anomaly": "板块出现异常",
        }
        return signal_labels.get(signal_type, f"信号类型: {signal_type}")

    def _extract_symbols(self, event: Dict[str, Any], payload: Dict) -> List:
        """从信号中提取标的"""
        symbols = event.get("symbols") or []
        if symbols:
            return list(symbols)
        symbol = payload.get("symbol") or payload.get("标的") or ""
        if symbol and symbol != "-":
            return [symbol]
        return []

    def _extract_topic_signal_info(self, event: Dict[str, Any], signal_type: str, payload: Dict, raw_data: Dict) -> str:
        """从 topic_* 信号中提取有意义的 theme"""
        topic_name = payload.get("topic_name", "") or raw_data.get("topic_name", "")
        topic_id = payload.get("topic_id", "") or raw_data.get("topic_id", "")
        message = event.get("message", "")

        if topic_name and topic_name != "UNKNOWN":
            return f"📉 {topic_name}"
        if topic_id:
            return f"📉 话题: {topic_id[:15]}"

        signal_labels = {
            "topic_emerge": "📈 新话题出现",
            "topic_grow": "📈 话题增长",
            "topic_fade": "📉 话题消退",
            "topic_high_attention": "🔥 话题高关注",
            "topic_trend_shift": "🔄 话题趋势转变",
        }
        return signal_labels.get(signal_type, f"📊 {signal_type}")

    def _extract_narrative_signal_info(self, event: Dict[str, Any], signal_type: str, payload: Dict, raw_data: Dict) -> str:
        """从 narrative_* 信号中提取有意义的 theme"""
        narrative = payload.get("narrative", "") or raw_data.get("narrative", "")
        if narrative and narrative != "UNKNOWN":
            return f"🌊 {narrative[:20]}"
        return f"🌊 叙事: {signal_type.replace('narrative_', '')}"

    def _extract_attention_shift_info(self, event: Dict[str, Any], payload: Dict, raw_data: Dict) -> str:
        """从 attention_shift 信号中提取有意义的 theme"""
        shift_type = payload.get("shift_type", "") or raw_data.get("shift_type", "")
        if shift_type:
            return f"🔄 注意力转移: {shift_type}"

        from_symbol = payload.get("from_symbol", "") or raw_data.get("from_symbol", "")
        to_symbol = payload.get("to_symbol", "") or raw_data.get("to_symbol", "")
        if from_symbol and to_symbol:
            return f"🔄 {from_symbol} → {to_symbol}"

        from_sector = payload.get("from_sector", "") or raw_data.get("from_sector", "")
        to_sector = payload.get("to_sector", "") or raw_data.get("to_sector", "")
        if from_sector and to_sector:
            return f"🔄 板块: {from_sector} → {to_sector}"

        return "🔄 注意力转移"

    def _extract_sector_signal_info(self, event: Dict[str, Any], signal_type: str, payload: Dict, raw_data: Dict) -> str:
        """从 sector_* 信号中提取有意义的 theme"""
        sector = payload.get("sector", "") or payload.get("板块", "") or raw_data.get("sector", "") or raw_data.get("板块", "")
        if sector and sector != "-":
            return f"🔥 板块: {sector}"
        return f"🔥 {signal_type}"

    def _extract_theme(self, output: Any, strategy_name: str) -> str:
        if isinstance(output, dict):
            for key in ("topic", "theme", "sector", "industry", "signal_type"):
                value = output.get(key)
                if value:
                    return str(value)
            return strategy_name
        return strategy_name

    def _extract_summary(self, output: Any, strategy_name: str) -> str:
        if isinstance(output, dict):
            for key in ("message", "content", "reason", "summary", "title"):
                value = output.get(key)
                if value:
                    if isinstance(value, str):
                        return value
                    elif isinstance(value, dict):
                        return self._format_dict_as_text(value)
                    else:
                        return str(value)
            narrative = output.get("narrative")
            if narrative:
                return str(narrative)
        text = str(output) if output is not None else ""
        if text.startswith("{") and text.endswith("}"):
            return strategy_name
        return text[:120] if text else strategy_name

    def _format_dict_as_text(self, d: Dict[str, Any]) -> str:
        """将字典格式化为易读的文本"""
        parts = []
        for key, value in d.items():
            if key in ("signals", "events", "items"):
                if isinstance(value, list) and len(value) > 0:
                    parts.append(f"{len(value)}条{key}")
                continue
            if isinstance(value, str) and len(value) < 50:
                parts.append(value)
            elif isinstance(value, (int, float)):
                parts.append(f"{key}={value}")
        if parts:
            return " | ".join(parts[:3])
        return str(d)[:80]

    def _extract_symbols_from_output(self, output: Any) -> List[str]:
        if not isinstance(output, dict):
            return []
        symbols: Set[str] = set()
        for key in ("symbols", "stocks", "codes", "tickers"):
            val = output.get(key)
            if isinstance(val, list):
                symbols.update(str(x) for x in val if x)
        for key in ("stock_code", "symbol", "code", "ticker"):
            val = output.get(key)
            if val:
                symbols.add(str(val))
        return list(symbols)

    def _extract_sectors(self, output: Any) -> List[str]:
        if not isinstance(output, dict):
            return []
        sectors: Set[str] = set()
        for key in ("sectors", "industries"):
            val = output.get(key)
            if isinstance(val, list):
                sectors.update(str(x) for x in val if x)
        for key in ("sector", "industry"):
            val = output.get(key)
            if val:
                sectors.add(str(val))
        return list(sectors)

    def _extract_confidence(self, output: Any) -> float:
        if isinstance(output, dict):
            value = output.get("confidence", output.get("score", 0.5))
            return self._normalize_score(value)
        return 0.5

    def _extract_actionability(self, output: Any) -> float:
        if not isinstance(output, dict):
            return 0.3
        signal = str(output.get("signal_type", "")).upper()
        if signal in {"BUY", "SELL"}:
            return 0.9
        if output.get("stock_code") or output.get("symbol") or output.get("code"):
            return 0.7
        if output.get("price") or output.get("close"):
            return 0.6
        return 0.4

    def _extract_system_attention(self, output: Any, metadata: Dict[str, Any]) -> float:
        if isinstance(output, dict):
            for key in ("attention", "attention_score", "global_attention"):
                if key in output:
                    return self._normalize_score(output.get(key))
        for key in ("attention", "global_attention"):
            if key in metadata:
                return self._normalize_score(metadata.get(key))
        return 0.5

    def _normalize_score(self, value: Any) -> float:
        score = _safe_float(value, 0.0)
        if score <= 1.0:
            return _clamp(score)
        if score <= 100.0:
            return _clamp(score / 100.0)
        return _clamp(score / 5.0)


class UserAttentionRanker:
    """Rank insights for user-facing attention."""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or {
            "system_attention": 0.4,
            "confidence": 0.2,
            "actionability": 0.2,
            "novelty": 0.2,
        }

    def score(self, *, system_attention: float, confidence: float, actionability: float, novelty: float) -> float:
        return _clamp(
            self.weights["system_attention"] * system_attention
            + self.weights["confidence"] * confidence
            + self.weights["actionability"] * actionability
            + self.weights["novelty"] * novelty
        )


class InsightPool:
    """Insight pool with lightweight clustering and user attention ranking."""

    def __init__(
        self,
        max_size: int = 200,
        merge_window_seconds: int = 600,
        novelty_window_seconds: int = 3600,
    ):
        self.max_size = max_size
        self.merge_window_seconds = merge_window_seconds
        self.novelty_window_seconds = novelty_window_seconds
        self._insights: List[Insight] = []
        self._lock = threading.RLock()
        self._builder = InsightBuilder()
        self._ranker = UserAttentionRanker()
        self._last_seen: Dict[str, float] = {}
        self._latest_by_theme: Dict[str, str] = {}
        self._db = NB(INSIGHT_POOL_TABLE)
        self._load_from_db()

    def ingest_result(self, result: Any) -> Optional[Insight]:
        candidate = self._builder.build_from_result(result)
        if not candidate:
            return None
        return self._append_or_merge(candidate)

    def ingest_attention_event(self, event: Dict[str, Any]) -> Optional[Insight]:
        candidate = self._builder.build_from_attention_event(event)
        if not candidate:
            return None
        return self._append_or_merge(candidate)

    def emit(self, event: Dict[str, Any]) -> Optional[Insight]:
        """统一入口：发送任意事件到洞察池

        自动识别事件类型并路由到正确的处理方法：
        - 包含 strategy_id/strategy_name 的事件 → 视为 RadarEvent 转换的信号
        - 包含 type=news/content 的事件 → 视为新闻/内容事件
        - 其他事件 → 视为注意力事件
        """
        if not event:
            return None

        try:
            if "strategy_id" in event or "strategy_name" in event:
                return self.ingest_attention_event(event)

            if event.get("type") in ("news", "content", "result"):
                return self.ingest_result(event)

            return self.ingest_attention_event(event)
        except Exception:
            return None

    def _append_or_merge(self, candidate: Dict[str, Any]) -> Insight:
        now_ts = time.time()
        theme = str(candidate.get("theme", "unknown"))

        candidate_novelty = _clamp(_safe_float(candidate.get("novelty", None)))
        if candidate_novelty is not None and candidate_novelty > 0:
            novelty = candidate_novelty
        else:
            novelty = self._calc_novelty(theme, now_ts)

        insight = Insight(
            id=f"insight_{uuid.uuid4().hex[:12]}",
            ts=now_ts,
            theme=theme,
            summary=str(candidate.get("summary", theme)),
            symbols=list(candidate.get("symbols") or []),
            sectors=list(candidate.get("sectors") or []),
            system_attention=_clamp(_safe_float(candidate.get("system_attention", 0.5))),
            confidence=_clamp(_safe_float(candidate.get("confidence", 0.5))),
            actionability=_clamp(_safe_float(candidate.get("actionability", 0.5))),
            novelty=novelty,
            source=str(candidate.get("source", "")),
            signal_type=str(candidate.get("signal_type", "")),
            payload=candidate.get("payload", {}) or {},
        )
        insight.user_score = self._ranker.score(
            system_attention=insight.system_attention,
            confidence=insight.confidence,
            actionability=insight.actionability,
            novelty=insight.novelty,
        )

        with self._lock:
            merged = self._merge_if_possible(insight)
            if merged:
                self._last_seen[theme] = now_ts
                self.persist()
                return merged

            self._insights.append(insight)
            if len(self._insights) > self.max_size:
                self._insights = self._insights[-self.max_size :]
            self._last_seen[theme] = now_ts
            self._latest_by_theme[theme] = insight.id
            self.persist()
            return insight

    def _merge_if_possible(self, new_insight: Insight) -> Optional[Insight]:
        theme = new_insight.theme
        last_seen = self._last_seen.get(theme)
        if not last_seen or (time.time() - last_seen) > self.merge_window_seconds:
            return None

        latest_id = self._latest_by_theme.get(theme)
        if not latest_id:
            return None

        for insight in reversed(self._insights):
            if insight.id != latest_id:
                continue
            insight.ts = new_insight.ts
            insight.summary = new_insight.summary or insight.summary
            insight.symbols = list({*insight.symbols, *new_insight.symbols})
            insight.sectors = list({*insight.sectors, *new_insight.sectors})
            insight.system_attention = max(insight.system_attention, new_insight.system_attention)
            insight.confidence = max(insight.confidence, new_insight.confidence)
            insight.actionability = max(insight.actionability, new_insight.actionability)
            insight.novelty = new_insight.novelty
            insight.user_score = self._ranker.score(
                system_attention=insight.system_attention,
                confidence=insight.confidence,
                actionability=insight.actionability,
                novelty=insight.novelty,
            )
            insight.count += 1
            return insight
        return None

    def _calc_novelty(self, theme: str, now_ts: float) -> float:
        last_ts = self._last_seen.get(theme)
        if not last_ts:
            return 1.0
        delta = max(0.0, now_ts - last_ts)
        return _clamp(delta / float(self.novelty_window_seconds))

    def get_top_insights(self, limit: int = 5) -> List[Dict[str, Any]]:
        with self._lock:
            ranked = sorted(self._insights, key=lambda i: i.user_score, reverse=True)
            return [i.to_dict() for i in ranked[: max(1, int(limit))]]

    def get_recent_insights(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._insights)[-max(1, int(limit)) :]
            return [i.to_dict() for i in reversed(items)]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._insights)
            themes = len({i.theme for i in self._insights})
            avg_score = sum(i.user_score for i in self._insights) / total if total else 0.0
            return {
                "total_insights": total,
                "active_themes": themes,
                "avg_user_score": round(avg_score, 3),
            }

    def _load_from_db(self):
        """从持久化存储加载"""
        import logging
        logger = logging.getLogger(__name__)

        try:
            data = self._db.get("insights")
            if not data:
                return
            insights_data = data.get("insights", [])
            self._insights = [
                Insight(**item) for item in insights_data
            ]
            self._last_seen = data.get("last_seen", {})
            self._latest_by_theme = data.get("latest_by_theme", {})
            logger.info(f"[InsightPool] 从数据库加载了 {len(self._insights)} 条历史洞察")
        except Exception as e:
            logger.warning(f"[InsightPool] 从数据库加载洞察失败: {e}，将使用空洞察池")

    def persist(self):
        """持久化到存储"""
        import logging
        logger = logging.getLogger(__name__)

        try:
            with self._lock:
                data = {
                    "insights": [i.to_dict() for i in self._insights],
                    "last_seen": self._last_seen,
                    "latest_by_theme": self._latest_by_theme,
                }
                self._db["insights"] = data
        except Exception as e:
            logger.warning(f"[InsightPool] 持久化洞察失败: {e}")

    def clear(self):
        """清空洞察池"""
        with self._lock:
            self._insights.clear()
            self._last_seen.clear()
            self._latest_by_theme.clear()
            self.persist()


_insight_pool: Optional[InsightPool] = None
_insight_pool_lock = threading.Lock()


def get_insight_pool() -> InsightPool:
    global _insight_pool
    if _insight_pool is None:
        with _insight_pool_lock:
            if _insight_pool is None:
                _insight_pool = InsightPool()
    return _insight_pool


def emit_to_insight_pool(event: Dict[str, Any]) -> Optional[Insight]:
    """全局统一入口：发送事件到洞察池

    用法：
        from deva.naja.cognition.insight import emit_to_insight_pool
        emit_to_insight_pool({"type": "news", "content": "...", ...})
        emit_to_insight_pool({"strategy_id": "...", "signal_type": "...", ...})
        emit_to_insight_pool({"event_type": "pattern", "message": "...", ...})
    """
    pool = get_insight_pool()
    return pool.emit(event)


class InsightEngine:
    """洞察引擎 - 管理认知产物"""

    def __init__(self):
        self._pool = get_insight_pool()

    def get_summary(self) -> Dict[str, Any]:
        stats = self._pool.get_stats()
        return {
            "total_insights": stats.get("total_insights", 0),
            "signal_buffer_size": 0,
            "long_memory_size": stats.get("active_themes", 0),
        }

    def get_attention_hints(self, lookback: int = 200) -> Dict[str, Any]:
        recent = self._pool.get_recent_insights(limit=lookback)
        symbols: Dict[str, float] = {}
        sectors: Dict[str, float] = {}
        narratives: List[str] = []

        for item in recent:
            syms = item.get("symbols", [])
            secs = item.get("sectors", [])
            score = float(item.get("user_score", 0.5))
            for s in syms:
                symbols[s] = symbols.get(s, 0) + score
            for s in secs:
                sectors[s] = sectors.get(s, 0) + score
            theme = item.get("theme", "")
            if theme and theme not in narratives:
                narratives.append(theme)

        return {
            "symbols": symbols,
            "sectors": sectors,
            "narratives": narratives[:10],
        }

    def update(self, result: Any) -> None:
        self._pool.ingest_result(result)

    def ingest_signal(self, signal: Dict[str, Any]) -> None:
        self._pool.ingest_attention_event(signal)

    def get_pool(self) -> InsightPool:
        return self._pool


_insight_engine: Optional[InsightEngine] = None
_insight_engine_lock = threading.Lock()


def get_insight_engine() -> InsightEngine:
    """获取洞察引擎单例"""
    global _insight_engine
    if _insight_engine is None:
        with _insight_engine_lock:
            if _insight_engine is None:
                _insight_engine = InsightEngine()
    return _insight_engine
