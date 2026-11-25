"""
geo_risk 定时任务注册：只有 NAJA_GEO_RISK_ENABLE 开启时才注册。

默认关闭 → 不建生产库、不写生产报告；测试直接调 daily/weekly 并传临时库。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from deva.core.bus import log
from deva.naja.geo_risk.jobs.daily import is_enabled, run_daily
from deva.naja.geo_risk.jobs.weekly import run_weekly

_REGISTERED: list[str] = []


def _make_job(unit_id: str, label: str, fn):
    """把任务登记进 fleet_registry 后再包一层，保证异常不把调度器打挂。

    probe 挂在内层：异常先被探针记为失败（首页能看见），再由外层吞掉。
    """
    from deva.naja.infra.observability.fleet_registry import KIND_STRATEGY, probe

    @probe(KIND_STRATEGY, unit_id, f"GeoRisk {label}", cadence="cron", source="geo_risk")
    def _run():
        from deva.naja.geo_risk.alerts import get_alert_center
        return fn(notifier=get_alert_center().publish)

    def _scheduled():
        try:
            result = _run()
            log.info(f"[GeoRisk] {label} 完成: {result.get('path')}")
            return result
        except Exception as exc:  # noqa: BLE001 - 定时任务不能把调度器打挂
            log.error(f"[GeoRisk] {label} 失败: {exc}")
            return {"error": str(exc)}
    return _scheduled


def _make_collect_job():
    """采集编排（7:00）：collect → extract → evidence → series，先于 7:30 日更。

    探针挂在 pipeline 内部调用上；外层只负责隔离异常，不让调度器被打挂。
    """
    from deva.naja.infra.observability.fleet_registry import (
        KIND_DATASOURCE, probe,
    )
    from deva.naja.geo_risk.pipeline import run_pipeline

    @probe(KIND_DATASOURCE, "ds:geo_risk_pipeline", "GeoRisk 采集编排",
           cadence="cron", source="geo_risk")
    def _run():
        return run_pipeline()

    def _scheduled():
        try:
            result = _run()
            log.info(
                "[GeoRisk] 采集完成: fetched=%s stored=%s series=%s failed=%s",
                result.get("fetched"), result.get("stored"),
                result.get("series"), len(result.get("failed_sources") or []),
            )
            return result
        except Exception as exc:  # noqa: BLE001
            log.error("[GeoRisk] 采集失败: %s", exc)
            return {"error": str(exc)}
    return _scheduled


def register_jobs(manager=None) -> Dict[str, Any]:
    """注册日更(7:30)与周报(周一 09:00)；返回注册结果，便于启动期日志。"""
    if not is_enabled():
        return {"enabled": False, "registered": [], "message": "NAJA_GEO_RISK_ENABLE 未启用"}

    if manager is None:
        from deva.naja.scheduler.common import SchedulerManager
        manager = SchedulerManager()

    results = []
    if "geo_risk_collect" not in _REGISTERED:
        results.append(manager.add_scheduler_job(
            "geo_risk_collect",
            _make_collect_job(),
            "cron",
            hour=7,
            minute=0,
        ))
        _REGISTERED.append("geo_risk_collect")

    if "geo_risk_daily" not in _REGISTERED:
        results.append(manager.add_scheduler_job(
            "geo_risk_daily",
            _make_job("st:geo_risk_daily", "日更", run_daily),
            "cron",
            hour=7,
            minute=30,
        ))
        _REGISTERED.append("geo_risk_daily")

    if "geo_risk_weekly" not in _REGISTERED:
        results.append(manager.add_scheduler_job(
            "geo_risk_weekly",
            _make_job("st:geo_risk_weekly", "周报", run_weekly),
            "cron",
            day_of_week="mon",
            hour=9,
            minute=0,
        ))
        _REGISTERED.append("geo_risk_weekly")

    log.info("[GeoRisk] 日更/周报已注册")
    return {"enabled": True, "registered": list(_REGISTERED), "results": results}
