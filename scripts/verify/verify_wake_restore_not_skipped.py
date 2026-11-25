"""守卫：短休眠只允许跳过「补作业」，绝不允许跳过「组件状态恢复」。

背景（2026-10-21 实查，一次真实的线上事故）：

``WakeOrchestrator.wake()`` 原来写成——

    if sleep_hours < 1.0 and last_active is not None and has_jin10_cache:
        return {"action": "skipped", ...}        # ← 直接 return

而 ``_recover_components()``（把上次在跑的数据源/策略单元重新拉起来）
在这个 return **之后**。于是：

    2026-10-20 23:47 服务下线 → 23:50 重启（只停了 3 分钟）
    → 休眠 0.08h < 1h 且有金十缓存 → 直接 return
    → 5 个数据源一个都没被拉起，全是 stopped
    → 整个 10-21 交易日 realtime_tick_5s 的 run_count=0、total_emitted=0
    → 而 NB 里这些条目的 ``was_running`` 明明是 True：
      台账说「该在跑」，进程里一个都没有。

「要不要补历史数据」和「上次在跑的东西要不要重新拉起来」是两件事，
前者看重（重），后者只看上次状态（轻），共用一个阈值就会出这种事故。

本守卫钉的是**动作有没有发生**（``recovery_manager.restore_all`` 被调用），
不是「代码里有没有那一行」—— 后者能被 ``return`` 位置骗过去。
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import types
import unittest.mock as mock
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WAKE_PATH = ROOT / "deva/naja/application/wake_orchestrator.py"

# ❗旧实现（负向注入用）：把 recovery 放回 skip 之后，模拟修复前的写法。
# 守卫必须能在它上面报错，否则说明守卫根本没在守。
OLD_WAKE_SRC = '''
def wake(self):
    state_summary = self._state_manager.get_state_summary()
    sleep_hours = state_summary.get("sleep_duration_hours", 0)
    last_active = self._state_manager.get_last_active_time()
    has_jin10_cache = True
    if sleep_hours < self.SKIP_THRESHOLD_HOURS and last_active is not None and has_jin10_cache:
        return {"success": True, "action": "skipped", "reason": "short"}
    results = {"success": True, "sleep_hours": sleep_hours, "recovery": None, "wake_sync": None}
    if last_active:
        results["recovery"] = self._recover_components()
        results["wake_sync"] = {"mode": "external"}
    else:
        results["recovery"] = self._recover_components()
        results["wake_sync"] = {"mode": "jin10"}
    return results
'''


def _load_wake_module():
    """❗不许用 import：会拿到 sys.modules 里的旧对象，改了源码守卫还是全绿。"""
    spec = importlib.util.spec_from_file_location("_wake_under_test", WAKE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {WAKE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    # ❗先占位再 exec：否则 @dataclass 解析 KW_ONLY 会抛
    # 'NoneType' object has no attribute '__dict__'
    sys.modules["_wake_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeRecoveryManager:
    """``recovery_manager`` 的替身：只记有没有被调用、调用时带了什么。

    ❗替身要跟产品 API 同构（``restore_all(order=...)`` 返回带 success 的 dict），
    否则被测代码走到下一层就炸，守卫报的是「炸了」而不是「没恢复」。
    """

    def __init__(self):
        self.calls = []

    def restore_all(self, order=None, **kw):
        self.calls.append({"order": list(order or []), "kw": kw})
        return {
            "success": True,
            "datasource": {"success": True, "restored_count": 5, "failed_count": 0},
        }


def _install_fake_recoverable(fake_mgr):
    """把 deva.naja.infra.runtime.recoverable 换成假模块，避免真的去拉起单元"""
    pkg_name = "deva.naja.infra.runtime.recoverable"
    mod = types.ModuleType(pkg_name)
    mod.recovery_manager = fake_mgr
    mod.RecoveryManager = object
    mod.UnitMetadata = object
    old = sys.modules.get(pkg_name)
    sys.modules[pkg_name] = mod
    return old


class _FakeSyncComponent:
    def should_wake_sync(self, last_active):
        return False

    def get_wake_sync_range(self, last_active):
        return None, None

    def execute_wake_sync(self, a, b):
        return {"success": True}


class _FakeSyncManager:
    def get_component(self, name):
        return _FakeSyncComponent()

    def perform_wake_sync(self, last_active):
        return {"success": True, "components": []}


def _install_fake_wake_sync():
    """❗守卫绝不能真的跑补作业。

    第一版这里没 patch，结果守卫一跑就注册了 6 个真实 WakeSync 组件、
    触发 NewsFetcher 24 小时 backfill、还起了 Playwright 去抓金十 ——
    一个"只读"的守卫把线上数据源污染了一遍。
    凡是碰到输出口的依赖，一律换成替身。
    """
    saved = {}
    fake_mgr = _FakeSyncManager()

    handlers = types.ModuleType("deva.naja.state.system.wake_sync_handlers")
    handlers.Jin10LiveNewsWakeSync = _FakeSyncComponent
    handlers.PortfolioPriceWakeSync = _FakeSyncComponent
    handlers.NewsFetcherWakeSync = _FakeSyncComponent

    manager_mod = types.ModuleType("deva.naja.state.system.wake_sync_manager")
    manager_mod.get_wake_sync_manager = lambda: fake_mgr
    manager_mod.WakeSyncManager = object

    for name, mod in (
        ("deva.naja.state.system.wake_sync_handlers", handlers),
        ("deva.naja.state.system.wake_sync_manager", manager_mod),
    ):
        saved[name] = sys.modules.get(name)
        sys.modules[name] = mod
    return saved


def _restore_modules(saved: dict):
    for name, old in saved.items():
        if old is not None:
            sys.modules[name] = old
        else:
            sys.modules.pop(name, None)


class _FakeStateManager:
    def __init__(self, sleep_hours, last_active):
        self._sleep = sleep_hours
        self._last = last_active

    def get_state_summary(self):
        return {"sleep_duration_hours": self._sleep}

    def get_last_active_time(self):
        return self._last


def _all_checks() -> list:
    fails: list = []
    mod = _load_wake_module()
    WakeOrchestrator = mod.WakeOrchestrator

    def run(sleep_hours, has_cache=True, last_active=True):
        mgr = _FakeRecoveryManager()
        old_mod = _install_fake_recoverable(mgr)
        saved = _install_fake_wake_sync()
        try:
            sm = _FakeStateManager(
                sleep_hours, datetime.now() if last_active else None
            )
            with mock.patch("os.path.exists", return_value=has_cache):
                result = WakeOrchestrator(sm).wake()
            return mgr, result
        finally:
            _restore_modules(saved)
            if old_mod is not None:
                sys.modules["deva.naja.infra.runtime.recoverable"] = old_mod
            else:
                sys.modules.pop("deva.naja.infra.runtime.recoverable", None)

    # ── 1. 核心：短休眠 + 有缓存 → 恢复照做，只跳补作业 ────────────────
    try:
        mgr, res = run(sleep_hours=0.08)
        if not mgr.calls:
            fails.append(
                "休眠 0.08h 时 restore_all 一次都没调用 —— 这就是 2026-10-20 23:50 "
                "那次重启后 5 个数据源全停的原因（短重启=运行时停摆）"
            )
        else:
            order = mgr.calls[0]["order"]
            if "datasource" not in order:
                fails.append(
                    f"恢复了但没恢复 datasource：order={order} "
                    "—— realtime_tick_5s 还是起不来"
                )
        if res.get("action") != "skipped":
            fails.append(
                f"短休眠应当仍跳过补作业（action='skipped'），实际 {res.get('action')!r}"
                " —— 补作业是重操作，该跳还得跳"
            )
    except Exception as e:  # noqa: BLE001
        fails.append(f"短休眠用例无法执行：{type(e).__name__}: {e}")

    # ── 2. 短休眠 + 无金十缓存 → 恢复照做，且走外部同步 ────────────────
    try:
        mgr, res = run(sleep_hours=0.08, has_cache=False)
        if not mgr.calls:
            fails.append("无缓存的短休眠也没做组件恢复")
        if res.get("action") == "skipped":
            fails.append("无金十缓存时不该跳过补作业")
    except Exception as e:  # noqa: BLE001
        fails.append(f"无缓存用例无法执行：{type(e).__name__}: {e}")

    # ── 3. 长休眠 → 恢复 + 全量补作业都要做 ─────────────────────────────
    try:
        mgr, res = run(sleep_hours=5.0)
        if not mgr.calls:
            fails.append("长休眠没做组件恢复")
        if res.get("action") == "skipped":
            fails.append("休眠 5h 不该跳过补作业")
    except Exception as e:  # noqa: BLE001
        fails.append(f"长休眠用例无法执行：{type(e).__name__}: {e}")

    # ── 4. 首次启动（无上次活跃时间）→ 也要恢复，不能崩 ─────────────────
    try:
        mgr, res = run(sleep_hours=0.0, last_active=False)
        if not mgr.calls:
            fails.append("首次启动没做组件恢复")
    except Exception as e:  # noqa: BLE001
        fails.append(f"首次启动用例无法执行：{type(e).__name__}: {e}")

    return fails


def _injections() -> list:
    """负向注入：把 wake() 换回修复前的实现，守卫必须报错。

    ❗「绿」不等于在守。每条注入的失败原因必须各不相同，
    否则说明坏版本被固化进 sys.modules 里了。
    """
    results = []
    mod = _load_wake_module()

    ns = {"mock": mock, "datetime": datetime}
    exec(OLD_WAKE_SRC, ns)  # noqa: S102
    old_wake = ns["wake"]

    for label, sleep_hours in (("短休眠+有缓存", 0.08),):
        mgr = _FakeRecoveryManager()
        old_mod = _install_fake_recoverable(mgr)
        saved = _install_fake_wake_sync()
        try:
            mod.WakeOrchestrator.wake = old_wake
            sm = _FakeStateManager(sleep_hours, datetime.now())
            with mock.patch("os.path.exists", return_value=True):
                old_wake(mod.WakeOrchestrator(sm))
            bad = not mgr.calls
            results.append((label, bad))
        except Exception:
            results.append((label, True))
        finally:
            _restore_modules(saved)
            if old_mod is not None:
                sys.modules["deva.naja.infra.runtime.recoverable"] = old_mod
            else:
                sys.modules.pop("deva.naja.infra.runtime.recoverable", None)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        results = _injections()
        print("=== 负向注入（坏版本必须被抓到）===")
        ok = 0
        for label, bad in results:
            mark = "✅ 抓到" if bad else "❌ 漏了"
            print(f"  {mark}  {label}")
            if bad:
                ok += 1
        print(f"注入检出 {ok}/{len(results)}")
        return 0 if ok == len(results) and results else 1

    fails = _all_checks()
    if fails:
        print("❌ 守卫失败：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✅ 短休眠也会执行组件状态恢复（只跳过补作业）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
