"""
通用 RSS / Atom 解析（不依赖第三方库）

BIS 新闻稿与英文媒体都用它；每个来源只差一个 feed URL 和 source 名。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from typing import List, Optional

from .base import RawItem, http_get_text

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> Optional[ET.Element]:
    for c in list(el):
        if _local(c.tag) == name:
            return c
    return None


def _clean_html(text: str, limit: int = 1000) -> str:
    s = unescape(_TAG.sub(" ", text or ""))
    return _WS.sub(" ", s).strip()[:limit]


def _iso(pub: str) -> str:
    if not pub:
        return ""
    try:
        return parsedate_to_datetime(pub).isoformat()
    except Exception:
        return pub


def parse_feed(xml_text: str, source: str) -> List[RawItem]:
    root = ET.fromstring(xml_text)
    items: List[RawItem] = []
    for el in root.iter():
        name = _local(el.tag)
        if name == "item":  # RSS 2.0
            title = _clean_html((_child(el, "title").text or "") if _child(el, "title") is not None else "", 300)
            link_el = _child(el, "link")
            link = (link_el.text or "").strip() if link_el is not None else ""
            guid_el = _child(el, "guid")
            guid = (guid_el.text or "").strip() if guid_el is not None else ""
            body = _clean_html((_child(el, "description").text or "") if _child(el, "description") is not None else "")
            pub = _iso((_child(el, "pubDate").text or "").strip() if _child(el, "pubDate") is not None else "")
            if not title or not (link or guid):
                continue
            items.append(RawItem(source=source, url=link or guid, title=title,
                                 published_at=pub, body=body, external_id=guid or link))
        elif name == "entry":  # Atom
            title = _clean_html((_child(el, "title").text or "") if _child(el, "title") is not None else "", 300)
            link = ""
            for c in list(el):
                if _local(c.tag) == "link" and c.get("href"):
                    link = c.get("href")
                    break
            id_el = _child(el, "id")
            guid = (id_el.text or "").strip() if id_el is not None else ""
            body = _clean_html((_child(el, "summary").text or "") if _child(el, "summary") is not None else "")
            # ❗Element 的真假值取决于「有没有子节点」，不能用 `a or b`，必须显式判 None
            pub_el = _child(el, "updated")
            if pub_el is None:
                pub_el = _child(el, "published")
            pub = (pub_el.text or "").strip() if pub_el is not None else ""
            if not title or not (link or guid):
                continue
            items.append(RawItem(source=source, url=link or guid, title=title,
                                 published_at=pub, body=body, external_id=guid or link))
    return items


def fetch_feed(url: str, source: str, *, timeout: float = 15.0) -> List[RawItem]:
    return parse_feed(http_get_text(url, timeout=timeout), source)
