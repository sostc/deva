#!/usr/bin/env python3
"""守卫：基本面仓必须「说真话」。

守三件事：
1. 拿不到 → ``snapshot() is None``，不能返回 0 分/中性；
2. 缺失字段 → 记在 ``missing`` 里，毛利率缺失不能被当成 0%；
3. 落库幂等：同一期重复写入只更新，不产生重复行。

用法：
    python3 scripts/verify/verify_fundamental_store.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deva.naja.fundamental import FundamentalService, FundamentalStore  # noqa: E402

failures: list[str] = []


def _check(cond, msg):
    if not cond:
        failures.append(msg)


class _FakeFetcher:
    def __init__(self, rows_by_symbol):
        self.rows = rows_by_symbol
        self.calls = []

    def fetch(self, symbol, force_refresh=False):
        self.calls.append(symbol)
        return list(self.rows.get(symbol, []))


def _row(**kw):
    base = dict(
        stock_code="X", report_date="2026-06-30", period_end="2026-06-30",
        revenue=1e9, revenue_yoy=5.0, net_profit=1e8, net_profit_yoy=3.0,
        gross_margin=0.0, cashflow=1.2e8, capex=0.0,
        source="eastmoney", missing=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / "t.db"
    store = FundamentalStore(db_path=tmp)
    fetcher = _FakeFetcher({
        "BANK": [_row(stock_code="BANK", missing=["gross_margin", "capex"])],
        "EMPTY": [],
    })
    svc = FundamentalService(store=store, fetcher=fetcher)

    status = svc.refresh(["BANK", "EMPTY", "MISSING"])
    _check(status["BANK"]["ok"] is True, "有数据的标的应成功")
    _check(status["EMPTY"]["ok"] is False, "空结果必须标失败而不是写 0")
    _check("无财报" in status["MISSING"]["reason"], "取数异常/无覆盖要给出可读原因")

    snap = svc.snapshot("BANK")
    _check(snap is not None and snap["has_gross_margin"] is False,
           "毛利率缺失必须显式标记 has_gross_margin=False")
    _check(snap["has_capex"] is False, "capex 缺失必须显式标记")

    _check(svc.snapshot("EMPTY") is None, "没有财报的标的必须返回 None，不能伪造中性值")

    # 幂等：同一期写两次不应出现两行
    svc.refresh(["BANK"])
    _check(store.stats()["rows"] == 1, f"重复写入产生了多行：{store.stats()}")

    # 历史顺序：最新在前
    store.upsert("BANK", "2025-12-31", {"period_end": "2025-12-31", "revenue": 9e8,
                                        "source": "eastmoney", "missing": []})
    hist = store.history("BANK")
    _check(hist[0]["period_end"] == "2026-06-30", "history 必须最新在前")

    if failures:
        print("❌ 失败：")
        for f in failures:
            print("  -", f)
        return 1
    print("✅ 基本面仓校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
