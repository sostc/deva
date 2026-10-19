#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：注意力 UI 不许用字面量伪造系统状态，退役的面板不许复活。

背景（2026-10-15）
----------------
``attention/ui/components.py`` 里有一整批「Kernel 可视化」面板，它们**全仓零调用方**
（唯一在跑的注意力页面是 ``/awakening`` → ``dashboard.render_attention_monitor_page``，
只用 ``render_awakening_status`` / ``render_decision_plan_panel``；
新闻摘要自 2026-10-19 起搬到独立页面 ``/news``，不走这里）。

其中 ``render_kernel_live_view`` **硬编码**了一份假 ``query_state``::

    query_state = {"strategy_state": {}, "portfolio_state": {},
                   "market_regime": {"type": "trend"},
                   "attention_focus": {"market": 0.8, "news": 0.5},
                   "risk_bias": 0.6}      # ← 且根本没有 macro_liquidity_signal 键

再喂给 ``render_query_state_panel`` —— 于是那个面板永远显示
「TREND + 风险偏好 0.60 + 宏观流动性 0.50 中性」。这些数看着像系统状态，
实则全是字面量，跟真实决策链一点关系没有 —— 正是本仓反复踩的
「**页面显示错 = 系统状态错**」。

同款病在**活链**上也有一处：``awakening._get_query_state()`` 取数整条失败时返回的
兜底字典里，``risk_bias=0.5`` / ``active_value_type="trend"`` / ``value_weights``
全是不带标记的字面量 —— 调用方无法区分「真读到一份中性状态」与「压根没读到」
（线上实测该分支从未触发，但它是活页上的雷）。已给它加上 ``available: False``
标记，并由 :func:`_is_state_unavailable` 统一判定。

本守卫守四条硬性质
------------------
① **退役的面板不许复活**：8 个名字不再以 ``def`` 形式出现在 ``deva/naja/``。
② **不许用字面量伪造展示状态**：``attention/ui/*.py`` 里带状态键（market_regime /
   risk_bias / attention_focus / macro_liquidity_signal …）的**常量**值，必须是
   带 ``available: False`` 标记的诚实兜底，否则就是伪造。
   ❗只盯**字面量**——``{"attention_focus": output.get(...)}`` 这种计算出来的是真的。
③ **兜底必须可区分**：行为用例真跑两个渲染函数，喂兜底字典必须出现「数据不可用」、
   喂真值必须出现真实文案（「上涨趋势」），两边都不许串味。
④ **导出不许悬空**：``ui/__init__.py`` 与 ``components.py`` 的 ``__all__`` 里的名字
   必须在本模块里真的被导入/定义过（删了函数忘了摘导出 → 导入即炸）。

用法
----
    python scripts/verify/verify_attention_ui_no_fabricated_state.py
    python scripts/verify/verify_attention_ui_no_fabricated_state.py --strict
    python scripts/verify/verify_attention_ui_no_fabricated_state.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UI_DIR = ROOT / "deva/naja/attention/ui"
COMPONENTS_PY = UI_DIR / "components.py"
UI_INIT_PY = UI_DIR / "__init__.py"
AWAKENING_PY = UI_DIR / "awakening.py"
DEVA_PKG = ROOT / "deva/naja"

#: 已退役、不许再定义的面板函数（2026-10-15 删除，原因见 components.py 顶部注释）。
RETIRED_RENDERERS = {
    "render_kernel_dashboard",
    "render_query_state_panel",
    "render_multi_head_panel",
    "render_memory_panel",
    "render_feedback_panel",
    "render_kernel_live_view",
    "render_attention_flow_diagram",
    "render_manas_engine_status",
}

#: 出现在这些键上的**字面量**就是伪造的系统状态。
STATE_KEYS = {
    "market_regime",
    "risk_bias",
    "attention_focus",
    "macro_liquidity_signal",
    "query_state",
    "kernel_state",
}

#: 诚实兜底的标记键 / 值。
AVAILABLE_KEY = "available"


def _const_str(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dict_keys_and_consts(node: ast.Dict):
    """返回 (键名集合, 「键名 → 常量值」的列表)。"""
    keys = set()
    const_pairs = []
    for k, v in zip(node.keys, node.values):
        name = _const_str(k)
        if name is None:
            continue
        keys.add(name)
        if isinstance(v, ast.Constant):
            const_pairs.append((name, v.value))
    return keys, const_pairs


def _is_honest_fallback(node: ast.Dict) -> bool:
    """兜底字典必须自我声明（``available: False``）才能带字面量状态。"""
    for k, v in zip(node.keys, node.values):
        if _const_str(k) == AVAILABLE_KEY and isinstance(v, ast.Constant):
            return v.value is False
    return False


def _module_defined_or_imported_names(tree: ast.AST) -> set:
    """模块里所有「顶层可引用」的名字（import 进来的 + 本模块定义的）。"""
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
    return names


def _all_of(path: Path) -> list:
    """取模块 ``__all__`` 里的字符串列表（没有则空）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        return [e.value for e in node.value.elts
                                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


# ── ① 退役的面板不许复活 ────────────────────────────────────────────────────────
def check_retired_renderers_stay_retired() -> list:
    """8 个死面板不许以任何形式复活。

    只扫 ``ast.FunctionDef`` —— ``components.py`` 顶部那段**说明它们为什么被删**的
    注释里也提到了这些名字，不能因此误报（所以不许用字符串 grep）。
    """
    failures: list = []
    for path in sorted(DEVA_PKG.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "__pycache__" in rel:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            failures.append(f"{rel} 语法错误，无法扫描（{e}）")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in RETIRED_RENDERERS:
                failures.append(
                    f"{rel}:{node.lineno} 定义了已退役的 {node.name} —— 它全仓零调用方，"
                    f"且历史上靠硬编码假 query_state 显示；要恢复请先给接上真数据源"
                )
    return failures


# ── ② 不许用字面量伪造展示状态 ──────────────────────────────────────────────────
def check_no_fabricated_display_state() -> list:
    """``attention/ui/*.py`` 里状态键上的**常量**值只能出现在诚实兜底里。

    ❗关键取舍：只盯 ``ast.Constant``。``{"attention_focus": output.get(...)}``
    这种**算出来**的是真状态，不能误伤 —— 一刀切禁掉字典会让守卫变成噪音，
    噪音守卫等于没有守卫。
    """
    failures: list = []
    for path in sorted(UI_DIR.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "__pycache__" in rel:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            failures.append(f"{rel} 语法错误，无法扫描（{e}）")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys, const_pairs = _dict_keys_and_consts(node)
            hit = [(k, v) for k, v in const_pairs if k in STATE_KEYS]
            if not hit:
                continue
            if _is_honest_fallback(node):
                continue  # 自我声明过的兜底，允许
            for k, v in hit[:1]:
                failures.append(
                    f"{rel}:{node.lineno} 状态键 {k!r} 被写成字面量 {v!r} —— "
                    f"这是伪造的系统状态（页面会把它当真值显示）。"
                    f"真兜底必须带 {AVAILABLE_KEY}: False 自我声明"
                )
    return failures


# ── ③ 兜底必须可区分（行为用例） ────────────────────────────────────────────────
def check_fallback_is_distinguishable() -> list:
    """真跑渲染函数：喂兜底字典必须显示「不可用」，喂真值必须显示真文案。

    光看源码里有 ``_is_state_unavailable`` 是假绿 —— 得看渲染**结果**串不串味：
    两边都出现「数据初始化中」就等于没区分。
    """
    failures: list = []
    try:
        mod = importlib.import_module("deva.naja.attention.ui.awakening")
    except Exception as e:  # noqa: BLE001
        return [f"无法导入 awakening 模块（{type(e).__name__}: {e}）"]

    judge = getattr(mod, "_is_state_unavailable", None)
    if judge is None:
        return ["缺 _is_state_unavailable —— 兜底与真值无法区分"]

    fallback = {
        "available": False, "reason": "boom",
        "market_regime": "unknown", "risk_bias": 0.5,
        "attention_focus_count": 0, "top_attention": [],
    }
    real = {"market_regime": "trend_up", "risk_bias": 0.7,
            "top_attention": ["nvda"], "attention_focus_count": 1}
    if judge(fallback) is not True:
        failures.append("_is_state_unavailable(兜底字典) 应为 True —— 兜底没被认出来")
    if judge(real) is not False:
        failures.append("_is_state_unavailable(真状态) 应为 False —— 真值被误判成兜底")

    manas = {"awakening_level": "dormant", "should_act": False,
             "action_type": "hold", "harmony_state": "neutral"}

    for fn_name in ("_render_current_state_narrative", "_render_system_overview"):
        fn = getattr(mod, fn_name, None)
        if fn is None:
            failures.append(f"缺 {fn_name}")
            continue
        try:
            out_bad = fn(manas, fallback)
            out_ok = fn(manas, real)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{fn_name} 抛异常：{type(e).__name__}: {e}")
            continue
        if "数据不可用" not in out_bad:
            failures.append(f"{fn_name} 喂兜底字典时没显示「数据不可用」—— 字面量被当真值渲染")
        if "数据不可用" in out_ok:
            failures.append(f"{fn_name} 喂真值时却显示「数据不可用」—— 真值被误判")
        if fn_name == "_render_current_state_narrative" and "上涨趋势" not in out_ok:
            failures.append(f"{fn_name} 喂真值时没显示真实文案（上涨趋势）—— 渲染逻辑坏了")
    return failures


# ── ④ 导出不许悬空 ──────────────────────────────────────────────────────────────
def check_exports_resolve() -> list:
    """``__all__`` 里的名字必须在本模块里真的被导入/定义过。

    删掉一批函数却忘了摘 ``__all__`` → 任何人 ``from ... import *`` 或
    ``from ... import 那个名字`` 都会 ImportError，而且是**启动期**才炸。
    """
    failures: list = []
    for path in (UI_INIT_PY, COMPONENTS_PY):
        rel = path.relative_to(ROOT).as_posix()
        names = _all_of(path)
        if not names:
            continue
        available = _module_defined_or_imported_names(ast.parse(path.read_text(encoding="utf-8")))
        for n in names:
            if n not in available:
                failures.append(f"{rel} 的 __all__ 里 {n!r} 在本模块没有对应定义/导入（悬空导出）")
    return failures


# ── 负向注入 ─────────────────────────────────────────────────────────────────────
INJECTIONS = [
    {
        "name": "死面板复活（render_kernel_live_view + 硬编码假 query_state）",
        "file": COMPONENTS_PY,
        "old": "# 行动档位 → （中文名, 颜色）。权威档位来自 manas（见 decision/plan.py）。\n",
        "new": "# 行动档位 → （中文名, 颜色）。权威档位来自 manas（见 decision/plan.py）。\n"
               "\n"
               "\n"
               "def render_kernel_live_view(kernel) -> str:\n"
               "    query_state = {\"market_regime\": {\"type\": \"trend\"}, \"risk_bias\": 0.6}\n"
               "    return str(query_state)\n",
    },
    {
        "name": "兜底字典摘掉 available: False（又变回无法区分的「合法的空」）",
        "file": AWAKENING_PY,
        "old": "            \"available\": False,\n            \"reason\": str(e),\n",
        "new": "",
    },
    {
        "name": "渲染时不判兜底（字面量照旧当真值显示）",
        "file": AWAKENING_PY,
        "old": "    unavailable = _is_state_unavailable(query_state)\n\n    awakening_text = {",
        "new": "    unavailable = False\n\n    awakening_text = {",
    },
    {
        "name": "__all__ 里留一个悬空导出（删了函数忘了摘）",
        "file": UI_INIT_PY,
        "old": "    \"render_decision_plan_panel\",\n",
        "new": "    \"render_decision_plan_panel\",\n    \"render_kernel_dashboard\",\n",
    },
]


def _all_checks() -> list:
    return (
        check_retired_renderers_stay_retired()
        + check_no_fabricated_display_state()
        + check_fallback_is_distinguishable()
        + check_exports_resolve()
    )


def _reload():
    """注入了哪个模块就要重载哪个（漏一个 → 注入不生效 → 假绿）。"""
    for name in ("deva.naja.attention.ui.awakening", "deva.naja.attention.ui.components"):
        try:
            importlib.reload(importlib.import_module(name))
        except Exception:  # noqa: BLE001
            pass


def run_injections() -> int:
    """逐个注入 bug，确认守卫抓得到。锚点未命中一律判失败（防守卫腐烂）。"""
    caught = 0
    missed = []
    for inj in INJECTIONS:
        path: Path = inj["file"]
        original = path.read_text(encoding="utf-8")
        if inj["old"] not in original:
            missed.append(inj["name"])
            print(f"❌ 注入锚点未命中（守卫腐烂信号，锚点该修了）：{inj['name']}")
            continue
        count = inj.get("count", 1)
        if original.count(inj["old"]) != count:
            missed.append(inj["name"])
            print(f"❌ 锚点出现 {original.count(inj['old'])} 次（期望 {count}）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            _reload()
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")
            _reload()
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            print(f"       · {found[0][:110]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")
        if path.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            path.write_text(original, encoding="utf-8")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（另有 {len(missed)} 条锚点未命中，已计失败）" if missed else ""))
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
        print("❌ 注意力 UI 反伪造守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ 注意力 UI 反伪造守卫全绿（退役面板未复活 / 无字面量伪造状态 / 兜底可区分 / 导出不悬空）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
