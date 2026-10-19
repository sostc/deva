"""守卫：NarrativeTracker 全仓唯一实例。

背景（2026-10-19 实测，不是推测）：

同一进程内曾并存两个 NarrativeTracker——

  * ``cognition/core.py`` 里 ``NewsMindStrategy.narrative_tracker``，
    由 ``radar/news_fetcher.py → process_record → ingest_event`` 喂；
  * ``cognition/narrative/tracker.py`` 的 ``get_narrative_tracker()`` 单例，
    由 ``event_registrar`` 订阅 ``TextFocusedEvent`` 喂。

日志实证：每次进程启动「从持久化恢复 10 个叙事状态」都出现两次（两个实例
各自 ``__init__`` 里 ``_load_state()``）。实测一个 16 条、一个 10 条。

危害排序：
  1. **决策与展示不是同一份数据**：Manas / TradingCenter 读单例，认知页读
     引擎内实例。同一个 ``llm_reflection.py`` 里 373 行读单例、587/703/715/817
     行读引擎内实例。
  2. **状态互相整表覆盖**：``save_state()`` 是全量覆写 + 截断 top10，两边交替
     写 → 一方积累的叙事会被另一方冲掉。
  3. **"有数据"证明不了在干活**：``__init__`` 里就 ``_load_state()``，所以僵尸
     快照和活实例长得一模一样。

本守卫把「只走 ``get_narrative_tracker()``」钉成硬约束。
"""

from __future__ import annotations

import argparse
import ast
import importlib
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NAJA = REPO / "deva" / "naja"

TRACKER_PY = NAJA / "cognition" / "narrative" / "tracker.py"
CORE_PY = NAJA / "cognition" / "core.py"
SIGNAL_EXEC_PY = NAJA / "attention" / "orchestration" / "signal_executor.py"
ORCHESTRATOR_PY = NAJA / "attention" / "orchestration" / "cognition_orchestrator.py"
DAILY_REVIEW_PY = NAJA / "strategy" / "daily_review.py"
KERNEL_PY = NAJA / "attention" / "kernel" / "kernel.py"
REGISTRAR_PY = NAJA / "application" / "event_registrar.py"
TRADING_CENTER_PY = NAJA / "attention" / "orchestration" / "trading_center.py"
NARRATIVE_UI_PY = NAJA / "cognition" / "ui" / "components" / "narrative_track.py"

#: 唯一允许直接构造的地方：单例工厂本体
ALLOW_DIRECT_CONSTRUCTION = {"cognition/narrative/tracker.py"}


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _mod():
    """❗必须 reload：注入改的是源码，旧模块对象留在 sys.modules 里会让注入
    看起来"没生效"，也会让多条注入的失败原因全都一样（假捕获）。"""
    m = importlib.import_module("deva.naja.cognition.narrative.tracker")
    return importlib.reload(m)


# ── 检查项 ───────────────────────────────────────────────────────────────────

def check_no_direct_construction() -> list:
    """全仓禁止 ``NarrativeTracker()`` 直接构造。

    ❗用 AST 而不是文本匹配：代码里到处是「不要直接 NarrativeTracker()」的
    注释和 docstring，裸扫会误报，真注入反而被淹没。
    """
    failures: list = []
    for path in NAJA.rglob("*.py"):
        rel = path.relative_to(NAJA).as_posix()
        if rel in ALLOW_DIRECT_CONSTRUCTION:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "NarrativeTracker"
            ):
                failures.append(
                    f"{_rel(path)}:{node.lineno} 直接构造 NarrativeTracker() —— "
                    f"必须走 get_narrative_tracker()，否则会出现第二份状态、"
                    f"整表覆写别人的持久化数据，且决策与展示读到不同实例"
                )
    return failures


def check_singleton_identity() -> list:
    """``get_narrative_tracker()`` 必须是真单例：已存在时不重建、config 只在首
    次生效、后到的 config 必须告警而不是静默丢弃。"""
    failures: list = []
    T = _mod()

    captured: dict = {}

    class _Fake:
        def __init__(self, config=None):
            captured["config"] = config

    orig_cls = T.NarrativeTracker
    orig_inst = T._narrative_tracker_instance

    logger = logging.getLogger(T.__name__)
    records: list = []

    class _Handler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    h = _Handler()
    logger.addHandler(h)
    try:
        T.NarrativeTracker = _Fake
        T._narrative_tracker_instance = None

        first = T.get_narrative_tracker({"narrative_peak_count": 99})
        if first is None:
            failures.append("首次调用返回 None —— 叙事链路会全部降级为空")
        if captured.get("config") != {"narrative_peak_count": 99}:
            failures.append(
                f"首次创建没有把 config 传给构造函数（收到 {captured.get('config')}）—— "
                f"core.py 传的配置会静默失效"
            )

        # 第二次：不重建
        second = T.get_narrative_tracker({"narrative_peak_count": 1})
        if second is not first:
            failures.append("第二次调用重建了实例 —— 不是单例，又会出现两份状态")
        if captured.get("config") != {"narrative_peak_count": 99}:
            failures.append("已存在时仍把新 config 灌进了构造函数")

        # 后到的 config 必须告警（"改了配置没效果"属于静默失效）
        if not any("忽略后到的" in r for r in records):
            failures.append(
                "单例已存在时后到的 config 被静默忽略且不告警 —— 将来有人改了 "
                "narrative_* 配置会发现永远不生效，且查不到原因"
            )
    finally:
        logger.removeHandler(h)
        T.NarrativeTracker = orig_cls
        T._narrative_tracker_instance = orig_inst
    return failures


def check_core_uses_singleton() -> list:
    """``NewsMindStrategy.narrative_tracker`` 必须来自单例工厂。"""
    tree = _parse(CORE_PY)
    if tree is None:
        return [f"{_rel(CORE_PY)} 解析失败"]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [
            t for t in node.targets
            if isinstance(t, ast.Attribute) and t.attr == "narrative_tracker"
        ]
        if not targets:
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "get_narrative_tracker"
        ):
            return []
        return [
            f"{_rel(CORE_PY)}:{node.lineno} NewsMindStrategy.narrative_tracker 不是从 "
            f"get_narrative_tracker() 取的 —— 认知引擎内会再长出一个实例，"
            f"与决策链路读的单例分裂"
        ]
    return [f"{_rel(CORE_PY)} 找不到 narrative_tracker 赋值 —— 守卫锚点腐烂"]


def check_construction_failure_not_silent() -> list:
    """单例构造失败必须打日志。

    ❗``except: return None`` 会让所有消费者降级成「叙事恒空」，而页面上分不清
    是构造失败还是真的没叙事。
    """
    tree = _parse(TRACKER_PY)
    if tree is None:
        return [f"{_rel(TRACKER_PY)} 解析失败"]
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_narrative_tracker":
            for handler in ast.walk(node):
                if not isinstance(handler, ast.ExceptHandler):
                    continue
                logged = any(
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("error", "warning", "exception", "critical")
                    for n in ast.walk(handler)
                )
                if not logged:
                    return [
                        f"{_rel(TRACKER_PY)}:{handler.lineno} 构造失败分支没有日志 —— "
                        f"失败会静默返回 None，叙事恒空却查不到原因"
                    ]
            return []
    return [f"{_rel(TRACKER_PY)} 找不到 get_narrative_tracker —— 守卫锚点腐烂"]


def check_consumers_share_source() -> list:
    """决策链路与展示必须同一个来源；展示侧还要能识别"其实是同一个对象"。"""
    failures: list = []

    tc = TRADING_CENTER_PY.read_text(encoding="utf-8")
    if "get_narrative_tracker()" not in tc:
        failures.append(
            f"{_rel(TRADING_CENTER_PY)} 没用 get_narrative_tracker() —— "
            f"Manas 读的叙事与页面展示的不是同一份"
        )

    reg = REGISTRAR_PY.read_text(encoding="utf-8")
    if "get_narrative_tracker()" not in reg:
        failures.append(
            f"{_rel(REGISTRAR_PY)} 没用单例订阅 —— 事件总线会喂给另一个实例"
        )

    ui = NARRATIVE_UI_PY.read_text(encoding="utf-8")
    if "get_narrative_tracker()" not in ui:
        failures.append(
            f"{_rel(NARRATIVE_UI_PY)} 没引用单例 —— 页面与决策读的不是同一份"
        )
    if "id(tracker) in seen" not in ui:
        failures.append(
            f"{_rel(NARRATIVE_UI_PY)} 没有按对象身份去重 —— 收敛后诊断块仍会把"
            f"同一个实例列成两份，页面继续谎报「存在多个 tracker 实例」"
        )
    return failures


def check_other_construction_sites_converted() -> list:
    """历史遗留的其它构造点必须已改为单例（防止有人照着老代码抄回去）。"""
    failures: list = []
    for path, label in (
        (SIGNAL_EXEC_PY, "SignalExecutor"),
        (ORCHESTRATOR_PY, "CognitionOrchestrator"),
        (DAILY_REVIEW_PY, "DailyReviewAnalyzer"),
        (KERNEL_PY, "AttentionKernel"),
    ):
        src = path.read_text(encoding="utf-8")
        if "NarrativeTracker" not in src:
            continue
        if "get_narrative_tracker" not in src:
            failures.append(
                f"{_rel(path)}（{label}）还在直接构造 NarrativeTracker "
                f"—— 每次调用都会新建实例并整表覆写状态"
            )
    return failures


def _all_checks() -> list:
    failures: list = []
    failures += check_no_direct_construction()
    failures += check_singleton_identity()
    failures += check_core_uses_singleton()
    failures += check_construction_failure_not_silent()
    failures += check_consumers_share_source()
    failures += check_other_construction_sites_converted()
    return failures


# ── 负向注入 ─────────────────────────────────────────────────────────────────
INJECTIONS = [
    {
        "name": "core.py 改回直接构造（引擎内再长出一个实例）",
        "path": CORE_PY,
        "old": "        self.narrative_tracker = get_narrative_tracker(self.config)",
        "new": "        self.narrative_tracker = NarrativeTracker(self.config)",
    },
    {
        "name": "signal_executor 改回每次新建实例",
        "path": SIGNAL_EXEC_PY,
        "old": "            tracker = get_narrative_tracker()",
        "new": "            tracker = NarrativeTracker()",
    },
    {
        "name": "单例工厂每次都重建（单例性被破坏）",
        "path": TRACKER_PY,
        "old": "    if _narrative_tracker_instance is None:\n        try:",
        "new": "    if True:\n        try:",
    },
    {
        "name": "构造失败改回静默（叙事恒空却查不到原因）",
        "path": TRACKER_PY,
        "old": '            log.error(f"[NarrativeTracker] 单例构造失败，叙事链路将全部降级为空: {e}")\n            return None',
        "new": "            return None",
    },
    {
        "name": "去掉 UI 按对象身份去重（收敛后仍谎报多个实例）",
        "path": NARRATIVE_UI_PY,
        "old": "            if id(tracker) in seen:\n                dupes.append(name)\n                continue",
        "new": "            if False:\n                dupes.append(name)\n                continue",
    },
    {
        # ❗反方向用例：注释里出现 NarrativeTracker() 不许被判违规，
        # 否则"禁止直接构造"这条检查会因为自己在注释里写了它而永远红。
        "name": "注释里出现 NarrativeTracker()（反方向：不许误报）",
        "path": CORE_PY,
        "old": "        # 叙事追踪器\n",
        "new": "        # 叙事追踪器 —— 别写成 NarrativeTracker() 直接构造\n",
        "expect_clean": True,
    },
]


def run_injections() -> int:
    caught = 0
    expected = len(INJECTIONS)
    missed: list = []
    for inj in INJECTIONS:
        path: Path = inj["path"]
        original = path.read_text(encoding="utf-8")
        hits = original.count(inj["old"])
        if hits != 1:
            missed.append(inj["name"])
            print(f"❌ 注入锚点命中 {hits} 次（期望 1，守卫腐烂信号）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")

        if inj.get("expect_clean"):
            if found:
                print(f"  ❌ 反方向用例被误报：{found[0][:110]}")
            else:
                caught += 1
                print("  ✅ 正确地没有报警（注释不算构造）")
        elif found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            for f in found[:3]:
                print(f"       · {f[:110]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")

        if path.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            path.write_text(original, encoding="utf-8")

    print(f"\n负向注入：{caught}/{expected} 被捕获"
          + (f"（另有 {len(missed)} 条锚点未命中，已计失败）" if missed else ""))
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
        print("❌ 叙事单例守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 叙事单例守卫全绿"
          "（无直接构造 · 真单例 · core 走工厂 · 失败不静默 · 决策与展示同源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
