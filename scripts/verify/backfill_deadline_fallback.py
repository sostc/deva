#!/usr/bin/env python3
"""补记历史「收盘兜底放行」事件到决策面板计数。

背景
----
面板的「已批准 / 已否决」数的是 DecisionJournal 里的 DecisionPlan.approved。
底仓补仓在决策否决后、距收盘 ≤30 分钟由 CoreEstablishGate 按预案真实买入，
这条路径在 journal 里仍是 approved=False，面板因此解释不了这类成交。
新留痕表 ``naja_deadline_fallback_journal`` 从 2026-11-26 起才在线记录，
本脚本把之前的历史兜底成交补进去。

数据来源与判据（两条独立证据必须同时成立）
------------------------------------------
1. ``~/.naja/futu_sim_orders/claimed/*_core_*.json`` 的下单时间落在
   该市场收盘前 30 分钟窗口内（用 ``minutes_to_close`` 判定，非简单钟点）；
2. ``~/.naja/futu_sim_orders/orders.jsonl`` 里同标的、2 分钟内有一条
   ``side=buy`` 且 ``ok=true`` 的真实成交。

按 ``(标的, 交易日)`` 去重 —— 收盘前每 30 秒轮询多次放行，但一个标的
一个交易日只算一次「走过兜底」。

用法
----
    python3 scripts/verify/backfill_deadline_fallback.py            # dry-run
    python3 scripts/verify/backfill_deadline_fallback.py --apply    # 真正写入

重复执行安全：ledger 按 (code, trade_date) 去重，已有记录会跳过。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from deva.naja.bandit.market_session import minutes_to_close, session_date  # noqa: E402
from deva.naja.decision.fallback_ledger import (  # noqa: E402
    get_deadline_fallback_ledger,
)

CLAIMED_DIR = Path.home() / ".naja/futu_sim_orders/claimed"
ORDERS_LOG = Path.home() / ".naja/futu_sim_orders/orders.jsonl"
WINDOW_MIN = 30.0
MATCH_TOLERANCE_S = 120.0


def _load_orders() -> list:
    out = []
    if not ORDERS_LOG.exists():
        return out
    with ORDERS_LOG.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def derive_events() -> tuple[list, list]:
    """返回 ``(候选事件, 被排除的 core 订单)``。"""
    orders = _load_orders()
    grouped = defaultdict(list)
    excluded = []

    if not CLAIMED_DIR.exists():
        return [], []

    for path in sorted(CLAIMED_DIR.glob("*.json")):
        if "_core_" not in path.name:
            continue
        parts = path.name.replace(".json", "").split("_")
        if len(parts) < 3:
            continue
        market, symbol = parts[1], parts[2]
        try:
            claimed_at = json.loads(path.read_text(encoding="utf-8")).get("claimed_at", 0)
        except Exception:
            continue
        if not claimed_at:
            continue
        dt = datetime.fromtimestamp(claimed_at)
        mtc = minutes_to_close(market, dt)
        trade_date = session_date(market, dt)
        if mtc is None or not (0 <= mtc <= WINDOW_MIN):
            excluded.append((dt, market, symbol, mtc))
            continue
        grouped[(symbol.upper(), trade_date)].append((dt, mtc, claimed_at, market))

    events = []
    for (symbol, trade_date), items in grouped.items():
        items.sort()
        first_ts = items[0][2]
        matched = [
            o for o in orders
            if str(o.get("symbol", "")).upper() == symbol
            and o.get("side") == "buy"
            and o.get("ok") is True
            and abs(float(o.get("ts", 0)) - first_ts) <= MATCH_TOLERANCE_S
        ]
        if not matched:
            excluded.append((items[0][0], items[0][3], symbol, -1))
            continue
        buy = min(matched, key=lambda o: abs(float(o.get("ts", 0)) - first_ts))
        events.append({
            "code": symbol,
            "name": "",
            "trade_date": trade_date,
            "trade_at": first_ts,
            "qty": float(buy.get("quantity", 0) or 0),
            "price": float(buy.get("price", 0) or 0),
            "reason": (f"历史补记：收盘前 {items[0][1]:.0f} 分钟按最小档兜底买入，"
                       f"当日共 {len(items)} 笔 core 报单"),
            "size_hint": 0.0,
            "orders": len(items),
            "order_id": str(buy.get("order_id", "")),
        })
    events.sort(key=lambda e: (e["trade_date"], e["code"]))
    return events, excluded


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="真正写入留痕表（默认 dry-run）")
    args = ap.parse_args()

    events, excluded = derive_events()
    print(f"候选兜底事件: {len(events)}；排除: {len(excluded)}\n")
    print(f"{'交易日':<12}{'标的':<9}{'笔数':<6}{'成交时刻':<10}{'数量':>10}  {'价格':>8}")
    print("-" * 62)
    for e in events:
        time_str = datetime.fromtimestamp(e["trade_at"]).strftime("%H:%M")
        print(f"{e['trade_date']:<12}{e['code']:<9}{e['orders']:<6}"
              f"{time_str:<10}"
              f"{e['qty']:>10.0f}  {e['price']:>8.3f}")
    if excluded:
        print("\n排除明细（不在收盘前 30 分钟窗口 / 无成交交叉验证）:")
        for dt, market, sym, mtc in sorted(excluded):
            print(f"  {dt:%m-%d %H:%M:%S} {market} {sym} mtc={mtc}")

    if not args.apply:
        print("\n[dry-run 完成，未写入任何数据；加 --apply 才真正写入]")
        return 0

    ledger = get_deadline_fallback_ledger()
    before = ledger.count()
    added = 0
    for e in events:
        ts = ledger.record_backfill(**{k: v for k, v in e.items()
                                       if k not in ("orders", "order_id")})
        if ts is not None:
            added += 1
    after = ledger.count()
    print(f"\n写入完成: 新增 {added} 条，计数 {before} → {after}")
    if after - before != added:
        print("⚠️ 计数增量与新增条数不一致，请检查留痕表状态")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
