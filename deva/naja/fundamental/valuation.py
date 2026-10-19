"""估值：把「日线价格」和「时点基本面」拼成 PE/PB 序列，算历史分位。

分位而不是绝对值
----------------
PE 15 倍对银行是贵，对软件是便宜，跨行业不可比；同一家公司 PE 15 倍在
2021 年是低估、在 2025 年可能是高估。所以进入决策的只能是**自身历史分位**。

一条硬规则：**亏损（EPS≤0）不产生 PE**。把负 EPS 算出来的负 PE 混进分位，
会让「巨亏」看起来像「极度便宜」，这是估值分位最常见的坑。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .points import FundamentalPoint, latest_before

log = logging.getLogger(__name__)

#: 分位至少要这么多交易日才有统计意义；不足时给出样本数但不给分位
MIN_SAMPLES = 120


@dataclass
class Valuation:
    symbol: str
    as_of: str = ""                     # 价格日期
    price: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    pe_percentile: Optional[float] = None   # 0~1，越低越便宜
    pb_percentile: Optional[float] = None
    pe_median: Optional[float] = None
    pe_min: Optional[float] = None
    pe_max: Optional[float] = None
    samples: int = 0
    window_years: float = 0.0
    eps_basis: str = ""
    eps_as_of: str = ""
    caveats: List[str] = field(default_factory=list)
    ok: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of,
            "price": self.price,
            "pe": self.pe,
            "pb": self.pb,
            "pe_percentile": self.pe_percentile,
            "pb_percentile": self.pb_percentile,
            "pe_median": self.pe_median,
            "pe_range": [self.pe_min, self.pe_max],
            "samples": self.samples,
            "window_years": self.window_years,
            "eps_basis": self.eps_basis,
            "eps_as_of": self.eps_as_of,
            "caveats": list(self.caveats),
            "ok": self.ok,
        }


def _percentile(values: Sequence[float], current: float) -> Optional[float]:
    if not values or current is None:
        return None
    below = sum(1 for v in values if v <= current)
    return below / len(values)


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def build(
    symbol: str,
    prices: Sequence[Tuple[str, float]],
    points: Sequence[FundamentalPoint],
) -> Valuation:
    """拼出 PE/PB 序列并算当前分位。"""
    v = Valuation(symbol=str(symbol))
    if not prices:
        v.caveats.append("无价格序列")
        return v
    if not points:
        v.caveats.append("无财报数据（ETF/基金或数据源无覆盖）")
        return v

    pe_series: List[float] = []
    pb_series: List[float] = []
    current_pe = current_pb = None
    used_point: Optional[FundamentalPoint] = None

    for day, close in prices:
        p = latest_before(points, day)
        if p is None or not close or close <= 0:
            continue
        used_point = p          # 循环结束时停在「最新价格可见的那个基本面点」
        if p.eps_ttm is not None and p.eps_ttm > 0:
            pe = close / p.eps_ttm
            # 极端值会污染分位（例如 EPS 接近 0 时 PE 上千倍），截断不隐藏
            if 0 < pe < 1000:
                pe_series.append(pe)
                current_pe = pe
        if p.bps is not None and p.bps > 0:
            pb = close / p.bps
            if 0 < pb < 100:
                pb_series.append(pb)
                current_pb = pb

    if used_point is None:
        v.caveats.append("价格区间内没有可见的基本面点")
        return v

    v.as_of = prices[-1][0]
    v.price = prices[-1][1]
    v.pe, v.pb = current_pe, current_pb
    v.samples = len(pe_series)
    v.eps_basis = used_point.basis
    v.eps_as_of = used_point.as_of
    try:
        first = date.fromisoformat(prices[0][0])
        last = date.fromisoformat(prices[-1][0])
        v.window_years = round((last - first).days / 365.25, 2)
    except ValueError:
        v.window_years = 0.0

    if v.samples >= MIN_SAMPLES and current_pe:
        v.pe_percentile = _percentile(pe_series, current_pe)
        v.pe_median = _median(pe_series)
        v.pe_min, v.pe_max = min(pe_series), max(pe_series)
    elif current_pe:
        v.caveats.append(f"PE 样本仅 {v.samples} 天，不给分位")

    if len(pb_series) >= MIN_SAMPLES and current_pb:
        v.pb_percentile = _percentile(pb_series, current_pb)

    if current_pe is None:
        v.caveats.append("EPS 为负或缺失，不产生 PE（亏损不能算「便宜」）")
    if used_point.basis != "ttm":
        v.caveats.append(f"EPS 口径为 {used_point.basis}，非滚动 12 个月")

    v.ok = bool(current_pe or current_pb)
    return v
