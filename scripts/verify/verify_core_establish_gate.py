#!/usr/bin/env python3
"""守卫：底仓补仓必须先过大环境闸门（决策中心 / Manas）。

守什么
------
2026-10-14 用户问「买的时候不考虑大环境背景吗」。核查结果是**完全没接**：

* ``TRotationRunner._maybe_establish_core`` 直接 ``open_position``，
  整个做 T 包里此前没有 ``manas`` 这个词；
* ``adaptive_cycle`` 里那份 manas 上下文喂的是 ``scanner=None``，
  而 ``RegimeEngine`` 在 scanner 为空时 trend/diffusion 都返回 0.0 → **假接**；
* 目标份额 = 总资产 × alloc ÷ **现价**，分母是价格 →
  **越跌目标越大，逆风反而触发买入**。

本守卫守的是新增的 :mod:`deva.naja.bandit.core_establish_gate` 四条语义，
以及 runner 里「下单前先问闸门」这段接线。

❗反方向用例（记忆里的硬规则：「一项保护会掩盖另一项缺失」）
------------------------------------------------------
光证明「被拦住」是**假绿**——一个永远返回 False 的闸门也能通过。所以每条
保护都配一条反方向用例：

* hold 拦得住 → 但**收盘兜底必须放行**（否则策略永久空转，这是另一种死法）；
* 链路不可用不买 → 但**必须喊出来**（否则故障伪装成「行情不好，在观望」）；
* size_hint 会缩量 → 但**不能缩到 0**（否则放行了却不动，等于换姿势死锁）；
* 闸门关得上 → 但**必须有关得上的反向保证**（disabled 时维持旧行为，可回滚）。

用法
----
    python scripts/verify/verify_core_establish_gate.py            # 全量
    python scripts/verify/verify_core_establish_gate.py --strict   # CI 用
    python scripts/verify/verify_core_establish_gate.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import logging
import re
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from deva.naja.bandit.core_establish_gate import (  # noqa: E402
    CoreEstablishGate,
    EstablishmentVerdict,
    VerdictUnavailable,
)
from deva.naja.bandit.core_holdings import CoreHoldingSpec  # noqa: E402
from deva.naja.bandit.core_position import CorePositionLedger  # noqa: E402

GATE_PY = REPO / "deva/naja/bandit/core_establish_gate.py"
RUNNER_PY = REPO / "deva/naja/bandit/t_rotation_runner.py"


# ─────────────────────────────────────────────────────────────
REQUIRED_RULES = [
    (GATE_PY, r"def ask_decision_center",
     "缺少向决策中心请教的函数（闸门必须真去问，不能自己拍）"),
    (GATE_PY, r"process_strategy_signal",
     "必须走公开入口 process_strategy_signal（自带 DecisionPlan 留痕，事后可查）"),
    (GATE_PY, r"raise VerdictUnavailable",
     "拿不到结论必须抛专用异常，不能折叠成「否决」"),
    (GATE_PY, r"[\"']unavailable[\"']",
     "必须区分「链路不可用」与「Manas 否决」（ast.unparse 输出单引号，别写死双引号）"),
    (GATE_PY, r"[\"']deadline[\"']", "必须有收盘兜底来源标记（否则策略可能永久空转）"),
    (GATE_PY, r"minutes_to_close is not None",
     "距收盘未知时不能触发兜底（不知道还有多久就别急着买）"),
    (GATE_PY, r"self\._cache", "缺少缓存（30 秒一次全跑决策管线会把 journal 灌满）"),
    (GATE_PY, r"fail_streak", "缺少连续失败计数（闸门故障会退化为静默）"),
    (RUNNER_PY, r"self\._gate\.evaluate", "runner 下单前没问闸门"),
    (RUNNER_PY, r"if not verdict\.allowed", "runner 没有在闸门否决时收手"),
    (RUNNER_PY, r"max\(lot, wanted\)", "缩量必须有 1 手地板（否则放行了却什么都买不到）"),
    (RUNNER_PY, r"src == [\"']unavailable[\"']",
     "不可用与失利必须分开处理（混起来会让故障伪装成策略观望）"),
    (RUNNER_PY, r"\[TRotationRunner\] 🚧",
     "🚧 不可用分支缺失 —— 闸门故障没人喊"),
]

FORBIDDEN_RULES = [
    (RUNNER_PY, r"except VerdictUnavailable[^\n]*\n\s*pass",
     "❌ 不可用被吞成 pass —— 闸门故障会伪装成策略观望"),
]


# ─────────────────────────────────────────────────────────────
# 行为：闸门本体
# ─────────────────────────────────────────────────────────────
def _spec() -> CoreHoldingSpec:
    return CoreHoldingSpec(
        code="588200", bus_code="sh588200", name="科创芯片ETF嘉实",
        market="CN", target_shares=0.0, round_lot=100.0, alloc_pct=40.0,
    )


def _ok(size_hint: float = 1.0, action_type: str = "act_fully") -> dict:
    return {
        "approved": True, "action_type": action_type,
        "manas_score": 0.62, "regime_score": 0.15, "timing_score": 0.71,
        "final_confidence": 0.73,
        "plan": {"size_hint": size_hint, "gate_reason": ""},
    }


def _hold(reason: str = "Manas建议观望: 保持hold") -> dict:
    return {
        "approved": False, "action_type": "hold",
        "manas_score": 0.301, "regime_score": -0.42, "timing_score": 0.31,
        "final_confidence": 0.5,
        "plan": {"size_hint": 0.0, "gate_reason": reason},
    }


def _provider(raw, calls=None):
    """返回一个记录调用次数的 provider。"""
    calls = calls if calls is not None else []

    def _p(spec, price):
        calls.append((spec.code, price))
        if isinstance(raw, Exception):
            raise raw
        return raw

    return _p


def _gate(raw, *, ttl=300.0, deadline=30.0, clock=None, enabled=True, calls=None):
    return CoreEstablishGate(
        _provider(raw, calls), ttl=ttl, deadline_min=deadline,
        clock=clock, enabled=enabled,
    )


def behaviour_checks() -> list:
    failures = []

    # reload：注入改的是磁盘源码，模块可能已在内存里被污染
    import deva.naja.bandit.core_establish_gate as gate_mod

    gate_mod = importlib.reload(gate_mod)
    CoreEstablishGate_ = gate_mod.CoreEstablishGate

    # ① Manas hold + 盘中 → 不买
    v = CoreEstablishGate_(_provider(_hold()), deadline_min=30.0).evaluate(
        _spec(), 0.968, 200.0
    )
    if v.allowed or v.source != "decision_center":
        failures.append("① hold 且盘中：必须拦下且来源标记为 decision_center")
    if v.regime_score >= 0:
        failures.append("① regime 逆风值没有透出到裁定里（日志无法自证）")

    # ② act_fully → 放行，且带上 Quantitative size_hint
    v = CoreEstablishGate_(_provider(_ok(0.84))).evaluate(_spec(), 0.968, 200.0)
    if not v.allowed or abs(v.size_hint - 0.84) > 1e-9:
        failures.append("② 放行时 size_hint 必须来自 DecisionPlan")
    if v.degraded:
        failures.append("② 正常放行不该被标记为 degraded")

    # ③【反方向】hold 但已到收盘窗口 → 必须放行（否则策略永久空转）
    v = CoreEstablishGate_(_provider(_hold()), deadline_min=30.0).evaluate(
        _spec(), 0.968, 12.0
    )
    if not v.allowed or v.source != "deadline":
        failures.append("③ 收盘兜底必须放行并标记 source=deadline")
    if v.size_hint <= 0:
        failures.append("③ 兜底必须给正的最小额度，否则底仓永远建不出来")
    if not v.degraded:
        failures.append("③ 兜底不是正常放行，必须标记 degraded 供事后区分")

    # ④【反方向】还在 60 分钟外 → 不许兜底（兜底窗口不能被放宽到全场）
    v = CoreEstablishGate_(_provider(_hold()), deadline_min=30.0).evaluate(
        _spec(), 0.968, 60.0
    )
    if v.allowed:
        failures.append("④ 距收盘 60 分钟不应触发兜底")

    # ⑤ 距收盘未知（None）→ 不兜底，继续等
    v = CoreEstablishGate_(_provider(_hold()), deadline_min=30.0).evaluate(
        _spec(), 0.968, None
    )
    if v.allowed:
        failures.append("⑤ minutes_to_close 未知时不能触发兜底")

    # ⑥ 链路不可用 → 不买 + source=unavailable + fail_streak 累加
    # ❗异常类必须**取重载后的**：脚本顶部 import 的那个 identity 已经过期，
    # 拿它raise的话，闸门里的 `except VerdictUnavailable` 认不出来 → 用例假红。
    boom = gate_mod.VerdictUnavailable("boom")
    g = CoreEstablishGate_(
        _provider(boom), deadline_min=30.0
    )
    v = g.evaluate(_spec(), 0.968, 5.0)
    if v.allowed or v.source != "unavailable" or not v.degraded:
        failures.append("⑥ 链路不可用必须拦下并标记为 unavailable/degraded")
    if g.fail_streak != 1:
        failures.append("⑥ fail_streak 未累加 —— 连续故障无法被发现")
    # 拿到一次有效结论后必须归零
    g2 = CoreEstablishGate_(_provider(_ok(1.0)), deadline_min=30.0)
    v2 = g2.evaluate(_spec(), 0.968, 200.0)
    if not v2.allowed or g2.fail_streak != 0:
        failures.append("⑥ 恢复后 fail_streak 未归零")

    # ⑦ provider 返回非 dict → 按不可用处理，不能偷偷放行
    v = CoreEstablishGate_(_provider(None)).evaluate(_spec(), 0.968, 200.0)
    if v.allowed or v.source != "unavailable":
        failures.append("⑦ provider 返回 None 必须按不可用处理")

    # ⑧ 缓存：TTL 内不重复问（否则每 30 秒跑一次完整管线）
    calls = []
    clk = [1000.0]
    g = CoreEstablishGate_(
        _provider(_ok(1.0), calls), ttl=300.0, clock=lambda: clk[0],
    )
    g.evaluate(_spec(), 0.968, 200.0)
    clk[0] += 60.0
    g.evaluate(_spec(), 0.968, 200.0)
    if len(calls) != 1:
        failures.append(f"⑧ TTL 内重复请求（调用 {len(calls)} 次）")
    clk[0] += 400.0
    g.evaluate(_spec(), 0.968, 200.0)
    if len(calls) != 2:
        failures.append(f"⑧ 超出 TTL 未重新请求（调用 {len(calls)} 次）")

    # ⑨ 缓存按标的隔离：三个市场的裁决不能互相覆盖
    calls = []
    g = CoreEstablishGate_(_provider(_ok(1.0), calls), ttl=300.0)
    base = _spec()
    for code in ("588200", "00700", "QQQ"):
        g.evaluate(replace(base, code=code), 1.0, 200.0)
    if len(calls) != 3:
        failures.append("⑨ 缓存未按标的隔离 —— 三个市场会共用同一份裁决")

    # ⑩【反方向】闸门关闭时维持旧行为（回滚开关必须真的能用）
    v = CoreEstablishGate_(
        _provider(VerdictUnavailable("boom")), enabled=False,
    ).evaluate(_spec(), 0.968, 200.0)
    if not v.allowed or v.source != "disabled":
        failures.append("⑩ NAJA_T_ESTABLISH_GATE=0 时应放行并标记 disabled")

    # ⑯ 否决分支没有 manas/regime 字段时，必须是 None 而不是默认 0.0。
    # ❗「0.0」会被读成「Manas 打了 0 分」，而真实含义是「上游没给」——
    # 这正是本仓库反复踩的「default 假值」坑。
    bare = {"approved": False, "action_type": "hold",
            "plan": {"size_hint": 0.0, "gate_reason": "策略不自信"}}
    v = CoreEstablishGate_(_provider(bare)).evaluate(_spec(), 0.968, 200.0)
    if v.manas_score is not None or v.regime_score is not None:
        failures.append("⑯ 上游没给的分量必须记为 None，不能用 0.0 伪装成打了 0 分")
    if "manas=0.00" in v.reason:
        failures.append("⑯ 日志不得把缺失值打印成 0.00（假数据比缺失更毒）")
    if "策略不自信" not in v.reason:
        failures.append("⑯ 门理由必须透出（否则排查只能看到「没放行」三个字）")
    # 有值时照常带上
    v2 = CoreEstablishGate_(_provider(_hold())).evaluate(_spec(), 0.968, 200.0)
    if v2.manas_score is None or abs(v2.manas_score - 0.301) > 1e-9:
        failures.append("⑯ 上游给了真实分量时必须原样透出")

    return failures


# ─────────────────────────────────────────────────────────────
# 行为：runner 接线（真的会下单的那条路）
# ─────────────────────────────────────────────────────────────
class _FakePF:
    def __init__(self, open_result=None):
        self.open_calls = []
        self._open_result = open_result

    def get_summary(self):
        return {
            "total_capital": 1_000_000.0, "available_capital": 1_000_000.0,
            "used_capital": 0.0, "total_value": 1_000_000.0,
            "position_count": 0, "currency": "CNY",
        }

    def get_all_positions(self, status=None):
        return []

    def in_flight_buy_orders(self, code):
        return []

    def open_position(self, **kw):
        self.open_calls.append(kw)
        return self._open_result


class _FakeEngine:
    def register_target(self, code, target, name=None, note=None):
        pass


class _Rec(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append((record.levelname, record.getMessage()))


def _run_establish(verdict, *, pf_total=1_000_000.0):
    """跑一次完整的补仓决策，返回 (pf, 记录的日志)。"""
    from deva.naja.bandit.t_rotation_runner import TRotationRunner

    spec = CoreHoldingSpec(
        code="588200", bus_code="sh588200", name="科创芯片ETF嘉实",
        market="CN", target_shares=0.0, round_lot=100.0, alloc_pct=40.0,
    )
    pf = _FakePF()
    runner = TRotationRunner(specs=[spec], establish_missing=True,
                             poll_seconds=30.0, establish_gate=_StubGate(verdict))
    runner._portfolios = {"CN": pf}
    runner._engines = {"CN": _FakeEngine()}
    runner._portfolio = pf
    ledger = CorePositionLedger()
    ledger._save = lambda *a, **k: None
    runner._ledger = ledger

    handler = _Rec()
    logger = logging.getLogger("deva.naja.bandit.t_rotation_runner")
    prev = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        now = time.time()
        quote = SimpleNamespace(current=0.986, prev_close=0.98)
        runner._maybe_establish_core(
            spec, quote, now, now - 600.0, time.strftime("%Y-%m-%d")
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)
    return pf, handler.records


class _StubGate:
    def __init__(self, verdict):
        self.verdict = verdict

    def evaluate(self, spec, price, minutes_to_close):
        return self.verdict


def wiring_checks() -> list:
    failures = []

    hold = EstablishmentVerdict(
        allowed=False, source="decision_center", action_type="hold",
        reason="Manas 闸门未放行 档位=hold manas=0.301",
    )
    # ⑪ hold → 一笔单都不许下
    pf, records = _run_establish(hold)
    if pf.open_calls:
        failures.append(f"⑪ Manas hold 却下了 {len(pf.open_calls)} 笔单")
    if not any("等待时机" in m for _, m in records):
        failures.append("⑪ 被否掉必须留下可见日志，否则无法区分「没买」与「没跑」")

    # ⑫【反方向】不可用 → 不下单，且必须是 WARNING
    blind = EstablishmentVerdict(
        allowed=False, source="unavailable", degraded=True,
        reason="决策中心不可用，本轮不建仓（boom）",
    )
    pf, records = _run_establish(blind)
    if pf.open_calls:
        failures.append("⑫ 决策中心看不清时不许下单")
    # 断言必须**认准这一条**：整个跑动过程中还有别的 WARNING（额度、资金不足…），
    # 只判断「有没有 WARNING」会被别处的告警掩盖 —— 注入改动照样溜过去（假绿）。
    if not any(lv == "WARNING" and "决策中心不可用" in m for lv, m in records):
        failures.append(
            "⑫ 链路不可用必须 WARNING —— 降级成 INFO 会让故障伪装成策略观望"
        )

    # ⑬ act_fully（hint=1）→ 正常把缺口打满
    ok1 = EstablishmentVerdict(
        allowed=True, source="decision_center", action_type="act_fully",
        size_hint=1.0,
    )
    pf, _ = _run_establish(ok1)
    if not pf.open_calls:
        failures.append("⑬ 放行却没下单")
    else:
        qty = pf.open_calls[0].get("quantity") or pf.open_calls[0].get("qty")
        if qty is None:
            # open_position 的实参名可能是别的，退而验证它确实带了数量
            failures.append("⑬ 无法从 open_position 实参里读到数量")
        else:
            target_shares = int(1_000_000.0 * 0.4 / 0.986 / 100) * 100
            if qty < target_shares * 0.999:
                failures.append(f"⑬ hint=1 时应打满缺口，实买 {qty}")

    # ⑭【反方向】act_minimally（hint=0.25）→ 缩量，但**不能缩到 0**
    ok25 = EstablishmentVerdict(
        allowed=True, source="decision_center", action_type="act_minimally",
        size_hint=0.25,
    )
    pf, _ = _run_establish(ok25)
    if not pf.open_calls:
        failures.append("⑭ 缩量档必须仍然下单（归零=换姿势死锁）")
    else:
        kw = pf.open_calls[0]
        qty = kw.get("quantity") or kw.get("qty")
        full = 405600.0
        if not (0 < qty < full * 0.5):
            failures.append(f"⑭ hint=0.25 应显著缩量，实买 {qty}")

    # ⑮ 收盘兜底（source=deadline）→ 按最小档至少买入，不能空转
    deadline = EstablishmentVerdict(
        allowed=True, source="deadline", degraded=True,
        action_type="hold", size_hint=0.25,
    )
    pf, _ = _run_establish(deadline)
    if not pf.open_calls:
        failures.append("⑮ 收盘兜底必须真的补进去，否则底仓永远到不了位")

    return failures


# ─────────────────────────────────────────────────────────────
# 静态 / 注入
# ─────────────────────────────────────────────────────────────
def code_only(path: Path) -> str:
    """剥掉注释与 docstring 后的代码文本。

    ❗必须扫这个而不是原始文本：注释里写着「应区别 unavailable 与否决」
    这类**说明性**文字，搜原文会把正确实现判成违规（假红）。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def static_checks() -> list:
    failures = []
    cache = {}

    def code_of(path: Path) -> str:
        if path not in cache:
            try:
                cache[path] = code_only(path)
            except SyntaxError:
                cache[path] = path.read_text(encoding="utf-8")
        return cache[path]

    for path, pattern, why in REQUIRED_RULES:
        if not path.exists():
            failures.append(f"文件不存在: {path}")
            continue
        if not re.search(pattern, code_of(path)):
            failures.append(f"[静态] {path.name}: {why}")
    for path, pattern, why in FORBIDDEN_RULES:
        if not path.exists():
            continue
        if re.search(pattern, code_of(path)):
            failures.append(f"[禁止] {path.name}: {why}")
    return failures


INJECTIONS = [
    {
        "name": "闸门判定结果被忽略（hold 也照买）",
        "file": RUNNER_PY,
        "old": "        if not verdict.allowed:",
        "new": "        if False:",
        "count": -1,
    },
    {
        "name": "hold 也被当成放行",
        "file": GATE_PY,
        "old": "        if should_act and size_hint > 0:",
        "new": "        if size_hint >= 0:",
        "count": -1,
    },
    {
        "name": "链路不可用偷偷放行",
        "file": GATE_PY,
        "old": '            allowed=False, source="unavailable", degraded=True, reason=reason,',
        "new": '            allowed=True, source="unavailable", degraded=True, reason=reason,',
        "count": -1,
    },
    {
        "name": "删掉收盘兜底（策略永久空转）",
        "file": GATE_PY,
        "old": 'source="deadline", degraded=True,',
        "new": 'source="decision_center", degraded=False,',
        "count": -1,
    },
    {
        "name": "缩量没有地板（放行了却买不到）",
        "file": RUNNER_PY,
        "old": "            qty = min(qty, max(lot, wanted))",
        "new": "            qty = min(qty, wanted)",
        "count": -1,
    },
    {
        "name": "不可用降级成 INFO（故障伪装成观望）",
        "file": RUNNER_PY,
        "old": "            log.warning(\n                f\"[TRotationRunner] 🚧 {spec.name}({spec.code}) {reason} —— \"",
        "new": "            log.info(\n                f\"[TRotationRunner] 🚧 {spec.name}({spec.code}) {reason} —— \"",
        "count": -1,
    },
    {
        "name": "缺失分量用 0.0 兜底（假数据伪装成 Manas 打 0 分）",
        "file": GATE_PY,
        "old": "    if key not in raw:\n        return None",
        "new": "    if key not in raw:\n        return 0.0",
        "count": -1,
    },
    {
        "name": "缓存跨标的串味",
        "file": GATE_PY,
        "old": "        hit = self._cache.get(spec.code)",
        "new": "        hit = self._cache.get('__all__')",
        "count": -1,
    },
]


def apply_injection(inj) -> bool:
    path: Path = inj["file"]
    text = path.read_text(encoding="utf-8")
    if inj["old"] not in text:
        print(f"  ⚠️  注入锚点不存在，跳过：{inj['name']}")
        return False
    path.write_text(
        text.replace(inj["old"], inj["new"], inj.get("count", 1)),
        encoding="utf-8",
    )
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        path.write_text(text, encoding="utf-8")
        print(f"  ⚠️  注入后语法非法（无效用例），已还原：{inj['name']} → {e}")
        return False
    return True


def run_injections() -> int:
    caught = 0
    for inj in INJECTIONS:
        original = inj["file"].read_text(encoding="utf-8")
        print(f"\n注入：{inj['name']}")
        if not apply_injection(inj):
            continue
        try:
            found = static_checks() + behaviour_checks() + wiring_checks()
        except Exception as e:
            found = [f"守卫自身抛异常: {e}"]
        finally:
            inj["file"].write_text(original, encoding="utf-8")
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            for f in found[:3]:
                print(f"       · {f[:110]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")
        if inj["file"].read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            inj["file"].write_text(original, encoding="utf-8")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获")
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = static_checks() + behaviour_checks() + wiring_checks()
    if failures:
        print("❌ 底仓大环境闸门守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ 底仓大环境闸门守卫全绿（静态 + 闸门本体 + runner 接线）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
