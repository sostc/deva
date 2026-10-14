#!/usr/bin/env python3
"""守卫：单例注册表一致性 —— 「取了没注册 / 注册了没人取」

背景（为什么要有这个守卫）
------------------------------------------------------------------
`deva/naja/register.py` 是一张声明式单例表，`SR('name')` 是全库取用入口。
两者一旦脱节，**两种方向的故障都是静默的**：

  * **取了没注册** → `SR()` 抛 `KeyError`；本项目大量取用点在 `try/except` 里，
    于是退化成「功能永久缺失、不报错、也没人发现」。2026-10-15 审计发现 3 例
    （`connector` / `replay_scheduler` / `block_noise_detector`）。
  * **注册了没人取** → 装配阶段一切正常、`print_registry_status()` 也漂亮，
    但没有任何消费者。容易让人误以为「链路已通」。
    同一轮审计发现 `strategy_result_store` / `signal_dispatcher` / `cognition_bus`
    三例，其中 `strategy_result_store` 还是 `bandit_attribution` 的 deps，
    没人取 `bandit_attribution` 就两个都不会实例化。

还有一类**只在语义上重复**的坑（一个语义、两个实例）：「注册表工厂 `Class()`
新建一个」与「模块级 `_xxx = Class()` 已有另一个」并存。
`snapshot_manager` / `scheduler_manager` 都踩过 —— 已在本轮改为工厂复用模块级单例，
本守卫的 ③ 段会持续盯着。

⚠️ 本守卫只读源码，不 import 项目（避免触发装配 / 网络 / DB）。

三段检查
------------------------------------------------------------------
  ① **取了没注册**（硬错误）：全库 `SR('x')` 的 x 必须在注册表里。
     `KNOWN_UNREGISTERED` 里的除外 —— 那是**已确认且已留因**的豁免，
     每条都必须写清为什么还没修。默认打印 ⏭️，不判失败。
  ② **注册了没人取**（黄）：注册名在整包里（含非 SR 访问）应至少出现一次。
     按「零提及 / 仅经容器装配」两档如实区分 —— 后者不算断链，但需人工确认。
  ③ **工厂直接构造**（提示项）：`_create_*` 工厂里 `return SomeClass()` 形态会
     新建实例；若同类在别处已有模块级单例（`_xxx` / `get_xxx()`），
     就成了「一个语义两个实例」。仅提示不判失败 —— 需人工确认哪个才是权威。

用法
------------------------------------------------------------------
    python3 scripts/verify/verify_singleton_registry_consistency.py
    python3 scripts/verify/verify_singleton_registry_consistency.py --strict   # 有豁免也不许过
    python3 scripts/verify/verify_singleton_registry_consistency.py --self-test  # 自证有区分度
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = REPO_ROOT / "deva"

# ① 已知「取了但从未注册」的名单。每一项都必须写清「为什么还没修」。
#    ❗不要为了让守卫变绿而往这里加东西 —— 只有确认是既定取舍才进得来，
#      且必须在对应调用点留同样的注释。
KNOWN_UNREGISTERED: Dict[str, str] = {
    "connector": (
        "home/ui/stats.py:48、knowledge/wisdom/ui.py:19。全库不存在 Connector 类，"
        "且它调用的 get_wisdom_stats() 也无定义 —— 纯死路径，UI 靠 except 兜底显示 0。"
        "需先决定「智慧统计」这个能力做不做（审计 P1-1）。"
    ),
    "replay_scheduler": (
        "infra/observability/auto_tuner.py:32、web_ui/modes.py:365、"
        "bandit/market_observer.py:91。无任何生产者注册它；"
        "调用方 `if scheduler:` 判空安全降级，代价是「回放间隔调优」子功能永久失效"
        "（审计 P1-1）。"
    ),
}

# ② 「注册了没人取」里被判定为**预留**（不算黄）的名字。宁缺毋滥。
KNOWN_RESERVED: Set[str] = set()


def _iter_py(root: Path) -> List[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _const_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _func_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def collect_registered(sources: Dict[str, str]) -> Set[str]:
    """收集注册名：SIMPLE_SINGLETONS 表 + register_singleton('x', ...) 字面量。"""
    names: Set[str] = set()
    for src in sources.values():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if _func_name(node.func) in ("register_singleton", "_register_singleton") and node.args:
                    v = _const_str(node.args[0])
                    if v:
                        names.add(v)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                hit = any(isinstance(t, ast.Name) and t.id == "SIMPLE_SINGLETONS" for t in targets)
                if hit and isinstance(node.value, ast.List):
                    for el in node.value.elts:
                        if isinstance(el, ast.Tuple) and el.elts:
                            v = _const_str(el.elts[0])
                            if v:
                                names.add(v)
    return names


def collect_used(sources: Dict[str, str]) -> Dict[str, Set[str]]:
    """收集全库 `SR('x')` 的字面量取用点。"""
    used: Dict[str, Set[str]] = {}
    for path, src in sources.items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _func_name(node.func) == "SR" and node.args:
                v = _const_str(node.args[0])
                if v:
                    used.setdefault(v, set()).add(path)
    return used


def count_mentions(sources: Dict[str, str], name: str, exclude_suffix: str = "register.py") -> int:
    """统计除注册表文件外的纯文本提及次数（用于区分「真零引用」与「经容器装配」）。"""
    # ❗用 `(?<![A-Za-z0-9])` 而非 `\b`：模块级单例常写作 `_snapshot_manager`，
    # 而 `\b` 要求词边界、`_` 属词字符 → `_snapshot_manager` 里的 `snapshot_manager`
    # 匹配不到，会把「已有模块级单例」误判成「真·零引用」。
    pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(name))
    total = 0
    for path, src in sources.items():
        if path.endswith(exclude_suffix):
            continue
        total += len(pat.findall(src))
    return total


def check(
    registered: Set[str],
    used: Dict[str, Set[str]],
    whitelist: Set[str],
) -> Tuple[List[Tuple[str, str, List[str]]], List[Tuple[str, str, List[str]]], List[str]]:
    """返回 (硬错误, 豁免, 零SR引用名单)。纯函数，便于自证。"""
    errors: List[Tuple[str, str, List[str]]] = []
    skips: List[Tuple[str, str, List[str]]] = []

    for name in sorted(used):
        if name in registered:
            continue
        entry = (name, "", sorted(used[name]))
        if name in whitelist:
            skips.append(entry)
        else:
            errors.append(entry)

    idle = [n for n in sorted(registered) if n not in used]
    return errors, skips, idle


def collect_direct_constructs(sources: Dict[str, str]) -> List[Tuple[str, str]]:
    """③ 找出注册表里「工厂函数直接 `return SomeClass()`」的形态。

    返回 [(函数名, 类名)]。仅提示：需人工确认该类在别处是否已有模块级单例。
    """
    out: List[Tuple[str, str]] = []
    for path, src in sources.items():
        if not path.endswith("register.py"):
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("_create_"):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Call):
                    fn = sub.value.func
                    if isinstance(fn, ast.Name) and fn.id[:1].isupper():
                        out.append((node.name, fn.id))
    return sorted(set(out))


def _self_test() -> int:
    """自证有区分度：同一套逻辑，喂「有问题」与「没问题」两份源，结论必须不同。"""
    reg_ok = {"a": "SIMPLE_SINGLETONS = [('a', 'm', 'C', [])]"}
    reg_bad = {"a": "SIMPLE_SINGLETONS = [('a', 'm', 'C', [])]"}
    other_ok = {"other.py": "from register import SR\nx = SR('a')\n"}
    other_bad = {"other.py": "from register import SR\nx = SR('b')\n"}

    e_ok, _, idle_ok = check(collect_registered(reg_ok), collect_used(other_ok), set())
    e_bad, _, _ = check(collect_registered(reg_bad), collect_used(other_bad), set())

    problems = []
    if e_ok or idle_ok:
        problems.append(f"健康样例被误报: errors={e_ok} idle={idle_ok}")
    if not e_bad:
        problems.append("故障样例（取了未注册 'b'）没有被抓出来 —— 守卫无区分度")

    if problems:
        for p in problems:
            print(f"  ✗ 自证失败: {p}")
        return 1
    print("  ✓ 自证通过：健康样例无告警，故障样例被抓出")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="单例注册表一致性守卫")
    ap.add_argument("--strict", action="store_true", help="有豁免项也不许过")
    ap.add_argument("--self-test", action="store_true", help="只跑自证")
    args = ap.parse_args()

    # 本守卫会 ast.parse 全库 700+ 文件；个别历史文件带无效转义序列，
    # 只影响解析器的 SyntaxWarning，与本次判定无关，静音掉避免刷屏。
    warnings.simplefilter("ignore", SyntaxWarning)

    if args.self_test:
        return _self_test()

    print("=" * 72)
    print("守卫：单例注册表一致性")
    print("=" * 72)

    paths = _iter_py(SCAN_ROOT)
    sources: Dict[str, str] = {}
    for p in paths:
        try:
            sources[str(p)] = p.read_text(encoding="utf-8")
        except Exception:
            continue

    registered = collect_registered(sources)
    used = collect_used(sources)
    errors, skips, idle = check(registered, used, set(KNOWN_UNREGISTERED))

    print(f"\n扫描 {len(sources)} 个源文件；注册名 {len(registered)} 个；"
          f"SR() 取用名 {len(used)} 个\n")

    print("① 取了但没注册（硬错误）")
    if not errors:
        print("  ✅ 无")
    for name, _, where in errors:
        print(f"  ✗ SR('{name}')  取用于 {', '.join(where[:3])}")
        print("      → 调用点在 try/except 里就会静默失效；请补注册或删除取用")

    if skips:
        print("\n  ⏭️ 已知豁免（已在代码里留因，待决策）")
        for name, _, where in skips:
            print(f"  · SR('{name}')  → {KNOWN_UNREGISTERED.get(name, '')[:60]}...")

    print("\n② 注册了但全库无 SR() 取用")
    idle_zero = [n for n in idle if count_mentions(sources, n) == 0 and n not in KNOWN_RESERVED]
    idle_ref = [n for n in idle if count_mentions(sources, n) > 0]
    if idle_zero:
        print("  真·零引用（除注册声明外全库未出现；最可能是「装配了但没接上」）")
        for n in idle_zero:
            print(f"    · {n}")
    else:
        print("  ✅ 无真·零引用")
    if idle_ref:
        shown = ", ".join(idle_ref[:8])
        more = " …" if len(idle_ref) > 8 else ""
        print(f"  另 {len(idle_ref)} 个仅在非 SR 处出现（多半经 container 装配，属正常）：{shown}{more}")

    print("\n③ 工厂里直接构造类（提示：确认是否与模块级单例重复）")
    directs = collect_direct_constructs(sources)
    if not directs:
        print("  ✅ 无")
    for fname, cls in directs:
        print(f"  · {fname:34s} → return {cls}()")

    print("\n" + "=" * 72)
    if errors:
        print(f"结论：失败 —— {len(errors)} 处「取了没注册」")
        return 1
    if args.strict and skips:
        print(f"结论：失败（--strict）—— {len(skips)} 处豁免未清")
        return 1
    print(f"结论：通过（豁免 {len(skips)} 处；②为提示项，不影响退出码）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
