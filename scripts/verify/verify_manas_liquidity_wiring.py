#!/usr/bin/env python3
"""守卫：宏观流动性必须**真的**进决策（接线那一段）。

守什么
------
Manas 的 RegimeEngine 只认 ``market_state['macro_liquidity_signal']``
（见 ``os_kernel.make_decision`` / ``os_kernel.process``），而 ``TradingCenter``
组装 ``market_state`` 时**从不填这个键** → 内核恒取默认 0.5
→ 流动性分量 ``macro*2-1`` 恒为 0 → 宏观环境对 ``harmony_strength`` 的贡献
凭空消失。线上表现为 regime 折扣**恒 0.85**（= regime_score 0.0 的常数），
12 条行动门审计全是 ``0.270×折扣0.85=0.230``。

链路（座位早就在，只是一直没人坐）::

    trading_center.process_strategy_signal
      → market_state['macro_liquidity_signal']          ← 本守卫守这里
      → AttentionKernel / os_kernel.make_decision
      → ManasEngine.compute(macro_signal=...)           ← 与这里
      → RegimeEngine: liquidity = macro*2-1
      → regime_score = trend*0.4 + liquidity*0.35 + diffusion*0.25
      → 折扣 0.85+0.15×regime → harmony_strength → 行动门槛

本守卫守三条硬性质
------------------
* **必须接线**：``process_strategy_signal`` 必须把该键写进 ``market_state``，
  且值来自 ``_get_macro_liquidity_signal()`` —— **不许是字面量**（写死 0.5
  等于没接，而且看起来一切正常）。
* **必须有 None 护栏**：放键必须包在 ``is not None`` 判断里。真值取不到时若写进
  ``None``，Manas 侧 ``macro_signal * 2 - 1`` 会直接 TypeError
  （``_get_liquidity_signal`` 的 try 只包 scanner 分支，兜不住），整条决策链炸掉。
* **内核必须消费**：``os_kernel`` 里两条路径（process / make_decision）都要把
  ``market_state`` 的该键喂给 ``macro_signal=``；少一条就是「信号到了家门口又放下」。

行为用例（光看字符串是假绿）
--------------------------
取值器用假容器覆盖四条路径：无容器 / 容器无 query_state / QueryState 无该属性 /
正常取值（含「真值恰好 0.5」也要如实返回 float，不能与「拿不到」混为一谈）。
另外「容器抛异常」必须降级为 None 而不是把异常抛进决策。

用法
----
    python scripts/verify/verify_manas_liquidity_wiring.py
    python scripts/verify/verify_manas_liquidity_wiring.py --strict
    python scripts/verify/verify_manas_liquidity_wiring.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TRADING_CENTER_PY = ROOT / "deva/naja/attention/orchestration/trading_center.py"
OS_KERNEL_PY = ROOT / "deva/naja/attention/os/os_kernel.py"

#: ``market_state`` 里那个键名。改名要同步这里（守卫失败是好事，不是误报）。
LIQUIDITY_KEY = "macro_liquidity_signal"

#: 期望在 os_kernel 里看到的接线处数（process / make_decision 两条路径）。
OS_KERNEL_WIRES = 2


def _find_fn(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _strip_doc(fn) -> str:
    """函数体去掉 docstring 后再 unparse（说明文字里也有关键词，不剥就是假绿）。"""
    body = list(getattr(fn, "body", ()) or ())
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return "\n".join(ast.unparse(s) for s in body)


def _const_str(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_none_check(test) -> bool:
    """``X is not None`` / ``X is None`` 形状的判断。"""
    if isinstance(test, ast.Compare) and len(test.ops) == 1 \
            and isinstance(test.ops[0], (ast.IsNot, ast.Is)):
        return any(isinstance(c, ast.Constant) and c.value is None for c in test.comparators)
    return False


def _is_liquidity_key_assign(stmt) -> bool:
    return (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Subscript)
        and isinstance(stmt.targets[0].value, ast.Name)
        and stmt.targets[0].value.id == "market_state"
        and _const_str(stmt.targets[0].slice) == LIQUIDITY_KEY
    )


# ── 静态检查 ─────────────────────────────────────────────────────────────────

def check_trading_center_wiring() -> list:
    """宏观流动性要有真值来源、要放进 market_state、且不能放 None 进去。"""
    failures: list = []
    tree = ast.parse(TRADING_CENTER_PY.read_text(encoding="utf-8"))

    consume = _find_fn(tree, "process_strategy_signal")
    if consume is None:
        return ["trading_center 找不到 process_strategy_signal（决策入口换了？）"]

    # ① 必须真的把键写进 market_state
    keys = [s for s in ast.walk(consume) if _is_liquidity_key_assign(s)]
    if not keys:
        failures.append(
            f"process_strategy_signal 没把 {LIQUIDITY_KEY} 写进 market_state"
            "（宏观流动性没进决策）"
        )

    # ② 值不许是字面量（写死 0.5 == 没接，而且看上去一切正常）
    for stmt in keys:
        if isinstance(stmt.value, ast.Constant):
            failures.append(
                f"market_state['{LIQUIDITY_KEY}'] 被赋成字面量 {stmt.value.value!r}"
                "（不是 QueryState 真值，等于没接）"
            )

    # ③ 真值必须来自单一出处 self._get_macro_liquidity_signal()
    called = {
        n.func.attr
        for n in ast.walk(consume)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    if "_get_macro_liquidity_signal" not in called:
        failures.append(
            "process_strategy_signal 未调用 _get_macro_liquidity_signal"
            "（宏观流动性真值来源不明）"
        )

    # ④ 放键必须包在 None 判断里 —— 否则取不到真值时会写进 None，
    #    下游 `macro_signal * 2 - 1` 直接 TypeError（护栏在 scanner 分支之外）。
    guarded = False
    for node in ast.walk(consume):
        if isinstance(node, ast.If) and _is_none_check(node.test):
            if any(_is_liquidity_key_assign(s) for s in ast.walk(node)):
                guarded = True
    if keys and not guarded:
        failures.append(
            f"market_state['{LIQUIDITY_KEY}'] 未包在 `is not None` 判断里"
            "（取不到真值时会写入 None → Manas 侧 macro_signal*2-1 抛 TypeError）"
        )

    # ⑤ 取值器自身必须从 QueryState 读该键
    getter = _find_fn(tree, "_get_macro_liquidity_signal")
    if getter is None:
        failures.append("缺 _get_macro_liquidity_signal（宏观流动性没有单一出处）")
    else:
        body = _strip_doc(getter)
        if LIQUIDITY_KEY not in body:
            failures.append(f"_get_macro_liquidity_signal 没读 {LIQUIDITY_KEY}")
        if "query_state" not in body:
            failures.append("_get_macro_liquidity_signal 没从 QueryState 取数")
    return failures


def check_os_kernel_consumes() -> list:
    """内核两条路径都要把 market_state 的宏观流动性喂给 Manas。"""
    failures: list = []
    tree = ast.parse(OS_KERNEL_PY.read_text(encoding="utf-8"))
    n_ok = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "compute":
            continue
        for kw in node.keywords:
            if kw.arg == "macro_signal" and LIQUIDITY_KEY in ast.unparse(kw.value):
                n_ok += 1
    if n_ok < OS_KERNEL_WIRES:
        failures.append(
            f"os_kernel 只有 {n_ok} 处把 {LIQUIDITY_KEY} 喂给 Manas"
            f"（应 {OS_KERNEL_WIRES} 处：process / make_decision）"
        )
    return failures


# ── 行为检查（真跑，不只看字符串） ────────────────────────────────────────────

_MISSING = object()


class _FakeContainer:
    def __init__(self, query_state):
        self.query_state = query_state


class _QS:
    """假 QueryState：给 _MISSING 表示「没有这个属性」。"""

    def __init__(self, value):
        if value is not _MISSING:
            self.macro_liquidity_signal = value


def check_getter_behavior() -> list:
    """取值器各路径：无容器 / 无 query_state / 无属性 / 有值 / 抛异常。"""
    from unittest import mock

    failures: list = []
    tc_mod = importlib.reload(
        importlib.import_module("deva.naja.attention.orchestration.trading_center")
    )
    app_mod = importlib.import_module("deva.naja.application")

    tc = tc_mod.TradingCenter.__new__(tc_mod.TradingCenter)   # 不跑 __init__

    cases = [
        ("容器为 None", lambda: None, None),
        ("容器无 query_state", lambda: object(), None),
        ("QueryState 无该属性", lambda: _FakeContainer(_QS(_MISSING)), None),
        ("正常取值 0.195", lambda: _FakeContainer(_QS(0.195)), 0.195),
        ("真值恰好 0.5 也要如实返回", lambda: _FakeContainer(_QS(0.5)), 0.5),
    ]
    for label, factory, want in cases:
        with mock.patch.object(app_mod, "get_app_container", factory):
            # _get_macro_liquidity_signal 内部是函数级 import，
            # patch 模块属性即可命中。
            got = tc._get_macro_liquidity_signal()
        if got != want:
            failures.append(f"[{label}] 应返回 {want!r}，实得 {got!r}")

    def _boom():
        raise RuntimeError("container 炸了")

    with mock.patch.object(app_mod, "get_app_container", _boom):
        got = tc._get_macro_liquidity_signal()
    if got is not None:
        failures.append(f"[容器抛异常] 应降级为 None，实得 {got!r}")
    return failures


# ── 负向注入 ─────────────────────────────────────────────────────────────────

INJECTIONS = [
    {
        "name": "宏观流动性不写进 market_state（断点 A 复发）",
        "file": TRADING_CENTER_PY,
        "old": "            macro_liquidity = self._get_macro_liquidity_signal()\n"
               "            if macro_liquidity is not None:\n"
               "                market_state['macro_liquidity_signal'] = macro_liquidity\n",
        "new": "",
    },
    {
        "name": "写死一个 0.5 冒充真值（接了等于没接）",
        "file": TRADING_CENTER_PY,
        "old": "                market_state['macro_liquidity_signal'] = macro_liquidity\n",
        "new": "                market_state['macro_liquidity_signal'] = 0.5\n",
    },
    {
        "name": "去掉 None 护栏（取不到就往里写 None）",
        "file": TRADING_CENTER_PY,
        "old": "            if macro_liquidity is not None:\n",
        "new": "            if True:\n",
    },
    {
        "name": "取值器脱离 QueryState（改从别处取）",
        "file": TRADING_CENTER_PY,
        "old": '            value = getattr(query_state, "macro_liquidity_signal", None)\n',
        "new": "            value = 0.5\n",
    },
    {
        "name": "内核不把宏观流动性喂给 Manas（信号到家门口又放下）",
        "file": OS_KERNEL_PY,
        "old": '            macro_signal=market_state.get("macro_liquidity_signal", 0.5) if market_state else 0.5,\n',
        "new": "            macro_signal=0.5,\n",
        "count": 2,
    },
]


def _all_checks() -> list:
    return (
        check_trading_center_wiring()
        + check_os_kernel_consumes()
        + check_getter_behavior()
    )


def _reload():
    try:
        importlib.reload(
            importlib.import_module("deva.naja.attention.orchestration.trading_center")
        )
    except Exception:
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
            print(f"❌ 锚点出现 {original.count(inj['old'])} 次（期望 {count}），注入不确定：{inj['name']}")
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
        print("❌ 宏观流动性接线守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ 宏观流动性接线守卫全绿（接线 / 真值来源 / None 护栏 / 内核两路消费 / 取值器行为）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
