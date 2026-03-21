"""Insight engine for user-facing attention."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


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
        symbols = self._extract_symbols(output)
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

        theme = event.get("theme") or event.get("title") or "attention"
        summary = event.get("content") or event.get("summary") or theme
        symbols = event.get("symbols") or []
        sectors = event.get("sectors") or []
        system_attention = _clamp(_safe_float(event.get("score", 0.6)))
        confidence = _clamp(_safe_float(event.get("confidence", 0.6)))
        actionability = _clamp(_safe_float(event.get("actionability", 0.4)))
        signal_type = str(event.get("signal_type", "attention"))

        return {
            "theme": theme,
            "summary": summary,
            "symbols": list(symbols),
            "sectors": list(sectors),
            "confidence": confidence,
            "actionability": actionability,
            "system_attention": system_attention,
            "source": "attention",
            "signal_type": signal_type,
            "payload": event,
        }

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
                    return str(value)
        text = str(output) if output is not None else ""
        return text[:120] if text else strategy_name

    def _extract_symbols(self, output: Any) -> List[str]:
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

    def _append_or_merge(self, candidate: Dict[str, Any]) -> Insight:
        now_ts = time.time()
        theme = str(candidate.get("theme", "unknown"))
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
                return merged

            self._insights.append(insight)
            if len(self._insights) > self.max_size:
                self._insights = self._insights[-self.max_size :]
            self._last_seen[theme] = now_ts
            self._latest_by_theme[theme] = insight.id
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


_insight_pool: Optional[InsightPool] = None
_insight_pool_lock = threading.Lock()


def get_insight_pool() -> InsightPool:
    global _insight_pool
    if _insight_pool is None:
        with _insight_pool_lock:
            if _insight_pool is None:
                _insight_pool = InsightPool()
    return _insight_pool
