"""Radar engine for pattern/drift/anomaly detection."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from deva import NB

from ..config import get_radar_config

try:
    from river import drift
    _RIVER_AVAILABLE = True
except Exception:
    drift = None
    _RIVER_AVAILABLE = False


def _clamp_event_score(score: Any) -> float:
    try:
        value = abs(float(score))
    except Exception:
        return 0.5
    if value <= 1.0:
        return value
    if value <= 100.0:
        return min(1.0, value / 100.0)
    return min(1.0, value / 5.0)


RADAR_EVENTS_TABLE = "naja_radar_events"


@dataclass
class RadarEvent:
    id: str
    ts: float
    event_type: str
    score: float
    strategy_id: str
    strategy_name: str
    signal_type: str = ""
    message: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.id,
            "timestamp": self.ts,
            "event_type": self.event_type,
            "score": self.score,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "signal_type": self.signal_type,
            "message": self.message,
            "payload": self.payload,
        }


class RadarEngine:
    """思想雷达引擎。"""

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

        self._db = NB(RADAR_EVENTS_TABLE)
        self._state_lock = threading.RLock()

        self._pattern_window_seconds = 300
        self._pattern_min_count = 3
        self._pattern_cooldown_seconds = 120
        self._pattern_hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._pattern_last_emit: Dict[str, float] = {}

        self._drift_detectors: Dict[str, Any] = {}
        self._anomaly_stats: Dict[str, Dict[str, float]] = {}

        cfg = get_radar_config()
        self._retention_days = float(cfg.get("event_retention_days", 7))
        self._cleanup_interval_seconds = float(cfg.get("cleanup_interval_seconds", 600))
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()

        if self._retention_days > 0 and self._cleanup_interval_seconds > 0:
            self._start_cleanup_thread()

        self._initialized = True

    def ingest_result(self, result: Any) -> List[RadarEvent]:
        payload = self._extract_payload(result)
        if payload is None:
            return []

        events: List[RadarEvent] = []
        with self._state_lock:
            events.extend(self._detect_pattern(result, payload))
            events.extend(self._detect_drift(result, payload))
            events.extend(self._detect_anomaly(result, payload))

        for event in events:
            self._store_event(event)
        self._emit_events_to_memory(events)
        return events

    def ingest_attention_event(
        self,
        *,
        event_type: str,
        score: float,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        signal_type: str = "attention",
        strategy_id: str = "attention_system",
        strategy_name: str = "Attention System",
        ts: Optional[float] = None,
    ) -> RadarEvent:
        event = self._build_event_from_fields(
            event_type=event_type,
            score=score,
            signal_type=signal_type,
            message=message,
            payload=payload or {},
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            ts=ts,
        )
        self._store_event(event)
        self._emit_events_to_memory([event])
        return event

    def get_recent_events(self, limit: int = 20) -> List[dict]:
        try:
            keys = list(self._db.keys())
            keys.sort(reverse=True)
            items = []
            for key in keys[:limit]:
                data = self._db.get(key)
                if isinstance(data, dict):
                    items.append(data)
            return items
        except Exception:
            return []

    def summarize(self, window_seconds: int = 600) -> dict:
        now = time.time()
        cutoff = now - max(60, int(window_seconds))
        events = []
        try:
            for _, data in list(self._db.items()):
                if not isinstance(data, dict):
                    continue
                if float(data.get("timestamp", 0)) >= cutoff:
                    events.append(data)
        except Exception:
            pass

        counts = defaultdict(int)
        for e in events:
            counts[str(e.get("event_type", "unknown"))] += 1

        return {
            "window_seconds": window_seconds,
            "event_count": len(events),
            "event_type_counts": dict(counts),
            "events": events[:50],
        }

    def prune_events(self, *, retention_days: Optional[float] = None) -> dict:
        days = self._retention_days if retention_days is None else float(retention_days)
        if days <= 0:
            return {"success": False, "error": "retention disabled"}

        cutoff = time.time() - days * 86400
        removed = 0

        with self._state_lock:
            try:
                keys = list(self._db.keys())
                for key in keys:
                    ts = None
                    if isinstance(key, str) and "_" in key:
                        prefix = key.split("_", 1)[0]
                        try:
                            ts = int(prefix) / 1000.0
                        except Exception:
                            ts = None

                    if ts is None:
                        data = self._db.get(key)
                        try:
                            ts = float(data.get("timestamp", 0))
                        except Exception:
                            ts = None

                    if ts is not None and ts < cutoff:
                        try:
                            del self._db[key]
                            removed += 1
                        except Exception:
                            pass
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": True, "removed": removed, "cutoff": cutoff}

    def _extract_payload(self, result: Any) -> Optional[Dict[str, Any]]:
        output = getattr(result, "output_full", None)
        if output is None:
            return None

        if isinstance(output, dict):
            signal_type = str(output.get("signal_type") or output.get("signal") or "")
            score = output.get("score", output.get("confidence"))
            return {
                "signal_type": signal_type,
                "score": score,
                "output": output,
            }
        return None

    def _detect_pattern(self, result: Any, payload: Dict[str, Any]) -> List[RadarEvent]:
        signal_type = payload.get("signal_type") or "unknown"
        key = f"{result.strategy_id}:{signal_type}"

        now = time.time()
        window = self._pattern_hits[key]
        window.append(now)
        cutoff = now - self._pattern_window_seconds
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) < self._pattern_min_count:
            return []

        last_emit = self._pattern_last_emit.get(key, 0)
        if now - last_emit < self._pattern_cooldown_seconds:
            return []

        self._pattern_last_emit[key] = now
        return [
            self._build_event(
                result,
                event_type="pattern",
                score=float(len(window)),
                signal_type=signal_type,
                message=f"{signal_type} 模式在短时间内出现 {len(window)} 次",
                payload={"count": len(window), "window_seconds": self._pattern_window_seconds},
            )
        ]

    def _detect_drift(self, result: Any, payload: Dict[str, Any]) -> List[RadarEvent]:
        if not _RIVER_AVAILABLE:
            return []
        score = payload.get("score")
        if score is None:
            return []

        try:
            value = float(score)
        except (TypeError, ValueError):
            return []

        detector = self._drift_detectors.get(result.strategy_id)
        if detector is None:
            detector = drift.ADWIN()
            self._drift_detectors[result.strategy_id] = detector

        detector.update(value)
        if detector.change_detected:
            return [
                self._build_event(
                    result,
                    event_type="drift",
                    score=float(value),
                    signal_type=payload.get("signal_type", ""),
                    message="检测到概念漂移",
                    payload={"value": value},
                )
            ]
        return []

    def _detect_anomaly(self, result: Any, payload: Dict[str, Any]) -> List[RadarEvent]:
        score = payload.get("score")
        if score is None:
            return []

        try:
            value = float(score)
        except (TypeError, ValueError):
            return []

        key = f"{result.strategy_id}:{payload.get('signal_type', '')}"
        stats = self._anomaly_stats.get(key)
        if stats is None:
            stats = {"count": 0.0, "mean": 0.0, "m2": 0.0}
            self._anomaly_stats[key] = stats

        stats["count"] += 1.0
        delta = value - stats["mean"]
        stats["mean"] += delta / stats["count"]
        delta2 = value - stats["mean"]
        stats["m2"] += delta * delta2

        if stats["count"] < 30:
            return []

        variance = stats["m2"] / max(1.0, stats["count"] - 1.0)
        if variance <= 0:
            return []

        z = (value - stats["mean"]) / (variance ** 0.5)
        if abs(z) < 3.0:
            return []

        return [
            self._build_event(
                result,
                event_type="anomaly",
                score=float(abs(z)),
                signal_type=payload.get("signal_type", ""),
                message="异常波动",
                payload={"z_score": z, "value": value, "mean": stats["mean"]},
            )
        ]

    def _build_event(
        self,
        result: Any,
        *,
        event_type: str,
        score: float,
        signal_type: str,
        message: str,
        payload: Dict[str, Any],
    ) -> RadarEvent:
        return RadarEvent(
            id=f"radar_{uuid.uuid4().hex[:12]}",
            ts=time.time(),
            event_type=event_type,
            score=score,
            strategy_id=str(getattr(result, "strategy_id", "")),
            strategy_name=str(getattr(result, "strategy_name", "")),
            signal_type=str(signal_type or ""),
            message=message,
            payload=payload or {},
        )

    def _build_event_from_fields(
        self,
        *,
        event_type: str,
        score: float,
        signal_type: str,
        message: str,
        payload: Dict[str, Any],
        strategy_id: str,
        strategy_name: str,
        ts: Optional[float] = None,
    ) -> RadarEvent:
        return RadarEvent(
            id=f"radar_{uuid.uuid4().hex[:12]}",
            ts=time.time() if ts is None else float(ts),
            event_type=event_type,
            score=score,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            signal_type=str(signal_type or ""),
            message=message,
            payload=payload or {},
        )

    def _store_event(self, event: RadarEvent) -> None:
        try:
            key = f"{int(event.ts * 1000)}_{event.id}"
            self._db[key] = event.to_dict()
        except Exception:
            return

    def _emit_events_to_memory(self, events: List[RadarEvent]) -> None:
        if not events:
            return
        try:
            from ..memory import get_memory_engine
        except Exception:
            return

        try:
            memory = get_memory_engine()
        except Exception:
            return

        for event in events:
            record = {
                "timestamp": event.ts,
                "source": f"radar:{event.strategy_name}",
                "title": f"雷达事件: {event.event_type}",
                "content": event.message,
                "signal_type": event.signal_type,
                "score": event.score,
                "event_type": event.event_type,
                "strategy_id": event.strategy_id,
                "strategy_name": event.strategy_name,
                "payload": event.payload,
                "importance": "high",
            }
            try:
                memory.process_record(record)
            except Exception:
                continue

        # 同步到洞察池（表达层）
        try:
            from ..insight import get_insight_pool
        except Exception:
            return

        try:
            pool = get_insight_pool()
        except Exception:
            return

        for event in events:
            pool.ingest_attention_event(
                {
                    "theme": f"雷达{event.event_type}",
                    "title": f"雷达事件: {event.event_type}",
                    "content": event.message,
                    "score": _clamp_event_score(event.score),
                    "signal_type": event.signal_type or "radar",
                    "payload": event.payload,
                    "confidence": 0.6,
                    "actionability": 0.4,
                }
            )

    def _start_cleanup_thread(self) -> None:
        if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
            return
        self._stop_cleanup.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="radar_cleanup",
        )
        self._cleanup_thread.start()

    def _cleanup_loop(self) -> None:
        while not self._stop_cleanup.is_set():
            self._stop_cleanup.wait(self._cleanup_interval_seconds)
            if self._stop_cleanup.is_set():
                break
            try:
                self.prune_events()
            except Exception:
                pass


_radar_engine: Optional[RadarEngine] = None
_radar_engine_lock = threading.Lock()


def get_radar_engine() -> RadarEngine:
    global _radar_engine
    if _radar_engine is None:
        with _radar_engine_lock:
            if _radar_engine is None:
                _radar_engine = RadarEngine()
    return _radar_engine
