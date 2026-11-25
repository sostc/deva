"""
BIS（美国商务部工业与安全局）新闻稿采集。

BIS 站点是 Next.js 应用：原来的 RSS 端点（``/news-updates/rss.xml``）现在
**返回 HTML，而不是 XML**——真正的新闻稿列表被内联在 ``<script id="__NEXT_DATA__">``
的 JSON 里（``props.pageProps.pressReleaseTeasers``）。所以这里不再走 RSS 解析，
而是抽取这份内联 JSON。

❗抓取失败必须显式抛错，不能返回空列表——否则「看起来每天都没有新政策」。
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any, Dict, List

from .base import RawItem, http_get_text

#: 该端点现在返回 Next.js 页面；数据在内联 __NEXT_DATA__ 里。
FEED_URL = "https://www.bis.gov/news-updates/rss.xml"
BASE_URL = "https://www.bis.gov"

_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean(text: str, limit: int = 1000) -> str:
    return _WS.sub(" ", unescape(_TAG.sub(" ", text or ""))).strip()[:limit]


def _iso(published_on: Any) -> str:
    if isinstance(published_on, dict):
        return str(published_on.get("time") or "")
    return str(published_on or "")


def extract_next_data(html_text: str) -> Dict[str, Any]:
    """从 Next.js 页面里抽出内联 JSON（纯函数）。"""
    m = _NEXT_DATA.search(html_text)
    if not m:
        raise ValueError("BIS 页面里没有 __NEXT_DATA__，站点结构可能又变了")
    return json.loads(m.group(1))


def parse_teasers(payload: Dict[str, Any]) -> List[RawItem]:
    """把 __NEXT_DATA__ 里的 pressReleaseTeasers 转成 RawItem（纯函数）。"""
    teasers = payload.get("props", {}).get("pageProps", {}).get("pressReleaseTeasers") or []
    items: List[RawItem] = []
    for t in teasers:
        title = str(t.get("title") or "").strip()
        path = str(t.get("path") or "").strip()
        if not title or not path:
            continue
        body = _clean((t.get("body") or {}).get("processed") or "")
        topics = []
        for tp in t.get("newsUpdatesTopic") or []:
            name = str(tp.get("name") or "").strip()
            if name:
                topics.append(name)
        hint = f"bis_{topics[0].lower().replace(' ', '_')}" if topics else "bis_press_release"
        items.append(RawItem(
            source="bis",
            url=f"{BASE_URL}{path}",
            title=title,
            published_at=_iso(t.get("publishedOn")),
            body=body,
            external_id=str(t.get("uuid") or t.get("id") or ""),
            event_hint=hint,
        ))
    return items


def parse(xml_text: str) -> List[RawItem]:
    """兼容旧签名：对返回的 HTML 做同样的抽取。"""
    return parse_teasers(extract_next_data(xml_text))


def fetch_documents(*, timeout: float = 20.0) -> List[RawItem]:
    html = http_get_text(FEED_URL, timeout=timeout)
    items = parse_teasers(extract_next_data(html))
    if not items:
        raise RuntimeError("BIS 抓到了页面但没有任何新闻稿条目（结构可能变化）")
    return items
