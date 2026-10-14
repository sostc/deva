#!/usr/bin/env python3
"""守卫：认知 → 决策链路的关键环节（静态断言）

背景
----
审计发现「认知层产出影响不了交易」的表象，根因**不在**未启用的 BusBridge，
而在决策管线自身的两处缺陷（且互相掩盖）：

* **参数错位**：``DecisionOrchestrator`` 调 ``FirstPrinciplesMind.think(market_state, snapshot)``，
  而 ``think`` 的第二个形参是 ``narratives: List[str]`` → 真实叙事丢失、
  ``_analyze_narratives`` 遍历 dict 键名注册伪叙事 → ``fp_insights`` 恒空。
* **类型不匹配**：``DecisionFusion.fuse`` 按 dict 访问，生产者返回 dataclass **对象**；
  因上一条导致 ``fp_insights`` 恒空，此缺陷被掩盖，上游一修就崩。

本守卫把这些环节钉死：任何一环被改回错误形态、或被静默移除，立即失败。

检查项
------
1. **叙事 → Manas**（拉取正路）
   - ``TradingCenter._get_current_narratives`` 必须用**单例** ``get_narrative_tracker()``，
     不得 ``NarrativeTracker()`` 新建（新建实例 `_states` 为空 → 叙事恒空）
   - ``market_state["narratives"]`` 必须被写入
   - 内核 ``compute`` 必须把 ``market_state["narratives"]`` 传给 ManasEngine
   - ``ManasEngine.compute`` 必须有 ``narratives`` 形参
2. **FP 洞察 → DecisionFusion**
   - ``orchestrator`` 调 ``think`` 时**不得**把 snapshot 作为第二个位置参数
   - ``orchestrator`` 必须有 ``NAJA_FP_NARRATIVES`` 开关
   - ``fusion.fuse`` 必须调用 ``_normalize_fp_insight`` 做归一化
3. **BusBridge 保持默认关**
   - ``BusBridge.__init__`` 里 ``_bridge_enabled`` 初值必须为 False
   - 容器装配必须走 ``enable_bridge_from_env()``，不得硬编码 ``enable_bridge(True)``

用法
----
    python3 scripts/verify/verify_cognition_decision_chain.py            # 正常
    python3 scripts/verify/verify_cognition_decision_chain.py --strict   # 提示项也算失败
    python3 scripts/verify/verify_cognition_decision_chain.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
NAJA = ROOT / "deva" / "naja"

ORCHESTRATOR = NAJA / "decision" / "orchestrator.py"
FUSION = NAJA / "decision" / "fusion.py"
TRADING_CENTER = NAJA / "attention" / "orchestration" / "trading_center.py"
OS_KERNEL = NAJA / "attention" / "os" / "os_kernel.py"
MANAS_ENGINE = NAJA / "attention" / "kernel" / "manas_engine.py"
BUS_BRIDGE = NAJA / "events" / "bus_bridge.py"
CONTAINER = NAJA / "application" / "container.py"

problems: List[str] = []
hints: List[str] = []


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> Optional[ast.Module]:
    try:
        return ast.parse(_read(path))
    except SyntaxError as e:  # pragma: no cover
        problems.append(f"{path.relative_to(ROOT)}: 语法错误 {e}")
        return None


def _calls_of(tree: ast.AST, func_name: str) -> List[ast.Call]:
    """收集所有 ``xxx.<func_name>(...)`` / ``<func_name>(...)`` 调用。"""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else None)
            if name == func_name:
                out.append(node)
    return out


def _func(tree: ast.AST, name: str) -> Optional[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node  # type: ignore[return-value]
    return None


def _funcs(tree: ast.AST, name: str) -> List[ast.AST]:
    """同名函数可能有多个（如 manas_engine.py 里 TimingEngine / RegimeEngine /
    ManasEngine 各有一个 ``compute``），检查时需**遍历全部**再判定。"""
    return [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]


def _attr_assigns(tree: ast.AST, attr: str) -> List[ast.Assign]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == attr:
                    out.append(node)
    return out


# ─────────────────────────── 检查 1：叙事 → Manas ───────────────────────────

def check_narrative_to_manas() -> None:
    tc = _parse(TRADING_CENTER)
    if tc:
        fn = _func(tc, "_get_current_narratives")
        if fn is None:
            problems.append(
                "叙事→Manas: TradingCenter._get_current_narratives 不存在（叙事读取入口被移除）")
        else:
            src = ast.unparse(fn)
            if "get_narrative_tracker()" not in src:
                problems.append(
                    "叙事→Manas: _get_current_narratives 未使用单例 get_narrative_tracker()"
                    "（新建 NarrativeTracker() 的 _states 为空 → 叙事恒空）")
            if "NarrativeTracker()" in src:
                problems.append(
                    "叙事→Manas: _get_current_narratives 出现 NarrativeTracker() 直接构造（应走单例）")

        # market_state["narratives"] 必须被写入
        wrote = False
        for node in ast.walk(tc):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if (isinstance(t, ast.Subscript)
                            and isinstance(t.slice, ast.Constant)
                            and t.slice.value == "narratives"):
                        wrote = True
        if not wrote:
            problems.append("叙事→Manas: trading_center 未把 narratives 写进 market_state")

    kernel = _parse(OS_KERNEL)
    if kernel:
        hits = [c for c in _calls_of(kernel, "compute")
                if "narratives" in ast.unparse(c)]
        if not hits:
            problems.append(
                "叙事→Manas: os_kernel 的 ManasEngine.compute 未传 narratives（认知输入被截断）")
    else:
        problems.append("叙事→Manas: os_kernel.py 无法解析")

    manas = _parse(MANAS_ENGINE)
    if manas:
        # manas_engine.py 内含多个同名 compute（Timing/Regime/Manas），
        # 只要**存在一个**带 narratives 形参的即可（不能只看第一个）。
        fns = _funcs(manas, "compute")
        if not fns:
            problems.append("叙事→Manas: manas_engine.py 中找不到 compute 方法")
        elif not any("narratives" in [a.arg for a in getattr(fn, "args", None).args]
                     for fn in fns if getattr(fn, "args", None)):
            problems.append("叙事→Manas: ManasEngine.compute 缺少 narratives 形参")
    else:
        problems.append("叙事→Manas: manas_engine.py 无法解析")


# ─────────────────────── 检查 2：FP 洞察 → DecisionFusion ───────────────────────

def check_fp_to_fusion() -> None:
    orch = _parse(ORCHESTRATOR)
    if orch:
        for call in _calls_of(orch, "think"):
            # think(market_state, snapshot) → 2 个位置参数 = 回归
            if len(call.args) >= 2:
                second = ast.unparse(call.args[1])
                problems.append(
                    f"FP→fuse: orchestrator 调 think 时第二个位置参数是 `{second}`"
                    "（think 的第二个形参是 narratives，传 snapshot 会造成参数错位）")
        if "fp_narratives_enabled" not in _read(ORCHESTRATOR):
            problems.append("FP→fuse: orchestrator 缺少 NAJA_FP_NARRATIVES 回滚开关")
    else:
        problems.append("FP→fuse: orchestrator.py 无法解析")

    fus = _parse(FUSION)
    if fus:
        has_norm = _func(fus, "_normalize_fp_insight") is not None
        if not has_norm:
            problems.append(
                "FP→fuse: fusion.py 缺少 _normalize_fp_insight"
                "（生产者返回 dataclass 对象，融合层按 dict 访问 → AttributeError）")
        else:
            fn = _func(fus, "fuse")
            if fn is None or "_normalize_fp_insight" not in ast.unparse(fn):
                problems.append("FP→fuse: fuse() 未调用 _normalize_fp_insight 做归一化")
    else:
        problems.append("FP→fuse: fusion.py 无法解析")


# ─────────────────────────── 检查 3：桥保持默认关 ───────────────────────────

def check_bridge_default_off() -> None:
    tree = _parse(BUS_BRIDGE)
    if tree is None:
        problems.append("BusBridge: bus_bridge.py 无法解析")
        return

    assigns = _attr_assigns(tree, "_bridge_enabled")
    init_val = None
    for node in assigns:
        v = node.value
        if isinstance(v, ast.Constant) and isinstance(v.value, bool):
            init_val = v.value
            break
    if init_val is True:
        problems.append("BusBridge: _bridge_enabled 初值为 True（必须默认关闭）")
    elif init_val is None:
        hints.append("BusBridge: 未找到 _bridge_enabled 的布尔字面量初值（请人工确认默认关）")

    container = _parse(CONTAINER)
    if container:
        for call in _calls_of(container, "enable_bridge"):
            if call.args and isinstance(call.args[0], ast.Constant) and call.args[0].value is True:
                problems.append(
                    "BusBridge: 容器中硬编码 enable_bridge(True)（应由 NAJA_BUS_BRIDGE 环境变量决定）")
        if "enable_bridge_from_env" not in _read(CONTAINER):
            problems.append("BusBridge: 容器未见 enable_bridge_from_env 装配点")


# ─────────────────────────── 提示项：融合层消费者 ───────────────────────────

def report_fusion_consumers() -> str:
    """注意力融合层（AttentionFusion/ConvictionValidator）的产出是否有消费者。

    该链路当前整体空转（见 docs/naja/cognition_to_decision_paths_2026-10-15.md §2.2）。
    本项是**参考信息**，不计入问题、不影响 --strict（它反映的是待产品决策的现状，
    不是被破坏的链路）。
    """
    hits = []
    for py in NAJA.rglob("*.py"):
        s = str(py)
        if "__pycache__" in s or "/tests/" in s:
            continue
        # 排除「定义处」：attention_fusion.py 自身 + models/output.py 的 to_dict
        if py.name in ("attention_fusion.py", "output.py"):
            continue
        try:
            src = py.read_text(encoding="utf-8")
        except Exception:
            continue
        if ".fusion_output" in src:
            hits.append(str(py.relative_to(ROOT)))
    if not hits:
        return ("AttentionKernelOutput.fusion_output 无消费者 —— "
                "注意力融合层产出当前不参与决策（见定案文档 §2.2）")
    return f"fusion_output 被 {len(hits)} 处引用: {hits[:3]}"


# ───────────────────────────────── 自证 ─────────────────────────────────

def _self_test() -> int:
    """对检查器本身做正反例自证（不触碰真实文件）。"""
    import tempfile

    global ROOT, NAJA, ORCHESTRATOR, FUSION, TRADING_CENTER, OS_KERNEL
    global MANAS_ENGINE, BUS_BRIDGE, CONTAINER  # noqa

    tmp = Path(tempfile.mkdtemp())
    (tmp / "deva" / "naja" / "decision").mkdir(parents=True)
    (tmp / "deva" / "naja" / "attention" / "orchestration").mkdir(parents=True)
    (tmp / "deva" / "naja" / "attention" / "os").mkdir(parents=True)
    (tmp / "deva" / "naja" / "attention" / "kernel").mkdir(parents=True)
    (tmp / "deva" / "naja" / "events").mkdir(parents=True)
    (tmp / "deva" / "naja" / "application").mkdir(parents=True)

    (tmp / "deva" / "naja" / "decision" / "orchestrator.py").write_text(
        "import os\n"
        "ENV='NAJA_FP_NARRATIVES'\n"
        "def fp_narratives_enabled():\n    return True\n"
        "class O:\n"
        "    def run(self, market_state, snapshot=None):\n"
        "        fp_mind.think(market_state, snapshot)\n", encoding="utf-8")
    (tmp / "deva" / "naja" / "decision" / "fusion.py").write_text(
        "def _normalize_fp_insight(i):\n    return {}\n"
        "def fuse(fp_insights, kernel_output, current_position=0.0):\n"
        "    fp_insights=[_normalize_fp_insight(x) for x in fp_insights or []]\n"
        "    return None\n", encoding="utf-8")
    (tmp / "deva" / "naja" / "attention" / "orchestration" / "trading_center.py").write_text(
        "class T:\n"
        "    def _get_current_narratives(self):\n"
        "        tracker = get_narrative_tracker()\n"
        "        return []\n"
        "    def build(self, market_state, narratives):\n"
        "        market_state['narratives'] = narratives\n", encoding="utf-8")
    (tmp / "deva" / "naja" / "attention" / "os" / "os_kernel.py").write_text(
        "def f(market_state):\n    self.manas_engine.compute(narratives=market_state.get('narratives'))\n",
        encoding="utf-8")
    (tmp / "deva" / "naja" / "attention" / "kernel" / "manas_engine.py").write_text(
        "class M:\n    def compute(self, narratives=None):\n        pass\n", encoding="utf-8")
    (tmp / "deva" / "naja" / "events" / "bus_bridge.py").write_text(
        "class B:\n    def __init__(self):\n        self._bridge_enabled = False\n", encoding="utf-8")
    (tmp / "deva" / "naja" / "application" / "container.py").write_text(
        "def f():\n    enable_bridge_from_env()\n", encoding="utf-8")

    ROOT, NAJA = tmp, tmp / "deva" / "naja"
    ORCHESTRATOR = NAJA / "decision" / "orchestrator.py"
    FUSION = NAJA / "decision" / "fusion.py"
    TRADING_CENTER = NAJA / "attention" / "orchestration" / "trading_center.py"
    OS_KERNEL = NAJA / "attention" / "os" / "os_kernel.py"
    MANAS_ENGINE = NAJA / "attention" / "kernel" / "manas_engine.py"
    BUS_BRIDGE = NAJA / "events" / "bus_bridge.py"
    CONTAINER = NAJA / "application" / "container.py"

    problems.clear()
    hints.clear()
    check_narrative_to_manas()
    check_fp_to_fusion()
    check_bridge_default_off()

    ok = True
    print("  [自证] 反例夹具（think 传 snapshot）")
    if not any("第二个位置参数" in p for p in problems):
        print("    ❌ 未抓出参数错位"); ok = False
    else:
        print("    ✅ 已抓出")

    # 修好后应通过
    ORCHESTRATOR.write_text(
        "ENV='NAJA_FP_NARRATIVES'\n"
        "def fp_narratives_enabled():\n    return True\n"
        "class O:\n"
        "    def run(self, market_state, snapshot=None):\n"
        "        fp_mind.think(market_state, narratives=market_state.get('narratives'))\n",
        encoding="utf-8")
    problems.clear(); hints.clear()
    check_narrative_to_manas(); check_fp_to_fusion(); check_bridge_default_off()
    print("  [自证] 正例夹具（think 用 narratives= 关键字）")
    if problems:
        print("    ❌ 正例被误报:", problems); ok = False
    else:
        print("    ✅ 通过")

    # 桥初值 True 必须被抓住
    BUS_BRIDGE.write_text(
        "class B:\n    def __init__(self):\n        self._bridge_enabled = True\n",
        encoding="utf-8")
    problems.clear(); hints.clear()
    check_bridge_default_off()
    print("  [自证] 反例夹具（桥初值 True）")
    if not any("初值为 True" in p for p in problems):
        print("    ❌ 未抓出"); ok = False
    else:
        print("    ✅ 已抓出")

    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="提示项也视为失败")
    ap.add_argument("--self-test", action="store_true", help="只跑自证")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    print("=" * 72)
    print("守卫：认知 → 决策链路（叙事→Manas / FP→fuse / 桥默认关）")
    print("=" * 72)

    check_narrative_to_manas()
    check_fp_to_fusion()
    check_bridge_default_off()
    fusion_note = report_fusion_consumers()

    for p in problems:
        print(f"  ❌ {p}")
    for h in hints:
        print(f"  · {h}")

    print(f"\n[参考] {fusion_note}")

    if problems:
        print(f"\n❌ {len(problems)} 项问题 —— 认知到决策的链路被破坏")
        return 1
    if args.strict and hints:
        print(f"\n❌ --strict：{len(hints)} 项提示")
        return 1

    print("\n✅ 链路关键环节完好")
    return 0


if __name__ == "__main__":
    sys.exit(main())
