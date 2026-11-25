"""
P3 采集层（Federal Register）验收：参数构造 / 解析 / 入库 / 去重

全部用离线样例，不打网络；真实抓取另有 smoke，不写生产库。
"""

import pytest

from deva.naja.geo_risk.collectors import (
    build_params, parse_documents, persist_items,
)
from deva.naja.geo_risk.entities import EntityIndex
from deva.naja.geo_risk.seeds import load_seed
from deva.naja.geo_risk.store import GeoRiskDB

SAMPLE = {
    "count": 2,
    "results": [
        {
            "document_number": "2026-12345",
            "title": "Export Controls on Advanced Computing Items",
            "abstract": "BIS amends the Export Administration Regulations for advanced computing.",
            "publication_date": "2026-11-20",
            "html_url": "https://www.federalregister.gov/d/2026-12345",
            "agencies": [{"raw_name": "Bureau of Industry and Security",
                          "name": "Industry and Security Bureau"}],
            "type": "rule",
        },
        {
            "document_number": "2026-99999",
            "title": "Fisheries of the Exclusive Economic Zone Off Alaska",
            "abstract": "NMFS announces a closure.",
            "publication_date": "2026-11-19",
            "html_url": "https://www.federalregister.gov/d/2026-99999",
            "agencies": [{"raw_name": "National Oceanic and Atmospheric Administration",
                          "name": "National Oceanic and Atmospheric Administration"}],
            "type": "notice",
        },
    ],
}


@pytest.fixture
def db(tmp_path):
    d = GeoRiskDB(tmp_path / "geo_risk.db")
    load_seed(d)
    yield d
    d.close()


def test_build_params():
    p = build_params(term="export controls", agencies=("industry-and-security-bureau",),
                     since="2026-10-01", per_page=5)
    assert p["conditions[term]"] == "export controls"
    assert p["conditions[agencies][]"] == ["industry-and-security-bureau"]
    assert p["conditions[publication_date][gte]"] == "2026-10-01"
    assert p["order"] == "newest" and p["per_page"] == 5
    assert "document_number" in p["fields[]"] and "agencies" in p["fields[]"]


def test_parse_documents():
    items = parse_documents(SAMPLE)
    assert len(items) == 2
    first = items[0]
    assert first.source == "federal_register"
    assert first.external_id == "2026-12345"
    assert first.published_at == "2026-11-20"
    assert "Bureau of Industry and Security" in first.body
    assert first.event_hint == "policy_rule"
    assert first.url.endswith("/2026-12345")


def test_persist_lands_in_evidence_table(db):
    idx = EntityIndex.from_db(db)
    stats = persist_items(db, parse_documents(SAMPLE), idx)
    assert stats == {"fetched": 2, "stored": 1, "duplicates": 0, "unresolved": 1}

    rows = db.query("SELECT subject_type, subject_id, source, url, quote FROM evidence"
                    " WHERE source = 'federal_register'")
    assert len(rows) == 1
    assert rows[0]["subject_type"] == "entity"
    assert rows[0]["subject_id"] == "ent_bis"
    assert "Export Controls" in rows[0]["quote"]
    # 不在 P1 表结构之外另存一份证据副本；series 是 P3 模型输入时序，不是证据副本
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"entity", "project", "evidence"} <= tables
    assert "evidence_copy" not in tables


def test_persist_is_idempotent(db):
    idx = EntityIndex.from_db(db)
    first = persist_items(db, parse_documents(SAMPLE), idx)
    second = persist_items(db, parse_documents(SAMPLE), idx)
    assert second["stored"] == 0
    assert second["duplicates"] == 1
    kept = db.scalar("SELECT COUNT(*) FROM evidence WHERE source = 'federal_register'")
    assert kept == first["stored"] == 1


def test_unresolved_is_counted_not_stored(db):
    idx = EntityIndex.from_db(db)
    items = parse_documents({"results": [SAMPLE["results"][1]]})
    stats = persist_items(db, items, idx)
    assert stats["unresolved"] == 1 and stats["stored"] == 0
    assert db.scalar("SELECT COUNT(*) FROM evidence WHERE source = 'federal_register'") == 0
