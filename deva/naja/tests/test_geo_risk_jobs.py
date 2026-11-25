"""
P5 日更/周报验收：报告落盘、等级跃迁推送、启用开关、临时库不外溢。

全部用临时 sqlite 和临时报告目录，不碰 ~/.naja。
"""

import json

import pytest

import deva.naja.geo_risk.jobs as jobs
from deva.naja.geo_risk.jobs.daily import run_daily
from deva.naja.geo_risk.jobs.weekly import run_weekly
from deva.naja.geo_risk.store.db import GeoRiskDB

PROJECT = {
    "project_id": "prj_job_test",
    "operator_entity_id": "ent_job_operator",
    "name": "YTL Johor AI Data Centre Campus",
    "site": "Kulai, Johor",
    "country": "MY",
    "capacity_mw": 300.0,
}
ENTITY = {
    "entity_id": "ent_job_operator",
    "kind": "company",
    "canonical_name": "YTL Power International Berhad",
    "country": "MY",
    "aliases": ["YTL Power", "YTLP"],
}

SNAPSHOT = {
    "gpu_count": 2000,
    "monthly_rent_per_gpu_usd": 1800.0,
    "utilization": 0.9,
    "china_linked_share": 0.5,
    "annual_debt_service_usd": 30_000_000.0,
    "debt_usd": 20_000_000.0,
    "gpu_models": [
        {"model": "H100", "count": 1000, "age_months": 18},
        {"model": "A100", "count": 1000, "age_months": 36},
    ],
    "dimensions": {"policy": 20, "utilization": 20, "price": 20},
}
SNAPSHOT_WORSE = {**SNAPSHOT, "dimensions": {"policy": 80, "utilization": 70, "price": 70}}


@pytest.fixture
def db(tmp_path):
    database = GeoRiskDB(tmp_path / "geo.db")
    database.upsert_entities([ENTITY]).result()
    database.upsert_projects([PROJECT]).result()
    database.add_evidence([
        {
            "evidence_id": "ev_job_fin",
            "subject_type": "project",
            "subject_id": PROJECT["project_id"],
            "source": "fixture.financing_news",
            "url": "fixture://geo-risk/job/fin",
            "published_at": "2026-11-05T09:00:00+08:00",
            "quote": "银团为柔佛 AI 数据中心提供项目融资",
        },
        {
            "evidence_id": "ev_job_ops",
            "subject_type": "project",
            "subject_id": PROJECT["project_id"],
            "source": "fixture.operator_announcement",
            "url": "fixture://geo-risk/job/ops",
            "published_at": "2026-11-06T18:00:00+08:00",
            "quote": "运营商公告：园区一期投运",
        },
    ]).result()
    yield database
    database.close()


def test_daily_writes_report_and_pushes_only_on_escalation(db, tmp_path):
    reports = tmp_path / "reports"
    pushed = []

    first = run_daily(as_of="2026-11-22", db=db, snapshots={"prj_job_test": SNAPSHOT},
                      report_dir=reports, notifier=pushed.append)
    assert first["transitions"] == []
    assert pushed == []
    path = reports / "2026-11-22.md"
    text = path.read_text(encoding="utf-8")
    assert "YTL Johor AI Data Centre Campus" in text
    assert "未评级原因" not in text
    assert first["stats"]["rated"] == 1
    assert first["stats"]["evidence"] == 2

    second = run_daily(as_of="2026-11-23", db=db, snapshots={"prj_job_test": SNAPSHOT_WORSE},
                       report_dir=reports, notifier=pushed.append)
    assert len(second["transitions"]) == 1
    change = second["transitions"][0]
    assert change["from"] == "yellow"
    assert change["to"] == "red"
    assert change["direction"] == "escalated"
    assert len(pushed) == 1 and pushed[0]["to"] == "red"

    state = json.loads((reports / "state" / "ratings.json").read_text(encoding="utf-8"))
    history = state["projects"]["prj_job_test"]["history"]
    assert [h["date"] for h in history] == ["2026-11-22", "2026-11-23"]


def test_daily_without_snapshot_is_unrated_but_still_writes(db, tmp_path):
    reports = tmp_path / "reports2"
    out = run_daily(as_of="2026-11-23", db=db, report_dir=reports)
    assert out["stats"]["unrated"] == 1
    text = (reports / "2026-11-23.md").read_text(encoding="utf-8")
    assert "无模型输入" in text

    # 有财务输入但缺政策/利用率/价格维度 → 明确写清缺什么
    no_dims = {k: v for k, v in SNAPSHOT.items() if k != "dimensions"}
    run_daily(as_of="2026-11-24", db=db, snapshots={"prj_job_test": no_dims},
              report_dir=reports)
    text2 = (reports / "2026-11-24.md").read_text(encoding="utf-8")
    assert "缺少 dimensions" in text2


def test_weekly_reports_changes_and_new_evidence(db, tmp_path):
    reports = tmp_path / "reports"
    run_daily(as_of="2026-11-22", db=db, snapshots={"prj_job_test": SNAPSHOT},
              report_dir=reports)
    run_daily(as_of="2026-11-23", db=db, snapshots={"prj_job_test": SNAPSHOT_WORSE},
              report_dir=reports)
    out = run_weekly(as_of="2026-11-24", db=db, snapshots={"prj_job_test": SNAPSHOT_WORSE},
                     report_dir=reports)
    path = reports / "weekly-2026-11-24.md"
    assert path.exists()
    assert out["changes"][0]["from"] == "yellow"
    assert out["changes"][0]["to"] == "red"
    assert out["stats"]["new_evidence"] == 2
    text = path.read_text(encoding="utf-8")
    assert "等级变化" in text and "fixture.financing_news" in text


def test_disabled_means_no_scheduler_jobs(monkeypatch):
    monkeypatch.delenv("NAJA_GEO_RISK_ENABLE", raising=False)
    jobs._REGISTERED.clear()

    class FakeManager:
        def __init__(self):
            self.calls = []

        def add_scheduler_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    manager = FakeManager()
    result = jobs.register_jobs(manager=manager)
    assert result["enabled"] is False
    assert manager.calls == []


def test_enabled_registers_daily_and_weekly_cron(monkeypatch):
    monkeypatch.setenv("NAJA_GEO_RISK_ENABLE", "1")
    jobs._REGISTERED.clear()

    class FakeManager:
        def __init__(self):
            self.calls = []

        def add_scheduler_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    manager = FakeManager()
    result = jobs.register_jobs(manager=manager)
    assert result["registered"] == ["geo_risk_collect", "geo_risk_daily", "geo_risk_weekly"]
    assert len(manager.calls) == 3

    collect_args, collect_kw = manager.calls[0]
    assert collect_args[0] == "geo_risk_collect"
    assert collect_kw["hour"] == 7 and collect_kw["minute"] == 0

    daily_args, daily_kw = manager.calls[1]
    assert daily_args[0] == "geo_risk_daily"
    assert daily_kw["hour"] == 7 and daily_kw["minute"] == 30

    weekly_args, weekly_kw = manager.calls[2]
    assert weekly_args[0] == "geo_risk_weekly"
    assert weekly_kw["day_of_week"] == "mon"
    assert weekly_kw["hour"] == 9 and weekly_kw["minute"] == 0


def test_disabled_refuses_to_create_production_db(monkeypatch, tmp_path):
    monkeypatch.delenv("NAJA_GEO_RISK_ENABLE", raising=False)
    with pytest.raises(RuntimeError, match="NAJA_GEO_RISK_ENABLE"):
        run_daily(db=None, report_dir=tmp_path / "x")
