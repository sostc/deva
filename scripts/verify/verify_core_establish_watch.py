#!/usr/bin/env python3
"""守卫：守望系统（有了目标，等待机会）。

守什么
------
2026-10-14 用户提的：「等待机会是个很好的概念……能否做成一个系统」。
核查结果是此前**根本没有「等待」这个对象** —— 每 30 秒轮询一次，判断为
「不能」就什么都不做也不记录。缺三样：**没记录我在等什么 / 没声明等到什么
才动手 / 没度量等了多久算异常**。

新增的 :mod:`deva.naja.watch` 就是补这三样。本守卫守它的五条纪律
外加 1 号守望（``core_establish_watch``）与 runner 的接线。

❗反方向用例（「一项保护会掩盖另一项缺失」）
-----------------------------------------
只证明「守得住」是**假绿** —— 一个永远沉默的守望同样能通过。所以每条保护都
配一条反向用例：

* 机会未成立不问 → 但**环境判据看不清时也不能当成没机会**（None ≠ []）；
* 环境升级才问 → 但**沉默太久必须强制问**（防「接好了但从不放行」死锁）；
* 守望会等 → 但**到期必须结算**（无限等待和线程死掉长得一模一样）；
* 守望会记录 → 但**不能落盘**（避免瞅一眼就把生产数据写了）。

用法
----
    python scripts/verify/verify_core_establish_watch.py
    python scripts/verify/verify_core_establish_watch.py --strict
    python scripts/verify/verify_core_establish_watch.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import logging
import re
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import deva.naja.watch as W  # noqa: E402

WATCH_DIR = REPO / "deva/naja/watch"
OBJ_PY = WATCH_DIR / "objective.py"
OPP_PY = WATCH_DIR / "opportunity.py"
WATCH_PY = WATCH_DIR / "watch.py"
REG_PY = WATCH_DIR / "registry.py"
CW_PY = REPO / "deva/naja/bandit/core_establish_watch.py"
RUNNER_PY = REPO / "deva/naja/bandit/t_rotation_runner.py"


REQUIRED_RULES = [
    ("objective.py", r"raise MissingSettlementPoint",
     "缺结算点必须抛异常（不允许存在可以无限期等下去的守望）"),
    ("objective.py", r"max_wait_seconds is None or float\(self\.max_wait_seconds\) <= 0",
     "结算点必须在构造时校验，而不是运行期兜底"),
    ("opportunity.py", r"def unclear", "三态判据缺少 unknown 构造器"),
    ("opportunity.py", r"raise TypeError",
     "❗三态必须拒绝退化成布尔（bool(hit) 会把 unknown 当成 False）"),
    ("opportunity.py", r"return OpportunityHit\.unclear",
     "行情/锚缺失必须返回 unknown，不能折叠成未成立"),
    ("opportunity.py", r"raise UnknownOpportunityKind",
     "机会类型认不出来必须喊（静态 getattr 兜底那类事故的教训）"),
    # ❗用 [^)] 跳过引号：ast.unparse 输出的是**单引号**，写死双引号必然匹配不上
    ("opportunity.py", r"return OpportunityHit\.no\([^)]*不触发",
     "距收盘未知时不得触发最后通牒"),
    ("watch.py", r"max_silence_seconds",
     "缺少活性保证：环境判据依赖问过才有答案，不催会死锁"),
    ("watch.py", r"bootstrap: bool = False",
     "缺少 bootstrap 开关：环境型守望首次不问就永远拿不到 action_type"),
    ("watch.py", r"need_seed = self\.bootstrap and \(?not self\._bootstrapped\)?",
     "bootstrap 没有真正参与疏醒判断（仍然是死代码）"),
    ("watch.py", r"def settle", "守望必须有显式结算"),
    ("registry.py", r"def due", "守望台缺结算点扫描（到期会无声消失）"),
    ("registry.py", r"def heartbeat", "守望台缺自证心跳（分不清在等还是死了）"),
    ("registry.py", r"contexts\.get\(watch\.watch_id\)",
     "查不到观测面要按缺失处理（记 unknown，不是当成没机会）"),
    ("core_establish_watch.py", r"last_action_type",
     "1 号守望的环境信号必须取自缓存，不能每轮重跑决策管线"),
    ("core_establish_watch.py", r"NAJA_T_ESTABLISH_WATCH", "缺回滚开关"),
    # ❗ast.unparse 输出的是**单引号**，正则里两种引号都要认
    ("core_establish_watch.py", r"ENV_SOURCE = [\"']NAJA_T_ESTABLISH_WATCH_SOURCE[\"']",
     "缺 Manas / 缓存信号源回滚开关"),
    ("core_establish_watch.py", r"manas_window",
     "1 号守望的默认环境信号须自 Manas 数（是存残）"),
    ("t_rotation_runner.py", r"self\._establish_watch\.peek",
     "runner 没在问决策中心之前先问守望"),
    ("t_rotation_runner.py", r"if not ask:", "runner 没有在守望认为不值得问时收手"),
]

FORBIDDEN_RULES = [
    # ❗守望是纯运行期视图，落盘就是事故（字典那次是「构造即写盘」这么来的）
    ("watch.py", r"\bopen\s*\(", "守望不该做文件 IO（纯内存视图）"),
    ("watch.py", r"_save|write_text|json\.dump|to_csv",
     "守望不许落盘（重启后重新 declare 即可）"),
    ("registry.py", r"\bopen\s*\(", "守望台不该做文件 IO（纯内存视图）"),
    ("registry.py", r"_save|write_text|json\.dump|to_csv",
     "守望台不许落盘（纯内存视图，重启后重新 declare）"),
    ("objective.py", r"\bopen\s*\(", "目标不该做文件 IO"),
    # 守望层绝对不许自己下单 —— 它只有「该不该问」的资格，没有放行权
    ("watch.py", r"open_position|place_order|\.buy\(",
     "守望层不许下单（机会 ≠ 放行）"),
    ("registry.py", r"open_position|place_order|\.buy\(",
     "守望台不许下单（机会 ≠ 放行）"),
    ("core_establish_watch.py", r"open_position|place_order|\.buy\(",
     "1 号守望不许下单（它只回答要不要去问）"),
]


# ─────────────────────────────────────────────────────────────
# 行为用例
# ─────────────────────────────────────────────────────────────
def _mk_registry():
    return W.WatchRegistry(heartbeat_sec=0)


def _obj(**kw):
    base = dict(
        id="w1", kind="establish_core", subject="588200", market="CN",
        max_wait_seconds=3600.0, note="底仓补到 40%",
    )
    base.update(kw)
    return W.Objective(**base)


def _ctx(now=1000.0, price=0.99, anchor=1.0, minutes_to_close=200.0,
         action_type=None):
    return W.WatchContext(
        now=now, price=price, anchor=anchor,
        minutes_to_close=minutes_to_close, action_type=action_type,
    )


def behavior_checks() -> list:
    f = []

    # ① 无结算点 → 必须报错
    try:
        W.Objective(id="x", kind="establish_core", subject="588200")
        f.append("① 缺结算点竟然没报错（会允许无限期守望）")
    except W.MissingSettlementPoint:
        pass

    # ② 三态拒绝退化成布尔
    hit = W.OpportunityHit.unclear("行情没取到")
    try:
        bool(hit)
        f.append("② 三态被当成布尔用了 —— unknown 会被静默当 False")
    except TypeError:
        pass

    reg = _mk_registry()
    # max_silence 设到极大：这一段只测机会判据本身，
    # 免得 liveness 兜底混进来把「机会不成立」伪装成「值得问」。
    reg.declare(_obj(), [
        {"kind": "price_deviation", "pct": 1.0, "direction": "below"},
        {"kind": "deadline_window", "minutes": 30.0},
    ], now=1000.0, max_silence_seconds=1e9)

    # ③ unknown ≠ no：没有观测面 → 不放行且标记为看不清
    s = reg.scan({}, now=1100.0)[0]
    if s.should_ask or not s.unknown:
        f.append("③ 无观测面应不放行且标记 unknown（None ≠ []）")

    # ④ 价格机会成立 → 值得问
    s = reg.scan({"w1": _ctx(price=0.90, now=1200.0)}, now=1200.0)[0]
    if not s.should_ask or "price_deviation" not in s.fired_kinds:
        f.append("④ 价格跌破锚应当触发守望")

    # ⑤ 都不到 → 安静
    s = reg.scan({"w1": _ctx(price=0.999, minutes_to_close=200.0,
                             now=1250.0)}, now=1250.0)[0]
    if s.should_ask:
        f.append("⑤ 机会未成立时不该去问")

    # ⑥ 距收盘 → 触发
    s = reg.scan({"w1": _ctx(price=0.999, minutes_to_close=10.0,
                             now=1300.0)}, now=1300.0)[0]
    if not s.should_ask or "deadline_window" not in s.fired_kinds:
        f.append("⑥ 距收盘进入窗口应当触发（最后通牒）")

    # ⑦【反方向】锚缺失 → 看不清，不是没机会
    ctx7 = W.WatchContext(now=1350.0, price=0.90, anchor=None,
                          minutes_to_close=200.0)
    s = reg.scan({"w1": ctx7}, now=1350.0)[0]
    if not s.unknown:
        f.append("⑦ 锚缺失必须报 unknown（折成未成立会让 serendipity 被当成耐心）")

    # ⑧ 到期必须能结算成终态
    reg2 = _mk_registry()
    reg2.declare(_obj(max_wait_seconds=60.0), [
        {"kind": "price_deviation", "pct": 50.0, "direction": "below"},
    ], now=0.0)
    due = reg2.due(now=61.0, settle=True)
    if len(due) != 1:
        f.append("⑧ 到期守望没被扫出来（会无声消失）")
    else:
        w = due[0]
        if w.state != W.WatchState.SETTLED or w.settlement.value != "expired":
            f.append("⑧ 到期没有显式结算成 expired")
        s = reg2.scan({}, now=62.0)[0]
        if s.should_ask:
            f.append("⑧ 已结算的守望不该再提出询问")

    # ⑨ 活性：长期失效的环境下仍会被催醒
    reg3 = _mk_registry()
    reg3.declare(_obj(id="stuck", max_wait_seconds=360000.0), [
        {"kind": "environment_upgrade", "min_action": "act_minimally"},
    ], now=0.0, bootstrap=True)
    w3 = reg3.get("stuck")
    blind = W.WatchContext(now=0.0, price=1.0, anchor=1.0,
                           minutes_to_close=200.0, action_type=None)
    first = reg3.scan({"stuck": blind}, now=0.0)[0]
    if not first.should_ask:
        f.append("⑨ 首次扫描必须问（否则永远拿不到第一个 action_type → 死锁）")
    mid = reg3.scan({"stuck": blind}, now=599.0)[0]
    if mid.should_ask:
        f.append("⑨ 沉默未超时时不应重复催问")
    later = reg3.scan({"stuck": blind}, now=600.0)[0]
    if not later.should_ask:
        f.append("⑨ 沉默达上限必须强制再问（活性保证失效＝死锁）")
    del w3

    # ⑩ 环境升级 → 触发（正面）
    reg4 = _mk_registry()
    reg4.declare(_obj(id="env", max_wait_seconds=3600.0), [
        {"kind": "environment_upgrade", "min_action": "act_minimally"},
    ], now=0.0, bootstrap=True)
    # 先 bootstrap 一次建立基线（这次问是应该的）
    reg4.scan({"env": W.WatchContext(now=0.5, price=1.0, anchor=1.0,
                                     minutes_to_close=200.0, action_type="hold")},
              now=0.5)
    cold = reg4.scan(
        {"env": W.WatchContext(now=1.0, price=1.0, anchor=1.0,
                               minutes_to_close=200.0, action_type="hold")},
        now=1.0,
    )[0]
    if cold.should_ask:
        f.append("⑩ hold 档位不该再触发（基线已建立，环境没变就该继续等）")
    warm = reg4.scan(
        {"env": W.WatchContext(now=2.0, price=1.0, anchor=1.0,
                               minutes_to_close=200.0,
                               action_type="act_carefully")},
        now=2.0,
    )[0]
    if not warm.should_ask:
        f.append("⑩ 环境升到 act_carefully 应当触发守望")

    # ⑪ 未知机会类型必须喊
    try:
        W.build_opportunity({"kind": "maybe_some_day"})
        f.append("⑪ 未知机会类型竟然被接受了")
    except W.UnknownOpportunityKind:
        pass

    # ⑫ 自证心跳能产出文本且带上「在等什么」
    text = reg4.heartbeat(now=3.0, force=True)
    if not text or "💓" not in text:
        f.append("⑫ 心跳没产出自报文本")
    elif "等待" not in text and "等=" not in text:
        f.append("⑫ 心跳没说明在等什么")
    return f


# ─────────────────────────────────────────────────────────────
# 1 号守望接线
# ─────────────────────────────────────────────────────────────
def wiring_checks() -> list:
    f = []
    from deva.naja.bandit.core_establish_watch import (  # noqa: E402
        CoreEstablishWatch, watch_id_for,
    )
    from deva.naja.watch import ManasLens  # noqa: E402

    if watch_id_for("588200") != "core_establish:588200":
        f.append("① 守望 id 形态变了，日志与守卫都会对不上")

    class _Gate:
        enabled = True
        _deadline_min = 30.0

        def __init__(self):
            self._action = {}

        def last_action_type(self, code):
            return self._action.get(code)

    gate = _Gate()
    spec = SimpleNamespace(
        code="588200", bus_code="sh588200", name="科创芯片ETF嘉实",
        market="CN", alloc_pct=40.0, round_lot=100.0,
    )

    # 默认信号源：Manas 读数。用辑时钟不是墙上时钟 —— 时间戳与 now
    # 必须是同一把尺子，否则 age 会混算出数。
    raw = {"action_type": "hold", "manas_score": 0.30, "timestamp": 0.0}
    lens = ManasLens(provider=lambda: raw)
    cw = CoreEstablishWatch(gate, lens=lens)
    if cw.source != "manas":
        f.append("① 认号应是 Manas 数不是存残")

    # ② 守望着，环境知 / hold → 首次会（bootstrap 基线）
    cw.ensure(spec, now=0.0)
    ctx = cw.context_for(spec, now=0.0, price=0.99, anchor=1.0,
                         minutes_to_close=200.0)
    ask, _s = cw.peek(spec, ctx, now=0.0)
    if not ask:
        f.append("② 1 号守望次当问（bootstrap 一份线）")

    # ③ Manas 行动门级应当去
    raw["action_type"] = "act_carefully"
    raw["timestamp"] = 1.0
    ctx = cw.context_for(spec, now=1.0, price=0.99, anchor=1.0,
                         minutes_to_close=200.0)
    ask, _s = cw.peek(spec, ctx, now=1.0)
    if not ask:
        f.append("③ Manas 行动门级应当去")

    # ④ hold 且离收盘很远 → 不复
    raw["action_type"] = "hold"
    raw["timestamp"] = 100.0
    asked = 0
    for t in (100.0, 130.0, 160.0):
        ctx = cw.context_for(spec, now=t, price=0.99, anchor=1.0,
                             minutes_to_close=200.0)
        ask, _s = cw.peek(spec, ctx, now=t)
        asked += 1 if ask else 0
    if asked:
        f.append(f"④ Manas hold 且离盘时该复（问了 {asked} 次）")

    # ⑤【反方向】数期不放行，且须成不清
    #    新鲜比常毒拿份知道么时候算的位"现在机会"糟
    raw["action_type"] = "act_fully"
    raw["timestamp"] = 200.0 - 99999.0
    ctx = cw.context_for(spec, now=200.0, price=0.99, anchor=1.0,
                         minutes_to_close=200.0)
    ask, s = cw.peek(spec, ctx, now=200.0)
    if ask:
        f.append("⑤ 期 Manas 数该为会立（新鲜）")
    if s is not None and not s.unknown:
        f.append("⑤ 期数须成不清，是单成没会")

    # ⑥ 距盘入口必问
    raw["timestamp"] = 300.0
    ctx = cw.context_for(spec, now=300.0, price=0.99, anchor=1.0,
                         minutes_to_close=10.0)
    ask, _s = cw.peek(spec, ctx, now=300.0)
    if not ask:
        f.append("⑥ 距收盘入口当问（后牒）")

    # ⑦【行为】NAJA_T_ESTABLISH_WATCH_SOURCE=cache 能用存
    cw_cache = CoreEstablishWatch(gate, registry=None, source="cache")
    cw_cache.ensure(spec, now=0.0)
    gate._action["588200"] = "hold"
    ctx = cw_cache.context_for(spec, now=0.0, price=0.99, anchor=1.0,
                               minutes_to_close=200.0)
    ask, _s = cw_cache.peek(spec, ctx, now=0.0)
    if not ask:
        f.append("⑦ cache 源次 bootstrap（第一 action_type）")
    ctx = cw_cache.context_for(spec, now=1.0, price=0.99, anchor=1.0,
                               minutes_to_close=200.0)
    ask, _s = cw_cache.peek(spec, ctx, now=1.0)
    if ask:
        f.append("⑦ cache 源中是 hold，该复")
    gate._action["588200"] = "act_carefully"
    ctx = cw_cache.context_for(spec, now=2.0, price=0.99, anchor=1.0,
                               minutes_to_close=200.0)
    ask, _s = cw_cache.peek(spec, ctx, now=2.0)
    if not ask:
        f.append("⑦ cache 源级应再问")

    # ⑧【反方向】回滚关须用
    off = CoreEstablishWatch(gate, enabled=False)
    out = off.peek(spec, None, now=400.0)
    if out != (True, None):
        f.append("⑧ NAJA_T_ESTABLISH_WATCH=0 时应退回「每轮都问」的旧行为")

    # ⑨ 闸门自身闭，望并路
    class _OffGate(_Gate):
        enabled = False

    off2 = CoreEstablishWatch(_OffGate())
    if off2.enabled:
        f.append("⑨ 闸门闭守望并路（免辑裂）")
    return f


# ─────────────────────────────────────────────────────────────
def code_only(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
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

    lookup = {
        "objective.py": OBJ_PY, "opportunity.py": OPP_PY,
        "watch.py": WATCH_PY, "registry.py": REG_PY,
        "core_establish_watch.py": CW_PY,
        "t_rotation_runner.py": RUNNER_PY,
    }
    for name, pattern, why in REQUIRED_RULES:
        path = lookup.get(name)
        if path is None:
            failures.append(f"[静态] 未登记的 {name}")
            continue
        if not re.search(pattern, code_of(path)):
            failures.append(f"[静态] {name}: {why}")
    for name, pattern, why in FORBIDDEN_RULES:
        path = lookup.get(name)
        if path is None:
            continue
        if re.search(pattern, code_of(path)):
            failures.append(f"[禁止] {name}: {why}")
    return failures


INJECTIONS = [
    {
        "name": "缺结算点不再报错（允许无限期守望）",
        "file": OBJ_PY,
        "old": "        if self.max_wait_seconds is None or float(self.max_wait_seconds) <= 0:",
        "new": "        if False:",
        "count": -1,
    },
    {
        "name": "三态退化成布尔（unknown 会被当成 False）",
        "file": OPP_PY,
        "old": "    def __bool__(self) -> bool:",
        "new": "    def __boolx__(self) -> bool:",
        "count": -1,
    },
    {
        "name": "未知机会类型被静默放过",
        "file": OPP_PY,
        "old": "        raise UnknownOpportunityKind(\n            f\"未知机会类型 {kind!r}",
        "new": "        if True:\n            return DeadlineWindow(minutes=0.0001)  # 静默兜底\n        raise UnknownOpportunityKind(\n            f\"未知机会类型 {kind!r}",
        "count": -1,
    },
    {
        "name": "❗活性保证失效：bootstrap 判定被短路（环境型守望当天死锁）",
        "file": WATCH_PY,
        "old": "        need_seed = self.bootstrap and not self._bootstrapped",
        "new": "        need_seed = False",
        "count": -1,
    },
    {
        "name": "删掉沉默催问（环境判据失效时永不询问）",
        "file": WATCH_PY,
        "old": "        silence = now - self.last_prod_at",
        "new": "        silence = -1.0",
        "count": -1,
    },
    {
        "name": "到期不再结算（守望无声消失）",
        "file": REG_PY,
        "old": "        if settle:",
        "new": "        if False:",
        "count": -1,
    },
    {
        "name": "runner 不再问守望（守望被旁路）",
        "file": RUNNER_PY,
        "old": "        if not ask:",
        "new": "        if False:",
        "count": -1,
    },
    {
        "name": "1 号守望回滚开关失效（关不掉）",
        "file": CW_PY,
        "old": "        return self._enabled and bool(getattr(self.gate, \"enabled\", True))",
        "new": "        return True",
        "count": -1,
    },
]


def _apply(inj) -> bool:
    path: Path = inj["file"]
    text = path.read_text(encoding="utf-8")
    old, new = inj["old"], inj["new"]
    if old not in text:
        print(f"   ⚠️ 锚点不存在：{inj['name']}")
        return False
    n = inj.get("count", 1)
    path.write_text(text.replace(old, new) if n == -1 else text.replace(old, new, n),
                    encoding="utf-8")
    return True


def exercise_injections() -> int:
    print("\n=== 负向注入：故意改坏代码，验证守卫不是摆设 ===")
    caught = 0
    for inj in INJECTIONS:
        backup = inj["file"].read_text(encoding="utf-8")
        try:
            if not _apply(inj):
                print(f"   ⚠️ 跳过（锚点缺失，属于用例 bug 不是产品 bug）：{inj['name']}")
                continue
            # ❗必须 reload：模块早就在内存里了，不重载会拿到被污染的旧对象
            bad = []
            for mod in ("deva.naja.watch.objective", "deva.naja.watch.opportunity",
                        "deva.naja.watch.watch", "deva.naja.watch.registry",
                        "deva.naja.watch", "deva.naja.bandit.core_establish_watch",
                        "deva.naja.bandit.t_rotation_runner"):
                try:
                    importlib.reload(importlib.import_module(mod))
                except Exception:
                    pass
            global W
            W = importlib.reload(W)
            bad = behavior_checks() + wiring_checks() + static_checks()
            if bad:
                print(f"   ✅ 被捕获：{inj['name']}（{bad[0][:46]}）")
                caught += 1
            else:
                print(f"   ❌ 没抓到：{inj['name']}")
        finally:
            inj["file"].write_text(backup, encoding="utf-8")

    total = len(INJECTIONS)
    print(f"\n负向注入 {caught}/{total} 被捕获")
    return 0 if caught == total else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    a = ap.parse_args()
    logging.disable(logging.CRITICAL)

    if a.exercise_injections:
        return exercise_injections()

    failures = static_checks() + behavior_checks() + wiring_checks()
    if failures:
        print("❌ 守望系统守卫发现 %d 项问题：" % len(failures))
        for x in failures:
            print("   -", x)
        return 1
    print("✅ 守望系统守卫全绿（静态 + 守望本体 + 1号守望接线）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
