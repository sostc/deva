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

本守卫守四条硬性质
------------------
* **必须接线**：``process_strategy_signal`` 必须把该键写进 ``market_state``，
  且值来自 ``_get_macro_liquidity_signal()`` —— **不许是字面量**（写死 0.5
  等于没接，而且看起来一切正常）。
* **必须有 None 护栏**：放键必须包在 ``is not None`` 判断里。真值取不到时若写进
  ``None``，Manas 侧 ``macro_signal * 2 - 1`` 会直接 TypeError
  （``_get_liquidity_signal`` 的 try 只包 scanner 分支，兜不住），整条决策链炸掉。
* **内核必须消费**：``os_kernel`` 里两条路径（process / make_decision）都要把
  ``market_state`` 的该键喂给 ``macro_signal=``；少一条就是「信号到了家门口又放下」。
* **只能有一处读取口径，且两条路都调它**：决策路径（``trading_center``）与展示
  路径（``ManasManager.compute``，UI / 守望台 / ``/api/attention/manas/state``
  走的就是它）必须同源。展示路径曾硬编码 ``return 0.5`` —— 它高频调用
  ``ManasEngine.compute()``、又是行动门审计的主要写入者，于是线上
  ``regime_score`` 恒 0.0 / 折扣恒 0.85，看着像「环境一直中性」，其实是这条线
  压根没接上。

行为用例（光看字符串是假绿）
--------------------------
① 决策路径取值器用假容器覆盖五条路径：无容器 / 容器无 query_state / QueryState
无该属性 / 正常取值 / 真值恰好 0.5；「容器抛异常」必须降级为 None 而不是把异常
抛进决策。
② 端到端：真跑 ``process_strategy_signal``，在 ``_full_decision_pipeline`` 处
截获组装好的 ``market_state``，看键到底有没有进去。
③ 展示路径：把假引擎塞进 ``ManasManager.compute()``，直接读它递给 Manas 的
实参 —— 有真值必须带、真值恰好 0.5 必须如实带、取不到必须**不带**（而不是带
None）；并交叉验证两条路对同一份 QueryState 给出同一个数。

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
MANAS_MANAGER_PY = ROOT / "deva/naja/attention/kernel/manas_manager.py"
MACRO_LIQ_PY = ROOT / "deva/naja/attention/kernel/macro_liquidity.py"

#: ``market_state`` 里那个键名。改名要同步这里（守卫失败是好事，不是误报）。
LIQUIDITY_KEY = "macro_liquidity_signal"

#: 期望在 os_kernel 里看到的接线处数（process / make_decision 两条路径）。
OS_KERNEL_WIRES = 2

#: 唯一读取口径的函数名（两条路都必须调它）。
SHARED_READER = "read_macro_liquidity_signal"


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


def _is_kwarg_assign(stmt) -> bool:
    """``kwargs["macro_signal"] = ...`` 形状。"""
    return (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Subscript)
        and isinstance(stmt.targets[0].value, ast.Name)
        and stmt.targets[0].value.id == "kwargs"
        and _const_str(stmt.targets[0].slice) == "macro_signal"
    )


def _calls(fn, name: str) -> bool:
    """函数体里是否调用了 ``name``（含 ``mod.name`` 形式）。"""
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if getattr(f, "id", None) == name or getattr(f, "attr", None) == name:
                return True
    return False


def _floats_returned(fn) -> list:
    """函数体里 ``return <数字常量>`` 的那些常量（写死值）。"""
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, (int, float)) \
                and not isinstance(node.value.value, bool):
            out.append(node.value.value)
    return out


def _module_const_str(tree: ast.AST, name: str):
    """模块级 ``NAME = "字面量"`` 的值。"""
    for node in getattr(tree, "body", ()):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return _const_str(node.value)
    return None


def _reads_query_state_key(fn) -> bool:
    """必须真的 ``getattr(query_state, <键常量>, ...)`` —— 防止「读别处」。"""
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "getattr"):
            continue
        if len(node.args) < 2:
            continue
        if not (isinstance(node.args[0], ast.Name) and node.args[0].id == "query_state"):
            continue
        if "MACRO_LIQUIDITY_KEY" in ast.unparse(node.args[1]):
            return True
    return False


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

    # ⑤ 取值器必须走**唯一读取口径**（不许自己再写一份读法 —— 展示路径曾经
    #    就是自己写了一份，并且写死成 0.5）
    getter = _find_fn(tree, "_get_macro_liquidity_signal")
    if getter is None:
        failures.append("缺 _get_macro_liquidity_signal（宏观流动性没有取值器）")
    else:
        if not _calls(getter, SHARED_READER):
            failures.append(
                f"_get_macro_liquidity_signal 没走唯一读取口径 {SHARED_READER}"
                "（两条路会各读各的 → 漂移）"
            )
        for literal in _floats_returned(getter):
            failures.append(
                f"_get_macro_liquidity_signal 直接返回常量 {literal!r}（等于没接）"
            )
    return failures


def check_single_source_reader() -> list:
    """宏观流动性只能有**一处**读法，且那一处必须真的认 ``QueryState``。

    两条投喂路径（决策 / 展示）若各写一份读法，一定漂移 —— 实锤是展示路径
    硬编码 ``return 0.5``，导致行动门审计里的 ``regime_score`` 恒 0.0。
    """
    failures: list = []
    if not MACRO_LIQ_PY.exists():
        return ["缺 kernel/macro_liquidity.py（宏观流动性没有唯一读取口径）"]
    tree = ast.parse(MACRO_LIQ_PY.read_text(encoding="utf-8"))

    value = _module_const_str(tree, "MACRO_LIQUIDITY_KEY")
    if value != LIQUIDITY_KEY:
        failures.append(
            f"MACRO_LIQUIDITY_KEY = {value!r}，与 market_state 的键名 {LIQUIDITY_KEY!r} 不一致"
        )

    fn = _find_fn(tree, SHARED_READER)
    if fn is None:
        return failures + [f"macro_liquidity 缺 {SHARED_READER}"]
    if not _reads_query_state_key(fn):
        failures.append(
            f"{SHARED_READER} 没有 `getattr(query_state, MACRO_LIQUIDITY_KEY, ...)`"
            "（唯一读取口径脱离了真源）"
        )
    body = _strip_doc(fn)
    if "value is None" not in body:
        failures.append(
            f"{SHARED_READER} 缺少 `value is None` 三态判断"
            "（「拿不到」会被静默当成「中性 0.5」）"
        )
    return failures


def check_manager_wiring() -> list:
    """展示路径（``ManasManager.compute``）必须把真值喂给 Manas。

    这条是「宏观流动性已进决策」**可观测**的关键：UI / 守望台 / 状态接口走的
    就是这条路，而行动门审计（每次 compute 都留痕）主要由它写入。它若写死
    0.5，审计里的 ``regime_score`` 就恒 0.0 —— 看着像「环境一直中性」。
    """
    failures: list = []
    tree = ast.parse(MANAS_MANAGER_PY.read_text(encoding="utf-8"))

    getter = _find_fn(tree, "_get_macro_signal")
    if getter is None:
        return ["manas_manager 缺 _get_macro_signal（展示路径没有宏观流动性来源）"]
    if not _calls(getter, SHARED_READER):
        failures.append(
            f"_get_macro_signal 没走唯一读取口径 {SHARED_READER}（与决策路径会漂移）"
        )
    for literal in _floats_returned(getter):
        failures.append(
            f"_get_macro_signal 硬编码返回常量 {literal!r}"
            "（展示路径永远看不到真实宏观环境）"
        )

    compute = _find_fn(tree, "compute")
    if compute is None:
        return failures + ["manas_manager 缺 compute"]
    cbody = _strip_doc(compute)
    if "macro_signal" not in cbody:
        failures.append("ManasManager.compute 没把宏观流动性递给 Manas（展示路径没接线）")
        return failures

    # 放 kwargs 必须包在 `is not None` 里 —— 否则取不到真值时会传 None，
    # Manas 侧 `macro_signal * 2 - 1` 直接 TypeError。
    guarded = False
    for node in ast.walk(compute):
        if isinstance(node, ast.If) and _is_none_check(node.test):
            if any(_is_kwarg_assign(s) for s in ast.walk(node)):
                guarded = True
    if not guarded:
        failures.append(
            "ManasManager.compute 的 macro_signal 未包在 `is not None` 判断里"
            "（取不到真值会传 None → macro_signal*2-1 抛 TypeError）"
        )

    # kwargs 必须真的透传给引擎（写了不传 = 静默失效）
    passed = any(
        isinstance(n, ast.Call)
        and getattr(n.func, "attr", None) == "compute"
        and any(kw.arg is None and isinstance(kw.value, ast.Name) and kw.value.id == "kwargs"
                for kw in n.keywords)
        for n in ast.walk(compute)
    )
    if not passed:
        failures.append("ManasManager.compute 没把 kwargs 透传给 manas_engine.compute")
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


class _Probe(Exception):
    """在 ``_full_decision_pipeline`` 处截断，捕获组装好的 market_state。"""


def _mk_trading_center(tc_mod, captured: dict):
    tc = tc_mod.TradingCenter.__new__(tc_mod.TradingCenter)   # 不跑 __init__
    tc.attention_os = object()            # 非 None → 不走「按置信度兜底」的降级路径
    tc._get_current_narratives = lambda: []

    def _probe(market_state, snapshot=None):
        captured.clear()
        captured.update(market_state)
        raise _Probe()

    tc._full_decision_pipeline = _probe
    tc._record_plan = lambda *a, **k: None    # 守卫不得写生产数据
    return tc


def check_process_signal_market_state() -> list:
    """端到端（截到 market_state 为止）：真跑决策入口，看键到底有没有进去。

    静态检查只能证明「代码里写了」，证明不了「跑起来真的带上了」—— 这一步
    把 ``_full_decision_pipeline`` 换成探针，真实调用 ``process_strategy_signal``，
    直接看它递下去的 market_state。
    """
    from unittest import mock

    failures: list = []
    tc_mod = importlib.reload(
        importlib.import_module("deva.naja.attention.orchestration.trading_center")
    )
    app_mod = importlib.import_module("deva.naja.application")
    signal = {
        "strategy_id": "verify_probe",
        "stock_code": "TEST",
        "signal_type": "buy",
        "price": 1.0,
        "confidence": 0.6,
    }

    def _run(container_factory) -> dict:
        captured: dict = {}
        tc = _mk_trading_center(tc_mod, captured)
        with mock.patch.object(app_mod, "get_app_container", container_factory):
            try:
                tc.process_strategy_signal(signal)
            except _Probe:
                pass
            except Exception as e:  # noqa: BLE001
                failures.append(
                    f"process_strategy_signal 意外异常: {type(e).__name__}: {e}"
                )
        return captured

    # ① 有真值 → 必须带上，且值就是真值
    got = _run(lambda: _FakeContainer(_QS(0.42)))
    if LIQUIDITY_KEY not in got:
        failures.append(
            f"process_strategy_signal 组装的 market_state 缺 {LIQUIDITY_KEY}"
            "（宏观流动性到不了 Manas）"
        )
    else:
        value = got[LIQUIDITY_KEY]
        if not isinstance(value, float) or abs(value - 0.42) > 1e-9:
            failures.append(f"market_state 里的宏观流动性应为 0.42(float)，实得 {value!r}")

    # ② 取不到 → **不放键**（放 None 会让 Manas 侧 macro_signal*2-1 抛 TypeError）
    got2 = _run(lambda: None)
    if LIQUIDITY_KEY in got2:
        failures.append(
            f"取不到宏观流动性时仍写了 {LIQUIDITY_KEY}={got2[LIQUIDITY_KEY]!r}"
            "（应当不放键，让 Manas 用默认 0.5）"
        )
    return failures


# ── 展示路径行为（ManasManager.compute）─────────────────────────────────────


class _FakeManasOutput:
    def to_dict(self):
        return {
            "manas_score": 0.21, "timing_score": 0.5, "regime_score": 0.0,
            "confidence_score": 0.3, "risk_temperature": 1.25,
            "bias_state": "neutral", "should_act": False,
            "action_type": "hold", "awakening_level": "dormant",
        }


class _RecordingEngine:
    """只把收到的实参记下来，不真算 —— 要验的是「递进去的是什么」。"""

    def __init__(self):
        self.calls: list = []

    def compute(self, **kwargs):
        self.calls.append(dict(kwargs))
        return _FakeManasOutput()


class _FakeKernel:
    def __init__(self, engine):
        self._engine = engine

    def get_manas_engine(self):
        return self._engine

    def get_manas_inputs(self):
        return {
            "session_manager": None, "portfolio": None,
            "scanner": None, "bandit_tracker": None,
        }


def _mk_manager(mm_mod, engine):
    m = mm_mod.ManasManager.__new__(mm_mod.ManasManager)   # 不跑 __init__
    m.kernel = _FakeKernel(engine)
    m._manas_engine = None
    m._trading_clock = None
    m._virtual_portfolio = None
    m._bandit_tracker = None
    m._enabled = True
    m._last_compute_time = 0.0
    m._last_output = None
    return m


def check_manager_behavior() -> list:
    """展示路径真跑一次 ``compute()``，看它到底给 Manas 递了什么。

    静态检查只能证明「代码里写了」；这里把假引擎塞进去，直接读实参。
    """
    from unittest import mock

    failures: list = []
    mm_mod = importlib.reload(
        importlib.import_module("deva.naja.attention.kernel.manas_manager")
    )
    app_mod = importlib.import_module("deva.naja.application")

    def _run(container_factory) -> dict:
        engine = _RecordingEngine()
        m = _mk_manager(mm_mod, engine)
        with mock.patch.object(app_mod, "get_app_container", container_factory):
            m.compute()
        return engine.calls[-1] if engine.calls else {}

    # ① 有真值 → 必须带上，且就是真值
    got = _run(lambda: _FakeContainer(_QS(0.42)))
    if "macro_signal" not in got:
        failures.append(
            "ManasManager.compute 没把 macro_signal 递给 Manas（展示路径没接线）"
        )
    elif not isinstance(got["macro_signal"], float) or abs(got["macro_signal"] - 0.42) > 1e-9:
        failures.append(
            f"展示路径递给 Manas 的 macro_signal 应为 0.42(float)，实得 {got['macro_signal']!r}"
        )

    # ② 真值恰好 0.5 也要如实传（「拿不到」与「0.5」是两回事）
    got2 = _run(lambda: _FakeContainer(_QS(0.5)))
    if got2.get("macro_signal") != 0.5:
        failures.append(f"真值恰好 0.5 时也应如实传递，实得 {got2.get('macro_signal')!r}")

    # ③ 取不到 → **不传该参数**（传 None 会让 Manas 侧 macro*2-1 抛 TypeError）
    for label, factory in (
        ("容器为 None", lambda: None),
        ("QueryState 无该属性", lambda: _FakeContainer(_QS(_MISSING))),
    ):
        got3 = _run(factory)
        if "macro_signal" in got3:
            failures.append(
                f"[{label}] 不应传 macro_signal（应让 Manas 用默认 0.5），"
                f"实得 {got3['macro_signal']!r}"
            )

    # ④ 两条路必须**同源**：同一份假 QueryState → 同一个数
    factory = lambda: _FakeContainer(_QS(0.3187))
    tc_mod = importlib.reload(
        importlib.import_module("deva.naja.attention.orchestration.trading_center")
    )
    tc = tc_mod.TradingCenter.__new__(tc_mod.TradingCenter)   # 不跑 __init__
    with mock.patch.object(app_mod, "get_app_container", factory):
        decision_side = tc._get_macro_liquidity_signal()
    display_side = _run(factory).get("macro_signal")
    if decision_side is None or decision_side != display_side:
        failures.append(
            f"决策路径与展示路径取的宏观流动性不一致：{decision_side!r} vs {display_side!r}"
            "（同一份 QueryState 必须同源，否则同一个引擎会给出两种环境结论）"
        )
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
        "name": "决策路径的取值器写死 0.5（绕过唯一读取口径）",
        "file": TRADING_CENTER_PY,
        "old": "        value, why = read_macro_liquidity_signal()\n",
        "new": "        value, why = 0.5, ''\n",
    },
    {
        "name": "内核不把宏观流动性喂给 Manas（信号到家门口又放下）",
        "file": OS_KERNEL_PY,
        "old": '            macro_signal=market_state.get("macro_liquidity_signal", 0.5) if market_state else 0.5,\n',
        "new": "            macro_signal=0.5,\n",
        "count": 2,
    },
    {
        "name": "展示路径的取值器写死 0.5（历史实锤：regime_score 恒 0.0）",
        "file": MANAS_MANAGER_PY,
        "old": "        value, why = read_macro_liquidity_signal()\n",
        "new": "        value, why = 0.5, ''\n",
    },
    {
        "name": "展示路径不把 macro_signal 递给 Manas（整段去掉）",
        "file": MANAS_MANAGER_PY,
        "old": "        kwargs = dict(inputs)\n"
               "        macro_signal = self._get_macro_signal()\n"
               "        if macro_signal is not None:\n"
               '            kwargs["macro_signal"] = macro_signal\n',
        "new": "        kwargs = dict(inputs)\n",
    },
    {
        "name": "展示路径去掉 None 护栏（取不到就往引擎传 None）",
        "file": MANAS_MANAGER_PY,
        "old": "        if macro_signal is not None:\n",
        "new": "        if True:\n",
    },
    {
        "name": "唯一读取口径不再读 QueryState 的真值（拿常量顶替）",
        "file": MACRO_LIQ_PY,
        "old": "    value = getattr(query_state, MACRO_LIQUIDITY_KEY, None)\n",
        "new": "    value = NEUTRAL_MACRO_SIGNAL\n",
    },
]


def _all_checks() -> list:
    return (
        check_trading_center_wiring()
        + check_os_kernel_consumes()
        + check_single_source_reader()
        + check_manager_wiring()
        + check_getter_behavior()
        + check_process_signal_market_state()
        + check_manager_behavior()
    )


def _reload():
    """注入了哪个模块就要重载哪个（漏一个 → 注入不生效 → 假绿）。"""
    for name in (
        "deva.naja.attention.kernel.macro_liquidity",
        "deva.naja.attention.kernel.manas_manager",
        "deva.naja.attention.orchestration.trading_center",
    ):
        try:
            importlib.reload(importlib.import_module(name))
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
    print("✅ 宏观流动性接线守卫全绿（接线 / 唯一读取口径 / None 护栏 / 内核两路消费 / 两条路径同源 / 取值器与端到端行为）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
