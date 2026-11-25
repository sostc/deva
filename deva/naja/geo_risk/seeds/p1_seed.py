"""
P1 种子数据 —— **仅用于验证存储层与「同一项目跨来源是同一件事」，不是生产事实**

所有证据的 url 都是 ``fixture://``，不会指向任何真实网页；运营商/项目/容量
也是示例值，不得进入生产库、不得被当成事实引用。

这套数据要证明的事：
    prj_ytl_johor 同时出现在「融资新闻」和「运营商公告」两条不同来源的证据里，
    但 subject_id 相同 —— 下游只需要按 (subject_type, subject_id) 聚合，
    就能把两篇报道识别成同一个项目，而不是两条互不相干的新闻。
"""

from __future__ import annotations

from typing import Any, Dict

ENTITIES: list[Dict[str, Any]] = [
    {
        "entity_id": "ent_ytl_power",
        "kind": "company",
        "canonical_name": "YTL Power International Berhad",
        "country": "MY",
        "ticker": "6742.KL",
        "aliases": ["YTL Power", "杨忠礼电力", "YTLP"],
    },
    {
        "entity_id": "ent_bridge_dc",
        "kind": "company",
        "canonical_name": "Bridge Data Centres",
        "country": "MY",
        "aliases": ["Bridge DC", "BDC", "桥数据中心"],
    },
    {
        "entity_id": "ent_stt_gdc",
        "kind": "company",
        "canonical_name": "ST Telemedia Global Data Centres",
        "country": "SG",
        "aliases": ["STT GDC", "STT"],
    },
    {
        "entity_id": "ent_digital_edge",
        "kind": "company",
        "canonical_name": "Digital Edge DC",
        "country": "SG",
        "aliases": ["Digital Edge", "DE DC"],
    },
    {
        "entity_id": "ent_pdg",
        "kind": "company",
        "canonical_name": "Princeton Digital Group",
        "country": "SG",
        "aliases": ["PDG", "普林斯顿数字集团"],
    },
    {
        "entity_id": "ent_dayone",
        "kind": "company",
        "canonical_name": "DayOne Data Centers",
        "country": "SG",
        "aliases": ["DayOne", "DayOne DC"],
    },
    {
        "entity_id": "ent_nvidia",
        "kind": "company",
        "canonical_name": "NVIDIA Corporation",
        "country": "US",
        "ticker": "NVDA",
        "aliases": ["NVIDIA", "英伟达"],
    },
    {
        "entity_id": "ent_coreweave",
        "kind": "company",
        "canonical_name": "CoreWeave, Inc.",
        "country": "US",
        "ticker": "CRWV",
        "aliases": ["CoreWeave", "CRWV"],
    },
    {
        "entity_id": "ent_dbs",
        "kind": "bank",
        "canonical_name": "DBS Bank Ltd",
        "country": "SG",
        "aliases": ["DBS", "星展银行"],
    },
    {
        "entity_id": "ent_bis",
        "kind": "regulator",
        "canonical_name": "Bureau of Industry and Security",
        "country": "US",
        "aliases": ["BIS", "美国工业与安全局"],
    },
]

PROJECTS: list[Dict[str, Any]] = [
    {
        "project_id": "prj_ytl_johor",
        "operator_entity_id": "ent_ytl_power",
        "name": "YTL Johor AI Data Centre Campus",
        "site": "Kulai, Johor",
        "country": "MY",
        "state": "Johor",
        "capacity_mw": 300.0,
        "gpu_count": None,
        "customer_mix": {"china_linked": None, "note": "fixture：客户结构待核实"},
        "financing_refs": ["fx_prj_ytl_johor_syndicated"],
        "status": "fixture_operating",
    },
    {
        "project_id": "prj_bridge_johor",
        "operator_entity_id": "ent_bridge_dc",
        "name": "Bridge Data Centres Johor Campus",
        "site": "Kulai, Johor",
        "country": "MY",
        "state": "Johor",
        "capacity_mw": 120.0,
        "gpu_count": None,
        "customer_mix": {"china_linked": None, "note": "fixture：客户结构待核实"},
        "financing_refs": [],
        "status": "fixture_operating",
    },
    {
        "project_id": "prj_stt_johor",
        "operator_entity_id": "ent_stt_gdc",
        "name": "STT GDC Johor Campus",
        "site": "Johor",
        "country": "MY",
        "state": "Johor",
        "capacity_mw": 100.0,
        "gpu_count": None,
        "customer_mix": {"china_linked": None},
        "financing_refs": [],
        "status": "fixture_operating",
    },
    {
        "project_id": "prj_de_batam",
        "operator_entity_id": "ent_digital_edge",
        "name": "Digital Edge Batam Campus",
        "site": "Batam",
        "country": "ID",
        "state": None,
        "capacity_mw": 80.0,
        "gpu_count": None,
        "customer_mix": {"china_linked": None},
        "financing_refs": [],
        "status": "fixture_operating",
    },
    {
        "project_id": "prj_pdg_jakarta",
        "operator_entity_id": "ent_pdg",
        "name": "PDG Jakarta Campus",
        "site": "Jakarta",
        "country": "ID",
        "state": None,
        "capacity_mw": 60.0,
        "gpu_count": None,
        "customer_mix": {"china_linked": None},
        "financing_refs": [],
        "status": "fixture_operating",
    },
]

EVIDENCE: list[Dict[str, Any]] = [
    # —— prj_ytl_johor：同一项目，两条不同来源 ——
    {
        "evidence_id": "ev_ytl_fin_01",
        "subject_type": "project",
        "subject_id": "prj_ytl_johor",
        "source": "fixture.financing_news",
        "url": "fixture://geo-risk/financing/ytl-johor-2026-11",
        "published_at": "2026-11-05T09:00:00+08:00",
        "quote": "银团为柔佛 AI 数据中心提供项目融资（fixture 示例，非真实报道）",
        "event_hint": "project_financing",
    },
    {
        "evidence_id": "ev_ytl_ops_01",
        "subject_type": "project",
        "subject_id": "prj_ytl_johor",
        "source": "fixture.operator_announcement",
        "url": "fixture://geo-risk/operator/ytl-johor-2026-11",
        "published_at": "2026-11-06T18:00:00+08:00",
        "quote": "运营商公告：柔佛园区一期投运（fixture 示例，非真实公告）",
        "event_hint": "project_commissioning",
    },
    # —— prj_bridge_johor：融资 + 政策两条来源 ——
    {
        "evidence_id": "ev_bridge_fin_01",
        "subject_type": "project",
        "subject_id": "prj_bridge_johor",
        "source": "fixture.financing_news",
        "url": "fixture://geo-risk/financing/bridge-johor-2026-11",
        "published_at": "2026-11-07T10:30:00+08:00",
        "quote": "Bridge 柔佛园区完成新一轮授信（fixture 示例）",
        "event_hint": "project_financing",
    },
    {
        "evidence_id": "ev_bridge_policy_01",
        "subject_type": "project",
        "subject_id": "prj_bridge_johor",
        "source": "fixture.regulator_rule",
        "url": "fixture://geo-risk/regulation/bis-bridge-2026-11",
        "published_at": "2026-11-08T07:00:00+08:00",
        "quote": "出口管制规则更新，涉及该园区潜在的 GPU 供给路径（fixture 示例）",
        "event_hint": "policy_restriction",
    },
    # —— 其余项目各一条，证明 subject_id 可被不同实体引用 ——
    {
        "evidence_id": "ev_stt_ops_01",
        "subject_type": "project",
        "subject_id": "prj_stt_johor",
        "source": "fixture.operator_announcement",
        "url": "fixture://geo-risk/operator/stt-johor-2026-11",
        "published_at": "2026-11-04T12:00:00+08:00",
        "quote": "STT 柔佛园区扩容公告（fixture 示例）",
        "event_hint": "project_expansion",
    },
    {
        "evidence_id": "ev_de_ops_01",
        "subject_type": "project",
        "subject_id": "prj_de_batam",
        "source": "fixture.operator_announcement",
        "url": "fixture://geo-risk/operator/de-batam-2026-11",
        "published_at": "2026-11-03T15:00:00+08:00",
        "quote": "Digital Edge 巴淡岛园区开工公告（fixture 示例）",
        "event_hint": "project_construction",
    },
    {
        "evidence_id": "ev_pdg_fin_01",
        "subject_type": "project",
        "subject_id": "prj_pdg_jakarta",
        "source": "fixture.financing_news",
        "url": "fixture://geo-risk/financing/pdg-jakarta-2026-11",
        "published_at": "2026-11-02T09:30:00+08:00",
        "quote": "PDG 雅加达园区项目贷款（fixture 示例）",
        "event_hint": "project_financing",
    },
    # —— 实体级证据（规则/母公司与项目分属不同 subject_type）——
    {
        "evidence_id": "ev_bis_rule_01",
        "subject_type": "entity",
        "subject_id": "ent_bis",
        "source": "fixture.regulator",
        "url": "fixture://geo-risk/regulation/bis-affiliated-2026-11",
        "published_at": "2026-11-01T06:00:00+08:00",
        "quote": "BIS 发布 affiliated entities 规则解释（fixture 示例）",
        "event_hint": "policy_rule",
    },
    {
        "evidence_id": "ev_ytl_entity_01",
        "subject_type": "entity",
        "subject_id": "ent_ytl_power",
        "source": "fixture.company_filing",
        "url": "fixture://geo-risk/filing/ytl-power-2026-11",
        "published_at": "2026-11-05T17:00:00+08:00",
        "quote": "YTL Power 季度披露提及数据中心业务（fixture 示例）",
        "event_hint": "company_disclosure",
    },
]


def load_seed(db) -> Dict[str, int]:
    """把种子数据写入给定库并返回条数。**只应写入测试库。**"""
    ent = db.upsert_entities(ENTITIES).result()
    prj = db.upsert_projects(PROJECTS).result()
    ev = db.add_evidence(EVIDENCE).result()
    return {"entities": ent, "projects": prj, "evidence": ev}
