"""Market identity helpers.

Internal market identity is intentionally small:
- ``CN`` for A-share/China equity paths
- ``US`` for US equity paths

Boundary code may still receive legacy names such as ``a_share`` or
``us_share``. Normalize them at the edge before touching market state.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class Market(str, Enum):
    CN = "CN"
    US = "US"


_CN_ALIASES = {
    "CN",
    "A",
    "A_SHARE",
    "ASHARE",
    "CHINA",
    "CHINA_A",
    "SH",
    "SZ",
    "BJ",
}

_US_ALIASES = {
    "US",
    "USA",
    "US_SHARE",
    "USSTOCK",
    "US_STOCK",
    "US_EQUITY",
    "AMERICA",
}


def normalize_market(market: Optional[str], default: str = Market.CN.value) -> str:
    """Normalize market aliases to ``CN`` or ``US``."""
    if market is None:
        return default

    raw = str(market).strip()
    if not raw:
        return default

    upper = raw.upper().replace("-", "_").replace(" ", "_")
    if upper in _CN_ALIASES:
        return Market.CN.value
    if upper in _US_ALIASES:
        return Market.US.value

    lower = raw.lower()
    if lower.startswith("gb_"):
        return Market.US.value
    if lower.startswith(("sh", "sz", "bj")):
        return Market.CN.value

    return default


def to_review_market(market: Optional[str], default: str = "a_share") -> str:
    """Convert a market alias to the legacy daily-review market name."""
    normalized = normalize_market(market, default=Market.CN.value)
    if normalized == Market.US.value:
        return "us_share"
    if normalized == Market.CN.value:
        return "a_share"
    return default
