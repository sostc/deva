#!/usr/bin/env python3
"""守卫：认知 ↔ 交易链路（事件导出 / 桥梁通道 / Manas 输入）

背景（为什么要有这个守卫）
------------------------------------------------------------------
2026-10-15 对「认知层产出到不了交易侧」的深挖（见
`docs/naja/p0_linkage_design_2026-10-15.md`）挖出四类**全部静默**的故障。
它们的共同点是：**不抛异常、不打错误日志、UI 也正常**，只能靠静态比对发现。

  A. ❗**一个缺失名砖掉半个事件家族**（最隐蔽）
     `events/__init__.py` 用一条 `from .cognition_events import (...)` 导入认知
     dataclass 事件。清单里曾混进三个**并不存在**的名字（`GlobalMarketEvent` /
     `create_risk_alert` / `EVENT_TYPE_MAP`）。该语句编译成**逐名**
     IMPORT_FROM/STORE_NAME —— 在第一个缺失名处抛 ImportError，于是
       · 缺失名**之前**的名字侥幸已绑定；
       · 缺失名**之后**的名字（`PortfolioSignalEvent` / `CognitionResetEvent` /
         `create_narrative_update` …）**全部没有绑定**；
       · `COGNITION_EVENTS_AVAILABLE = False`。
     而消费方一律 `except ImportError: pass` → 完全无声。
     这是本文件 ① 段看住的东西。

  B. ❗**引用了不存在的模块**
     `cross_signal_analyzer.py` 有 5 处 `from .narrative_block_mapping import ...`，
     但 `cognition/analysis/` 下**没有**这个模块（实现在
     `cognition/narrative/block_mapping.py`）。全部在函数体内 → 首次调用即
     ImportError → 被 `except ImportError: pass` 吞掉 → 舆情→题材联动 / 市场共振 /
     指数中文名三条子链路从未执行过一次。→ ② 段。

  C. ❗**订阅了错误的通道**
     `NajaEventBus` 有两条互不可见的通道：认知信号通道（`subscribe_cognitive`，
     按 `CognitiveEventType` 枚举路由）与 dataclass 通道（`subscribe('类名', cb)`，
     按 `type(event).__name__` 路由）。认知层实际产出全是 dataclass，
     桥若订阅前者 → **一个事件都收不到**。→ ③ 段。

  D. ❗**假接（编造输入冒充真实数据）**
     `AdaptiveCycle._get_manas_risk_context` 曾把 `portfolio` 传成**一个
     `{"position_pct": 0.0, ...}` 字面量 dict**，而 `RiskEngine` 期望
     `VirtualPortfolio` 并调 `portfolio.get_summary()` → AttributeError 被吞 →
     `cash_ratio≡0.5, drawdown≡0`；`scanner=None` → `volatility≡1.0`
     → `risk_temperature ≡ 1.25`（永远进不了 >1.3 / >1.5 档）
     → 自适应止盈止损**从未生效**（恒 -8%/+15%）。→ ⑤ 段。

  E. ❗**把叙事名当成股票代码**
     判定「token 是不是可交易代码」时用「纯字母大写」，而
     `'不存在的叙事XYZ'.isupper()` 为 **True**（CJK 不参与大小写判定）
     → 凭空造出一个标的送进决策中心。→ ⑥ 段（带硬编码期望值的**行为**断言）。

⚠️ 本守卫**只读源码**，不 import 项目（避免触发装配 / 网络 / DB / 写盘）。
⚠️ 判定基准（期望值）一律**硬编码在本文件**，不许从被测模块读回来 ——
   否则模块本身跑偏时守卫会跟着走，变成假绿。

六段检查
------------------------------------------------------------------
  ① 事件导出对齐：`events/__init__.py` 的 cognition_events 导入名单逐个必须存在；
     `__all__.extend(...)` 里的名字同样必须存在。
  ② 失效模块引用：全库不得 import `narrative_block_mapping`（模块不存在）。
  ③ 桥梁订阅通道：`bus_bridge.py` 不得用 `subscribe_cognitive`；必须用 dataclass
     通道；规则表的 key 必须对应真实存在的 dataclass 事件类。
  ④ 桥梁默认关且接线在：容器必须调用 `enable_bridge_from_env`；开关名必须是
     约定的 `NAJA_BUS_BRIDGE`；未设该 env 时不得启用。
  ⑤ Manas 输入必须真实：`adaptive_cycle._get_manas_risk_context` 不得出现
     「字面量 dict 当 portfolio」；必须经 `get_manas_inputs()` 取输入；必须有回滚开关。
  ⑥ `_looks_like_code` 行为基准：`AI` / `不存在的叙事XYZ` / `AI芯片` 必须为 False；
     `sh600487` / `600487` / `AAPL.US` / `00700.HK` 必须为 True。

用法
------------------------------------------------------------------
    python3 scripts/verify/verify_cognitive_trading_linkage.py
    python3 scripts/verify/verify_cognitive_trading_linkage.py --strict
    python3 scripts/verify/verify_cognitive_trading_linkage.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

EVENTS_INIT = REPO_ROOT / "deva/naja/events/__init__.py"
COGNITION_EVENTS = REPO_ROOT / "deva/naja/events/cognition_events.py"
COGNITIVE_EVENTS = REPO_ROOT / "deva/naja/events/cognitive_events.py"
BUS_BRIDGE = REPO_ROOT / "deva/naja/events/bus_bridge.py"
CONTAINER = REPO_ROOT / "deva/naja/application/container.py"
ADAPTIVE_CYCLE = REPO_ROOT / "deva/naja/bandit/adaptive_cycle.py"
SCAN_ROOT = REPO_ROOT / "deva"

# ── 硬编码基准（❗不许从被测模块读回来）────────────────────────────────
EXPECTED_BRIDGE_SWITCH = "NAJA_BUS_BRIDGE"
EXPECTED_ADAPTIVE_SL_SWITCH = "NAJA_MANAS_ADAPTIVE_SL"
EXPECTED_ENV_DEFAULT_ENABLED = False      # 未设 env 时，桥必须默认关

# 事件家族里**必须**能从 deva.naja.events 取到的名字（缺失名之后的那些最容易掉）
REQUIRED_COGNITION_EXPORTS: Tuple[str, ...] = (
    "NarrativeUpdateEvent",
    "TimingNarrativeShiftEvent",
    "BlockNarrativeUpdateEvent",
    "ResonanceDetectedEvent",
    "SupplyChainRiskEvent",
    "PortfolioSignalEvent",
    "RiskAlertEvent",
    "CognitionResetEvent",
    "create_narrative_update",
    "create_timing_shift",
    "create_resonance_detected",
)

# 桥规则表必须覆盖的事件（这些是认知层真实会发 / 已具备发射端的）
REQUIRED_BRIDGE_RULES: Tuple[str, ...] = (
    "NarrativeStateEvent",
    "ResonanceDetectedEvent",
)

# ⑥ 段行为基准：(token, 期望判定)
CODE_CLASSIFICATION_CASES: Tuple[Tuple[str, bool], ...] = (
    ("AI", False),                 # 叙事名，曾被误判为代码
    ("不存在的叙事XYZ", False),      # CJK + 大写字母，曾被误判为代码
    ("AI芯片", False),              # 中文题材名
    ("semiconductor", False),      # 英文题材名
    ("sh600487", True),
    ("sz000636", True),
    ("bj920056", True),
    ("600487", True),
    ("AAPL.US", True),
    ("00700.HK", True),            # 港股 5 位，旧规则漏认
)

# ② 段：已确认不存在、却被 import 的模块名（模块名 → 正确去处）
DEAD_MODULE_IMPORTS: Dict[str, str] = {
    "narrative_block_mapping": (
        "cognition/analysis/ 下没有该模块；唯一权威实现在 "
        "cognition/narrative/block_mapping.py。"
    ),
}


# ============================================================
#  工具
# ============================================================

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_comments_and_docstrings(src: str) -> str:
    """去注释 + 剥模块/类/函数 docstring。

    ❗静态守卫必须先做这一步：本仓的注释里大量出现「反面示例」
    （例如 `portfolio_state` / `narrative_block_mapping`），
    若直接扫原文，会拿注释当代码、并与自己的说明打架。
    """
    out = io.StringIO()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            out.write(tok.string)
            out.write("\n" if tok.type in (tokenize.NEWLINE, tokenize.NL) else " ")
    except tokenize.TokenError:
        out.write(src)

    code = out.getvalue()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return code

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc = body[0].value.value
                if doc:
                    code = code.replace(doc, " ")
    return code


def module_top_level_names(path: Path) -> Set[str]:
    """模块顶层「定义出来」的名字（class / def / 赋值 / import 名）

    ❗会下钻 `try` / `if` / `with` 等**模块级块**：本项目大量定义写在
    `try: ... except ImportError:` 里（如 `events/__init__.py` 的
    `EVENT_TYPE_MAP = EVENT_TYPE_MAPPING`），只扫 `tree.body` 会漏掉它们，
    把「有定义」误判成「悬空名」。
    """
    tree = ast.parse(_read(path))
    names: Set[str] = set()

    def _visit(node: ast.AST) -> None:
        # ❗只收**模块作用域**：遇到类/函数就记名但**不下钻**其函数体，
        # 免得把函数内部的局部变量也算成模块级名字。
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(child.name)
                continue
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                names.add(child.target.id)
            elif isinstance(child, ast.Import):
                for a in child.names:
                    names.add(a.asname or a.name.split(".")[0])
            elif isinstance(child, ast.ImportFrom):
                for a in child.names:
                    if a.name != "*":
                        names.add(a.asname or a.name)
            _visit(child)

    _visit(tree)
    return names


def find_import_from_names(path: Path, module_suffix: str) -> Optional[List[str]]:
    """找到第一条 `from <xxx.module_suffix> import (...)` 的名字清单"""
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(module_suffix):
            return [a.name for a in node.names if a.name != "*"]
    return None


def find_all_extend_names(path: Path) -> List[str]:
    """收集 `__all__.extend([...])` 里的所有字符串字面量"""
    tree = ast.parse(_read(path))
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "extend" and node.args:
            arg = node.args[0]
            if isinstance(arg, (ast.List, ast.Tuple)):
                for el in arg.elts:
                    if isinstance(el, ast.Constant) and isinstance(el.value, str):
                        names.append(el.value)
    return names


def find_class_method(path: Path, class_name: str, method_name: str):
    tree = ast.parse(_read(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == method_name:
                    return sub
    return None


def find_dict_literal_keys(path: Path, assign_name: str) -> List[str]:
    """找到 `self.<assign_name> = {...}` / `self.<assign_name>: T = {...}` 的顶层 key 清单

    ❗必须同时处理 `AnnAssign`：本项目给字典加了类型标注
    （`self._cognitive_to_trading_rules: Dict[str, Tuple[float, Any]] = {...}`），
    只认 `ast.Assign` 会漏掉整张表。
    """
    tree = ast.parse(_read(path))
    keys: List[str] = []
    for node in ast.walk(tree):
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if target is None or value is None:
            continue
        if isinstance(target, ast.Attribute) and target.attr == assign_name and isinstance(value, ast.Dict):
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.append(k.value)
    return keys


def compile_standalone_function(path: Path, class_name: str, method_name: str):
    """把类里的某个 @staticmethod 抽出来编成独立函数（不 import 项目）"""
    fn = find_class_method(path, class_name, method_name)
    if fn is None:
        return None
    fn.decorator_list = [d for d in fn.decorator_list
                         if not (isinstance(d, ast.Name) and d.id == "staticmethod")]
    src = ast.unparse(fn)
    ns: Dict[str, object] = {"re": re}
    try:
        exec(compile(src, f"<{path.name}:{method_name}>", "exec"), ns)  # noqa: S102
    except Exception:
        return None
    return ns.get(method_name)


# ============================================================
#  ① 事件导出对齐
# ============================================================

def check_event_exports() -> List[str]:
    problems: List[str] = []
    print("① 事件导出对齐（events/__init__.py ↔ cognition_events.py）")

    declared = module_top_level_names(COGNITION_EVENTS)
    imported = find_import_from_names(EVENTS_INIT, "cognition_events")

    if imported is None:
        print("  ⏭️  未找到 `from .cognition_events import (...)`，跳过")
        return problems

    missing = [n for n in imported if n not in declared]
    if missing:
        problems.append(f"events/__init__.py 导入了 cognition_events 里不存在的名字: {missing}")
        print(f"  ❌ 导入了不存在的名字 {missing}")
        print("     危害：`from X import (a,b,c)` 在第一个缺失名处抛 ImportError，")
        print("           缺失名**之后**的所有名字都不会绑定 → 半个事件家族静默不可用。")
    else:
        print(f"  ✅ 导入名单 {len(imported)} 个名字全部存在")

    # 条件导出块里的名字同样不能悬空
    extended = find_all_extend_names(EVENTS_INIT)
    dangling_ext = sorted({n for n in extended if n not in declared and n not in module_top_level_names(EVENTS_INIT)})
    if dangling_ext:
        problems.append(f"__all__.extend 中的名字在仓库里找不到定义: {dangling_ext}")
        print(f"  ❌ __all__.extend 悬空名 {dangling_ext}")
    else:
        print(f"  ✅ __all__.extend 中 {len(extended)} 个名字均可解析")

    # 关键名字必须真在导入名单里（防「只写在 __all__ 里」）
    absent = [n for n in REQUIRED_COGNITION_EXPORTS if n not in imported]
    if absent:
        problems.append(f"关键认知事件未出现在导入名单: {absent}")
        print(f"  ❌ 关键名字未导入 {absent}")
    else:
        print(f"  ✅ {len(REQUIRED_COGNITION_EXPORTS)} 个关键名字均在导入名单里")

    return problems


# ============================================================
#  ② 失效模块引用
# ============================================================

def check_dead_module_imports() -> List[str]:
    problems: List[str] = []
    print("\n② 失效模块引用（import 了不存在的模块）")

    hits: List[Tuple[str, int, str]] = []
    for path in SCAN_ROOT.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        try:
            tree = ast.parse(_read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "")
                tail = mod.split(".")[-1]
                if tail in DEAD_MODULE_IMPORTS:
                    hits.append((str(path.relative_to(REPO_ROOT)), node.lineno, mod))

    if hits:
        for f, ln, mod in hits:
            problems.append(f"{f}:{ln} import 了不存在的模块 {mod}")
            print(f"  ❌ {f}:{ln}  from {mod} import ...")
            print(f"     → {DEAD_MODULE_IMPORTS[mod.split('.')[-1]]}")
    else:
        print(f"  ✅ 全库无对 {list(DEAD_MODULE_IMPORTS)} 的引用")
    return problems


# ============================================================
#  ③ 桥梁订阅通道
# ============================================================

def check_bridge_channel() -> List[str]:
    problems: List[str] = []
    print("\n③ 桥梁订阅通道（必须走 dataclass 通道）")

    src = _read(BUS_BRIDGE)
    tree = ast.parse(src)

    # 3.1 不得再用 subscribe_cognitive
    if "subscribe_cognitive" in strip_comments_and_docstrings(src):
        problems.append("bus_bridge.py 仍在用 subscribe_cognitive（认知信号通道）")
        print("  ❌ 仍调用 subscribe_cognitive —— 认知层实际发的是 dataclass，收不到")
    else:
        print("  ✅ 未使用 subscribe_cognitive")

    # 3.2 必须按 dataclass 类名订阅
    uses_dc_subscribe = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "subscribe" and n.args
        and isinstance(n.args[0], ast.Name)
        for n in ast.walk(tree)
    )
    if uses_dc_subscribe:
        print("  ✅ 使用 dataclass 通道 subscribe(事件类名, cb)")
    else:
        problems.append("bus_bridge.py 未发现按 dataclass 类名订阅的调用")
        print("  ❌ 未发现 dataclass 通道订阅调用")

    # 3.3 规则表 key 必须是真实存在的 dataclass 事件类
    known_events = module_top_level_names(COGNITION_EVENTS) | module_top_level_names(COGNITIVE_EVENTS)
    rules = find_dict_literal_keys(BUS_BRIDGE, "_cognitive_to_trading_rules")
    if not rules:
        problems.append("未能解析 bus_bridge._cognitive_to_trading_rules 的 key")
        print("  ❌ 未解析到规则表")
    else:
        bad = [k for k in rules if k not in known_events]
        if bad:
            problems.append(f"规则表 key 不是真实事件类: {bad}")
            print(f"  ❌ 规则表含不存在的事件类 {bad}")
        else:
            print(f"  ✅ 规则表 {len(rules)} 条 key 均对应真实事件类: {rules}")

        absent = [n for n in REQUIRED_BRIDGE_RULES if n not in rules]
        if absent:
            problems.append(f"规则表缺少必备事件: {absent}")
            print(f"  ❌ 规则表缺少 {absent}")
        else:
            print(f"  ✅ 必备事件均在规则表内")

    # 3.4 转换函数里不得再读不存在的字段名
    code = strip_comments_and_docstrings(src)
    for bad_field in ("stock_codes", "narrative_type=", "risk_level"):
        # 允许出现在 metadata 透传里，但不得作为 getattr(event, ...) 的字段读取
        if re.search(r"getattr\(\s*event\s*,\s*['\"]" + re.escape(bad_field.rstrip("=")) + r"['\"]", code):
            problems.append(f"bus_bridge.py 读取了事件不存在的字段 {bad_field}")
            print(f"  ❌ 仍在 getattr(event, '{bad_field.rstrip('=')}') —— 该字段不在真实事件上")
        else:
            print(f"  ✅ 未把 '{bad_field.rstrip('=')}' 当作真实事件字段读取")

    return problems


# ============================================================
#  ④ 桥梁默认关 + 接线在
# ============================================================

def check_bridge_switch() -> List[str]:
    problems: List[str] = []
    print("\n④ 桥梁开关（默认关 + 装配点存在）")

    src = _read(BUS_BRIDGE)
    code = strip_comments_and_docstrings(src)

    if f'ENV_BRIDGE_SWITCH = "{EXPECTED_BRIDGE_SWITCH}"' in code:
        print(f"  ✅ 开关名 = {EXPECTED_BRIDGE_SWITCH}")
    else:
        problems.append(f"bus_bridge.py 的开关名不是 {EXPECTED_BRIDGE_SWITCH}")
        print(f"  ❌ 开关名与约定不符（期望 {EXPECTED_BRIDGE_SWITCH}）")

    # 默认值必须为空（未设 = 关）。硬编码期望：不设 env 时 bridge_enabled_by_env() 为 False
    fn = find_class_method(BUS_BRIDGE, "BusBridge", "__init__")
    default_off = False
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Attribute) and t.attr == "_bridge_enabled" for t in node.targets
        ):
            if isinstance(node.value, ast.Constant) and node.value.value is False:
                default_off = True
    if EXPECTED_ENV_DEFAULT_ENABLED is False and default_off:
        print("  ✅ 构造时 _bridge_enabled = False（默认关）")
    else:
        problems.append("bus_bridge.py 构造时未默认关闭")
        print("  ❌ 构造时未默认关闭")

    # 装配点：容器必须调用 enable_bridge_from_env
    if "enable_bridge_from_env" in strip_comments_and_docstrings(_read(CONTAINER)):
        print("  ✅ 容器装配期调用 enable_bridge_from_env()")
    else:
        problems.append("容器未调用 enable_bridge_from_env —— 桥又变成「没有装配点」")
        print("  ❌ 容器未见 enable_bridge_from_env 调用")

    return problems


# ============================================================
#  ⑤ Manas 输入必须真实
# ============================================================

def check_manas_wiring() -> List[str]:
    problems: List[str] = []
    print("\n⑤ Manas 输入必须真实（不得假接）")

    fn = find_class_method(ADAPTIVE_CYCLE, "AdaptiveCycle", "_get_manas_risk_context")
    if fn is None:
        problems.append("找不到 AdaptiveCycle._get_manas_risk_context")
        print("  ❌ 找不到目标方法")
        return problems

    fn.decorator_list = []
    body = ast.unparse(fn)          # 用 AST 重生成，天然不含注释；docstring 仍是字面量

    # 5.1 不得把字面量 dict 当 portfolio
    dict_as_portfolio = False
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "portfolio" and isinstance(kw.value, ast.Dict):
                    dict_as_portfolio = True
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    dict_as_portfolio = True
    if dict_as_portfolio:
        problems.append("_get_manas_risk_context 仍把字面量 dict 当 portfolio 传入")
        print("  ❌ 仍传字面量 dict 作为 portfolio（RiskEngine 期望 VirtualPortfolio）")
    else:
        print("  ✅ 未把字面量 dict 当 portfolio")

    # 5.2 不得在计算入参处硬编码假持仓键
    fake_keys = [k for k in ("position_pct", "total_value", "cash") if re.search(r"['\"]" + k + r"['\"]\s*:", body)]
    if fake_keys:
        problems.append(f"_get_manas_risk_context 仍有硬编码假持仓键: {fake_keys}")
        print(f"  ❌ 仍有硬编码假持仓键 {fake_keys}")
    else:
        print("  ✅ 无硬编码假持仓键")

    # 5.3 必须经内核单出口取输入
    if "get_manas_inputs" in body:
        print("  ✅ 经内核单出口 get_manas_inputs() 取输入")
    else:
        problems.append("_get_manas_risk_context 未使用 get_manas_inputs() 单出口")
        print("  ❌ 未使用 get_manas_inputs() 单出口")

    # 5.4 回滚开关必须在
    ac_code = strip_comments_and_docstrings(_read(ADAPTIVE_CYCLE))
    if f'ENV_MANAS_ADAPTIVE_SL = "{EXPECTED_ADAPTIVE_SL_SWITCH}"' in ac_code:
        print(f"  ✅ 回滚开关 = {EXPECTED_ADAPTIVE_SL_SWITCH}")
    else:
        problems.append(f"缺少回滚开关 {EXPECTED_ADAPTIVE_SL_SWITCH}")
        print(f"  ❌ 缺少回滚开关 {EXPECTED_ADAPTIVE_SL_SWITCH}")

    return problems


# ============================================================
#  ⑥ 代码判定基准（行为断言）
# ============================================================

def classify_all(fn) -> List[Tuple[str, bool, bool]]:
    rows: List[Tuple[str, bool, bool]] = []
    for token, expected in CODE_CLASSIFICATION_CASES:
        try:
            actual = bool(fn(token))
        except Exception:
            actual = False
        rows.append((token, expected, actual))
    return rows


def check_symbol_classifier(fn=None) -> List[str]:
    problems: List[str] = []
    print("\n⑥ 叙事名 vs 股票代码的判定基准（行为断言）")

    if fn is None:
        fn = compile_standalone_function(BUS_BRIDGE, "BusBridge", "_looks_like_code")
    if fn is None:
        problems.append("无法抽取 BusBridge._looks_like_code 执行")
        print("  ❌ 无法抽取 _looks_like_code（函数被删或签名变了？）")
        return problems

    rows = classify_all(fn)
    bad = [(t, e, a) for t, e, a in rows if e != a]
    for token, expected, actual in rows:
        mark = "✅" if expected == actual else "❌"
        print(f"  {mark} _looks_like_code({token!r}) = {actual}   (期望 {expected})")
    if bad:
        problems.append(f"代码判定基准不符: {[(t, e, a) for t, e, a in bad]}")
        print("  ❗把叙事名当代码 = 凭空造出标的送进决策中心；把代码当叙事名 = 信号解析不出来")
    return problems


# ============================================================
#  自证
# ============================================================

def _self_test() -> int:
    print("=" * 72)
    print("自证：注入「缺陷版」输入，验证检查器有区分度")
    print("=" * 72)

    checks: List[Tuple[str, bool]] = []

    # ① 注入一个缺失名
    declared = module_top_level_names(COGNITION_EVENTS)
    checks.append(("① 能识别「导入了不存在的名字」",
                   "GlobalMarketEvent" not in declared))
    checks.append(("① 能识别真实名字（不误报）",
                   "NarrativeUpdateEvent" in declared))

    # ③ 断言解析器能拿到规则表
    rules = find_dict_literal_keys(BUS_BRIDGE, "_cognitive_to_trading_rules")
    checks.append(("③ 能解析出桥梁规则表 key", len(rules) > 0))
    known = module_top_level_names(COGNITION_EVENTS) | module_top_level_names(COGNITIVE_EVENTS)
    checks.append(("③ 规则表 key 均对应真实事件类", all(k in known for k in rules)))

    # ⑤ 方法抽取
    fn = find_class_method(ADAPTIVE_CYCLE, "AdaptiveCycle", "_get_manas_risk_context")
    checks.append(("⑤ 能定位 _get_manas_risk_context", fn is not None))

    # ⑥ 注入一个「缺陷版」判定函数：旧写法（纯字母大写当代码）
    def buggy(token: str) -> bool:
        """注入的缺陷版：把纯字母大写当成代码（AI / 不存在的叙事XYZ 会被误判）"""
        t = (token or "").strip()
        if not t:
            return False
        if len(t) == 8 and t[:2].lower() in ("sh", "sz", "bj") and t[2:].isdigit():
            return True
        if len(t) == 6 and t.isdigit():
            return True
        head = t.split(".")[0]
        return head.isalpha() and head.isupper()

    buggy_rows = classify_all(buggy)
    buggy_bad = [r for r in buggy_rows if r[1] != r[2]]
    checks.append(("⑥ 缺陷版判定函数**会被本用例抓出**", len(buggy_bad) > 0))

    real_fn = compile_standalone_function(BUS_BRIDGE, "BusBridge", "_looks_like_code")
    if real_fn is not None:
        real_rows = classify_all(real_fn)
        checks.append(("⑥ 现行判定函数全部通过基准", all(r[1] == r[2] for r in real_rows)))
    else:
        checks.append(("⑥ 现行判定函数全部通过基准", False))

    print()
    ok = True
    for name, passed in checks:
        print(f"  {'✅' if passed else '❌'} {name}")
        ok = ok and passed
    print()
    print("✅ 自证通过：检查器既有区分度，也不误报" if ok else "❌ 自证失败")
    return 0 if ok else 1


# ============================================================
#  主流程
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="认知↔交易链路守卫")
    ap.add_argument("--strict", action="store_true", help="有任何问题即失败（默认同样失败，保留语义）")
    ap.add_argument("--self-test", action="store_true", help="只跑自证")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    print("=" * 72)
    print("守卫：认知 ↔ 交易链路（事件导出 / 桥梁通道 / Manas 输入）")
    print("=" * 72)

    problems: List[str] = []
    for check in (
        check_event_exports,
        check_dead_module_imports,
        check_bridge_channel,
        check_bridge_switch,
        check_manas_wiring,
        check_symbol_classifier,
    ):
        problems.extend(check())

    print("\n" + "=" * 72)
    if problems:
        print(f"❌ 发现 {len(problems)} 处问题：")
        for p in problems:
            print(f"   · {p}")
        print("=" * 72)
        return 1

    print("✅ 通过：认知↔交易链路的结构约束全部满足")
    print("   （注意：通过 ≠ 桥已启用。启用与否由 NAJA_BUS_BRIDGE 决定，"
          "方向口径属策略决策。）")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
