"""时点基本面序列（point-in-time fundamentals）。

为什么必须「时点」
------------------
估值分位要拿**今天**的 PE 和**过去**的 PE 比。如果历史 PE 用了当时还没
公布的财报，回测会凭空多出超额收益，实盘一定打脸。所以每个基本面点都
带 ``as_of``，取的是**公告日**（A 股 ``NOTICE_DATE``、美股 ``filed``），
而不是报告期末。

TTM 的两种算法
--------------
- **A 股**：东财给的是年初至今**累计值**。TTM = 本期累计 + 上年全年 − 上年同期累计。
- **美股**：SEC 给的是单季值。TTM = 最近连续四季之和（校验季度首尾相接）。

两条路都输出同一个 :class:`FundamentalPoint`，下游不用关心市场差异。
缺失一律是 ``None``，**绝不填 0** —— 银行没有毛利率、ETF 没有财报，
"0%" 和 "没这个数" 在打分里是完全不同的含义。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from deva.naja.infra.observability.fleet_registry import KIND_DATASOURCE, probe

log = logging.getLogger(__name__)

_SEC_HEADERS = {"User-Agent": "Naja Research Agent naja@example.com"}


@dataclass
class FundamentalPoint:
    """某一天「市场已经知道」的基本面。"""

    as_of: str                      # 公告日 YYYY-MM-DD（可见时间）
    period_end: str                 # 报告期截止日 YYYY-MM-DD
    eps_ttm: Optional[float] = None
    bps: Optional[float] = None
    net_profit_ttm: Optional[float] = None
    equity: Optional[float] = None
    revenue_ttm: Optional[float] = None
    cashflow_ttm: Optional[float] = None
    gross_margin: Optional[float] = None
    source: str = ""
    basis: str = ""                 # ttm / fy / cumulative

    @property
    def roe(self) -> Optional[float]:
        """TTM 净资产收益率（%）。equity 缺失或为负时不猜。"""
        if self.net_profit_ttm is None or not self.equity or self.equity <= 0:
            return None
        return self.net_profit_ttm / self.equity * 100.0

    @property
    def cash_conversion(self) -> Optional[float]:
        """经营现金流 / 净利润。>1 说明利润能收到现金。"""
        if self.cashflow_ttm is None or not self.net_profit_ttm:
            return None
        if abs(self.net_profit_ttm) < 1e-9:
            return None
        return self.cashflow_ttm / self.net_profit_ttm


# ---------------------------------------------------------------- A 股


def _a_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _type_of(report_date: str, report_type: str = "") -> str:
    """把东财的 ``REPORT_TYPE``（一季报/中报/三季报/年报）归一到 Q1/H1/Q3/FY。"""
    t = (report_type or "").strip()
    if t in ("一季报", "Q1"):
        return "Q1"
    if t in ("中报", "半年报", "H1"):
        return "H1"
    if t in ("三季报", "Q3"):
        return "Q3"
    if t in ("年报", "FY"):
        return "FY"
    md = str(report_date)[5:10]
    return {"03-31": "Q1", "06-30": "H1", "09-30": "Q3", "12-31": "FY"}.get(md, "")


def a_share_series(rows: Iterable[Any]) -> List[FundamentalPoint]:
    """把东财的累计报表序列变成时点 TTM 序列。

    Args:
        rows: :class:`StockFinancial` 列表（需带 ``eps``/``bps``/``equity``/
            ``notice_date``/``report_type``；老数据缺这些字段时该方法退化为
            「只用年报」，并把 ``basis`` 标成 ``fy``）。
    """
    by_key: Dict[Tuple[int, str], Any] = {}
    for r in rows:
        d = _a_date(getattr(r, "period_end", "") or getattr(r, "report_date", ""))
        if d is None:
            continue
        typ = _type_of(d.isoformat(), getattr(r, "report_type", "") or "")
        if not typ:
            continue
        # 同一报告期可能被重述，保留最后一条（列表本身已按报告期倒序，先到先得）
        by_key.setdefault((d.year, typ), r)

    def _val(row, name: str) -> Optional[float]:
        if row is None:
            return None
        v = getattr(row, name, None)
        if v is None:
            return None
        missing = getattr(row, "missing", None) or []
        if name in missing:
            return None
        return float(v)

    points: Dict[str, FundamentalPoint] = {}
    for (year, typ), row in by_key.items():
        period_end = (getattr(row, "period_end", "") or getattr(row, "report_date", ""))[:10]
        notice = (getattr(row, "notice_date", "") or "")[:10]
        if not notice:
            # 没有公告日就按行业惯例推后 45 天，并标记 basis 以提示这是估计值
            d = _a_date(period_end)
            notice = (d + timedelta(days=45)).isoformat() if d else period_end

        np_now = _val(row, "net_profit")
        eps_now = _val(row, "eps")
        rev_now = _val(row, "revenue")
        cf_now = _val(row, "cashflow")

        basis = "ttm"
        if typ == "FY" or np_now is None:
            np_ttm, eps_ttm, rev_ttm, cf_ttm = np_now, eps_now, rev_now, cf_now
            basis = "fy" if typ == "FY" else "cumulative"
        else:
            prev_fy = by_key.get((year - 1, "FY"))
            prev_same = by_key.get((year - 1, typ))
            np_prev_fy, np_prev_same = _val(prev_fy, "net_profit"), _val(prev_same, "net_profit")
            if np_prev_fy is None or np_prev_same is None:
                np_ttm = None
            else:
                np_ttm = np_now + np_prev_fy - np_prev_same

            eps_prev_fy, eps_prev_same = _val(prev_fy, "eps"), _val(prev_same, "eps")
            eps_ttm = (
                eps_now + eps_prev_fy - eps_prev_same
                if None not in (eps_now, eps_prev_fy, eps_prev_same)
                else None
            )
            rev_prev_fy, rev_prev_same = _val(prev_fy, "revenue"), _val(prev_same, "revenue")
            rev_ttm = (
                rev_now + rev_prev_fy - rev_prev_same
                if None not in (rev_now, rev_prev_fy, rev_prev_same)
                else None
            )
            cf_prev_fy, cf_prev_same = _val(prev_fy, "cashflow"), _val(prev_same, "cashflow")
            cf_ttm = (
                cf_now + cf_prev_fy - cf_prev_same
                if None not in (cf_now, cf_prev_fy, cf_prev_same)
                else None
            )

        points[notice] = FundamentalPoint(
            as_of=notice,
            period_end=period_end,
            eps_ttm=eps_ttm,
            bps=_val(row, "bps"),
            net_profit_ttm=np_ttm,
            equity=_val(row, "equity"),
            revenue_ttm=rev_ttm,
            cashflow_ttm=cf_ttm,
            gross_margin=_val(row, "gross_margin"),
            source="eastmoney",
            basis=basis,
        )
    return sorted(points.values(), key=lambda p: p.as_of)


# ---------------------------------------------------------------- 美股


def _quarterly(facts: Dict[str, Any], tag: str, unit: str) -> List[Dict[str, Any]]:
    """抽取单季数据，并补齐 Q4。

    两个坑，都必须处理：

    1. **十年报只给全年**：美股 10-K 里没有「第四季度」这个单季数，
       于是 Q3（10 月末）和次年 Q1（1 月末）之间会空出 92 天，
       连续四季的滚动窗口全部断裂。
    2. **重述**：同一区间可能有多条（原始 + 修订），取 ``filed`` 最新的。

    修法：Q4 = 全年 − (Q1+Q2+Q3)。这是标准做法，且只用到公开数字，
    没有引入任何估算。
    """
    raw = (facts.get(tag, {}).get("units", {}) or {}).get(unit, []) or []

    def _span(r) -> Optional[int]:
        start, end = r.get("start"), r.get("end")
        if not start or not end:
            return None
        try:
            return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        except ValueError:
            return None

    picked: Dict[Tuple[str, str], Dict[str, Any]] = {}
    annual: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in raw:
        span = _span(r)
        if span is None:
            continue
        key = (str(r["start"]), str(r["end"]))
        target = picked if 80 <= span <= 100 else (annual if 350 <= span <= 380 else None)
        if target is None:
            continue
        prev = target.get(key)
        if prev is None or str(r.get("filed", "")) >= str(prev.get("filed", "")):
            target[key] = r

    quarters = [
        {
            "start": k[0],
            "end": k[1],
            "val": float(v.get("val") or 0.0),
            "filed": str(v.get("filed") or ""),
        }
        for k, v in picked.items()
    ]
    quarters.sort(key=lambda x: x["end"])

    # 补 Q4：找相邻两季之间的空档，用「全年 − 前三季」填
    filled: List[Dict[str, Any]] = []
    for cur in quarters:
        if filled:
            prev = filled[-1]
            try:
                gap = (date.fromisoformat(cur["start"]) - date.fromisoformat(prev["end"])).days
            except ValueError:
                gap = 0
            if gap > 7:
                q4 = _synth_q4(annual, quarters, prev, cur)
                if q4:
                    filled.append(q4)
        filled.append(cur)

    # 尾巴上的 Q4：最新一季后面没有「下一季」来触发补洞，
    # 但它同样缺（10-K 只报全年）。用最近的财年末补一次。
    if filled:
        last = filled[-1]
        tail = _synth_tail_q4(annual, quarters, last)
        if tail:
            filled.append(tail)
    return filled


def _synth_tail_q4(
    annual: Dict[Tuple[str, str], Dict[str, Any]],
    quarters: List[Dict[str, Any]],
    last: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """末尾季度之后紧跟财年末时，补出该财年的 Q4。"""
    candidates = []
    for (_start, end), _row in annual.items():
        try:
            delta = (date.fromisoformat(end) - date.fromisoformat(last["end"])).days
        except ValueError:
            continue
        if 0 < delta <= 100:
            candidates.append(end)
    if not candidates:
        return None
    fy_end = min(candidates)
    fake_next = {"start": (date.fromisoformat(fy_end) + timedelta(days=1)).isoformat()}
    return _synth_q4(annual, quarters, last, fake_next)


def _synth_q4(
    annual: Dict[Tuple[str, str], Dict[str, Any]],
    quarters: List[Dict[str, Any]],
    prev: Dict[str, Any],
    nxt: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """用全年数减去同财年前三季，补出第四季度。"""
    try:
        want_end = date.fromisoformat(nxt["start"]) - timedelta(days=1)
    except ValueError:
        return None
    fy = None
    for (start, end), row in annual.items():
        try:
            if abs((date.fromisoformat(end) - want_end).days) <= 4 and start <= prev["start"]:
                fy = row
                break
        except ValueError:
            continue
    if fy is None:
        return None
    inside = [
        q for q in quarters
        if str(fy["start"]) <= q["start"] and q["end"] <= str(fy["end"])
    ]
    if not inside:
        return None
    val = float(fy.get("val") or 0.0) - sum(q["val"] for q in inside)
    return {
        "start": (date.fromisoformat(prev["end"]) + timedelta(days=1)).isoformat(),
        "end": want_end.isoformat(),
        "val": val,
        "filed": str(fy.get("filed") or ""),
    }


def _point_in_time_value(series: Sequence[Dict[str, Any]], as_of: str) -> Optional[float]:
    """取 ``filed <= as_of`` 的最后一条（避免用到未来才公布的数）。"""
    best = None
    for r in series:
        if str(r.get("filed", "")) <= as_of:
            best = r
    return None if best is None else float(best.get("val") or 0.0)


def _rolling_sum(quarters: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """连续四季求和 → {end: {val, filed, start}}。季度断档则不产点（宁缺勿凑）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for i in range(3, len(quarters)):
        window = quarters[i - 3: i + 1]
        contiguous = True
        for prev, cur in zip(window, window[1:]):
            try:
                gap = (date.fromisoformat(cur["start"]) - date.fromisoformat(prev["end"])).days
            except ValueError:
                contiguous = False
                break
            if gap > 4:          # 允许周末/节假日
                contiguous = False
                break
        if not contiguous:
            continue
        end = window[-1]["end"]
        out[end] = {
            "val": sum(q["val"] for q in window),
            "filed": window[-1]["filed"],
            "start": window[0]["start"],
        }
    return out


@probe(KIND_DATASOURCE, "ds:points_sec", "时点基本面：SEC companyfacts", cadence="按需/缓存")
def us_series(symbol: str, companyfacts: Optional[Dict[str, Any]] = None) -> List[FundamentalPoint]:
    """美股时点序列：季度 EPS/净利/现金流滚动 12 个月 + 每股净资产。

    ``companyfacts`` 可注入（测试用），不给则按 CIK 拉 SEC。
    """
    if companyfacts is None:
        from ..structural_growth.financial_data_fetcher import _get_cik

        cik = _get_cik(symbol.upper())
        if cik is None:
            return []
        import requests

        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json"
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=20)
        if resp.status_code != 200:
            return []
        companyfacts = resp.json()

    gaap = (companyfacts.get("facts", {}) or {}).get("us-gaap", {}) or {}
    dei = (companyfacts.get("facts", {}) or {}).get("dei", {}) or {}
    if not gaap:
        return []

    # EPS 有多套口径，优先稀释后（更保守）
    eps_q: List[Dict[str, Any]] = []
    for tag in ("EarningsPerShareDiluted", "EarningsPerShareBasic"):
        eps_q = _quarterly(gaap, tag, "USD/shares")
        if eps_q:
            break
    if not eps_q:
        return []

    ni_q = _quarterly(gaap, "NetIncomeLoss", "USD")
    rev_q: List[Dict[str, Any]] = []
    for tag in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"):
        rev_q = _quarterly(gaap, tag, "USD")
        if rev_q:
            break
    cf_q = _quarterly(gaap, "NetCashProvidedByUsedInOperatingActivities", "USD")

    eps_ttm = _rolling_sum(eps_q)
    ni_ttm = _rolling_sum(ni_q) if ni_q else {}
    rev_ttm = _rolling_sum(rev_q) if rev_q else {}
    cf_ttm = _rolling_sum(cf_q) if cf_q else {}

    equity_series = sorted(
        [
            {"end": r.get("end"), "val": float(r.get("val") or 0), "filed": str(r.get("filed") or "")}
            for r in (gaap.get("StockholdersEquity", {}).get("units", {}) or {}).get("USD", [])
            if r.get("end") and r.get("val") is not None
        ],
        key=lambda x: x["end"],
    )
    shares_series = sorted(
        [
            {"end": r.get("end"), "val": float(r.get("val") or 0), "filed": str(r.get("filed") or "")}
            for r in (dei.get("EntityCommonStockSharesOutstanding", {}).get("units", {}) or {}).get("shares", [])
            if r.get("end") and r.get("val")
        ],
        key=lambda x: x["end"],
    )

    points: List[FundamentalPoint] = []
    for end, eps_info in sorted(eps_ttm.items()):
        as_of = str(eps_info.get("filed") or "")[:10]
        if not as_of:
            continue
        equity = _point_in_time_value(equity_series, as_of)
        shares = _point_in_time_value(shares_series, as_of)
        bps = equity / shares if equity and shares else None
        np_ttm = (ni_ttm.get(end) or {}).get("val")
        rev = (rev_ttm.get(end) or {}).get("val")
        cf = (cf_ttm.get(end) or {}).get("val")
        gm = None
        if rev and rev > 0:
            gp_q = _quarterly(gaap, "GrossProfit", "USD")
            gp_ttm = _rolling_sum(gp_q).get(end) if gp_q else None
            if gp_ttm:
                gm = gp_ttm["val"] / rev * 100.0
        points.append(
            FundamentalPoint(
                as_of=as_of,
                period_end=end,
                eps_ttm=float(eps_info["val"]),
                bps=bps,
                net_profit_ttm=np_ttm,
                equity=equity,
                revenue_ttm=rev,
                cashflow_ttm=cf,
                gross_margin=gm,
                source="sec",
                basis="ttm",
            )
        )
    # 同一公告日通常同时披露「本期 + 上年同期」。按公告日去重，保留**报告期最新**
    # 的那条，否则时点查询可能拿到一年前的旧数（同一 filed 下顺序不稳定）。
    by_as_of: Dict[str, FundamentalPoint] = {}
    for p in points:
        prev = by_as_of.get(p.as_of)
        if prev is None or p.period_end > prev.period_end:
            by_as_of[p.as_of] = p
    return sorted(by_as_of.values(), key=lambda p: p.as_of)


def latest_before(points: Sequence[FundamentalPoint], as_of: str) -> Optional[FundamentalPoint]:
    """取 ``as_of`` 当天或之前最近的可见基本面点。"""
    best = None
    for p in points:
        if p.as_of <= as_of:
            best = p
    return best
