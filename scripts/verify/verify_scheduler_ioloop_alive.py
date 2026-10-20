#!/usr/bin/env python3
"""守卫：共享调度器（cron）必须真的会自己触发。

## 这份守卫守的是什么

2026-10-20 发现：8 个 ``execution_mode=scheduler`` 的 cron 任务集体静默失效 ——
``news_digest``(19:00)、``ai_daily_report``(21:00)、``knowledge_injector``(22:00)、
``openrouter_monitor``(9:00)、``merrill_clock_update``(4:30)、
``dict_refresh_雪球``(9:30) 全部停在「重启补跑」那一刻（14:02），
``structural_growth_radar`` 则从未执行过一次。

症状极具欺骗性：``add_job`` 返回成功、日志里 ``Added job`` 一条不少、
``next_run_time`` 算得完全正确 —— 就是一个都不跑。

根因是 ``deva/core/when.py`` 把 APScheduler 挂在了**一条永远不会 start() 的
IOLoop** 上：

    container.boot() 里首次构造调度器   → TornadoScheduler 取 IOLoop.current() = loop A
    run_web_application 再清洗一次 loop → AsyncIOMainLoop().install()      = loop B
    Deva.run()                          → 启动的是 loop B
    定时器全在 A 上                      → 永不触发

修法是显式把「流用的、守护线程里真在跑的那条 loop」交给 TornadoScheduler。
这份守卫钉三件事：

1. 调度器用的 loop 必须就是那条在跑的 loop（身份相同，不是「有个 loop」）；
2. **复刻真实启动顺序**跑一遍，2 秒间隔的作业必须真的触发（这是唯一硬判据，
   其它判据都是它的解释）；
3. 健康检查必须查 APScheduler 自己那条 loop —— 查 ``scheduler.loop`` 会得到
   一个恒绿的假象，正是它把这次故障瞒了一整天。

用法：
    python scripts/verify/verify_scheduler_ioloop_alive.py --strict
    python scripts/verify/verify_scheduler_ioloop_alive.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
import textwrap
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
FAILS: list[str] = []

WHEN_SRC = "deva/core/when.py"
CONTAINER_SRC = "deva/naja/application/container.py"

#: 端到端观察窗口（秒）。2 秒间隔 → 正常应触发 3 次左右。
WINDOW = 6.5


def _ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def _bad(msg: str) -> None:
    global FAIL
    FAIL += 1
    FAILS.append(msg)
    print(f"  ❌ {msg}")


def _load(rel_path: str, mod_name: str):
    """按文件路径重载模块。

    ❗不能用 ``import``：拿到的是 ``sys.modules`` 里的旧对象，源码改了也读不到。
    ❗``mod_name`` 必须是**带包名的真名**（``deva.core.when``）：when.py 里全是
    相对导入，用裸名加载会 ``attempted relative import with no known parent``。
    ❗``sys.modules[name] = mod`` 必须在 ``exec_module`` **之前**，
    否则模块内部的 dataclass / 自引用解析会拿到 None。
    """
    path = ROOT / rel_path
    if "." in mod_name:
        import importlib

        importlib.import_module(mod_name.rsplit(".", 1)[0])
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_patched(rel_path: str, mod_name: str, old: str, new: str, count: int = 1):
    """把源码改坏后重新加载（不落盘、不污染工作区）。

    ``count=-1`` 表示替换全部（``str.replace`` 的 0 是「一次都不换」）。
    """
    import types

    path = ROOT / rel_path
    src = path.read_text(encoding="utf-8")
    if old not in src:
        raise AssertionError(f"注入锚点找不到：{old[:60]!r}")
    patched = src.replace(old, new, count)

    mod = types.ModuleType(mod_name)
    mod.__file__ = str(path)
    mod.__package__ = mod_name.rsplit(".", 1)[0] if "." in mod_name else ""
    sys.modules[mod_name] = mod
    exec(compile(patched, str(path), "exec"), mod.__dict__)
    return mod


def _extract_function(src: str, name: str, next_name: str) -> str:
    """从容器源码里抠出一个嵌套函数，便于**行为**验证而不是「源码里出现过某词」。"""
    start = src.index(f"def {name}():")
    end = src.index(f"def {next_name}(", start)
    return textwrap.dedent(src[start:end])


# ── 判据 1：调度器用的 loop 与流用的是同一条，且在跑 ────────────────────────
def check_loop_identity(when_mod) -> None:
    print("\n[1] 绑定身份：APScheduler 的 loop 必须就是流那条在跑的 loop")
    s = when_mod.scheduler(start=False)
    inner = getattr(s, "_scheduler", None)
    if inner is None:
        _bad("scheduler 没有内部 _scheduler —— 结构变了，这份守卫需要跟着改")
        return
    sched_loop = getattr(inner, "_ioloop", None)
    if sched_loop is None:
        _bad("TornadoScheduler._ioloop 为空")
        return
    if sched_loop is not s.loop:
        _bad(
            "APScheduler 挂在另一条 loop 上（不是流用的那条）—— "
            "boot 之后有人 install() 了新 loop，定时器就会永远等不到唤醒"
        )
        return
    _ok("APScheduler 的 _ioloop 与流的 loop 是同一实例")

    if not s.ioloop_running:
        _bad("那条 loop 没有在跑 —— 定时器不会触发（add_job 照样返回成功）")
        return
    _ok("该 loop 的 asyncio_loop.is_running() 为真")


# ── 判据 2：复刻真实启动顺序，作业必须真的触发 ──────────────────────────────
def _churn_then_wait(when_mod, seconds: float = WINDOW) -> list:
    """复刻 run_web_application 的真实顺序，返回作业实际触发的时间戳。

    顺序来自 ``deva/naja/application/web.py``：
        _ensure_clean_event_loop()  # 第 76 行，boot 之前
        container.boot()            # 期间首次构造共享调度器
        _ensure_clean_event_loop()  # 第 116 行，boot 之后（会 install 新 loop）
        Deva.run()                  # 启动「当前」loop
    """
    import asyncio

    from deva.naja.application.web import _ensure_clean_event_loop

    _ensure_clean_event_loop()
    s = when_mod.scheduler(start=True)

    _ensure_clean_event_loop()

    fired: list[float] = []
    s.add_job(
        func=lambda: fired.append(time.time()),
        name="guard_probe",
        trigger="interval",
        seconds=2,
    )

    loop = asyncio.get_event_loop_policy().get_event_loop()
    loop.call_later(seconds, loop.stop)
    loop.run_forever()

    try:
        s.remove_job("guard_probe")
    except Exception:  # noqa: BLE001
        pass
    try:
        s.stop()
    except Exception:  # noqa: BLE001
        pass
    return fired


def check_end_to_end(when_mod) -> None:
    print("\n[2] 端到端：loop 被换血之后，定时作业必须仍然触发")
    fired = _churn_then_wait(when_mod)
    if not fired:
        _bad(
            "6.5 秒内作业一次都没触发 —— 定时器挂在了没有 start() 的 loop 上。"
            "这正是 8 个 cron 任务停在 14:02 的原因"
        )
        return
    if len(fired) < 2:
        _bad(f"只触发了 {len(fired)} 次（2 秒间隔应≥2 次）—— 触发一次就停同样是坏了")
        return
    gaps = [round(b - a, 2) for a, b in zip(fired, fired[1:])]
    _ok(f"6.5 秒内触发 {len(fired)} 次，间隔 {gaps} 秒（作业在持续被调度）")


# ── 判据 3：loop 死掉时必须告警，不许静默 ──────────────────────────────────
class _Recorder:
    """替身：接住 ``when.log.warning``。

    ``when.log`` 是 bus 里的 Stream（不是 logging.Logger），拿不到 ``level``
    之类的属性，所以按「被调用的行为」记消息，而不是去读日志级别。
    """

    def __init__(self):
        self.messages: list[str] = []

    def warning(self, msg, *args, **kwargs):  # noqa: ARG002
        self.messages.append(msg % args if args else msg)


def check_warns_when_loop_dead(when_mod) -> None:
    print("\n[3] 自我保护：loop 没在跑时必须留下告警，不能静默")
    from tornado.ioloop import IOLoop

    dead = IOLoop()  # 造出来但绝不 start()

    recorder = _Recorder()
    saved_log = getattr(when_mod, "log", None)
    if saved_log is None:
        _bad("when.py 里没有 log 对象，无法断言告警")
        return
    when_mod.log = recorder
    try:
        # 显式把一条「没启动」的 loop 交进去 —— 这正是故障时的形态
        s = when_mod.scheduler(start=True, loop=dead)
        try:
            s.stop()
        except Exception:  # noqa: BLE001
            pass
    finally:
        when_mod.log = saved_log

    warned = [m for m in recorder.messages if "定时任务都不会触发" in m]
    if not warned:
        _bad(
            "把调度器绑到一条没启动的 loop 上，居然一声不响 —— "
            "cron 全哑了也没人会发现"
        )
        return
    _ok(f"已告警：{warned[0][:60]}…")


# ── 判据 4/5：容器健康检查必须查对 loop ────────────────────────────────────
class _FakeScheduler:
    def __init__(self, running: bool):
        self._running = running

    @property
    def ioloop_running(self):
        return self._running


def check_health_check_target(when_mod) -> None:
    print("\n[4] 健康检查：必须查 APScheduler 的 loop，不能查流的 loop")
    src = (ROOT / CONTAINER_SRC).read_text(encoding="utf-8")
    if 'getattr(getattr(scheduler, "loop", None), "asyncio_loop", None)' in src:
        _bad(
            "健康检查还在读 scheduler.loop（流用的那条，恒在跑）—— "
            "定时器挂了它也是绿的，假健康检查"
        )
        return
    _ok("健康检查没有读 scheduler.loop")

    code = _extract_function(src, "check_shared_scheduler", "check_jobs_registered")
    ns: dict = {}
    try:
        exec(compile(code, str(ROOT / CONTAINER_SRC), "exec"), ns)
    except Exception as e:  # noqa: BLE001
        _bad(f"健康检查函数抠不出来（结构变了）：{type(e).__name__}: {e}")
        return
    fn = ns.get("check_shared_scheduler")
    if not callable(fn):
        _bad("抠出来的 check_shared_scheduler 不可调用")
        return

    from deva.naja.scheduler.common import SchedulerManager

    mgr = SchedulerManager()
    saved = mgr._scheduler
    try:
        print("\n[5] 健康检查的行为：loop 死 → 红；loop 活 → 绿")
        mgr._scheduler = _FakeScheduler(False)
        if fn() is not False:
            _bad("loop 没在跑时健康检查仍返回 True —— 这就是那个恒绿的假象")
        else:
            _ok("loop 死掉时健康检查判红")
        mgr._scheduler = _FakeScheduler(True)
        if fn() is not True:
            _bad("loop 在跑时健康检查却判红 —— 恒红假告警同样是坏")
        else:
            _ok("loop 在跑时健康检查判绿")
    finally:
        mgr._scheduler = saved


def _expect_catch(label: str, fn, should_fail_msg: str) -> bool:
    """跑一个判据，期望它**失败**；跑完把全局计数复原。"""
    global PASS, FAIL
    saved_pass, saved_fail = PASS, FAIL
    saved_fails = list(FAILS)
    before = FAIL
    try:
        fn()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    caught = FAIL > before
    detail = FAILS[before:]
    PASS, FAIL = saved_pass, saved_fail
    FAILS[:] = saved_fails
    if caught:
        print(f"  ✅ 被捕获：{label} → {detail[0][:70] if detail else ''}")
    else:
        print(f"  ❌ 没抓到：{label} —— {should_fail_msg}")
    return caught


def _run_injections() -> int:
    print("\n" + "=" * 70)
    print("负向注入自证（把修复改回坏版本，守卫必须喊出来）")
    print("=" * 70)

    results: list[bool] = []

    # 注入 1：去掉 io_loop，退回「用当前线程的 loop」（原始 bug 本体）
    print("\n[注入 1] 去掉 io_loop=，退回 IOLoop.current()")
    try:
        mod = _load_patched(WHEN_SRC, "deva.core.when", "io_loop=io_loop,", "")
        results.append(_expect_catch(
            "loop 被换血后作业不触发",
            lambda: check_end_to_end(mod),
            "退回默认 loop 后作业还能触发 —— 守卫抓不到原始 bug，等于没守",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 2：把 io_loop 显式指向「当前线程的 loop」（等价于旧行为，但代码里看着像传了）
    print("\n[注入 2] io_loop 指向当前线程的 loop（表面上「有传」，实际仍是孤儿）")
    try:
        mod = _load_patched(
            WHEN_SRC, "deva.core.when",
            "io_loop=io_loop,",
            'io_loop=__import__("tornado.ioloop", fromlist=["IOLoop"]).IOLoop.current(),',
        )
        results.append(_expect_catch(
            "身份不一致",
            lambda: check_loop_identity(mod),
            "绑到别的 loop 上，身份判据仍然绿",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 3：去掉「loop 没在跑」的告警
    print("\n[注入 3] 去掉 loop 死亡时的告警")
    try:
        mod = _load_patched(
            WHEN_SRC, "deva.core.when",
            "            if self.ioloop_running:\n                return",
            "            if True:\n                return",
        )
        results.append(_expect_catch(
            "loop 死了也不吭声",
            lambda: check_warns_when_loop_dead(mod),
            "不告警也判绿 —— 下一次静默失效依旧没人发现",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    # 注入 4：健康检查改回读 scheduler.loop
    print("\n[注入 4] 健康检查改回读 scheduler.loop")
    try:
        src = (ROOT / CONTAINER_SRC).read_text(encoding="utf-8")
        patched = src.replace(
            "            check = getattr(scheduler, \"ioloop_running\", None)",
            "            check = None",
            1,
        )
        patched = patched.replace(
            '            inner = getattr(scheduler, "_scheduler", None)',
            '            inner = getattr(scheduler, "loop", None)',
            1,
        )
        if patched == src:
            raise AssertionError("注入锚点找不到")
        results.append(_expect_catch(
            "健康检查查错 loop",
            lambda: check_health_check_target_source(patched),
            "改回读 scheduler.loop 仍判绿 —— 假健康检查复辟",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 锚点失效：{e}")
        results.append(False)

    print("\n" + "=" * 70)
    caught = sum(1 for r in results if r)
    print(f"负向注入：{caught}/{len(results)} 被捕获")
    if caught != len(results):
        print("❗ 有注入没被抓到 —— 对应判据是摆设")
        return 1
    print("✅ 每条注入都被捕获")
    return 0


def check_health_check_target_source(src: str) -> None:
    """只做源码层判定（注入时用，避免为了测一句源码就把对象换掉）。"""
    print("\n[4-inj] 健康检查源码层判定")
    if 'getattr(getattr(scheduler, "loop", None), "asyncio_loop", None)' in src:
        _bad("健康检查读的是 scheduler.loop")
        return
    if 'getattr(scheduler, "loop", None)' in src or 'getattr(scheduler, "loop"' in src:
        _bad("健康检查读的是 scheduler.loop（变体写法）")
        return
    _ok("健康检查读的是 APScheduler 的 loop")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--exercise-injections", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print("共享调度器 IOLoop / cron 触发 守卫")
    print("=" * 70)

    try:
        when_mod = _load(WHEN_SRC, "deva.core.when")
    except Exception as e:  # noqa: BLE001
        print(f"❌ 模块加载失败：{type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    for fn in (
        lambda: check_loop_identity(when_mod),
        lambda: check_end_to_end(when_mod),
        lambda: check_warns_when_loop_dead(when_mod),
        lambda: check_health_check_target(when_mod),
    ):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _bad(f"判据执行异常：{type(e).__name__}: {e}")
            traceback.print_exc()

    total = PASS + FAIL
    print("\n" + "=" * 70)
    if FAIL:
        print(f"❌ {FAIL}/{total} 项失败")
        for f in FAILS:
            print(f"   - {f}")
        return 1
    print(f"✅ 全部 {total} 项通过")

    if args.exercise_injections:
        return _run_injections()
    if args.strict:
        print("（--strict：仅判据，未跑负向注入）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
