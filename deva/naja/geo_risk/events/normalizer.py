"""文本归一与相似度：只做可解释的词元重合，不用向量。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable, Optional, Set

from deva.naja.geo_risk.entities.resolver import normalize_text

#: 去掉不携带项目区分度的通用词（留 gpu / thailand 这类区分词）
STOPWORDS = {
    "the", "a", "an", "of", "for", "and", "to", "in", "on", "with", "by",
    "data", "center", "centre", "campus", "project", "ai", "new", "phase",
    "announces", "announce", "announcement", "unveils", "unveiled", "secures",
    "secured", "live", "one", "inc", "ltd", "berhad",
}

_WORD = re.compile(r"[a-z0-9]+")
_CJK = re.compile(r"[\u4e00-\u9fff]+")


def tokens(text: str) -> Set[str]:
    s = normalize_text(text)
    out: Set[str] = set()
    for m in _WORD.finditer(s):
        w = m.group()
        if w not in STOPWORDS:
            out.add(w)
    for m in _CJK.finditer(s):
        seg = m.group()
        if len(seg) == 1:
            out.add(seg)
        else:
            out.update(seg[i:i + 2] for i in range(len(seg) - 1))
    return out


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def name_similarity(a: str, b: str) -> float:
    return jaccard(tokens(a), tokens(b))


def parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def days_between(a: str, b: str) -> Optional[float]:
    da, db = parse_dt(a), parse_dt(b)
    if not da or not db:
        return None
    try:
        return abs((da - db).total_seconds()) / 86400.0
    except TypeError:  # 一个带时区一个不带
        return None
