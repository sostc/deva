"""守卫：manas → 决策 → 执行 这条链路上三处「接了但没通」的缺陷。

背景（2026-10-14 实测，勿删）
----------------------------
决策留痕 ``naja_decision_journal`` 里 **50/50 全是 hold**、``size_hint`` 全 0，
即「链路看着完整，但一次都没放行过」。逐段取证后定位到三处独立缺陷：

1. **manas 战绩查询用了不存在的策略名** ``get_strategy_summary("default")``。
   真实 strategy_id 是运行期生成的（``88b104eca26c`` / ``Momentum Surge Tracker``），
   **没有任何策略叫 default** → ``total_trades`` 恒 0 → 置信度恒 0.3。
   实测战绩库 277 条记录，聚合全部是 **100 笔**，按 ``"default"`` 查是 **0 笔**。
2. **否决日志给假理由**。``else`` 分支恒打印 ``confidence=X < 阈值``，而真实原因
   可能是 ``should_act=False``（manas 闸门没放行）。日志里出现过
   ``confidence=0.500 < 0.4`` 这种**不可能成立**的表述。
3. **无点前缀代码判不出市场**。真实信号是 ``sh600487`` / ``sz000636``，
   老实现只认带点的 → A 股信号 **100% 被跳过**。

⚠️ 本守卫**不校验 manas 是否放行**（那是判断层的职权）。
修完上面三处后 manas 仍可能给 hold —— 那多半是**正确的保守行为**
（收盘时段 timing 低 / 风险温度高 / 战绩差），不是缺陷。
**禁止为了让系统下单而擅自降低行动门槛。**

用法：``--strict``（默认）｜``--self-test``｜``--exercise-injections``
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BANDIT = ROOT / "deva" / "naja" / "bandit"
KERNEL = ROOT / "deva" / "naja" / "attention" / "kernel"
ORCH = ROOT / "deva" / "naja" / "attention" / "orchestration"

EXEC_PY = BANDIT / "execution.py"
MANAS_PY = KERNEL / "manas_engine.py"
TC_PY = ORCH / "trading_center.py"


# ---------------------------------------------------------------- 工具

def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub_package(name: str, path=None) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    if path:
        mod.__path__ = [str(path)]
    sys.modules[name] = mod
    parent, _, child = name.rpartition(".")
    if parent:
        setattr(_stub_package(parent), child, mod)
    return mod


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_noise(src: str) -> str:
    """去掉注释与 docstring，只看代码。"""
    import ast

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    out: List[str] = []
    lines = src.splitlines()
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = node.body[0] if node.body else None
            if isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant) \
                    and isinstance(d.value.value, str):
                for i in range(d.lineno, (d.end_lineno or d.lineno) + 1):
                    skip.add(i)
    for i, line in enumerate(lines, 1):
        if i in skip:
            continue
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


# ---------------------------------------------------------------- ① 静态

#: (文件, 必须出现的正则, 缺失时的说明)
STATIC_RULES: List[Tuple[Path, str, str]] = [
    (MANAS_PY, r'_count_closed_trades',
     "战绩笔数没有独立统计函数 —— 直接查 get_strategy_summary(\"default\") 会恒读到 0 笔"),
    (MANAS_PY, r'if total_trades <= 0:\s*\n(?:[^\n]*\n){0,8}?\s*return 0\.5',
     "0 笔战绩必须给中性 0.5；给 0.3 会造成「没交易→没战绩→不放行」死锁"),
    (TC_PY, r'gate_ok = bool\(fusion\.should_act\)',
     "否决原因没拆成「闸门未放行 / 置信度不足」两路"),
    (TC_PY, r'approved = gate_ok and conf_ok',
     "批准判定未使用拆分后的两个原因"),
    # ❗否决**分支**必须真的按 gate_ok 分流。只校验「定义了 gate_ok」是不够的：
    # 注入 ``if False:`` 会把分流短路掉，日志又变成一律归因置信度。
    (TC_PY, r'if not gate_ok:\s*\n\s*reason = \(f"Manas 闸门未放行',
     "否决分支未按 gate_ok 分流（会退回「一律说置信度不足」的假理由）"),
    (TC_PY, r'信号否决: \{stock_code\} — \{reason\}',
     "否决日志没有打印拆分后的 reason"),
    (EXEC_PY, r'def strip_market_prefix',
     "缺少无点市场前缀剥离（sh600487 → 600487）"),
    (EXEC_PY, r'text\[:2\]\.isalpha\(\) and text\[2:\]\.isdigit\(\)',
     "无点前缀判定没有「后半段必须全数字」约束 —— 会把美股 usac 误削成 ac"),
]

#: (文件, 禁止出现的正则, 说明)
FORBIDDEN: List[Tuple[Path, str, str]] = [
    (MANAS_PY, r'get_strategy_summary\(\s*["\']default["\']\s*\)\s*\n\s*total_trades',
     "仍在按不存在的 'default' 策略统计战绩（恒 0 笔 → 置信度恒 0.3）"),
    (TC_PY, r'❌ 信号否决[^\n]*confidence=\{fusion\.fused_confidence[^}]*\} < \{approval_threshold\}',
     "否决日志又回到「一律归因置信度不足」的假理由"),
]


def check_static() -> List[str]:
    failures: List[str] = []
    for path, pattern, why in STATIC_RULES:
        src = _strip_noise(_read(path))
        import re
        if not re.search(pattern, src):
            failures.append(f"{path.name}: {why}")
    for path, pattern, why in FORBIDDEN:
        src = _strip_noise(_read(path))
        import re
        if re.search(pattern, src):
            failures.append(f"{path.name}: {why}")
    return failures


# ---------------------------------------------------------------- ② 契约

class _FakeTracker:
    """模拟真实形态：聚合查询有战绩，按 "default" 查是 0。"""

    def __init__(self, total: int = 100):
        self.total = total

    def get_strategy_summary(self, strategy_id):
        if strategy_id is None:
            return {"total_trades": self.total}
        return {"total_trades": 0}


class _ConfidenceOnly:
    """只暴露需要的部分，避免拉起整个 manas 引擎。"""


def check_contract() -> List[str]:
    failures: List[str] = []
    import re

    # --- 代码格式：无点前缀必须从「判不出」变成「判得出」
    exec_src = _read(EXEC_PY)
    mod = _load_by_path("_exec_manas_chain", EXEC_PY)

    for code, want_market, want_futu in (
        ("sh600487", "CN", "SH.600487"),
        ("sz000636", "CN", "SZ.000636"),
        ("sh601929", "CN", "SH.601929"),
        ("hk06666", "HK", "HK.06666"),
    ):
        m, _why = mod.infer_market(code)
        if m != want_market:
            failures.append(f"infer_market({code!r}) = {m!r}，应为 {want_market!r}")
            continue
        got = mod.futu_code(m, code)
        if got != want_futu:
            failures.append(f"futu_code({m!r}, {code!r}) = {got!r}，应为 {want_futu!r}")

    # 回归：后缀式不能被拼成 US.US
    m, _ = mod.infer_market("NVDA.US")
    if mod.futu_code(m, "NVDA.US") != "US.NVDA":
        failures.append("后缀式 NVDA.US 的富途码错误（应为 US.NVDA，老实现会拼成 US.US）")

    # 回归：美股字母代码不能被无点前缀规则误削
    if mod.strip_market_prefix("usac") != "usac":
        failures.append("strip_market_prefix 误削了美股代码 usac")

    # --- manas 战绩置信度
    manas_src = _read(MANAS_PY)
    if "_count_closed_trades" not in manas_src:
        failures.append("manas_engine 缺少 _count_closed_trades")
        return failures

    # 直接复用源码里的实现：把 ConfidenceEngine._get_bandit_confidence 抠出来跑，
    # 避免拉起整个引擎（会 import deva.NB 等重依赖）。
    eng = _make_confidence_engine(manas_src)
    if eng is None:
        failures.append("无法从源码构造 ConfidenceEngine（结构变了？）")
        return failures

    cases = [
        (None, 0.5, "tracker 缺失 = 无信息 → 中性"),
        (_FakeTracker(0), 0.5, "0 笔 = 无信息 → 中性（绝不能是 0.3，否则死锁）"),
        (_FakeTracker(3), 0.3, "1~4 笔 = 小样本 → 低置信"),
        (_FakeTracker(10), 0.5, "5~19 笔 → 0.5"),
        (_FakeTracker(30), 0.7, "20~49 笔 → 0.7"),
        (_FakeTracker(100), 0.9, "≥50 笔 → 0.9"),
    ]
    for tracker, want, why in cases:
        got = eng._get_bandit_confidence(tracker)
        if abs(got - want) > 1e-9:
            failures.append(f"置信度({why}) = {got}，应为 {want}")

    # ❗核心用例：只认 "default" 的实现必须也读到战绩（100 笔而不是 0 笔）
    got = eng._get_bandit_confidence(_FakeTracker(100))
    if got <= 0.3:
        failures.append(f"注入真实形态的 tracker（聚合 100 笔）后置信度仍 {got} —— "
                        "还在按不存在的 'default' 策略统计")

    # --- 否决理由必须两路分离
    tc_src = _read(TC_PY)
    if "gate_ok" not in tc_src or "conf_ok" not in tc_src:
        failures.append("trading_center 未把否决原因拆成 gate_ok / conf_ok")
    if re.search(r"❌ 信号否决[^\n]*confidence=\{fusion\.fused_confidence", tc_src):
        failures.append("trading_center 否决日志仍一律归因置信度不足")

    return failures


def _make_confidence_engine(src: str):
    """从源码里抠出 ConfidenceEngine，只保留 _get_bandit_confidence 相关成员。

    目的：验证**真实源码**的判定逻辑，而不是在守卫里重写一份会分叉的副本。
    """
    import ast
    import logging

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None

    wanted = {"_get_bandit_confidence", "_count_closed_trades"}
    picked: List[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ConfidenceEngine":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name in wanted:
                    picked.append(item)
            # 类体里的常量（如阈值）一并带上，保证语义一致
            for item in node.body:
                if isinstance(item, ast.Assign):
                    picked.append(item)

    if len(picked) < 2:
        return None

    ns: Dict[str, Any] = {"log": logging.getLogger("guard.manas_chain")}
    module = ast.Module(body=picked, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<guard:ConfidenceEngine>", "exec"), ns)  # noqa: S102

    cls = type("GuardConfidenceEngine", (), {})
    for name in wanted:
        fn = ns.get(name)
        if fn is not None:
            setattr(cls, name, fn)
    if "_count_closed_trades" in ns and isinstance(
            ns.get("_count_closed_trades"), staticmethod):
        setattr(cls, "_count_closed_trades", ns["_count_closed_trades"])
    return cls()


# ---------------------------------------------------------------- ③ 装配

SECTIONS: List[Tuple[str, Callable[[], List[str]]]] = [
    ("静态（三处缺陷的代码形状）", check_static),
    ("契约 · 代码归属 / 战绩置信度 / 否决理由", check_contract),
]


def check() -> int:
    failures: List[str] = []
    for title, fn in SECTIONS:
        got = fn()
        if got:
            failures.append(f"—— {title} ——")
            failures.extend(f"    {g}" for g in got)
        print(f"{'❌' if got else '✅'} {title}"
              + (f"（{len(got)} 项）" if got else ""))

    if failures:
        print("\n❌ 守卫未通过：")
        for f in failures:
            print(f"    {f}")
        return 1
    print("\n✅ manas 链路三处缺陷均已修复（注意：这不代表 manas 会放行）")
    return 0


# ---------------------------------------------------------------- 自证

def self_test() -> int:
    """把正确实现换成缺陷实现，守卫必须变红 —— 否则这条保护是假的。"""
    problems: List[str] = []

    orig = _read(MANAS_PY)
    try:
        # 把 0 笔的中性 0.5 改回 0.3（制造死锁）
        broken = orig.replace(
            "        if total_trades <= 0:\n            return 0.5",
            "        if total_trades <= 0:\n            return 0.3",
            1,
        )
        if broken == orig:
            problems.append("自证锚点失效：找不到 0 笔的中性返回")
        else:
            MANAS_PY.write_text(broken, encoding="utf-8")
            try:
                if not check_contract():
                    problems.append("把 0 笔改回 0.3（死锁）后守卫仍全绿 —— 保护是假的")
                else:
                    print("✅ 自证：0 笔改回 0.3 被捕获")
            finally:
                MANAS_PY.write_text(orig, encoding="utf-8")
    finally:
        if _read(MANAS_PY) != orig:
            problems.append("自证还原失败")

    # 把无点前缀规则删掉
    orig2 = _read(EXEC_PY)
    try:
        broken2 = orig2.replace(
            "    if len(text) > 2 and text[:2].isalpha() and text[2:].isdigit():\n"
            "        head_u = text[:2].upper()\n"
            "        if head_u in _KNOWN_MARKET_TOKENS:\n"
            "            return _normalise_market(head_u), f\"无点市场前缀（{text}）\"\n",
            "",
            1,
        )
        if broken2 == orig2:
            problems.append("自证锚点失效：找不到无点前缀规则")
        else:
            EXEC_PY.write_text(broken2, encoding="utf-8")
            try:
                if not check_contract():
                    problems.append("删掉无点前缀规则后守卫仍全绿 —— 保护是假的")
                else:
                    print("✅ 自证：删掉无点前缀规则被捕获")
            finally:
                EXEC_PY.write_text(orig2, encoding="utf-8")
    finally:
        if _read(EXEC_PY) != orig2:
            problems.append("自证还原失败")

    if problems:
        print("\n❌ 自证失败：")
        for p in problems:
            print(f"    - {p}")
        return 1
    print("\n✅ 自证通过：规则有区分度，且源码已还原")
    return 0


# ---------------------------------------------------------------- 注入

INJECTIONS: List[Dict[str, str]] = [
    {
        "name": "manas 回到只查 default 策略（恒 0 笔）",
        "file": str(MANAS_PY),
        "old": "        best = 0\n        for key in (None, \"default\"):",
        "new": "        best = 0\n        for key in (\"default\",):",
    },
    {
        "name": "0 笔战绩改回 0.3（死锁）",
        "file": str(MANAS_PY),
        "old": "        if total_trades <= 0:\n            return 0.5",
        "new": "        if total_trades <= 0:\n            return 0.3",
    },
    {
        "name": "否决日志回到一律归因置信度",
        "file": str(TC_PY),
        "old": "                if not gate_ok:",
        "new": "                if False:",
    },
    {
        "name": "无点前缀规则被删",
        "file": str(EXEC_PY),
        "old": "    if len(text) > 2 and text[:2].isalpha() and text[2:].isdigit():\n"
               "        head_u = text[:2].upper()",
        "new": "    if False:\n        head_u = text[:2].upper()",
    },
    {
        "name": "无点前缀去掉全数字约束（误削 usac）",
        "file": str(EXEC_PY),
        "old": "    if len(text) > 2 and text[:2].isalpha() and text[2:].isdigit() \\\n"
               "            and text[:2].upper() in _KNOWN_MARKET_TOKENS:\n"
               "        return text[2:]",
        "new": "    if len(text) > 2 and text[:2].upper() in _KNOWN_MARKET_TOKENS:\n"
               "        return text[2:]",
    },
]


def exercise_injections() -> int:
    problems: List[str] = []
    for inj in INJECTIONS:
        path = Path(inj["file"])
        original = _read(path)
        if inj["old"] not in original:
            problems.append(f"[{inj['name']}] 注入锚点找不到，用例已失效")
            continue

        path.write_text(original.replace(inj["old"], inj["new"], 1), encoding="utf-8")
        try:
            got: List[str] = []
            for _title, fn in SECTIONS:
                got.extend(fn())
        finally:
            path.write_text(original, encoding="utf-8")

        if not got:
            problems.append(f"[{inj['name']}] 注入后守卫仍全绿 —— 这条保护是假的")
        else:
            print(f"✅ 注入被捕获：{inj['name']}")
        if _read(path) != original:
            problems.append(f"[{inj['name']}] 还原失败，源码未复位")

    if problems:
        print("\n❌ 注入自证失败：")
        for p in problems:
            print(f"    - {p}")
        return 1
    print(f"\n✅ 注入自证通过：{len(INJECTIONS)} 例全部被捕获，且已还原")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="manas → 决策 → 执行 链路守卫")
    ap.add_argument("--strict", action="store_true", help="严格模式（默认）")
    ap.add_argument("--self-test", action="store_true", help="隔离自证：规则有区分度")
    ap.add_argument("--exercise-injections", action="store_true", help="真实注入后必须报错")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.exercise_injections:
        return exercise_injections()
    return check()


if __name__ == "__main__":
    sys.exit(main())
