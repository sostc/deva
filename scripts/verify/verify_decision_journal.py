#!/usr/bin/env python3
"""验证决策留痕**落盘**（重启可回放）。

为什么需要这个脚本
------------------
单测只能证明"同一个进程内写进去、读出来"——那连内存队列都能过。
"落盘"的唯一硬证据是：**A 进程写入，B 进程读回**。本脚本就用子进程做这件事。

跑法
----
    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_decision_journal.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_decision_journal.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

隔离
----
脚本把 ``DEVA_DB_PATH`` 指向临时 sqlite 文件（DBStream 的支持路径），
因此**不会**碰生产库 ``~/.deva/nb.sqlite`` 里的 ``naja_decision_journal``。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ⚠️ 必须在 import deva.* 之前设好：DBStream 只在构造时读一次这个变量。
_TMPDIR = tempfile.mkdtemp(prefix="naja_decision_journal_verify_")
os.environ["DEVA_DB_PATH"] = str(Path(_TMPDIR) / "nb.sqlite")

# 子进程用同一份环境（含 DEVA_DB_PATH），但不带宿主注入的 PYTHONPATH
_CHILD_ENV = dict(os.environ)
_CHILD_ENV.pop("PYTHONPATH", None)

# 子进程要跑的东西：走 TradingCenter 的真实留痕写入路径（_record_plan），
# 这正是 process_strategy_signal 三条返回路径共同调用的那个方法。
_CHILD_SNIPPET = """
import sys
sys.path.insert(0, {root!r})
from deva.naja.decision import DecisionPlan
from deva.naja.attention.orchestration.trading_center import get_trading_center

tc = get_trading_center()
plan = DecisionPlan(
    symbol={symbol!r},
    side="buy",
    action_type="act_carefully",
    size_hint=0.42,
    confidence=0.61,
    risk_temperature=1.15,
    gate_reason="验证脚本写入",
    should_act=True,
    reasons=["verify"],
    source_signal={{"origin": "verify_decision_journal"}},
)
tc._record_plan(plan, approved={approved!r})
print("CHILD_WROTE", {symbol!r})
"""


def _run_child(symbol: str, approved: bool) -> tuple[bool, str]:
    """在一个**全新进程**里写一条留痕。"""
    snippet = _CHILD_SNIPPET.format(
        root=str(PROJECT_ROOT), symbol=symbol, approved=approved
    )
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        env=_CHILD_ENV,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=180,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return (proc.returncode == 0 and f"CHILD_WROTE {symbol}" in out), out.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = parser.parse_args()

    violations: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name}" + (f"  —— {detail}" if detail else ""))
        if not ok:
            violations.append(name)

    print("=" * 68)
    print("① 子进程 A 写入一条决策（真实 TradingCenter 留痕路径）")
    print("=" * 68)
    ok_a, out_a = _run_child("600519", True)
    check("子进程 A 退出码 0 且写入成功", ok_a, out_a.splitlines()[-1] if out_a else "")

    print()
    print("=" * 68)
    print("② 子进程 B 再写入一条（证明是追加，不是覆盖）")
    print("=" * 68)
    ok_b, out_b = _run_child("000001", False)
    check("子进程 B 退出码 0 且写入成功", ok_b, out_b.splitlines()[-1] if out_b else "")

    # ↓↓↓ 到这里已经是"另一个进程"了：本进程从未构造过 journal ↓↓↓
    print()
    print("=" * 68)
    print("③ 本进程（全新）读回子进程写的决策")
    print("=" * 68)
    from deva.naja.decision.journal import DecisionJournal, TABLE_DECISION_JOURNAL

    journal = DecisionJournal()
    check("读的是默认生产表名", journal.table == TABLE_DECISION_JOURNAL, journal.table)

    count = journal.count()
    check("读到 2 条（跨进程存活）", count == 2, f"count={count}")

    recent = journal.recent(10)
    symbols = [e.get("symbol") for e in recent]
    check("顺序为最新在前", symbols == ["000001", "600519"], f"symbols={symbols}")

    by_symbol = {e.get("symbol"): e for e in recent}
    top = by_symbol.get("600519", {})
    check("字段完整（DecisionPlan 全字段随落盘保留）", bool(top) and top.get("action_type") == "act_carefully"
          and abs(float(top.get("size_hint", 0)) - 0.42) < 1e-9,
          f"action_type={top.get('action_type')!r} size_hint={top.get('size_hint')}")
    check("approved 标记保留", by_symbol.get("600519", {}).get("approved") is True
          and by_symbol.get("000001", {}).get("approved") is False,
          f"600519={by_symbol.get('600519', {}).get('approved')} "
          f"000001={by_symbol.get('000001', {}).get('approved')}")
    check("recorded_at 是真时间戳", isinstance(top.get("recorded_at"), float)
          and top.get("recorded_at", 0) > 1_700_000_000,
          f"recorded_at={top.get('recorded_at')}")

    print()
    print("=" * 68)
    print("④ 时间窗回放（replay）")
    print("=" * 68)
    check("24h 窗口取到 2 条", len(journal.history(hours=24, limit=100)) == 2,
          f"{len(journal.history(hours=24, limit=100))}")
    check("0h 窗口取到 0 条（窗口真的在生效）",
          journal.history(hours=0, limit=100) == [], "")
    check("limit 生效", len(journal.history(hours=24, limit=1)) == 1, "")

    print()
    print("=" * 68)
    print("⑤ maxsize 自动裁剪（不留无限增长的表）")
    print("=" * 68)
    bounded = DecisionJournal(table="naja_decision_journal_verify_bounded", maxsize=3)
    bounded.clear()
    for i in range(6):
        bounded.record({"symbol": f"CUT{i}", "recorded_at": None})
    kept = [e.get("symbol") for e in bounded.recent(10)]
    check("超出上限后只保留最新 3 条", kept == ["CUT5", "CUT4", "CUT3"], f"kept={kept}")
    bounded.clear()

    print()
    print("=" * 68)
    print("⑥ 落盘不可用时诚实降级（不抛、返回 None）")
    print("=" * 68)
    broken = DecisionJournal(table="naja_decision_journal_verify_broken")
    broken._db = None
    check("record() 返回 None 而非抛异常", broken.record({"x": 1}) is None, "")
    check("count() 返回 0", broken.count() == 0, "")
    check("recent() 返回空列表", broken.recent(10) == [], "")
    check("stats().available 为 False", broken.stats().get("available") is False, "")

    print()
    print("=" * 68)
    print("⑦ 静态守卫：process_strategy_signal 的三条返回路径都接了留痕")
    print("=" * 68)
    src = (PROJECT_ROOT / "deva/naja/attention/orchestration/trading_center.py").read_text(
        encoding="utf-8"
    )
    calls = src.count("self._record_plan(")
    check("源码中出现 3 处 _record_plan 调用（降级/批准/否决）", calls == 3, f"calls={calls}")

    print()
    print("=" * 68)
    print(f"隔离用的临时库: {os.environ['DEVA_DB_PATH']}")
    if violations:
        print(f"❌ 违约 {len(violations)} 项: {violations}")
        return 1 if args.strict else 0
    print("✅ 全部通过：决策留痕已落盘，跨进程可回放")
    return 0


if __name__ == "__main__":
    sys.exit(main())
