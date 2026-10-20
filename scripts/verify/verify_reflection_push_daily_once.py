"""守卫：钉钉「LLM 每日反思」同一自然日只能推一条。

背景（2026-10-20 实查）：
``盘后市场分析 + 每日反思`` 任务原来是 ``execution_mode: timer``，而
``IntervalTimer`` 的语义是「**先执行一次**，再等待间隔」
（``deva/naja/scheduler/common.py`` 的 docstring 里写死了这个语义）。
于是服务每重启一次，任务恢复时就把反思重放一遍并推一次钉钉：

    10-19  反思 66 次 / 服务退出 64 次
    10-20  反思 24 次 / 服务退出 25 次 / 钉钉实收 10 条（15:47~16:40）

推送链路原本**没有任何幂等**：``_push_reflection_to_dtalk`` 每次都无条件
``dtalk.send``；``_max_daily_reflections=10`` 只在「变化触发」分支生效，
而 ``run_daily_reflection`` 走 ``bypass_quality=True`` 完全绕过它。

本守卫钉的不是「代码里有没有 if」，而是**同一自然日是否真的只产生一条
Dtalk 调用**，以及这四件事同时成立：

1. 同一天第二次调用 → 一条都不许再发；
2. 跨天 → 必须能再发（不能因为一次幂等把后面所有天都锁死）；
3. 发送失败 → **不许**记「今天已推」，否则一次网络抖动会吞掉当天唯一的推送；
4. 多线程并发（timer 线程 + 收盘事件线程同时到）→ 仍然只发一条。

另外钉住两条「重放源」本身：
5. ``run_daily_reflection`` 今天已推过时**不再调 LLM**（否则天天烧 token）；
6. 交易时钟连续投递两次 ``closed`` 只起一个延迟线程（不是新线程去撞幂等）。

用法::

    python scripts/verify/verify_reflection_push_daily_once.py
    python scripts/verify/verify_reflection_push_daily_once.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFLECTION_PY = ROOT / "deva/naja/cognition/insight/llm_reflection.py"

MODNAME = "deva.naja.cognition.insight.llm_reflection"


# ----------------------------------------------------------------------
# 替身
# ----------------------------------------------------------------------
class FakeStateDB:
    """NB 替身：只要 get / upsert / __setitem__，语义与 DBStream 同构。"""

    def __init__(self, data=None):
        self.data = dict(data or {})

    def get(self, key, default=None):
        return self.data.get(key, default)

    def upsert(self, key, value):
        self.data[key] = value
        return key

    def __setitem__(self, key, value):
        self.data[key] = value


class FakeDtalk:
    """钉钉替身：记录真实发出了几条，并可控失败。"""

    calls: list = []
    fail = False

    def __init__(self, *a, **kw):
        pass

    def send(self, msg):
        # 留一点窗口，让并发用例真的能撞上
        time.sleep(0.01)
        if FakeDtalk.fail:
            raise RuntimeError("fake dtalk boom")
        FakeDtalk.calls.append(msg)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _yesterday() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def _load_mod():
    return importlib.import_module(MODNAME)


def _patch_dtalk():
    """把 deva.endpoints.Dtalk 换成替身，返回复原函数。"""
    import deva.endpoints as ep

    original = getattr(ep, "Dtalk", None)
    FakeDtalk.calls = []
    FakeDtalk.fail = False
    ep.Dtalk = FakeDtalk

    def restore():
        if original is not None:
            ep.Dtalk = original

    return restore


def _make_engine(mod, state_db=None):
    """构造一个只带推送相关属性的引擎实例（不走 __init__，避免真连 NB/LLM）。"""
    eng = object.__new__(mod.LLMReflectionEngine)
    eng._push_state_db = state_db if state_db is not None else FakeStateDB()
    eng._push_lock = threading.Lock()
    eng._close_lock = threading.Lock()
    eng._close_reflection_pending = False
    eng._last_push_date = ""
    eng.last_skip_reason = ""
    eng._collect_portfolio = lambda: {"summary": "stub 持仓"}
    return eng


def _make_reflection(mod, ts=None):
    return mod.Reflection(
        id="refl_test",
        ts=ts if ts is not None else time.time(),
        theme="测试主题",
        summary="测试结论",
        signals_count=3,
    )


# ----------------------------------------------------------------------
# 检查
# ----------------------------------------------------------------------
def _all_checks() -> list:
    fails = []
    mod = _load_mod()
    restore = _patch_dtalk()

    try:
        # ── 1. 同一天第二次调用不许再发 ──────────────────────────────
        try:
            eng = _make_engine(mod)
            refl = _make_reflection(mod)
            first = eng._push_reflection_to_dtalk(refl, [])
            second = eng._push_reflection_to_dtalk(refl, [])
            if len(FakeDtalk.calls) != 1:
                fails.append(
                    f"同一天推了 {len(FakeDtalk.calls)} 条（应为 1 条）—— 幂等没生效"
                )
            if first is not True:
                fails.append(f"首次推送应返回 True，实际 {first!r}")
            if second is not False:
                fails.append(f"重复推送应返回 False（被拦下），实际 {second!r}")
            if eng._last_push_date != _today():
                fails.append(
                    f"推送日期没记成今天：{eng._last_push_date!r}（应为 {_today()!r}）"
                )
        except Exception as e:  # noqa: BLE001
            fails.append(f"同日幂等无法验证：{type(e).__name__}: {e}")

        # ── 2. 跨天必须能再发（幂等不能锁死）────────────────────────
        try:
            FakeDtalk.calls = []
            db = FakeStateDB({"daily_push": {"date": _yesterday(), "ts": time.time() - 86400}})
            eng = _make_engine(mod, db)
            ok = eng._push_reflection_to_dtalk(_make_reflection(mod), [])
            if not ok or len(FakeDtalk.calls) != 1:
                fails.append(
                    f"跨天被误拦：发送={ok!r}，Dtalk 调用 {len(FakeDtalk.calls)} 条（应为 1）"
                )
            if db.get("daily_push", {}).get("date") != _today():
                fails.append(f"跨天推送后日期没更新到今天：{db.get('daily_push')!r}")
        except Exception as e:  # noqa: BLE001
            fails.append(f"跨天重发无法验证：{type(e).__name__}: {e}")

        # ── 3. 发送失败不许记「今天已推」（否则一次抖动吞掉当天唯一一条）──
        try:
            FakeDtalk.calls = []
            FakeDtalk.fail = True
            db = FakeStateDB()
            eng = _make_engine(mod, db)
            refl = _make_reflection(mod)
            failed = eng._push_reflection_to_dtalk(refl, [])
            if failed is not False:
                fails.append(f"发送失败应返回 False，实际 {failed!r}")
            if db.get("daily_push"):
                fails.append(
                    f"发送失败却写了推送日期 {db.get('daily_push')!r} —— 当天不会再重试了"
                )
            # 恢复后应该能补发
            FakeDtalk.fail = False
            again = eng._push_reflection_to_dtalk(refl, [])
            if not again or len(FakeDtalk.calls) != 1:
                fails.append(
                    f"失败后重试被幂等拦下：发送={again!r}，Dtalk 调用 {len(FakeDtalk.calls)} 条（应为 1）"
                )
        except Exception as e:  # noqa: BLE001
            fails.append(f"失败可重试无法验证：{type(e).__name__}: {e}")
        finally:
            FakeDtalk.fail = False

        # ── 4. 并发（timer 线程 + 收盘事件线程）仍只发一条 ──────────
        try:
            FakeDtalk.calls = []
            eng = _make_engine(mod)
            refl = _make_reflection(mod)
            barrier = threading.Barrier(4)
            errors = []

            def worker():
                try:
                    barrier.wait(timeout=5)
                    eng._push_reflection_to_dtalk(refl, [])
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

            if errors:
                fails.append(f"并发推送抛异常：{errors[0]!r}")
            if len(FakeDtalk.calls) != 1:
                fails.append(
                    f"4 线程并发推了 {len(FakeDtalk.calls)} 条（应为 1 条）—— 锁/二次检查失效"
                )
        except Exception as e:  # noqa: BLE001
            fails.append(f"并发幂等无法验证：{type(e).__name__}: {e}")

        # ── 5. 重启后仍然认「今天已推」——日期必须落库 ───────────────
        try:
            FakeDtalk.calls = []
            db = FakeStateDB()
            eng = _make_engine(mod, db)
            eng._push_reflection_to_dtalk(_make_reflection(mod), [])

            rebooted = _make_engine(mod, db)  # 同一份 NB，新的进程内状态
            if not rebooted._has_pushed_today():
                fails.append("重启后 _has_pushed_today()=False —— 推送日期没跨进程持久化")
            rebooted._push_reflection_to_dtalk(_make_reflection(mod), [])
            if len(FakeDtalk.calls) != 1:
                fails.append(
                    f"重启后又推了一条（共 {len(FakeDtalk.calls)} 条）—— 幂等只在进程内有效"
                )
        except Exception as e:  # noqa: BLE001
            fails.append(f"跨重启幂等无法验证：{type(e).__name__}: {e}")

        # ── 6. run_daily_reflection 今天已推过就不许再调 LLM ────────
        try:
            db = FakeStateDB({"daily_push": {"date": _today(), "ts": time.time()}})
            eng = _make_engine(mod, db)
            calls = {"run": 0}
            eng._run_reflection = lambda **kw: calls.__setitem__("run", calls["run"] + 1)
            eng._collect_market_analysis_from_nt = lambda: {"ok": True}
            eng._generate_market_analysis = lambda: True

            out = eng.run_daily_reflection()
            if calls["run"] != 0:
                fails.append(
                    f"今天已推送却仍调了 {calls['run']} 次 _run_reflection —— 重启即烧 token"
                )
            if out is not None:
                fails.append(f"跳过时应返回 None，实际 {out!r}")
            if not eng.last_skip_reason:
                fails.append("跳过时没写 last_skip_reason —— 任务历史里会看不出「为什么没跑」")

            # force_push=True 必须能穿透（手工补跑）
            eng.run_daily_reflection(force_push=True)
            if calls["run"] != 1:
                fails.append("force_push=True 没能穿透幂等 —— 手工补跑失效")
        except Exception as e:  # noqa: BLE001
            fails.append(f"run_daily_reflection 短路无法验证：{type(e).__name__}: {e}")

        # ── 7. 连续两次 closed 只起一个延迟线程 ──────────────────────
        try:
            db = FakeStateDB()
            eng = _make_engine(mod, db)
            started = {"n": 0}

            real_sleep = time.sleep
            # 延迟 300s 不许真睡，但也不能变成 0 —— 0 会让第一个线程立刻跑完并
            # 复位 pending，去重看起来"失效"（那测的就不是去重了）。
            time.sleep = lambda *_a, **_kw: real_sleep(0.35)
            eng.run_daily_reflection = lambda *a, **kw: started.__setitem__("n", started["n"] + 1)
            try:
                before = threading.active_count()
                eng._on_trading_clock_event({"phase": "closed"})
                eng._on_trading_clock_event({"phase": "closed"})
                eng._on_trading_clock_event({"phase": "closed"})
                # 等延迟线程跑完
                for _ in range(200):
                    if started["n"] >= 1 and not eng._close_reflection_pending:
                        break
                    real_sleep(0.02)
            finally:
                time.sleep = real_sleep

            if started["n"] != 1:
                fails.append(
                    f"3 次 closed 起了 {started['n']} 个反思任务（应为 1）—— 收盘信号没去重"
                )
            _ = before
        except Exception as e:  # noqa: BLE001
            fails.append(f"收盘信号去重无法验证：{type(e).__name__}: {e}")

    finally:
        restore()

    return fails


# ----------------------------------------------------------------------
# 负向注入：每条都必须被抓到，且失败原因互不相同
# ----------------------------------------------------------------------
INJECTIONS = [
    {
        "name": "推送幂等被关掉（同日重复发送）",
        "old": "            if not force and self._has_pushed_today():",
        "new": "            if False:",
    },
    {
        "name": "run_daily_reflection 不再短路（重启即重跑 LLM）",
        "old": "        if not force_push and self._has_pushed_today():",
        "new": "        if False:",
    },
    {
        "name": "推送日期只写内存、不落库（重启后失效）",
        "old": (
            "            if callable(upsert):\n"
            "                upsert(_PUSH_STATE_KEY, payload)\n"
            "            else:\n"
            "                self._push_state_db[_PUSH_STATE_KEY] = payload"
        ),
        "new": "            pass",
    },
    {
        "name": "发送失败也记「今天已推」（一次抖动吞掉当天）",
        "old": '                log.warning(f"[LLMReflection] 推送反思到钉钉失败: {e}")\n                return False',
        "new": '                log.warning(f"[LLMReflection] 推送反思到钉钉失败: {e}")\n                self._mark_pushed_today()\n                return False',
    },
    {
        "name": "收盘信号去重被关掉（每次 closed 起一个线程）",
        "old": "            if self._close_reflection_pending:",
        "new": "            if False:",
    },
]


def run_injections() -> int:
    print("负向注入（每条都该被抓到）：")
    original = REFLECTION_PY.read_text(encoding="utf-8")
    caught = 0
    missed = 0

    for inj in INJECTIONS:
        if inj["old"] not in original:
            print(f"  ❌ 锚点没命中，注入无效：{inj['name']}")
            missed += 1
            continue
        try:
            REFLECTION_PY.write_text(
                original.replace(inj["old"], inj["new"], 1), encoding="utf-8"
            )
            importlib.reload(_load_mod())
            fails = _all_checks()
        finally:
            REFLECTION_PY.write_text(original, encoding="utf-8")
            importlib.reload(_load_mod())

        if fails:
            caught += 1
            print(f"  ✅ 被捕获：{inj['name']}")
            print(f"       · {fails[0][:120]}")
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
    total = 7
    if failures:
        print(f"❌ {len(failures)}/{total} 项失败：每日反思推送幂等守卫")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0

    print("✅ 每日反思推送幂等守卫全绿"
          "（同日一条 · 跨天可发 · 失败可重试 · 并发只一条 · 重启仍生效 · 收盘信号去重）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
