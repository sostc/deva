#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：守望问询记录跨重启可查 + UI 文案与实现一致。

背景（2026-11-25 守望台审视）
------------------------------
``Watch.ask_log`` 原本是进程内 ``deque``，重启即清零 ——「这个意向问过几次、
被否几次」事后查不到，与 DecisionPlan 可回放的口径不一致。现在：

* ``Watch`` 加可选 ``ask_sink``（默认 None，保持内核可测试）；
* ``IntentRunner.desk`` 装配时注入 NB 落盘钩子（开关 NAJA_WATCH_ASK_PERSIST）；
* 落盘失败只降级为内存，绝不影响决策。

另外 UI 两处文案曾写「意愿只留痕、权重=0、决策中心读不到标的」，与已实现的
「有限放宽门槛 + 感知标的」矛盾 —— 本守卫一并钉住，防旧文案复活。

守四条
------
① record_ask 真调用 ask_sink（行为：注入假 sink，问一次应收到一条）。
② sink 落 NB 可被另一个 NB 实例读回（行为，隔离库）；DBStream 判空用 is None。
③ 落盘失败不影响计数（行为：注入抛异常的 sink，record_ask 仍正常记账）。
④ UI 文案不再声称「只留痕/权重=0/读不到标的」（静态）。

用法
----
    python scripts/verify/verify_watch_ask_persistence.py
    python scripts/verify/verify_watch_ask_persistence.py --strict
    python scripts/verify/verify_watch_ask_persistence.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)
if str(VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_DIR))

from guard_sandbox import isolate_guard_db  # noqa: E402
isolate_guard_db()

import os  # noqa: E402

os.environ["NAJA_WATCH_MARKET_CLOCK"] = "0"

WATCH_PY = ROOT / "deva/naja/watch/watch.py"
UI_PY = ROOT / "deva/naja/watch/ui.py"
RUNNER_PY = ROOT / "deva/naja/bandit/intent_runner.py"


def check_sink_called() -> list:
    failures = []
    import deva.naja.watch as W
    w = W.Watch(
        objective=W.to_objective(
            W.BuyIntent("NVDA", "US", max_wait_seconds=3 * 86400.0)
        ),
        opportunities=[{"kind": "manas_window", "min_action": "act_minimally"}],
        armed_at=1000.0,
    )
    got = []
    w.ask_sink = lambda wid, entry: got.append((wid, entry))
    w.record_ask(False, "被否", now=1001.0, fired_kinds=["manas_window"])
    if len(got) != 1:
        failures.append(f"record_ask 没调用 ask_sink（收到 {len(got)} 条）—— 落盘钩子没接上")
    elif got[0][1].get("granted") is not False or "未批准" not in str(got[0][1].get("verdict")):
        failures.append(f"sink 收到的 entry 不对（三态否决应如实留痕）：{got[0][1]}")
    return failures


def check_sink_failure_is_benign() -> list:
    failures = []
    import deva.naja.watch as W
    w = W.Watch(
        objective=W.to_objective(
            W.BuyIntent("NVDA", "US", max_wait_seconds=3 * 86400.0)
        ),
        opportunities=[{"kind": "manas_window", "min_action": "act_minimally"}],
        armed_at=1000.0,
    )

    def _boom(wid, entry):
        raise RuntimeError("DB down")

    w.ask_sink = _boom
    try:
        w.record_ask(True, "放行", now=1002.0)
    except Exception as e:  # noqa: BLE001
        failures.append(f"落盘失败竟然影响了决策路径：{type(e).__name__}: {e}")
    if (w.asked, w.granted_count) != (1, 1):
        failures.append(f"落盘失败后计数不对：{w.asked}/{w.granted_count}")
    return failures


def check_runner_sink_persists() -> list:
    failures = []
    import deva.naja.bandit.intent_runner as ir

    # 用隔离库里的独立表名，不碰生产
    ir.WATCH_ASK_TABLE = "naja_watch_ask_log_guard"
    runner = ir.IntentRunner()
    sink = runner._ask_log_sink()
    import time as _time
    key = f"guard-w-{_time.time_ns()}"  # 唯一 key，避免多次检查累积污染
    sink(key, {"granted": False, "reason": "被否"})
    sink(key, {"granted": True, "reason": "放行"})
    from deva import NB

    rows = NB("naja_watch_ask_log_guard").get(key)
    if not rows or len(rows) != 2:
        failures.append(f"另一个 NB 实例读不回落盘记录：{rows}")
    elif rows[1].get("granted") is not True:
        failures.append("落盘记录顺序/内容不对")
    return failures


def check_ui_copy_current() -> list:
    failures = []
    src = UI_PY.read_text(encoding="utf-8")
    for stale in ("尚未进入打分", "权重仍是 0", "读不到标的与方向", "当前只留痕"):
        if stale in src:
            failures.append(f"UI 仍有过时文案「{stale}」—— 与已实现的意愿放宽矛盾")
    if "有限放宽" not in src:
        failures.append("UI 没说明意愿的真实作用（有限放宽门槛）")
    return failures


def check_static_wiring() -> list:
    failures = []
    watch = WATCH_PY.read_text(encoding="utf-8")
    if "ask_sink" not in watch or "self.ask_sink(" not in watch:
        failures.append("Watch 没接 ask_sink 或在 record_ask 里没调用")
    registry = (ROOT / "deva/naja/watch/registry.py").read_text(encoding="utf-8")
    if "ask_sink=self.ask_sink" not in registry:
        failures.append("registry.declare 没把 ask_sink 透传给 Watch")
    runner = RUNNER_PY.read_text(encoding="utf-8")
    if "ENV_WATCH_ASK_PERSIST" not in runner or "registry.ask_sink" not in runner:
        failures.append("IntentRunner 没装配问询落盘钩子")
    if "is None" not in runner:
        failures.append("落盘判空没用 is None（DBStream 有 __len__，真值判空会永远写不进）")
    return failures


def _all_checks() -> list:
    return (check_static_wiring() + check_sink_called()
            + check_sink_failure_is_benign()
            + check_runner_sink_persists()
            + check_ui_copy_current())


INJECTIONS = [
    {
        "name": "record_ask 不调 sink（又变成重启即清零）",
        "file": WATCH_PY,
        "old": "        if self.ask_sink is not None:",
        "new": "        if False:",
    },
    {
        "name": "UI 旧文案复活（声称只留痕）",
        "file": UI_PY,
        "old": "                \"· <b>意愿强度</b>：人的主动意愿。决策中心看得到标的/方向，\"",
        "new": "                \"· <b>意愿强度</b>：人的主动意愿。当前只留痕、尚未进入打分。\"",
    },
    {
        "name": "registry 不透传 sink（注入了也不生效）",
        "file": ROOT / "deva/naja/watch/registry.py",
        "old": "            ask_sink=self.ask_sink,",
        "new": "",
    },
]


def _reload_modules():
    """重载被测模块。❗顺序：先子模块后包，包才能拿到新类符号。"""
    for name in ("deva.naja.watch.watch", "deva.naja.watch.registry",
                 "deva.naja.bandit.intent_runner", "deva.naja.watch"):
        try:
            importlib.reload(importlib.import_module(name))
        except Exception:  # noqa: BLE001
            pass


def run_injections() -> int:
    caught = 0
    reasons = []
    for inj in INJECTIONS:
        path: Path = inj["file"]
        original = path.read_text(encoding="utf-8")
        if inj["old"] not in original or original.count(inj["old"]) != 1:
            print(f"❌ 注入锚点问题：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        # ❗还原态先 reload 一次，确保从干净模块开始（上一条残留不污染）
        _reload_modules()
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            # ❗注入后 reload，让磁盘上的修改进内存类；否则行为检查用的还是旧类
            importlib.invalidate_caches()
            _reload_modules()
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")
            _reload_modules()
        if found:
            caught += 1
            reasons.append(found[0])
            print(f"  ✅ 被捕获：{found[0][:100]}")
        else:
            print("  ❌ 没抓到 —— 摆设")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获")
    if len(set(reasons)) != len(reasons):
        print("  ⚠️ 失败原因有重复，可能不是各自独立的守点")
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
        print("❌ 问询落盘守卫失败：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ 问询落盘守卫全绿（钩子接通 / 可回读 / 失败降级 / 文案一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
