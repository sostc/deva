#!/usr/bin/env python3
"""基本面探针：财报 + 估值分位 + 档位，一张表核对。

用法：
    python3 scripts/fundamental_probe.py                # 自动从 QueryState 取持仓
    python3 scripts/fundamental_probe.py 000001 nvda    # 指定标的

三块内容：
1. **财报对账单**：期数、来源、营收/净利/毛利/capex（与东财、SEC 页面逐项核对）
2. **估值分位**：自个算的 TTM PE/PB 在自身 5 年历史中的分位，以及 EPS 口径与
   可见日期（as_of 是公告日，不是报告期末）
3. **档位**：质量/估值/风险三段得分 → A/B/C/D，以及该档位对正 T 的仓位系数

``python3`` 直接跑可能在退出时卡在 sqlitedict 的非 daemon 线程上，脚本末尾
用 ``os._exit`` 收尾。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deva.naja.fundamental import get_fundamental_service  # noqa: E402


def _holdings_from_api() -> list[str]:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8080/api/query/state", timeout=5
        ) as resp:
            data = json.load(resp).get("data", {})
        held = (data.get("portfolio_state") or {}).get("held_symbols") or []
        return [str(s) for s in held]
    except Exception:
        return []


def _fmt(value: float, unit: str = "亿", scale: float = 1e8) -> str:
    if not value:
        return "—"
    return f"{value / scale:.1f}{unit}"


def main() -> int:
    symbols = sys.argv[1:] or _holdings_from_api() or ["000001", "nvda", "588200"]
    svc = get_fundamental_service()

    print(f"标的：{', '.join(symbols)}")
    print(f"落库：{svc.store.db_path}\n")

    status = svc.refresh(symbols, force=True)

    header = (
        f"{'标的':<8}{'期数':>4}  {'最新报告期':<12}{'来源':<10}"
        f"{'营收':>10}{'同比':>8}{'净利':>10}{'毛利':>7}{'现金流':>10}{'capex':>8}"
    )
    print(header)
    print("-" * len(header.encode("gbk", errors="ignore")))
    for symbol, info in status.items():
        if not info.get("ok"):
            print(f"{symbol:<8}{0:>4}  {info.get('reason')}")
            continue
        snap = svc.snapshot(symbol) or {}
        print(
            f"{symbol:<8}{info['periods']:>4}  "
            f"{snap.get('period_end') or snap.get('period', ''):<12}"
            f"{snap.get('source', ''):<10}"
            f"{_fmt(snap.get('revenue')):>10}"
            f"{snap.get('revenue_yoy', 0):>+7.1f}%"
            f"{_fmt(snap.get('net_profit')):>10}"
            f"{(str(round(snap.get('gross_margin', 0), 1)) + '%') if snap.get('has_gross_margin') else '—':>7}"
            f"{_fmt(snap.get('cashflow')):>10}"
            f"{_fmt(snap.get('capex')):>8}"
        )
        flags = []
        if snap.get("missing"):
            flags.append("缺 " + "/".join(snap["missing"]))
        if snap.get("stale"):
            flags.append(f"数据 {snap.get('age_days')} 天未更新")
        if flags:
            print(f"{'':<8}  ↳ {'；'.join(flags)}")

    print("\n库状态：", json.dumps(svc.stats(), ensure_ascii=False))

    print("\n" + "=" * 78)
    print("估值与档位")
    print("=" * 78)
    head = (
        f"{'标的':<8}{'档位':>4}{'总分':>6}{'PE':>8}{'PE分位':>8}{'PB':>7}{'PB分位':>8}"
        f"{'ROE':>7}{'现金转化':>8}  {'EPS口径@可见日':<20}"
    )
    print(head)
    for symbol in symbols:
        try:
            e = svc.evaluate(symbol)
        except Exception as exc:  # noqa: BLE001
            print(f"{symbol:<8}  评估失败: {exc}")
            continue
        v = e.get("valuation") or {}
        f = e.get("fundamental") or {}

        def _num(x, digits=2):
            return "—" if x is None else f"{x:.{digits}f}"

        def _pct(x):
            return "—" if x is None else f"{x * 100:.0f}%"

        basis = f"{f.get('basis') or '—'}@{f.get('as_of') or '—'}"
        print(
            f"{symbol:<8}{e.get('tier', 'NA'):>4}{e.get('total', 0):>6.1f}"
            f"{_num(v.get('pe'), 1):>8}{_pct(v.get('pe_percentile')):>8}"
            f"{_num(v.get('pb')):>7}{_pct(v.get('pb_percentile')):>8}"
            f"{_num(f.get('roe'), 1):>7}{_num(f.get('cash_conversion')):>8}  {basis:<20}"
        )
        notes = list(v.get("caveats") or []) + list((e.get("score") or {}).get("caveats") or [])
        if notes:
            print(f"{'':<8}  ↳ {'；'.join(notes)}")
        flags = (e.get("score") or {}).get("flags") or []
        if flags:
            print(f"{'':<8}  ↳ 风险标记：{', '.join(flags)}")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        sys.stdout.flush()
    os._exit(0)
