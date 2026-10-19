#!/usr/bin/env python3
"""基本面打分守卫。

守的是四件最容易悄悄错的事：
1. **TTM 算错**：A 股累计值直接当 TTM、美股 Q4 缺失后硬凑；
2. **用了未来数据**：报告期末就可见（应为公告日）；
3. **亏损被算成便宜**：负 EPS 产生负 PE，混进分位后「巨亏 = 极度低估」；
4. **缺数据被当成满分**：银行没有毛利率，归一化后反而拿满分。

用法：``python3 scripts/verify/verify_fundamental_scoring.py``，退出码 0 = 全过。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from deva.naja.fundamental.points import (  # noqa: E402
    FundamentalPoint,
    _quarterly,
    _rolling_sum,
    a_share_series,
    latest_before,
)
from deva.naja.fundamental.score import allows_dip, score  # noqa: E402
from deva.naja.fundamental.valuation import build  # noqa: E402

failures = []


def _check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def _row(period_end, typ, np_, eps, rev, cf, bps=10.0, equity=1000.0, notice=None):
    return SimpleNamespace(
        stock_code="000001",
        report_date=period_end,
        period_end=period_end,
        report_type=typ,
        notice_date=notice or period_end,
        net_profit=np_,
        eps=eps,
        revenue=rev,
        cashflow=cf,
        bps=bps,
        equity=equity,
        gross_margin=None,
        missing=["gross_margin"],
    )


def test_a_share_ttm():
    """累计值差分：Q3 TTM = Q3本期 + 上年全年 − 上年 Q3。"""
    rows = [
        _row("2026-09-30", "三季报", 90.0, 0.90, 900.0, 120.0, notice="2026-10-25"),
        _row("2026-06-30", "中报", 60.0, 0.60, 600.0, 80.0, notice="2026-08-15"),
        _row("2025-12-31", "年报", 100.0, 1.00, 1000.0, 110.0, notice="2026-03-20"),
        _row("2025-09-30", "三季报", 80.0, 0.80, 800.0, 90.0, notice="2025-10-25"),
    ]
    points = {p.as_of: p for p in a_share_series(rows)}
    q3 = points.get("2026-10-25")
    _check(q3 is not None, "A股 Q3 未生成时点")
    if q3:
        _check(abs(q3.net_profit_ttm - 110.0) < 1e-6,
               f"Q3 TTM 净利应=90+100-80=110，实得 {q3.net_profit_ttm}")
        _check(abs(q3.eps_ttm - 1.10) < 1e-6, f"Q3 TTM EPS 应=1.10，实得 {q3.eps_ttm}")
        _check(q3.basis == "ttm", f"Q3 口径应为 ttm，实得 {q3.basis}")
    fy = points.get("2026-03-20")
    _check(fy is not None and fy.basis == "fy", "年报应直接取当年值，口径标 fy")


def test_no_lookahead():
    """公告日之前不可见：这是回测不虚高的前提。"""
    rows = [
        _row("2026-09-30", "三季报", 90.0, 0.90, 900.0, 120.0, notice="2026-10-25"),
        _row("2025-12-31", "年报", 100.0, 1.00, 1000.0, 110.0, notice="2026-03-20"),
        _row("2025-09-30", "三季报", 80.0, 0.80, 800.0, 90.0, notice="2025-10-25"),
    ]
    points = a_share_series(rows)
    before = latest_before(points, "2026-10-24")
    _check(before is not None and before.as_of == "2026-03-20",
           f"10-24 只应看到年报（03-20），实得 {before.as_of if before else None}")
    after = latest_before(points, "2026-10-25")
    _check(after is not None and after.as_of == "2026-10-25", "公告日当天应可见")


def test_us_q4_synthesis():
    """美股 Q4 不在 10-K 单季里，必须用「全年 − 前三季」补出来。"""
    facts = {
        "EarningsPerShareDiluted": {
            "units": {
                "USD/shares": [
                    # FY2025: Q1 0.5 / Q2 0.6 / Q3 0.7，全年 2.4 → Q4 应为 0.6
                    {"start": "2025-01-27", "end": "2025-04-27", "val": 0.5, "filed": "2025-05-28"},
                    {"start": "2025-04-28", "end": "2025-07-27", "val": 0.6, "filed": "2025-08-27"},
                    {"start": "2025-07-28", "end": "2025-10-26", "val": 0.7, "filed": "2025-11-19"},
                    {"start": "2025-01-27", "end": "2026-01-25", "val": 2.4, "filed": "2026-02-25"},
                ]
            }
        }
    }
    quarters = _quarterly(facts["EarningsPerShareDiluted"] and facts, "EarningsPerShareDiluted", "USD/shares")
    _check(len(quarters) == 4, f"应补出 4 个季度，实得 {len(quarters)}")
    q4 = [q for q in quarters if q["end"] == "2026-01-25"]
    _check(bool(q4), "Q4 未被补出")
    if q4:
        _check(abs(q4[0]["val"] - 0.6) < 1e-6, f"Q4 应=2.4-1.8=0.6，实得 {q4[0]['val']}")
    ttm = _rolling_sum(quarters)
    _check(abs(ttm.get("2026-01-25", {}).get("val", 0) - 2.4) < 1e-6,
           "四季滚动应等于全年 2.4")


def test_loss_has_no_pe():
    """亏损不产生 PE：负 PE 混进分位会让「巨亏」看起来最便宜。"""
    p = FundamentalPoint(as_of="2026-01-01", period_end="2025-12-31",
                         eps_ttm=-1.2, bps=5.0, net_profit_ttm=-100.0, equity=500.0)
    prices = [(f"2026-01-{d:02d}", 10.0) for d in range(2, 28)]
    v = build("TEST", prices, [p])
    _check(v.pe is None, f"负 EPS 不应有 PE，实得 {v.pe}")
    _check(v.pb is not None and abs(v.pb - 2.0) < 1e-6, f"PB 应=10/5=2.0，实得 {v.pb}")
    _check(any("EPS 为负" in c for c in v.caveats), "应显式说明 EPS 为负")


def test_score_tiers():
    good = FundamentalPoint(as_of="2026-01-01", period_end="2025-12-31",
                            eps_ttm=5.0, bps=25.0, net_profit_ttm=200.0,
                            equity=1000.0, revenue_ttm=2000.0, cashflow_ttm=240.0,
                            gross_margin=45.0)
    prices = [(f"2025-{m:02d}-15", 100.0) for m in range(1, 13)] + [
        (f"2026-{m:02d}-15", 60.0) for m in range(1, 13)
    ]
    v = build("GOOD", prices, [good])
    s = score("GOOD", good, v, rev_yoy=20.0, np_yoy=25.0)
    _check(s.tier == "A", f"优质低估应 A 档，实得 {s.tier} total={s.total}")
    _check(allows_dip(s.tier), "A 档应允许逆势低吸")

    loss = FundamentalPoint(as_of="2026-01-01", period_end="2025-12-31",
                            eps_ttm=-1.0, bps=3.0, net_profit_ttm=-50.0, equity=300.0)
    s2 = score("LOSS", loss, None)
    _check(s2.tier == "D", f"亏损应 D 档，实得 {s2.tier}")
    _check(s2.fatal is not None, "亏损应有一票否决原因")
    _check(not allows_dip(s2.tier), "D 档不得抄底")

    s3 = score("ETF", None, None)
    _check(s3.tier == "NA", f"无财报应为 NA，实得 {s3.tier}")
    _check(not allows_dip(s3.tier), "NA 不得冒充合格")


def test_missing_not_full_marks():
    """银行没有毛利率：缺失按满分一半中性填充，不能归一化后拿满分。"""
    bank = FundamentalPoint(as_of="2026-01-01", period_end="2025-12-31",
                            eps_ttm=2.0, bps=20.0, net_profit_ttm=250.0,
                            equity=3000.0, revenue_ttm=1000.0, cashflow_ttm=None,
                            gross_margin=None)
    s = score("BANK", bank, None, rev_yoy=2.0, np_yoy=3.0)
    _check(s.quality <= 45.0, f"缺毛利率+现金流的质量分不应超过 45，实得 {s.quality}")
    _check(any("中性填充" in c for c in s.caveats), "应说明缺失维度按中性填充")


def test_gate_wiring():
    """档位必须真的改变正 T 的准入，否则前面算得再准也没用。"""
    from deva.naja.bandit.t_rotation_runner import TRotationRunner

    class _QS:
        def __init__(self, fund):
            self._fund = fund

        def get_fundamental(self, code):
            return self._fund

    runner = TRotationRunner.__new__(TRotationRunner)

    gate = {"allow_forward": True, "forward_size_scale": 1.0, "dip_ok": True}
    runner._apply_fundamental(gate, "AAA", _QS({"tier": "D", "forward_scale": 0.0, "total": 30}))
    _check(gate["allow_forward"] is False, "D 档必须关闭正 T")
    _check(gate["dip_ok"] is False, "D 档必须关闭抄底许可")

    gate = {"allow_forward": True, "forward_size_scale": 1.0, "dip_ok": True}
    runner._apply_fundamental(gate, "AAA", _QS({"tier": "B", "forward_scale": 0.6,
                                                "allows_dip": True, "total": 65}))
    _check(gate["allow_forward"] is True and abs(gate["forward_size_scale"] - 0.6) < 1e-6,
           f"B 档应放行且乘 0.6，实得 {gate['forward_size_scale']}")

    gate = {"allow_forward": True, "forward_size_scale": 1.0, "dip_ok": True}
    runner._apply_fundamental(gate, "588200", _QS({"tier": "NA", "forward_scale": 0.0}))
    _check(gate["allow_forward"] is True, "ETF（NA）不应被基本面关卡拦住")

    gate = {"allow_forward": True, "forward_size_scale": 1.0, "dip_ok": True}
    runner._apply_fundamental(gate, "AAA", _QS(None))
    _check(abs(gate["forward_size_scale"] - 0.7) < 1e-6,
           f"无基本面结论应打七折，实得 {gate['forward_size_scale']}")


def main() -> int:
    for fn in (
        test_a_share_ttm,
        test_no_lookahead,
        test_us_q4_synthesis,
        test_loss_has_no_pe,
        test_score_tiers,
        test_missing_not_full_marks,
        test_gate_wiring,
    ):
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failures.append(f"{fn.__name__} 抛异常: {type(e).__name__}: {e}")
            print(f"  ✗ {fn.__name__}: {e}")

    if failures:
        print("\n失败项：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
