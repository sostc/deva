"""geo_risk 生产采集编排守卫。

❗判据钉在「事实链路真的通了」，不是「函数存在」：
  - collectors → extract → evidence → series 串起来；
  - 抽取不到字段时 series 里必须没有该 metric（不许 0 伪装）；
  - daily 能从 series 读到模型输入并真的评级；
  - 单源失败不影响其它源，且失败被统计出来（不许静默）。
"""

from __future__ import annotations

import json

import pytest

from deva.naja.geo_risk.collectors.base import RawItem
from deva.naja.geo_risk.jobs.daily import run_daily
from deva.naja.geo_risk import pipeline as pipeline_mod
from deva.naja.geo_risk.pipeline import run_pipeline
from deva.naja.geo_risk.seeds.p1_seed import PROJECTS, load_seed
from deva.naja.geo_risk.store.db import get_db

SNAPSHOT = {
    "gpu_count": 2000,
    "monthly_rent_per_gpu_usd": 1800.0,
    "utilization": 0.9,
    "china_linked_share": 0.5,
    "annual_debt_service_usd": 30_000_000.0,
    "debt_usd": 20_000_000.0,
    "gpu_models": [{"model": "H100", "count": 2000, "age_months": 18}],
    "dimensions": {"policy": 20, "utilization": 20, "price": 20},
}


@pytest.fixture
def db(tmp_path):
    d = get_db(tmp_path / "geo.db")
    load_seed(d)
    yield d
    d.close()


class FakeExtractor:
    def __init__(self, fields):
        self.fields = fields

    async def extract(self, article):
        return {
            "fields": {**self.fields}, "source": "llm", "degraded": False,
            "confidence": 0.9, "error": None, "skipped": None, "cache_key": "x",
            "breaker": {},
        }


def _patch_collector(monkeypatch, items):
    """把 loader 换成真返回 RawItem 的假采集器，测编排而非 import 机制。"""
    monkeypatch.setattr(
        pipeline_mod, "_run_one_collector",
        lambda source_id, module_path, func_name: list(items),
    )


def test_pipeline_wires_collect_extract_evidence(db, monkeypatch):
    """采集 → 抽取 → evidence 真的落库，不是各测各的。"""
    before = db.count("evidence")
    item = RawItem(
        source="unit_test", url="https://example.test/a1",
        title="YTL Power Johor data centre expansion",
        body="YTL Power announces 300 MW campus in Johor",
        published_at="2026-11-25T10:00:00+08:00",
        external_id="a1",
    )
    _patch_collector(monkeypatch, [item])

    stats = run_pipeline(
        db=db,
        collectors=(("unit_test", "__fake__", "fetch"),),
        extractor=FakeExtractor({"project_name": "YTL Johor AI Data Centre Campus"}),
    )
    assert stats["fetched"] == 1
    assert stats["stored"] == 1, "抽取后的证据没落库，编排是断的"
    assert db.count("evidence") == before + 1


def test_pipeline_writes_only_real_fields_to_series(db, monkeypatch):
    """抽到的字段写 series；没抽到的 metric 必须不存在（不许填 0）。"""
    item = RawItem(
        source="unit_test", url="https://example.test/a2",
        title="YTL Power Johor expansion capacity 300 MW",
        body="YTL Power 300 MW campus", external_id="a2",
    )
    _patch_collector(monkeypatch, [item])
    stats = run_pipeline(
        db=db,
        collectors=(("unit_test", "__fake__", "fetch"),),
        extractor=FakeExtractor({
            "project_name": "YTL Johor AI Data Centre Campus",
            "capacity_mw": 300.0,
            "gpu_count": None,  # ❗没抽到，绝不能写 0
        }),
    )
    assert stats["series"] == 1, f"应只写 1 条真实字段: {stats}"
    vals = db.latest_series(PROJECTS[0]["project_id"])
    assert "capacity_mw" in vals
    assert "gpu_count" not in vals, "缺失字段被写进 series —— 伪装成事实"


def test_pipeline_records_source_failure_without_crashing(db, monkeypatch):
    """单源失败不能拖垮整批，且失败必须被统计（静默失败比异常更毒）。"""
    def _boom(source_id, module_path, func_name):
        raise RuntimeError("源挂了")

    monkeypatch.setattr(pipeline_mod, "_run_one_collector", _boom)
    stats = run_pipeline(
        db=db,
        collectors=(("broken", "__fake__", "fetch"),),
        extractor=FakeExtractor({}),
    )
    assert stats["failed_sources"], "采集失败没有留痕"
    assert all("broken" in f for f in stats["failed_sources"])


def test_daily_uses_series_as_model_input(db, tmp_path):
    """series 有完整模型输入时，日更必须真的评级（不是永远未评级）。"""
    pid = PROJECTS[0]["project_id"]
    rows = []
    for key in ("gpu_count", "monthly_rent_per_gpu_usd", "utilization",
                "china_linked_share", "annual_debt_service_usd", "debt_usd"):
        rows.append({
            "series_id": f"2026-11-25|{pid}|{key}|unit_test",
            "project_id": pid, "metric": key, "as_of": "2026-11-25",
            "value": str(SNAPSHOT[key]), "source_id": "unit_test", "quality": "unit",
        })
    for key in ("gpu_models", "dimensions"):
        rows.append({
            "series_id": f"2026-11-25|{pid}|{key}|unit_test",
            "project_id": pid, "metric": key, "as_of": "2026-11-25",
            "value": json.dumps(SNAPSHOT[key]), "source_id": "unit_test",
            "quality": "unit",
        })
    db.add_series(rows).result()

    result = run_daily(as_of="2026-11-25", db=db, report_dir=tmp_path / "reports")
    text = (tmp_path / "reports" / "2026-11-25.md").read_text(encoding="utf-8")
    assert result["stats"]["rated"] >= 1, f"series 有输入却没评级: {text[:500]}"
    assert "未评级" in text  # 其它项目仍应明确报缺
