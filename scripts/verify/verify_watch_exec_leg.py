#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：守望台「批准→落单」执行腿——默认关闭、复用权威链、二次校验。

背景（2026-11-25 用户拍板接执行腿）
------------------------------------
守望台历史上只「等」和「问」，从不碰账户。用户确认要接执行腿后，铁律：

① **默认关闭**：``NAJA_WATCH_EXEC_ENABLED`` 只在显式 =1 时才执行；
   关闭时 runner 行为与接执行腿之前完全一致（绝不偷偷下单）。
② **复用既有执行链**：只发一条 ``TradeDecisionEvent(APPROVED)`` 到 trading_bus，
   走 SignalListener → Bandit，不另写下单逻辑（避免两处漂移）。
③ **不二次审批**：asker 已经过一次 TradingCenter，这里再判会否掉自己。
④ **二次校验 + None≠[]**：价格/代码/方向合法；在飞单查询 None = 查不清 = 跳过，
   绝不当成「没有」而放心下单。

守五条
------
① 静态：开关存在且默认 0；granted 分支调了执行腿。
② 行为：开关关闭时 _execute_granted_ticket 直接 False、零事件、零 attempted。
③ 行为：开关打开且校验通过时发布 APPROVED 事件到 bus（替身捕获），字段齐全。
④ 行为：价格<=0 / 在飞单查询 None / 方向非法 时跳过，不发事件。
⑤ 负向注入：默认开 / 不调执行腿 / None 当 []，三条必须各自被抓。

用法
----
    python scripts/verify/verify_watch_exec_leg.py
    python scripts/verify/verify_watch_exec_leg.py --strict
    python scripts/verify/verify_watch_exec_leg.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)
if str(VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_DIR))

from guard_sandbox import isolate_guard_db  # noqa: E402
isolate_guard_db()

os.environ["NAJA_WATCH_MARKET_CLOCK"] = "0"

RUNNER_PY = ROOT / "deva/naja/bandit/intent_runner.py"


def _runner():
    import deva.naja.bandit.intent_runner as ir
    importlib.reload(ir)
    return ir


def _ticket(price=100.0, side="buy", code="NVDA", market="US"):
    obj = types.SimpleNamespace(
        subject=code, market=market,
        params={"side": side, "confidence": 0.65},
        describe=lambda: "test",
    )
    ctx = types.SimpleNamespace(price=price)
    return types.SimpleNamespace(
        watch_id="w-exec", objective=obj, context=ctx,
        granted=True, reason="test approved",
    )


def check_default_off() -> list:
    failures = []
    ir = _runner()
    os.environ.pop(ir.ENV_WATCH_EXEC_ENABLED, None)
    if ir.IntentRunner._exec_enabled() is not False:
        failures.append("执行腿默认值不是关闭 —— 服务一升级就会偷偷下单")
    src = RUNNER_PY.read_text(encoding="utf-8")
    if 'ENV_WATCH_EXEC_ENABLED = "NAJA_WATCH_EXEC_ENABLED"' not in src:
        failures.append("找不到执行腿开关常量")
    return failures


def check_off_no_event() -> list:
    failures = []
    ir = _runner()
    os.environ[ir.ENV_WATCH_EXEC_ENABLED] = "0"
    r = ir.IntentRunner()
    published = []
    with _patch_bus(ir, published):
        result = r._execute_granted_ticket(_ticket(), now=1000.0)
    if result is not False:
        failures.append("开关关闭时执行腿没直接返回 False")
    if published:
        failures.append(f"开关关闭时竟然发布了事件：{published}")
    if r.stats["exec_attempted"] != 0 or r.stats["executed"] != 0:
        failures.append(f"开关关闭时执行腿计数被改动：{r.stats}")
    return failures


def check_on_publishes_approved() -> list:
    failures = []
    ir = _runner()
    os.environ[ir.ENV_WATCH_EXEC_ENABLED] = "1"
    r = ir.IntentRunner()
    r._has_inflight_order = lambda code: False
    published = []
    with _patch_bus(ir, published):
        result = r._execute_granted_ticket(_ticket(), now=1000.0)
    if result is not True:
        failures.append("开关打开且校验通过时执行腿没返回 True")
    if len(published) != 1:
        failures.append(f"没有发布恰好一条事件：{published}")
    else:
        evt = published[0]
        if getattr(evt, "decision", None) is None or str(
            getattr(evt.decision, "value", evt.decision)
        ) != "approved":
            failures.append(f"发布的不是 APPROVED 决策：{evt}")
        if getattr(evt, "approved_symbol", None) != "NVDA":
            failures.append(f"事件代码不对：{evt.approved_symbol}")
    if r.stats["executed"] != 1:
        failures.append(f"executed 计数不对：{r.stats['executed']}")
    return failures


def check_guards() -> list:
    failures = []
    ir = _runner()
    os.environ[ir.ENV_WATCH_EXEC_ENABLED] = "1"
    r = ir.IntentRunner()

    # 价格无效
    r._has_inflight_order = lambda code: False
    published = []
    with _patch_bus(ir, published):
        r._execute_granted_ticket(_ticket(price=0), now=1000.0)
    if published:
        failures.append("价格<=0 仍发了事件")

    # 方向非法
    r2 = ir.IntentRunner()
    r2._has_inflight_order = lambda code: False
    published2 = []
    with _patch_bus(ir, published2):
        r2._execute_granted_ticket(_ticket(side="trim"), now=1000.0)
    if published2:
        failures.append("方向非法（trim）仍发了事件")

    # 在飞单查询 None = 查不清 → 必须拦
    r3 = ir.IntentRunner()
    r3._has_inflight_order = lambda code: True  # 模拟「查不清→保守拦」
    published3 = []
    with _patch_bus(ir, published3):
        r3._execute_granted_ticket(_ticket(), now=1000.0)
    if published3:
        failures.append("在飞单查不清时仍发了事件（None 当成 [] 了）")
    if r3.stats["exec_skipped"] < 1:
        failures.append("跳过时没记 exec_skipped")

    # 不二次审批：发的是 APPROVED，不是再走 TradingCenter
    src = RUNNER_PY.read_text(encoding="utf-8")
    seg = src[src.find("def _execute_granted_ticket"):]
    seg = seg[:seg.find("\n    def ")] if "\n    def " in seg else seg
    if "process_strategy_signal" in seg:
        failures.append("执行腿里又调了 TradingCenter 二次审批 —— 会否掉自己刚放行的票")
    # ❗钉「tick 的 granted 分支真的调了执行腿」——不然注入删掉这一行抓不到
    tick_seg = src[src.find("    def tick("):]
    tick_seg = tick_seg[:tick_seg.find("\n    def ")] if "\n    def " in tick_seg else tick_seg
    if "self._execute_granted_ticket(tk, t)" not in tick_seg:
        failures.append("tick() 的 granted 分支没调执行腿 —— 批准了仍不下单")
    # ❗钉 None≠[] 的那一行（行为用例用替身绕过，静态补上）
    if "if result is None:" not in src or "return True  # ❗查询失败 = 不能再下" not in src:
        failures.append("在飞单查询 None 没有被当成『查不清→拦住』（None≠[] 被破坏）")
    return failures


def _patch_bus(ir, sink):
    """把 events.get_trading_bus 换成假总线（被测代码是局部导入，必须打在源模块）。"""
    import deva.naja.events as events_mod

    class _Bus:
        def publish(self, evt):
            sink.append(evt)

    return _patch(events_mod, "get_trading_bus", lambda: _Bus())


class _patch:
    def __init__(self, module, name, value):
        self.module, self.name, self.value = module, name, value
        self.old = None

    def __enter__(self):
        self.old = getattr(self.module, self.name, None)
        setattr(self.module, self.name, self.value)
        return self

    def __exit__(self, *a):
        setattr(self.module, self.name, self.old)


def _all_checks() -> list:
    return (check_default_off() + check_off_no_event()
            + check_on_publishes_approved() + check_guards())


INJECTIONS = [
    {
        "name": "执行腿默认改成开启（升级就偷偷下单）",
        "old": 'return str(os.environ.get(ENV_WATCH_EXEC_ENABLED, "0")).strip() in (',
        "new": 'return str(os.environ.get(ENV_WATCH_EXEC_ENABLED, "1")).strip() in (',
    },
    {
        "name": "granted 分支不调执行腿（批准仍不下单）",
        "old": "                self._execute_granted_ticket(tk, t)\n",
        "new": "",
    },
    {
        "name": "在飞单 None 当成 []（查询失败还下单）",
        "old": "            if result is None:\n                return True  # ❗查询失败 = 不能再下，绝不当成没有\n",
        "new": "            if result is None:\n                return False\n",
    },
]


def _reload():
    import deva.naja.bandit.intent_runner as ir
    importlib.reload(ir)


def run_injections() -> int:
    caught = 0
    reasons = []
    original = RUNNER_PY.read_text(encoding="utf-8")
    for inj in INJECTIONS:
        old = inj["old"]
        if old not in original or original.count(old) != 1:
            print(f"❌ 注入锚点问题：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        _reload()
        RUNNER_PY.write_text(original.replace(old, inj["new"]), encoding="utf-8")
        try:
            importlib.invalidate_caches()
            _reload()
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫抛异常: {type(e).__name__}: {e}"]
        finally:
            RUNNER_PY.write_text(original, encoding="utf-8")
            _reload()
        if found:
            caught += 1
            reasons.append(found[0])
            print(f"  ✅ 被捕获：{found[0][:100]}")
        else:
            print("  ❌ 没抓到 —— 摆设")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获")
    if len(set(reasons)) != len(reasons):
        print("  ⚠️ 失败原因有重复")
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()
    # 每行一个检查，注意还原执行腿开关，避免污染
    try:
        if args.exercise_injections:
            rc = 0 if run_injections() == len(INJECTIONS) else 1
        else:
            failures = _all_checks()
            if failures:
                print("❌ 执行腿守卫失败：")
                for f in failures:
                    print(f"   - {f}")
                rc = 1
            else:
                print("✅ 执行腿守卫全绿（默认关闭 / 复用权威链 / 二次校验 / None≠[]）")
                rc = 0
    finally:
        os.environ.pop("NAJA_WATCH_EXEC_ENABLED", None)
    return rc


if __name__ == "__main__":
    sys.exit(main())
