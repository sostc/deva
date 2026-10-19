#!/usr/bin/env python3
"""守卫 deva 总线（RedisStream）在**进程收尾时闭嘴**，别把退出噪声甩成 traceback。

================================================================================
背景（2026-10-19 实锤）
================================================================================

``import deva`` 就会起一个事件总线：``deva/core/bus.py`` 的 ``BusRuntime`` 底层是
``deva/core/sources.py`` 的 ``RedisStream(topic='bus')``，对本机 Redis 做阻塞式
``xreadgroup``。任何跑 ``deva.naja`` 的东西（服务本身、每一份守卫）都躲不开它。

进程退出时会这样：``stop()`` 关连接（或者循环/thread 先烂），阻塞中的那条读操作
必然抛 ``ConnectionError: Connection closed by server.``。而 ``RedisStream.process``
原来是**无差别**记. ``logger.exception(...)`` 再重试：

    except Exception:
        retry_count += 1
        logger.exception("RedisStream(%s) loop failed (retry %s/%s)", ...)

于是输出里出现一行道歉式 traceback，而且**位置在守卫自己的结论行之后**——
``run_all_guards`` 的摘要当时是倒着扫输出的，这条 redis 噪声就把真正的
``❌ 9/25 项失败`` 顶掉了。两份做 T 守卫因此被当成"环境问题"忽略了一整轮。

**这是运行 cessation，不是故障**：连接是我们自己关的，报错只是"我关掉了还在读的
那条连接"。它既不该上控制台，也不该进诊断摘要。

================================================================================
核心不变量
================================================================================

**已停止（``self.stopped``）时的连接错误必须静默返回；未停止时的真实连接故障仍要
照常告警重试。**

只有前半句是 bug 的一半 —— 也必须有后半句的反向约束：如果把**所有**连接错误都
吞掉，Redis 真的挂了就没人知道，总线会静默失联（那就是"合法的空比异常更危险"
的标准形态）。

================================================================================
用法
================================================================================

    python3 scripts/verify/verify_deva_bus_quiet_exit.py
    python3 scripts/verify/verify_deva_bus_quiet_exit.py --strict
    python3 scripts/verify/verify_deva_bus_quiet_exit.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES_PY = REPO / "deva" / "core" / "sources.py"
BUS_LOGGER = "deva.core.sources"


def _rel(p: Path) -> str:
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


class _ClosedConnRedis:
    """替身 redis 客户端：模拟「连接已被自己的 ``stop()`` 拆掉」。

    ``stop()`` 与阻塞读是并发的，真实时序就是：``stopped`` 置 True 的同一会儿
    读操作炸了。所以这里在读的那一刻把 ``stopped`` 翻上去，贴近真实现。
    """

    def __init__(self, stream, flip: bool = True):
        self._stream = stream
        self._flip = flip

    def xread(self, **kwargs):
        if self._flip:
            self._stream.stopped = True
        raise ConnectionError("Connection closed by server.")

    def xreadgroup(self, **kwargs):
        return self.xread(**kwargs)


async def _run_process(stream, timeout: float = 3.0):
    """跑一遍 ``process()`` 并返回 ``(抛出的异常, 日志记录列表)``。"""
    logger = logging.getLogger(BUS_LOGGER)
    records: list = []
    handler = logging.Handler()
    handler.setLevel(logging.DEBUG)
    handler.emit = lambda rec: records.append(rec)
    orig_level, orig_exc, orig_prop = logger.level, logger.exception, logger.propagate
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    # 关掉向上传递：反方向用例（运行中真故障）本来就该告警，那条 traceback 是
    # 被测行为的一部分，不该污染本守卫自己的输出。收핸들 里照样收得到。
    logger.propagate = False
    raised: BaseException | None = None
    try:
        await asyncio.wait_for(stream.process(), timeout=timeout)
    except BaseException as e:  # noqa: BLE001 - TimeoutError 也算在内
        raised = e
    finally:
        logger.removeHandler(handler)
        logger.setLevel(orig_level)
        logger.propagate = orig_prop
        logger.exception = orig_exc
    return raised, records


def _error_records(records) -> list:
    return [r for r in records if r.levelno >= logging.ERROR]


def _sources_module():
    """❗**必须 reload**：注入写的是磁盘上的源码，而 ``sys.modules`` 里留着旧对象。

    不复载的话第一条注入会把"坏版本"固化在内存里，后面每条注入其实都在测它
    —— 全绿全是假的（这条在别处已经吃过一次，见叙事守卫的注入实践）。
    """
    import importlib

    import deva.core.sources as sources

    importlib.reload(sources)
    return sources


def _make_stream(retries: int = 5, flip: bool = True):
    stream = _sources_module().RedisStream("unit-test-quiet-exit", start=False)
    stream.stopped = False
    stream.retries = retries
    stream.redis = _ClosedConnRedis(stream, flip=flip)
    return stream


# ── 检查项 ───────────────────────────────────────────────────────────────────
def check_stopped_is_silent() -> list:
    """已停止时的连接断开：不许再甩 traceback（它是收尾，不是故障）。"""
    try:
        stream = _make_stream()
    except Exception as e:  # noqa: BLE001
        return [f"构造 RedisStream 失败：{type(e).__name__}: {e}"]

    raised, records = asyncio.run(_run_process(stream))
    errs = _error_records(records)
    if errs:
        return [
            f"已停止时仍以 ERROR 级别记了 {len(errs)} 条（{errs[0].getMessage()[:60]}…）—— "
            f"进程收尾会甩一整条 redis traceback，排在守卫结论行之后，"
            f"把失败摘要顶成无关的 redis"
        ]
    if raised is not None and not isinstance(raised, asyncio.TimeoutError):
        return [
            f"已停止时 process 抛出了 {type(raised).__name__}: {raised} —— "
            f"收尾路径不该有事传播出去"
        ]
    return []


def check_running_failure_still_alerts() -> list:
    """反方向：真正在跑时连接断开，必须照常告警（不许连真故障一起吞）。"""
    try:
        stream = _make_stream(retries=0, flip=False)
    except Exception as e:  # noqa: BLE001
        return [f"构造 RedisStream 失败：{type(e).__name__}: {e}"]

    raised, records = asyncio.run(_run_process(stream))
    if not _error_records(records):
        return [
            "运行中断开连接却完全没有 ERROR 级告警 —— 把「收尾静默」写成了"
            "「无条件静默」，Redis 真挂了会变成总线静默失联（比报错危险）"
        ]
    return []


def check_source_has_stopped_guard() -> list:
    """源码层面锚点：except 里必须先判 ``self.stopped`` 才能静默。"""
    tree = ast.parse(SOURCES_PY.read_text(encoding="utf-8"))
    fn = None
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RedisStream"]:
        for node in cls.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "process":
                fn = node
    if fn is None:
        return [f"{_rel(SOURCES_PY)} 找不到 RedisStream.process —— 锚点腐烂"]

    has_stopped_check = any(
        isinstance(n, ast.Attribute) and n.attr == "stopped"
        for n in ast.walk(fn)
    )
    if not has_stopped_check:
        return [
            f"{_rel(SOURCES_PY)} 的 RedisStream.process 没有判 stopped —— "
            f"退出噪声会回来"
        ]
    return []


def _all_checks() -> list:
    failures: list = []
    failures += check_stopped_is_silent()
    failures += check_running_failure_still_alerts()
    failures += check_source_has_stopped_guard()
    return failures


# ── 负向注入 ─────────────────────────────────────────────────────────────────
INJECTIONS = [
    {
        "name": "stopped 判定被短路（回到原来的无差别告警）",
        "old": "                if self.stopped:\n",
        "new": "                if False:\n",
    },
    {
        "name": "改成无条件静默（连真故障一起吞，总线会静默失联）",
        "old": "                if self.stopped:\n",
        "new": "                if True:\n",
    },
    {
        "name": "logger.debug 改成 logger.exception（静默失效：噪声回来了）",
        "old": "                    logger.debug(\n                        \"RedisStream(%s) 已停止",
        "new": "                    logger.exception(\n                        \"RedisStream(%s) 已停止",
    },
    {
        # 反方向：注释里说到 stopped 不代表真的判了 stopped
        "name": "注释里出现 stopped（反方向：不许误报）",
        "old": "                if self.stopped:\n",
        "new": "                # stopped 只出现在注释里，判定没有变\n                if self.stopped:\n",
        "expect_clean": True,
    },
]


def run_injections() -> int:
    original = SOURCES_PY.read_text(encoding="utf-8")
    caught, expected, missed = 0, len(INJECTIONS), 0
    try:
        for inj in INJECTIONS:
            hits = original.count(inj["old"])
            if hits != 1:
                missed += 1
                print(f"❌ 注入锚点命中 {hits} 次（期望 1，守卫腐烂信号）：{inj['name']}")
                continue
            print(f"· 注入：{inj['name']}")
            SOURCES_PY.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
            try:
                found = _all_checks()
            except Exception as e:  # noqa: BLE001
                found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
            finally:
                SOURCES_PY.write_text(original, encoding="utf-8")

            if inj.get("expect_clean"):
                if found:
                    print(f"  ❌ 反方向用例被误报：{found[0][:110]}")
                else:
                    caught += 1
                    print("  ✅ 正确地没有报警（注释不是真的判定）")
            elif found:
                caught += 1
                print(f"  ✅ 被捕获（{len(found)} 项）")
                for f in found[:2]:
                    print(f"       · {f[:110]}")
            else:
                print("  ❌ 没抓到 —— 这条守卫是摆设！")
    finally:
        if SOURCES_PY.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            SOURCES_PY.write_text(original, encoding="utf-8")

    print(f"\n负向注入：{caught}/{expected} 被捕获"
          + (f"（另有 {missed} 条锚点未命中，已计失败）" if missed else ""))
    return caught if not missed else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = _all_checks()
    if failures:
        print("❌ 总线收尾静默守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 总线收尾静默守卫全绿"
          "（已停止时不traceback · 运行中真故障仍告警 · 源码有 stopped 判定）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
