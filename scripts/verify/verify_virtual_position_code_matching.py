"""守卫：持仓代码必须归一后匹配，`NVDA` 和 `nvda` 不许是两只票。

背景（2026-10-20 实查）：

``VirtualPortfolio.update_price()`` 原来是 ``pos.stock_code == stock_code``
**严格等值**比较。持仓里存的是 ``NVDA``（大写，历史写入），行情总线推的是
``nvda`` —— 一只票都匹配不上，表现就是「NVDA 的成本价和现价永远是 450.0」。
450 不是行情，是当年按金额折算时用的占位价。

价格不动的后果全是静默的：浮盈亏恒 0、止盈止损永不触发、
「持仓价格陈旧」告警按错误的时间算、首页盈亏卡跟着失真。
页面上一切正常，只有数字是假的。

判据：同一只票的四种写法（``NVDA`` / ``nvda`` / ``US.NVDA`` / ``nvda.us``）
必须能互相匹配到同一个持仓。
"""

from __future__ import annotations

import argparse
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VP = ROOT / "deva/naja/bandit/virtual_portfolio.py"

VARIANTS = ["NVDA", "nvda", "US.NVDA", "nvda.us"]
A_SHARE = [("sh600000", "600000"), ("sz000001", "000001"), ("588200", "588200")]


def _make_portfolio(stock_code: str):
    """造一个不落库的持仓组合，只测匹配逻辑。"""
    from deva.naja.bandit.virtual_portfolio import VirtualPortfolio, VirtualPosition

    p = object.__new__(VirtualPortfolio)
    p._positions = {
        "VP_test_1": VirtualPosition(
            position_id="VP_test_1",
            strategy_id="s",
            strategy_name="n",
            stock_code=stock_code,
            stock_name="测试",
            entry_price=168.0,
            current_price=450.0,
            quantity=22.2,
            entry_time=0.0,
            last_update_time=0.0,
            status="OPEN",
        )
    }
    p._lock = threading.RLock()
    p._position_callbacks = []
    p._market_time_service = types.SimpleNamespace(get_market_time=lambda: 1.0)
    return p


def _all_checks() -> list:
    fails = []
    try:
        from deva.naja.bandit.virtual_portfolio import normalize_code
    except Exception as e:  # noqa: BLE001
        return [f"normalize_code 无法导入：{type(e).__name__}: {e}"]

    # ── 1. 四种写法归一成同一个 token ────────────────────────────────────
    try:
        tokens = {v: normalize_code(v) for v in VARIANTS}
        if len(set(tokens.values())) != 1:
            fails.append(f"同一只票的四种写法归一不到一起：{tokens}")
    except Exception as e:  # noqa: BLE001
        fails.append(f"normalize_code（美股）无法验证：{type(e).__name__}: {e}")

    # ── 2. A 股前缀要被剥掉，但裸码本身不许变 ────────────────────────────
    try:
        bad = [(x, normalize_code(x)) for x, want in A_SHARE if normalize_code(x) != want]
        if bad:
            fails.append(f"A 股代码归一不对：{bad}")
    except Exception as e:  # noqa: BLE001
        fails.append(f"normalize_code（A 股）无法验证：{type(e).__name__}: {e}")

    # ── 3. 大写的持仓必须能被小写的行情更新到 ────────────────────────────
    try:
        p = _make_portfolio("NVDA")
        p.update_price("nvda", 217.09)
        cur = p._positions["VP_test_1"].current_price
        if abs(float(cur) - 217.09) > 1e-6:
            fails.append(
                f"update_price('nvda') 没更新到 stock_code='NVDA' 的持仓"
                f"（current_price 还是 {cur}）—— 价格不动，浮盈亏/止盈止损全是假的"
            )
    except Exception as e:  # noqa: BLE001
        fails.append(f"update_price 匹配无法验证：{type(e).__name__}: {e}")

    # ── 4. 查询接口也必须归一（首页持仓卡要用）───────────────────────────
    try:
        p = _make_portfolio("NVDA")
        for probe in VARIANTS:
            got = p.get_positions_by_stock(probe)
            if len(got) != 1:
                fails.append(f"get_positions_by_stock({probe!r}) 返回 {len(got)} 条，应为 1 条")
                break
    except Exception as e:  # noqa: BLE001
        fails.append(f"get_positions_by_stock 无法验证：{type(e).__name__}: {e}")

    return fails


INJECTIONS = [
    {
        "name": "update_price 退回严格等值比较",
        "path": VP,
        "old": "                if normalize_code(pos.stock_code) == want and pos.status == \"OPEN\"",
        "new": "                if pos.stock_code == stock_code and pos.status == \"OPEN\"",
    },
]


def run_injections() -> int:
    import importlib

    print("负向注入（每条都该被抓到）：")
    caught = 0
    missed = 0
    for inj in INJECTIONS:
        path: Path = inj["path"]
        original = path.read_text(encoding="utf-8")
        if inj["old"] not in original:
            print(f"  ❌ 锚点没命中，注入无效：{inj['name']}")
            missed += 1
            continue
        try:
            path.write_text(original.replace(inj["old"], inj["new"], 1), encoding="utf-8")
            if "deva.naja.bandit.virtual_portfolio" in sys.modules:
                importlib.reload(sys.modules["deva.naja.bandit.virtual_portfolio"])
            fails = _all_checks()
        finally:
            path.write_text(original, encoding="utf-8")
            if "deva.naja.bandit.virtual_portfolio" in sys.modules:
                importlib.reload(sys.modules["deva.naja.bandit.virtual_portfolio"])

        if fails:
            caught += 1
            print(f"  ✅ 被捕获：{inj['name']}")
            for f in fails[:2]:
                print(f"       · {f[:110]}")
        else:
            print(f"  ❌ 没抓到 —— 这条注入白做了：{inj['name']}")

    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（{missed} 条锚点未命中，已计失败）" if missed else ""))
    return caught if not missed else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = _all_checks()
    total = 4
    if failures:
        print(f"❌ {len(failures)}/{total} 项失败：持仓代码归一号守卫")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0

    print("✅ 持仓代码归一号守卫全绿（NVDA/nvda/US.NVDA/nvda.us 归一 · 更新与查询都走归一）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
