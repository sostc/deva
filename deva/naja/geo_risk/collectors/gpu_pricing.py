"""
GPU 租赁价格页解析（HTML）

真实站点没有 API，且每家页面结构不同：这里的解析器只认「货币金额 + 时间单位」
这一最小可验证模式，并保留价格前 60 字符作为上下文（用来匹配运营商实体）。

❗抓不到价格时返回空列表；调用方必须把它当「本日价格缺失」记录下来，
不能当成「价格没变」。
"""

from __future__ import annotations

import re
from html import unescape
from typing import List

from .base import RawItem

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
#: $2.49/hr、USD 2.49 / hour、$199/month …
_PRICE = re.compile(
    r"(?:\$|USD)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/|per|\s)\s*(hour|hr|month|mo|月)\b",
    re.IGNORECASE,
)


def _plain(text: str) -> str:
    return _WS.sub(" ", unescape(_TAG.sub(" ", text or ""))).strip()


def parse_prices(html: str, *, source: str = "gpu_pricing", url: str = "",
                 published_at: str = "") -> List[RawItem]:
    plain = _plain(html)
    items: List[RawItem] = []
    for idx, m in enumerate(_PRICE.finditer(plain)):
        amount, unit = m.group(1), m.group(2).lower()
        context = plain[max(0, m.start() - 60):m.start()].strip()
        items.append(RawItem(
            source=source,
            url=f"{url}#price-{idx}" if url else f"price://{idx}",
            title=f"GPU 租赁价格 {amount} USD/{unit}",
            published_at=published_at,
            body=context,
            external_id=f"{url}#price-{idx}" if url else f"price-{idx}",
            event_hint="gpu_rental_price",
        ))
    return items


def fetch_prices(url: str, *, source: str = "gpu_pricing", timeout: float = 15.0,
                 published_at: str = "") -> List[RawItem]:
    from .base import http_get_text

    return parse_prices(http_get_text(url, timeout=timeout), source=source,
                        url=url, published_at=published_at)
