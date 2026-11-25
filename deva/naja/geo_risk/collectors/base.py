"""
采集层公共类型与最小 HTTP

只负责「把远端条目变成 RawItem」，不做实体解析、不做入库判断——
入库统一在 `ingest.persist_items`，保证抓到的东西只落 P1 的 evidence 表。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

USER_AGENT = "naja-geo-risk/0.1 (research monitor; low frequency)"


@dataclass
class RawItem:
    source: str
    url: str
    title: str
    published_at: str = ""
    body: str = ""
    external_id: str = ""
    event_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source, "url": self.url, "title": self.title,
            "published_at": self.published_at, "body": self.body,
            "external_id": self.external_id, "event_hint": self.event_hint,
        }


def http_get_json(url: str, params: Mapping[str, Any], *, timeout: float = 15.0) -> Dict[str, Any]:
    """GET 一个 JSON 端点（只读）。调用方负责频率与重试，这里不重试。"""
    body = http_get_text(url, params, timeout=timeout)
    return json.loads(body)


def http_get_text(url: str, params: Mapping[str, Any] | None = None, *, timeout: float = 15.0) -> str:
    """GET 文本（JSON / RSS / HTML），只读。"""
    query = urllib.parse.urlencode(params or {}, doseq=True)
    full = f"{url}?{query}" if query else url
    req = urllib.request.Request(full, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json, application/rss+xml, application/atom+xml, text/html;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")
