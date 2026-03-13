"""Strategy registry events for versioning and change history."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from deva import NB


STRATEGY_REGISTRY_TABLE = "naja_strategy_registry"
STRATEGY_METRICS_TABLE = "naja_strategy_metrics"

_last_perf_ts: Dict[str, float] = {}


def _collect_metrics(strategy_id: str) -> Optional[Dict[str, Any]]:
    try:
        metrics_db = NB(STRATEGY_METRICS_TABLE)
        payload = metrics_db.get(strategy_id)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def record_event(
    *,
    strategy_id: str,
    strategy_name: str,
    version: int,
    event_type: str,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    performance: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "id": uuid.uuid4().hex[:16],
        "ts": time.time(),
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "version": int(version),
        "event_type": str(event_type or "update"),
        "before": before or {},
        "after": after or {},
        "extra": extra or {},
    }
    metrics = performance or _collect_metrics(strategy_id)
    if metrics:
        payload["performance"] = metrics
    try:
        db = NB(STRATEGY_REGISTRY_TABLE)
        db[payload["id"]] = payload
    except Exception:
        return


def record_performance_snapshot(
    *,
    strategy_id: str,
    strategy_name: str,
    version: int,
    process_time_ms: float,
    success: bool,
    min_interval: float = 60.0,
) -> None:
    now = time.time()
    last = _last_perf_ts.get(strategy_id, 0.0)
    if now - last < min_interval:
        return
    _last_perf_ts[strategy_id] = now
    record_event(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        version=version,
        event_type="performance",
        extra={
            "process_time_ms": float(process_time_ms),
            "success": bool(success),
        },
    )

