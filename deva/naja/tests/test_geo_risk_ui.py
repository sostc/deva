""" /georisk 页面：未启用不建库、只读渲染、评级与跃迁展示。"""

import json

from deva.naja.geo_risk.store.db import GeoRiskDB
from deva.naja.geo_risk.ui import build_html, load_view

PROJECT = {
    "project_id": "prj_ui_test",
    "operator_entity_id": "ent_ui_operator",
    "name": "Batang AI Data Centre",
    "country": "ID",
    "capacity_mw": 240.0,
}
ENTITY = {
    "entity_id": "ent_ui_operator",
    "kind": "company",
    "canonical_name": "UI Test Operator",
}


def test_disabled_shows_not_enabled_and_does_not_create_db(monkeypatch, tmp_path):
    monkeypatch.delenv("NAJA_GEO_RISK_ENABLE", raising=False)
    db_path = tmp_path / "geo.db"
    view = load_view(report_dir=tmp_path / "reports", db_path=db_path)

    assert view["enabled"] is False
    assert view["db_exists"] is False
    assert view["projects"] == []
    assert not db_path.exists()

    html = build_html(view)
    assert "未启用" in html
    assert "NAJA_GEO_RISK_ENABLE" in html


def test_enabled_without_db_shows_empty_state(monkeypatch, tmp_path):
    monkeypatch.setenv("NAJA_GEO_RISK_ENABLE", "1")
    db_path = tmp_path / "geo.db"
    view = load_view(report_dir=tmp_path / "reports", db_path=db_path)

    assert view["enabled"] is True
    assert view["db_exists"] is False
    assert not db_path.exists()

    html = build_html(view)
    assert "库尚未创建" in html


def test_enabled_with_db_renders_projects_and_grades(monkeypatch, tmp_path):
    monkeypatch.setenv("NAJA_GEO_RISK_ENABLE", "1")
    db_path = tmp_path / "geo.db"
    report_dir = tmp_path / "reports"
    state_dir = report_dir / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "ratings.json").write_text(
        json.dumps({
            "version": 1,
            "projects": {
                "prj_ui_test": {"grade": "yellow", "score": 47.5,
                                "updated": "2026-11-23"},
            },
        }),
        encoding="utf-8",
    )
    (report_dir / "2026-11-23.md").write_text("# 日报\n", encoding="utf-8")

    database = GeoRiskDB(db_path)
    try:
        database.upsert_entities([ENTITY]).result()
        database.upsert_projects([PROJECT]).result()
        database.add_evidence([{
            "evidence_id": "ev_ui_1",
            "subject_type": "project",
            "subject_id": "prj_ui_test",
            "source": "fixture.operator_announcement",
            "url": "fixture://geo-risk/ui/1",
            "quote": "运营商公告：园区开工",
        }]).result()
    finally:
        database.close()

    view = load_view(report_dir=report_dir, db_path=db_path)
    assert view["db_exists"] is True
    assert view["latest_report"] == "2026-11-23.md"
    assert len(view["projects"]) == 1
    assert view["projects"][0]["grade"] == "yellow"

    html = build_html(view)
    assert "Batang AI Data Centre" in html
    assert "yellow" in html
    assert "47.50" in html
