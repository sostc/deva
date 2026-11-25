"""
采集结果入库：**只落 P1 的 evidence 表**，不另存原始副本

- 每条 RawItem 必须先解析出已知实体，才允许写 evidence；
  解不出来的计入 `unresolved`，不新建表、不塞进别处。
- 去重键与 evidence 表的 UNIQUE 完全一致（content_hash + subject + url）。
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Sequence

from deva.naja.geo_risk.collectors.base import RawItem

QUOTE_MAX = 800


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _subject(hits, index) -> str:
    """优先监管机构，其次按命中词长度降序，保证同一输入选择稳定。"""
    ordered = sorted(hits, key=lambda h: (0 if h.kind == "regulator" else 1, -len(h.term), h.entity_id))
    return ordered[0].entity_id


def persist_items(db, items: Sequence[RawItem], index, *, subject_type: str = "entity") -> Dict[str, int]:
    stats = {"fetched": len(items), "stored": 0, "duplicates": 0, "unresolved": 0}
    rows: List[Dict[str, Any]] = []

    for item in items:
        hits = index.match(f"{item.title} {item.body}")
        if not hits:
            stats["unresolved"] += 1
            continue

        subject_id = _subject(hits, index)
        quote = (item.title + (f" — {item.body}" if item.body else ""))[:QUOTE_MAX]
        content_hash = _sha256(f"{item.url}\n{quote}")

        exists = db.scalar(
            "SELECT 1 FROM evidence WHERE content_hash = ? AND subject_type = ?"
            " AND subject_id = ? AND url = ?",
            (content_hash, subject_type, subject_id, item.url),
        )
        if exists:
            stats["duplicates"] += 1
            continue

        rows.append({
            "evidence_id": f"ev_{item.source}_{item.external_id or content_hash[:12]}_{subject_id}",
            "subject_type": subject_type,
            "subject_id": subject_id,
            "source": item.source,
            "url": item.url,
            "published_at": item.published_at or None,
            "quote": quote,
            "content_hash": content_hash,
            "event_hint": item.event_hint or None,
        })

    if rows:
        db.add_evidence(rows).result()
        stats["stored"] = len(rows)
    return stats
