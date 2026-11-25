"""
跨来源归并：把「同一件事的多次提及」聚成一个项目事件

原则：
1. **可解释**——每一对提及的得分、命中的分量、是否被否决，全部留痕（pairwise_log）。
2. **可回溯**——归并结果保留每个 mention 的 source / url / evidence_id，不合并掉出处。
3. **可复现**——纯函数输入输出，不落中间状态；聚类是 evidence 的派生视图，
   不新增表，因此不涉及冻结字段变更。

字段冲突的取舍规则：source_priority（官方 > 项目公告 > 融资新闻 > 媒体），
同档再按 published_at 新者优先，全部候选连同出处一起记在 field_decisions。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from deva.naja.geo_risk.entities.resolver import EntityIndex
from deva.naja.geo_risk.events.models import Cluster, Mention
from deva.naja.geo_risk.events.normalizer import days_between, jaccard, name_similarity, parse_dt, tokens


@dataclass
class MergeRules:
    sim_threshold: float = 0.50
    window_days: float = 30.0
    weight_entity: float = 0.40
    weight_name: float = 0.40
    weight_location: float = 0.20


#: 来源分档：越小越权威
_SOURCE_RANKS = (
    (("regulator", "operator", "filing", "company"), 0),
    (("project_announcement", "project"), 1),
    (("financing", "bank", "lender"), 2),
    (("media", "news", "press"), 3),
)


def source_rank(source: str) -> int:
    s = (source or "").lower()
    for keywords, rank in _SOURCE_RANKS:
        if any(k in s for k in keywords):
            return rank
    return 4


def _ts(value: str) -> float:
    dt = parse_dt(value)
    return dt.timestamp() if dt else 0.0


class _UnionFind:
    def __init__(self, ids: Iterable[str]):
        self._parent = {i: i for i in ids}

    def find(self, x: str) -> str:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


def _pair_score(a: Mention, b: Mention, ea: Set[str], eb: Set[str],
                rules: MergeRules) -> Dict[str, Any]:
    """返回一对提及的判定：score 为加权和，veto 非空表示硬否决。"""
    detail: Dict[str, Any] = {
        "a": a.mention_id,
        "b": b.mention_id,
        "score": 0.0,
        "merged": False,
        "veto": "",
        "components": {},
    }

    # 1) 显式项目主键：相同直接归并，不同直接否决
    if a.project_id and b.project_id:
        if a.project_id == b.project_id:
            detail.update(score=1.0, merged=True, components={"project_id": 1.0})
            return detail
        detail.update(veto="project_id_conflict")
        return detail

    # 2) 地域否决：都给了国家且不同 → 不可能是同一个项目
    if a.country and b.country and a.country.upper() != b.country.upper():
        detail.update(veto="country_conflict")
        return detail

    # 3) 站点否决：都给了站点且词元几乎不重合
    if a.site and b.site:
        site_sim = jaccard(tokens(a.site), tokens(b.site))
        detail["components"]["site"] = round(site_sim, 3)
        if site_sim < 0.2:
            detail.update(veto="site_conflict")
            return detail

    # 4) 时间窗
    delta = days_between(a.published_at, b.published_at)
    detail["components"]["days"] = round(delta, 1) if delta is not None else None
    if delta is not None and delta > rules.window_days:
        detail.update(veto="outside_time_window")
        return detail

    # 5) 分量
    if ea and eb:
        ent = 1.0 if (ea & eb) else 0.0
    elif ea or eb:
        ent = 0.5
    else:
        ent = 0.0
    name = name_similarity(a.project_name or a.title, b.project_name or b.title)

    if a.country and b.country:
        country = 1.0
    elif a.country or b.country:
        country = 0.5
    else:
        country = 0.5
    loc = country

    score = (rules.weight_entity * ent
             + rules.weight_name * name
             + rules.weight_location * loc)
    detail["components"].update(
        entity=round(ent, 3), name=round(name, 3), location=round(loc, 3),
        weights=f"ent={rules.weight_entity} name={rules.weight_name} loc={rules.weight_location}",
    )
    detail["score"] = round(score, 3)
    detail["merged"] = score >= rules.sim_threshold
    return detail


def _auto_project_id(members: Sequence[Mention], entities: Set[str]) -> str:
    """无显式主键时，用「实体 + 国家 + 名称词元」派生稳定主键（同一输入必得同一 id）"""
    names = " ".join(sorted({m.project_name or m.title for m in members}))
    countries = sorted({m.country.upper() for m in members if m.country})
    key = f"{'|'.join(sorted(entities))}#{'/'.join(countries)}#{'|'.join(sorted(tokens(names)))}"
    return "prj_auto_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


def _decide_fields(members: Sequence[Mention]) -> Dict[str, Dict[str, Any]]:
    """冲突字段取舍：来源权威度优先，其次 published_at 新者优先，候选全留。"""
    decided: Dict[str, Dict[str, Any]] = {}
    all_fields = sorted({k for m in members for k in m.fields})
    for f in all_fields:
        candidates = [
            {
                "value": m.fields[f],
                "source": m.source,
                "mention_id": m.mention_id,
                "evidence_id": m.evidence_id,
                "published_at": m.published_at,
                "rank": source_rank(m.source),
            }
            for m in members if f in m.fields
        ]
        candidates.sort(key=lambda c: (c["rank"], -_ts(c["published_at"]), str(c["value"])))
        chosen = candidates[0]
        decided[f] = {
            "selected": chosen["value"],
            "rule": "source_priority(rank 小者优先) → published_at 新者优先",
            "selected_from": {"mention_id": chosen["mention_id"], "source": chosen["source"]},
            "candidates": candidates,
        }
    return decided


def cluster_mentions(mentions: Sequence[Mention], index: EntityIndex,
                     rules: MergeRules | None = None) -> List[Cluster]:
    """把提及聚成项目事件。纯函数，重复调用结果一致。"""
    rules = rules or MergeRules()
    if not mentions:
        return []

    entity_sets: Dict[str, Set[str]] = {}
    for m in mentions:
        ids = set(index.entity_ids(f"{m.title} {m.text} {m.project_name}"))
        if m.operator_entity_id:
            ids.add(m.operator_entity_id)
        entity_sets[m.mention_id] = ids

    uf = _UnionFind([m.mention_id for m in mentions])
    logs: Dict[str, List[Dict[str, Any]]] = {m.mention_id: [] for m in mentions}

    for i, a in enumerate(mentions):
        for b in mentions[i + 1:]:
            detail = _pair_score(a, b, entity_sets[a.mention_id], entity_sets[b.mention_id], rules)
            logs[a.mention_id].append(detail)
            logs[b.mention_id].append(detail)
            if detail["merged"]:
                uf.union(a.mention_id, b.mention_id)

    groups: Dict[str, List[Mention]] = {}
    for m in mentions:
        groups.setdefault(uf.find(m.mention_id), []).append(m)

    clusters: List[Cluster] = []
    seen_detail = set()
    for members in groups.values():
        pairs = sorted(
            (d for m in members for d in logs[m.mention_id] if d["merged"]),
            key=lambda d: (d["a"], d["b"]),
        )
        # 去重（同一对被记了两次）
        uniq = [d for d in pairs if not (d["a"], d["b"]) in seen_detail]
        seen_detail.update((d["a"], d["b"]) for d in uniq)

        entities = sorted(set().union(*[entity_sets[m.mention_id] for m in members]))
        explicit = [m.project_id for m in members if m.project_id]
        project_id = explicit[0] if explicit else _auto_project_id(members, set(entities))

        if len(members) == 1:
            confidence = 0.50
            reasons = ["单来源，无可比对项"]
        else:
            mean = sum(d["score"] for d in uniq) / len(uniq) if uniq else 0.0
            sources = len({m.source for m in members})
            bonus = min(0.2, 0.1 * (sources - 1))
            confidence = min(0.98, mean + bonus)
            reasons = [
                f"平均相似度 {mean:.2f}",
                f"{len(members)} 条提及来自 {sources} 个不同来源",
                f"阈值 {rules.sim_threshold}",
            ]

        cluster_id = "clu_" + hashlib.sha256(
            "|".join(sorted(m.mention_id for m in members)).encode("utf-8")
        ).hexdigest()[:10]

        clusters.append(Cluster(
            cluster_id=cluster_id,
            project_id=project_id,
            mentions=list(members),
            entities=entities,
            confidence=confidence,
            confidence_reasons=reasons,
            field_decisions=_decide_fields(members),
            pairwise_log=uniq,
        ))

    return sorted(clusters, key=lambda c: c.cluster_id)
