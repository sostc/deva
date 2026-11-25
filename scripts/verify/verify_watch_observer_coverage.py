#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：守望台每一种已挂台的守望都必须有观测面工厂（观测面覆盖）。

背景（2026-11-25 守望台审视）
------------------------------
做 T 常驻守望 ``rotation_t`` 与补底仓守望 ``establish_core`` 由
``IntentRunner._ensure_watch`` **直接** ``registry.declare`` 挂台，不走
``declare_intent``，因此从没登记过观测面工厂。后果是一条静默失效链：

    desk.poll → _observers.get(kind) = None → ctx = None
              → 所有判据记 unclear → should_ask 只靠 600s 沉默兜底
              → price=0 去问决策中心 → 日志里只有一行一次性 WARNING

它和「机会还没到」在 UI 上长得一模一样；守卫全绿却一整天没看过行情。

本守卫钉三条
------------
① 六类 kind（buy/sell/trim_intent + allocation + rotation_t + establish_core）
   全部登记进 ``desk._observers``；少一类即失败。
② ``_check_observer_coverage()`` 行为正确：对已挂但无观测面的 kind 显式报错、
   写入 ``missing_observer_kinds``；补回后自动清空（自愈）。
③ 有观测面的 kind 走真实 builder 拿到 ``WatchContext``（price/anchor/读数），
   判据拿得到数据而不是 unclear —— 钉在「判据真的被执行」上，不是「名字在字典里」。

负向注入：删掉 rotation_t 登记 / 自检不写 missing 集合 / 自检不调，
三种 bug 必须各自被抓到，失败原因不同。

用法
----
    python scripts/verify/verify_watch_observer_coverage.py
    python scripts/verify/verify_watch_observer_coverage.py --strict
    python scripts/verify/verify_watch_observer_coverage.py --exercise-injections
"""

from __future__ import annotations

import argparse
import os
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)
if str(VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_DIR))

# 守卫跑在临时库，绝不碰生产 NB。
from guard_sandbox import isolate_guard_db  # noqa: E402
isolate_guard_db()

# 关掉市场时钟：闭市会让 poll 在观测面前就跳过，用例会假绿。
os.environ["NAJA_WATCH_MARKET_CLOCK"] = "0"

DESK_PY = ROOT / "deva/naja/watch/desk.py"

#: 六类必须登记的 kind。四类原有 + 两类派生守望（本次补的）。
REQUIRED_KINDS = {
    "buy_intent", "sell_intent", "trim_intent",
    "allocation", "rotation_t", "establish_core",
}


def _load_watch():
    """重新加载 watch 包里与观测面有关的模块，拿到**新**对象。

    ❗按项目硬规则：不许 import 拿 sys.modules 里的旧对象（会让注入假绿）。
    spec_from_file_location + 先入 sys.modules 再 exec_module（dataclass 需要）。
    """
    import deva.naja.watch as W
    for name in ("deva.naja.watch.desk", "deva.naja.watch.watch",
                 "deva.naja.watch.registry", "deva.naja.watch.opportunity"):
        mod = sys.modules.get(name)
        path = ROOT / (name.replace(".", "/") + ".py")
        if mod is None or not path.exists():
            continue
        spec = spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            continue
        fresh = module_from_spec(spec)
        sys.modules[name] = fresh
        try:
            spec.loader.exec_module(fresh)
        except Exception:  # noqa: BLE001
            sys.modules[name] = mod
    return sys.modules["deva.naja.watch.desk"]


def _source() -> str:
    return DESK_PY.read_text(encoding="utf-8")


def check_required_kinds_registered() -> list:
    """静态 + 行为双重：六类 kind 都在构造时被登记。"""
    failures = []
    src = _source()
    # 三类意向 kind 由循环用 f-string 注册，锚点是循环那行，不是字面量
    if 'self._observers[f"{side}_intent"]' not in src:
        failures.append("构造时没有循环登记 buy/sell/trim_intent 观测面")
    # 三类派生/常驻 kind 是字面量登记，逐个钉
    for kind in ("allocation", "rotation_t", "establish_core"):
        if f'self._observers["{kind}"]' not in src:
            failures.append(f"构造时没有登记观测面：{kind} —— 派生守望会 ctx=None 空转")
    # poll 必须调用自检（钉执行点，不只是「方法存在」）
    poll_seg = src[src.find("    def poll("):]
    poll_seg = poll_seg[:poll_seg.find("\n    def ")] if "\n    def " in poll_seg else poll_seg
    if "self._check_observer_coverage()" not in poll_seg:
        failures.append("poll() 没调用观测面自检 —— 断链红灯在生产路径上永远不亮")
    # 行为：真造一个 desk，确认字典里六类都在
    try:
        d = _load_watch().WatchDesk(quote_fn=lambda c: None, heartbeat_sec=0.0)
    except Exception as e:  # noqa: BLE001
        return failures + [f"构造 WatchDesk 失败：{type(e).__name__}: {e}"]
    missing = REQUIRED_KINDS - set(d._observers)
    if missing:
        failures.append(f"运行时 _observers 缺：{sorted(missing)}")
    return failures


def check_coverage_selfcheck() -> list:
    """行为：已挂但无观测面的 kind 显式红灯；补回后自愈。"""
    failures = []
    Wd = _load_watch()
    import deva.naja.watch as W
    desk = Wd.WatchDesk(quote_fn=lambda c: None, heartbeat_sec=0.0)

    # 造一个「孤儿 kind」守望：objective.kind 不在 _observers 里。
    # ❗_check_observer_coverage 只读 objective.kind + state，用轻量替身即可，
    # 不必造完整 Watch（那需要真判据、会被无关校验挡住）。
    obj = W.to_objective(
        W.BuyIntent("NVDA", "US", max_wait_seconds=3 * 86400.0)
    )
    object.__setattr__(obj, "kind", "orphan_kind")
    desk.registry.declare(obj, [
        {"kind": "manas_window", "min_action": "act_minimally"}
    ])

    # ❗必须经 poll() 触发，不是直接调自检 —— 否则「poll 里漏调自检」
    # 这个 bug 抓不到（直接调当然会亮，但生产路径永远不调）。
    desk.poll(now=1000.0, wake_reason="timer")
    if "orphan_kind" not in desk.missing_observer_kinds:
        failures.append("poll 后没把缺观测面的 kind 记进 missing_observer_kinds —— 断链仍静默")

    # 补回 observer 后再自检，集合应清空（自愈，不靠手动清）
    Wd.WatchDesk.register_observer(desk, "orphan_kind", desk._intent_context)
    desk._check_observer_coverage()
    if desk.missing_observer_kinds:
        failures.append("补回 observer 后 missing_observer_kinds 没清空 —— 不自愈，会一直误报")

    # 正常六类不应误报
    clean = Wd.WatchDesk(quote_fn=lambda c: None, heartbeat_sec=0.0)
    clean._check_observer_coverage()
    if clean.missing_observer_kinds:
        failures.append(f"干净的 desk 被误报缺观测面：{clean.missing_observer_kinds}")
    return failures


def check_observer_feeds_real_context() -> list:
    """钉在「判据真的拿到数据」：有 observer 的 kind 拿到带 price/anchor 的 ctx。"""
    failures = []
    Wd = _load_watch()
    import deva.naja.watch as W

    ctx = types.SimpleNamespace(current=110.0, prev_close=100.0, age=1.0)
    desk = Wd.WatchDesk(quote_fn=lambda c: ctx, heartbeat_sec=0.0)
    for kind in ("rotation_t", "establish_core"):
        obj = W.to_objective(
            W.BuyIntent("NVDA", "US", max_wait_seconds=3 * 86400.0)
        )
        object.__setattr__(obj, "kind", kind)
        # observer builder 只读 watch.objective（subject/market），替身够用
        w = types.SimpleNamespace(objective=obj)
        try:
            built = desk._observers[kind](w, 1000.0)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{kind} 的观测面工厂抛异常：{type(e).__name__}: {e}")
            continue
        if getattr(built, "price", None) != 110.0 or getattr(built, "anchor", None) != 100.0:
            failures.append(
                f"{kind} 的观测面没喂到 price/anchor（判据仍会 unclear）："
                f"price={getattr(built, 'price', None)} anchor={getattr(built, 'anchor', None)}"
            )
    return failures


def _all_checks() -> list:
    return (check_required_kinds_registered()
            + check_coverage_selfcheck()
            + check_observer_feeds_real_context())


INJECTIONS = [
    {
        "name": "删掉 rotation_t 观测面登记（做T判据又空转）",
        "old": '        self._observers["rotation_t"] = self._intent_context\n',
        "new": "",
    },
    {
        "name": "自检不写 missing 集合（断链又不留痕）",
        "old": "            self.missing_observer_kinds = missing\n",
        "new": "            pass\n",
    },
    {
        "name": "poll 不调用自检（红灯永亮不起来）",
        "old": "        self._check_observer_coverage()\n\n        tickets: List[DeskTicket] = []",
        "new": "        tickets: List[DeskTicket] = []",
    },
]


def run_injections() -> int:
    caught = 0
    original = _source()
    for inj in INJECTIONS:
        old = inj["old"]
        if old not in original:
            print(f"❌ 注入锚点未命中（守卫腐烂）：{inj['name']}")
            continue
        if original.count(old) != 1:
            print(f"❌ 锚点出现 {original.count(old)} 次（期望 1）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        DESK_PY.write_text(original.replace(old, inj["new"]), encoding="utf-8")
        try:
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫抛异常: {type(e).__name__}: {e}"]
        finally:
            DESK_PY.write_text(original, encoding="utf-8")
            _load_watch()
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）：{found[0][:100]}")
        else:
            print("  ❌ 没抓到 —— 这条是摆设")
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
        print("❌ 观测面覆盖守卫失败：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ 观测面覆盖守卫全绿（六类登记 / 自检红灯自愈 / 判据拿到真实行情）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
