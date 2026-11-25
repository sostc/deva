"""
P2 事件层验收：别名匹配 + 跨来源合并 + 证据链 + 冲突取舍

核心用例：同一个泰国 GPU 项目，分别出现在
    融资新闻 / 运营商公告 / 数据中心项目公告 里，
必须被识别成 **1 个项目事件**，而不是 3 条独立事件；
并且三条原始出处一条都不能丢，冲突字段要能看出按什么规则取舍。
"""

import pytest

from deva.naja.geo_risk.entities import EntityIndex
from deva.naja.geo_risk.events import MergeRules, Mention, cluster_mentions
from deva.naja.geo_risk.seeds import load_seed
from deva.naja.geo_risk.store import GeoRiskDB


@pytest.fixture
def db(tmp_path):
    d = GeoRiskDB(tmp_path / "geo_risk.db")
    load_seed(d)
    yield d
    d.close()


def _m(mid, title, source, *, country="TH", name="Thailand GPU Campus",
       published="2026-11-05T09:00:00+08:00", text="", fields=None, project_id=""):
    return Mention(
        mention_id=mid,
        title=title,
        source=source,
        url=f"fixture://events/{mid}",
        published_at=published,
        text=text,
        project_id=project_id,
        project_name=name,
        country=country,
        fields=fields or {},
    )


# ------------------------------------------------------------------ 别名匹配
def test_alias_matching(db):
    idx = EntityIndex.from_db(db)

    m = idx.match("杨忠礼电力（YTLP）拟扩建柔佛园区")
    assert {h.entity_id for h in m} == {"ent_ytl_power"}
    assert any(h.term == "杨忠礼电力" or h.term == "ytlp" for h in m)

    assert {h.entity_id for h in idx.match("STT GDC 宣布扩容")} == {"ent_stt_gdc"}
    assert idx.match("一家不知名的本地承包商") == []


# ------------------------------------------- 核心：三来源 → 一个项目事件
def test_three_sources_merge_into_one_project(db):
    idx = EntityIndex.from_db(db)
    mentions = [
        _m("m_fin", "Thai GPU data centre secures project financing",
           "fixture.financing_news", published="2026-11-05T09:00:00+08:00",
           text="DayOne Data Centers' Thailand GPU campus secured a syndicated loan.",
           fields={"capacity_mw": 100, "status": "financing"}),
        _m("m_ops", "DayOne announces Thailand GPU campus phase one live",
           "fixture.operator_announcement", published="2026-11-07T18:00:00+08:00",
           text="Operator DayOne Data Centers said the Thailand GPU campus is live.",
           fields={"capacity_mw": 120, "status": "operating"}),
        _m("m_prj", "New Thailand GPU data centre project unveiled",
           "fixture.project_announcement", published="2026-11-06T11:00:00+08:00",
           text="The project is developed by DayOne Data Centers in Thailand.",
           fields={"capacity_mw": 100}),
    ]

    clusters = cluster_mentions(mentions, idx)
    assert len(clusters) == 1, f"应为 1 个项目事件，实际 {len(clusters)}"

    c = clusters[0]
    assert len(c.mentions) == 3
    assert c.project_id.startswith("prj_auto_")
    assert "ent_dayone" in c.entities
    assert c.confidence >= 0.60

    refs = c.evidence_refs
    assert len(refs) == 3, "必须保留每条证据的原始出处"
    assert {r["source"] for r in refs} == {
        "fixture.financing_news", "fixture.operator_announcement", "fixture.project_announcement",
    }
    assert len({r["url"] for r in refs}) == 3
    assert {r["mention_id"] for r in refs} == {"m_fin", "m_ops", "m_prj"}
    assert c.pairwise_log, "归并判定必须留痕"


def test_conflict_decision_is_explainable(db):
    clusters = cluster_mentions([
        _m("m_fin", "Thai GPU data centre secures financing", "fixture.financing_news",
           published="2026-11-05T09:00:00+08:00", fields={"capacity_mw": 100}),
        _m("m_ops", "Operator announces Thai GPU campus live", "fixture.operator_announcement",
           published="2026-11-07T18:00:00+08:00", fields={"capacity_mw": 120}),
    ], EntityIndex.from_db(db))

    c = clusters[0]
    d = c.field_decisions["capacity_mw"]
    assert d["selected"] == 120, "官方公告应压过融资新闻"
    assert "source_priority" in d["rule"]
    assert d["selected_from"]["source"] == "fixture.operator_announcement"
    assert len(d["candidates"]) == 2, "被弃用的值也要留档，不能只剩结论"
    assert [x["value"] for x in d["candidates"]] == [120, 100]


# ------------------------------------------------------ 不该合并的情形
def test_country_conflict_is_not_merged(db):
    idx = EntityIndex.from_db(db)
    clusters = cluster_mentions([
        _m("m_th", "DayOne Thailand GPU campus live", "fixture.operator_announcement", country="TH"),
        _m("m_my", "DayOne Johor GPU campus live", "fixture.operator_announcement",
           country="MY", name="Johor GPU Campus"),
    ], idx)
    assert len(clusters) == 2
    assert all(len(c.mentions) == 1 for c in clusters)


def test_outside_time_window_is_not_merged(db):
    idx = EntityIndex.from_db(db)
    clusters = cluster_mentions([
        _m("m_a", "Thai GPU campus announced", "fixture.media", published="2026-01-01T00:00:00+08:00"),
        _m("m_b", "Thai GPU campus announced", "fixture.media", published="2026-11-01T00:00:00+08:00"),
    ], idx, MergeRules(window_days=30))
    assert len(clusters) == 2


def test_explicit_project_id_merges_even_if_dates_far(db):
    idx = EntityIndex.from_db(db)
    clusters = cluster_mentions([
        _m("m_a", "Thai GPU campus financing", "fixture.financing_news",
           published="2026-01-01T00:00:00+08:00", project_id="prj_th_gpu"),
        _m("m_b", "Unrelated looking headline", "fixture.operator_announcement",
           published="2026-11-01T00:00:00+08:00", project_id="prj_th_gpu"),
    ], idx)
    assert len(clusters) == 1
    assert clusters[0].project_id == "prj_th_gpu"


def test_deterministic_cluster_ids(db):
    idx = EntityIndex.from_db(db)
    mentions = [
        _m("m1", "Thai GPU campus financing", "fixture.financing_news"),
        _m("m2", "Thai GPU campus live", "fixture.operator_announcement"),
    ]
    a = [c.to_dict() for c in cluster_mentions(mentions, idx)]
    b = [c.to_dict() for c in cluster_mentions(list(reversed(mentions))[::-1], idx)]
    assert a == b, "同一输入（哪怕顺序不同）应得到同一聚类结果"
