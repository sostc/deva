#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：做 T 的「粗筛阈值」与「精判阈值」必须同源、且粗筛不严于精判。

背景（2026-11-25 守望台审视）
------------------------------
做 T 有两条线：

* 守望台 ``rotation_t`` 用 :data:`DEFAULT_ROTATION_PCT` 粗筛「值不值得问一次」；
* 引擎 :func:`evaluate_deviation` 用 ``RotationThresholds.buy/sell_dev_close``
  + VWAP + 振幅 + 成本 + 企稳精判「要不要真下单」。

此前两处各写魔数（守望 1.0、引擎 1.5），改一处就口径打架：引擎有机会时
守望台可能问都不问，或守望台天天喊机会引擎从不动手。现在统一到引擎的
``RotationThresholds.screening_pct()`` 单一权威源。

守三条
------
① 守望台 DEFAULT_ROTATION_PCT == 引擎 screening_pct()（行为，真取值比对）。
② screening_pct() == min(buy_dev_close, sell_dev_close)，且 ≤ 两侧（粗筛不严于精判）。
③ 改引擎阈值后守望台默认值跟着变（注入：把引擎 buy_dev_close 改大 →
   两边同步；若守望台又写死魔数则抓到）。

用法
----
    python scripts/verify/verify_rotation_threshold_alignment.py
    python scripts/verify/verify_rotation_threshold_alignment.py --strict
    python scripts/verify/verify_rotation_threshold_alignment.py --exercise-injections
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)
if str(VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_DIR))

# 守卫跑临时库，不碰生产 NB。
from guard_sandbox import isolate_guard_db  # noqa: E402
isolate_guard_db()

ROTATION_PY = ROOT / "deva/naja/watch/rotation.py"
INTRADAY_PY = ROOT / "deva/naja/bandit/intraday_deviation.py"


def check_screening_is_single_source() -> list:
    failures = []
    from deva.naja.bandit.intraday_deviation import RotationThresholds
    from deva.naja.watch.rotation import DEFAULT_ROTATION_PCT

    thr = RotationThresholds()
    if not hasattr(thr, "screening_pct"):
        failures.append("引擎 RotationThresholds 缺 screening_pct() —— 权威源没了")
        return failures
    screen = thr.screening_pct()
    if abs(DEFAULT_ROTATION_PCT - screen) > 1e-9:
        failures.append(
            f"守望台默认阈值 {DEFAULT_ROTATION_PCT} != 引擎粗筛 {screen} —— 两处魔数又漂移了"
        )
    if abs(screen - min(thr.buy_dev_close, thr.sell_dev_close)) > 1e-9:
        failures.append(
            f"screening_pct()={screen} 不等于 min(buy/sell)={min(thr.buy_dev_close, thr.sell_dev_close)}"
        )
    if screen > thr.buy_dev_close or screen > thr.sell_dev_close:
        failures.append("粗筛严于精判 —— 引擎有机会时守望台却问都不会问")
    return failures


def check_source_wires_engine() -> list:
    """静态：rotation.py 必须从引擎权威源读，不许再写死魔数。"""
    failures = []
    src = ROTATION_PY.read_text(encoding="utf-8")
    if "RotationThresholds" not in src or "screening_pct()" not in src:
        failures.append("rotation.py 没从 RotationThresholds.screening_pct() 读默认阈值")
    intraday = INTRADAY_PY.read_text(encoding="utf-8")
    if "def screening_pct(" not in intraday:
        failures.append("引擎缺 screening_pct() 权威源")
    return failures


def _all_checks() -> list:
    # 静态在前：方法被改名时先报「权威源没了」，而不是后到的行为检查「阈值漂移」
    return check_source_wires_engine() + check_screening_is_single_source()


INJECTIONS = [
    {
        "name": "守望台又写死魔数（不从引擎读）",
        "old": "    DEFAULT_ROTATION_PCT = float(_RotationThresholds().screening_pct())",
        "new": "    DEFAULT_ROTATION_PCT = 1.0",
    },
    {
        "name": "引擎删掉 screening_pct 权威源",
        "old": "    def screening_pct(self) -> float:",
        "new": "    def _legacy_screening_pct(self) -> float:",
    },
]


def run_injections() -> int:
    caught = 0
    for inj in INJECTIONS:
        path = ROTATION_PY if "rotation.py" in inj["name"] or "_RotationThresholds" in inj["old"] else INTRADAY_PY
        original = path.read_text(encoding="utf-8")
        if inj["old"] not in original or original.count(inj["old"]) != 1:
            print(f"❌ 注入锚点问题：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")
        if found:
            caught += 1
            print(f"  ✅ 被捕获：{found[0][:100]}")
        else:
            print("  ❌ 没抓到 —— 摆设")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获")
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()
    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1
    failures = _all_checks()
    if failures:
        print("❌ 做T阈值同源守卫失败：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ 做T阈值同源守卫全绿（单一权威源 / 同源 / 粗筛不严于精判）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
