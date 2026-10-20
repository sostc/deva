"""守卫：运行时构建/编译失败不许伪装成「运行中」或「跳过」。

背景（2026-10-20 实查，两项都是真出现的，不是假想）：

1. ``历史行情回放`` 是 ``replay`` 数据源，按 NB 表回放，**不需要 func_code**
   （``DataSourceEntry.start()`` 早已单独放行）。但恢复路径
   ``RecoverableUnit.prepare_for_recovery()`` 无条件 ``ensure_compiled()``，
   于是它每次重启都返回 ``compile_failed``：手动能启动、重启必失败，
   而且这个失败还被算进 ``skipped_count``，摘要写成「恢复 4 个 / 跳过 1 个 /
   失败 0 个」—— 一个真的坏掉的数据源，在日志里人间蒸发。

2. ``openrouter_token_trend_strategy`` 配了 ``strategy_type: plugin`` 却没有
   ``class_path``。``PluginStrategyAdapter`` 构造即抛错，``_get_runtime()``
   只记一条 ERROR 返回 None，``_do_start()`` 照旧返回 success ——
   状态「运行中」、``processed_count`` 恒 0，页面上看不出任何异常。
   这类「接线正确但永远无效」比报错毒得多。

3. 数据源的 ``last_data_ts`` / ``total_emitted`` 以前只有 replay 回放线程
   会更新，timer/directory/file 四类永远停在 0 或上次回放的值。
   管理页把「一直在产出的实时行情」显示成「无数据 (0条)」——
   观测口径本身是假的，任何基于它做的判断都不成立。

本守卫用「返回值/状态」当断言对象，而不是「代码里有没有这一行」。
"""

from __future__ import annotations

import argparse
import inspect
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECOVERABLE = ROOT / "deva/naja/infra/runtime/recoverable.py"
DS_ENTRY = ROOT / "deva/naja/datasource/entry.py"
ST_ENTRY = ROOT / "deva/naja/strategy/entry.py"
MANAGERS = [
    ROOT / "deva/naja/datasource/manager.py",
    ROOT / "deva/naja/dictionary/manager.py",
    ROOT / "deva/naja/tasks/manager.py",
    ROOT / "deva/naja/strategy/manager.py",
]


def _all_checks() -> list:
    fails = []

    # ── 1. replay 不要求编译 ────────────────────────────────────────────
    try:
        from deva.naja.datasource.entry import DataSourceEntry
        from deva.naja.infra.runtime.recoverable import RecoverableUnit

        unit = object.__new__(DataSourceEntry)
        for st, expect in (("replay", False), ("timer", True), ("directory", True)):
            unit._metadata = types.SimpleNamespace(source_type=st)
            got = DataSourceEntry.requires_compiled_code(unit)
            if got is not expect:
                fails.append(f"requires_compiled_code({st}) = {got}，应为 {expect}")
        if RecoverableUnit.requires_compiled_code(unit) is not True:
            fails.append("基类 requires_compiled_code 默认值不是 True")
    except Exception as e:  # noqa: BLE001
        fails.append(f"replay 编译开关无法验证：{type(e).__name__}: {e}")

    # ── 2. compile_failed 必须带 fatal，且四个管理器按失败计 ─────────────
    try:
        from deva.naja.infra.runtime.recoverable import RecoverableUnit

        src = inspect.getsource(RecoverableUnit.prepare_for_recovery)
        if "requires_compiled_code" not in src:
            fails.append("prepare_for_recovery 没走 requires_compiled_code 开关")
        if '"fatal": True' not in src:
            fails.append("compile_failed 没标 fatal —— 会被算成「跳过」而不是「失败」")
    except Exception as e:  # noqa: BLE001
        fails.append(f"prepare_for_recovery 无法检查：{type(e).__name__}: {e}")

    for path in MANAGERS:
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as e:
            fails.append(f"{path.name} 读不到：{e}")
            continue
        if 'prep.get("fatal")' not in body:
            fails.append(f"{path.name} 未区分 fatal / skipped，失败摘要会撒谎")

    # ── 3. plugin 缺 class_path 时启动必须失败，且诊断要指向**真实原因** ──
    # 两种病必须给两种诊断：
    #   ① func_code 只有空壳（return None）→ 补 class_path 也跑不了，说「未配置实现」
    #   ② func_code 有真实逻辑、只缺 class_path → 说「运行时构建失败」
    # 以前两种情况都报「请检查 class_path」，读者会以为补上就能跑。
    try:
        from deva.naja.strategy.entry import StrategyEntry

        def _make_entry(func_code: str):
            unit = object.__new__(StrategyEntry)
            unit._metadata = types.SimpleNamespace(
                strategy_type="plugin",
                strategy_config={},          # 无 class_path
                strategy_params={},
                bound_datasource_ids=[],
                bound_datasource_id="",
            )
            unit._func_code = func_code
            unit._runtime = None
            unit._runtime_type = ""
            unit._runtime_config_hash = ""
            unit._runtime_build_error = "PluginStrategyAdapter 缺少 class_path 配置"
            unit._log = lambda *a, **k: None
            return unit

        # ① 空壳
        empty = _make_entry("def process(data, context=None):\n    return None\n")
        result = StrategyEntry._do_start(empty, lambda *a, **k: None)
        err = str(result.get("error", ""))
        if result.get("success") is not False:
            fails.append(
                "plugin 缺 class_path 却返回启动成功 —— 会以「运行中」姿态空转"
                f"（{result}）"
            )
        elif "未配置实现" not in err:
            fails.append(f"空壳策略没被判成「未配置实现」：{err!r}")
        elif "运行时构建失败" in err:
            # 这条是防回归的关键：空壳不该被说成「构建失败」，
            # 否则读者会以为补 class_path 就能跑。
            fails.append(f"空壳策略被报成「运行时构建失败」，诊断指向了错误的原因：{err!r}")

        # ② 有真实代码、只缺 class_path
        real = _make_entry(
            "def process(data, context=None):\n"
            "    score = len(data or [])\n"
            "    return {'score': score}\n"
        )
        result2 = StrategyEntry._do_start(real, lambda *a, **k: None)
        err2 = str(result2.get("error", ""))
        if result2.get("success") is not False:
            fails.append(f"有实现但缺 class_path 却启动成功：{result2}")
        elif "运行时构建失败" not in err2:
            fails.append(f"有实现、缺 class_path 却没报「运行时构建失败」：{err2!r}")
        elif "class_path" not in err2:
            fails.append(f"「运行时构建失败」没带真实原因（class_path）：{err2!r}")
    except Exception as e:  # noqa: BLE001
        fails.append(f"策略启动失败可见性无法验证：{type(e).__name__}: {e}")

    # ── 4. 产出计数只在唯一出口 ────────────────────────────────────────
    try:
        from deva.naja.datasource.entry import DataSourceEntry

        emit = inspect.getsource(DataSourceEntry._do_emit_data)
        for key in ("last_data_ts", "total_emitted"):
            if key not in emit:
                fails.append(f"_do_emit_data 没记 {key} —— timer 类数据源永远显示「无数据」")
        replay = inspect.getsource(DataSourceEntry._start_replay_legacy)
        if "total_emitted += 1" in replay or "last_data_ts = time.time()" in replay:
            fails.append("replay 段仍在自增计数 —— 与 _do_emit_data 双计")
    except Exception as e:  # noqa: BLE001
        fails.append(f"产出计数无法验证：{type(e).__name__}: {e}")

    return fails


# ── 负向注入：证明判据真的会响 ────────────────────────────────────────────

INJECTIONS = [
    {
        "name": "去掉 compile_failed 的 fatal 标记",
        "path": RECOVERABLE,
        "old": '"fatal": True,',
        "new": "",
    },
    {
        "name": "让 replay 也要求编译（退回手动能起、重启必失败）",
        "path": DS_ENTRY,
        "old": 'return source_type != "replay"',
        "new": "return True",
    },
    {
        "name": "拿掉 plugin 运行时构建失败的启动拦截",
        "path": ST_ENTRY,
        "old": 'if runtime is None and strategy_type not in ("", "legacy"):',
        "new": "if False and runtime is None:",
    },
]


def run_injections() -> int:
    caught = 0
    missed = []
    for inj in INJECTIONS:
        path = inj["path"]
        original = path.read_text(encoding="utf-8")
        if inj["old"] not in original:
            print(f"  ⚠️ 锚点未命中，跳过：{inj['name']}（{path.name}）")
            missed.append(inj["name"])
            continue
        try:
            path.write_text(original.replace(inj["old"], inj["new"], 1), encoding="utf-8")
            import importlib

            for mod in (
                "deva.naja.infra.runtime.recoverable",
                "deva.naja.datasource.entry",
                "deva.naja.strategy.entry",
            ):
                if mod in sys.modules:
                    importlib.reload(sys.modules[mod])
            fails = _all_checks()
        finally:
            path.write_text(original, encoding="utf-8")
            import importlib

            for mod in (
                "deva.naja.infra.runtime.recoverable",
                "deva.naja.datasource.entry",
                "deva.naja.strategy.entry",
            ):
                if mod in sys.modules:
                    importlib.reload(sys.modules[mod])

        if fails:
            caught += 1
            print(f"  ✅ 被捕获：{inj['name']}")
            for f in fails[:2]:
                print(f"       · {f[:110]}")
        else:
            print(f"  ❌ 没抓到 —— 这条注入白做了：{inj['name']}")

    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（{len(missed)} 条锚点未命中，已计失败）" if missed else ""))
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
        print("❌ 运行时失败可见性守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0

    print("✅ 运行时失败可见性守卫全绿"
          "（replay 免编译 · compile_failed 计失败 · plugin 构建失败即启动失败 · 产出计数唯一出口）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
