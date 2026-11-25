"""
实体解析：别名归一 + 文本命中

只做「文本里出现了哪个已知实体」，不做推断、不查网络。
索引来源是 P1 的 `entity` 表（canonical_name + aliases）。
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class EntityMatch:
    entity_id: str
    term: str        # 命中的原始别名
    kind: str
    start: int
    end: int

    def to_dict(self) -> Dict:
        return {
            "entity_id": self.entity_id,
            "term": self.term,
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
        }


def normalize_text(text: str) -> str:
    """NFKC + 小写 + 标点归一（只保留字母/数字/汉字）"""
    s = unicodedata.normalize("NFKC", text or "").lower().replace("&", " and ")
    out = []
    for ch in s:
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


class EntityIndex:
    """别名索引。长别名优先，避免 `STT` 把 `STT GDC` 切碎。"""

    def __init__(self, entities: Iterable[Dict]):
        self._terms: List[Tuple[str, str, str]] = []  # (归一别名, entity_id, kind)
        for e in entities:
            aliases = e.get("aliases") or []
            if isinstance(aliases, str):
                try:
                    aliases = json.loads(aliases)
                except Exception:
                    aliases = []
            names = [e.get("canonical_name") or ""] + list(aliases)
            for name in names:
                norm = normalize_text(name)
                if len(norm) < 2:
                    continue
                self._terms.append((norm, e["entity_id"], e.get("kind") or ""))
        self._terms.sort(key=lambda x: -len(x[0]))

    @classmethod
    def from_db(cls, db) -> "EntityIndex":
        rows = db.query("SELECT entity_id, kind, canonical_name, aliases FROM entity")
        return cls([dict(r) for r in rows])

    def match(self, text: str) -> List[EntityMatch]:
        hay = f" {normalize_text(text)} "
        taken: List[Tuple[int, int]] = []
        hits: List[EntityMatch] = []
        for norm, entity_id, kind in self._terms:
            needle = f" {norm} "
            start = hay.find(needle)
            while start != -1:
                s, e = start + 1, start + len(needle) - 1
                if not any(not (e <= a or s >= b) for a, b in taken):
                    taken.append((s, e))
                    hits.append(EntityMatch(entity_id, norm, kind, s, e))
                start = hay.find(needle, start + 1)
        return hits

    def entity_ids(self, text: str) -> List[str]:
        return sorted({m.entity_id for m in self.match(text)})
