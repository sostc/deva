"""事件层数据结构"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Mention:
    """一条「某来源在某个时间说了某件事」的原始提及。

    所有字段都必须能回溯到 P1 的 evidence（evidence_id / source / url / published_at）。
    """

    mention_id: str
    title: str
    source: str
    url: str = ""
    published_at: str = ""
    text: str = ""
    project_id: str = ""
    project_name: str = ""
    country: str = ""
    site: str = ""
    operator_entity_id: str = ""
    evidence_id: str = ""
    fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mention_id": self.mention_id,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "country": self.country,
            "site": self.site,
            "operator_entity_id": self.operator_entity_id,
            "evidence_id": self.evidence_id,
            "fields": dict(self.fields),
        }


@dataclass
class Cluster:
    """一个归并后的事件 = 一个项目。成员全部保留原始出处。"""

    cluster_id: str
    project_id: str
    mentions: List[Mention]
    entities: List[str]
    confidence: float
    confidence_reasons: List[str]
    field_decisions: Dict[str, Dict[str, Any]]
    pairwise_log: List[Dict[str, Any]]

    @property
    def evidence_refs(self) -> List[Dict[str, Any]]:
        return [
            {
                "mention_id": m.mention_id,
                "evidence_id": m.evidence_id,
                "source": m.source,
                "url": m.url,
                "title": m.title,
                "published_at": m.published_at,
            }
            for m in self.mentions
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "project_id": self.project_id,
            "entities": list(self.entities),
            "confidence": round(self.confidence, 3),
            "confidence_reasons": list(self.confidence_reasons),
            "field_decisions": self.field_decisions,
            "evidence_refs": self.evidence_refs,
            "pairwise_log": self.pairwise_log,
        }
