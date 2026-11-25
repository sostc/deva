"""
英文财经媒体 RSS（东南亚视角）

feed 地址需现场确认；抓不到的源要计入 errors 并在日报里体现，
不允许静默返回空。
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple, Union

from .base import RawItem
from .rss import fetch_feed, parse_feed

FEEDS: Dict[str, str] = {
    "the_edge": "https://www.theedgemalaysia.com/rss/news",
    "dealstreetasia": "https://www.dealstreetasia.com/feed",
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
}


def parse(xml_text: str, source: str) -> List[RawItem]:
    return parse_feed(xml_text, source)


def fetch_all(feeds: Union[Dict[str, str], Sequence[Tuple[str, str]]] | None = None,
              *, timeout: float = 15.0) -> Tuple[List[RawItem], Dict[str, str]]:
    pairs = list((feeds or FEEDS).items()) if isinstance(feeds, dict) else list(feeds or FEEDS.items())
    items: List[RawItem] = []
    errors: Dict[str, str] = {}
    for source, url in pairs:
        try:
            items.extend(fetch_feed(url, source, timeout=timeout))
        except Exception as exc:  # noqa: BLE001
            errors[source] = f"{type(exc).__name__}: {exc}"
    return items, errors
