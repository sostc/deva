#!/usr/bin/env python3
"""守卫：做 T 常驻守望与「一份目标 → 一组守望」的派生。

为什么单独一个守卫
==================
用户原话（2026-10-14）：「他终归是要 40% 的仓位……一个是守望一个机会
把它加仓加到 40%；还有一个是守望做 T 的机会……这个做 t 的守望应该是
**持续一直存在**的，一直在等待机会来买卖」。

这一句把长期配置拆成了**两层**，而分层最容易出的错是「两层没接上」：
目标层写好了，派生层没挂 —— 页面上只看到孤零零一条「定期回顾」，
而用户真正关心的「还差多少没补、做 T 在等什么」一个都看不见。
不报错，只是**什么都不发生**。正是本仓库头号病理。

四条硬纪律（守卫盯的就是它们）
==============================
1. **常驻 ≠ 无限期**：做 T 守望必须有观察窗口（``window_seconds``），
   缺了抛 :class:`MissingSettlementPoint`。「一直存在」是靠
   「每期很短 + 不断重挂」表达的，不是靠没有终点。
2. **抓到才续，撤下不续**：问过一次（无论批不批）→ 结算成 ``reached``
   → 立刻重挂；人工撤下（``abandoned``）**不许复活**。
3. **没人去问不许算抓到**：``granted=None`` 是链路断了，
   把它记成「这期问过了」是假成功 —— 守望必须继续挂着等。
4. **锚定只做一次**：目标未设定时默认锚定当前持仓，锚定后**不再随
   做 T 浮动**。否则卖一次 T 目标就少一块，缺口永远算不出来。

跑法
====
    python3 scripts/verify/verify_rotation_watch.py
    python3 scripts/verify/verify_rotation_watch.py --strict
    python3 scripts/verify/verify_rotation_watch.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import deva.naja.watch as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WATCH_DIR = ROOT / "deva" / "naja" / "watch"
BANDIT_DIR = ROOT / "deva" / "naja" / "bandit"

ROTATION_PY = WATCH_DIR / "rotation.py"
ALLOC_PY = WATCH_DIR / "allocation.py"
WATCH_PY = WATCH_DIR / "watch.py"
REGISTRY_PY = WATCH_DIR / "registry.py"
DESK_PY = WATCH_DIR / "desk.py"
UI_PY = WATCH_DIR / "ui.py"
RUNNER_PY = BANDIT_DIR / "intent_runner.py"

#: ❗**写死**的判定基准：守卫不许读被测模块的常量 ——
#: 否则注入把阈值改掉时守卫跟着变，用例照样绿。
CONFIDENCE_CAP = 0.75


# ─────────────────────────────────────────────────────────────
# 静态规则
# ─────────────────────────────────────────────────────────────

REQUIRED_RULES = [
    ("rotation.py", r"^class RotationIntent", "缺少 RotationIntent 类"),
    ("rotation.py", r"T_SIDES", "缺少做 T 方向枚举"),
    ("rotation.py", r'"sell_t"', "缺少卖 T 方向（先卖后买回）"),
    ("rotation.py", r'"buy_t"', "缺少买 T 方向（先买后卖回）"),
    ("rotation.py", r'"repay"', "缺少回购方向（欠着的份额要还）"),
    ("rotation.py", r"MissingSettlementPoint",
     "❗常驻守望也必须有观察窗口（常驻 ≠ 无限期）"),
    ("rotation.py", r"clamp_confidence", "意愿强度必须走封顶"),
    ("rotation.py", r"direction.*above|above",
     "❗卖 T 必须是「高于锚才卖」（涨过头=要跌），搞反了变追涨杀跌"),

    ("watch.py", r"standing", "❗守望缺少 standing 标志（做 T 无法表达）"),
    ("watch.py", r"self\.recurring and self\.standing",
     "❗recurring 与 standing 必须互斥（续期时机冲突）"),
    ("watch.py", r"if self\.standing and granted is not None",
     "❗常驻守望必须区分「真被问过」与「没人去问」—— 后者不许结算"),

    ("registry.py", r"standing", "❗renew 必须认得 standing 守望"),
    ("registry.py", r"w\.settlement == Settlement\.ABANDONED",
     "❗常驻守望撤下后不许被续期复活"),

    ("allocation.py", r"def anchor_if_needed", "缺少默认锚定入口"),
    ("allocation.py", r"def derive_watches", "缺少派生入口"),
    ("allocation.py", r"def derive_gap_objective", "缺少补缺口守望目标"),
    ("allocation.py", r"def with_anchor", "缺少锚定留痕"),
    ("allocation.py", r"anchor_shares", "缺少锚定份额字段"),
    ("allocation.py", r"anchor_source", "❗锚定必须记来源（人拍板 vs 默认锚持仓）"),

    ("desk.py", r"watch\.acknowledge\(None",
     "❗没接执行器时必须传 None（传 False 会把没人领的票记成「问过了」）"),

    ("ui.py", r"_derived_html", "❗页面缺少「旗下的守望」这一列"),
    ("ui.py", r"常驻", "❗页面必须标出常驻守望（读法与一次性守望不同）"),

    ("intent_runner.py", r"def sync_allocations", "❗缺少派生守望同步"),
    ("intent_runner.py", r"def holdings_snapshot", "缺少持仓快照读取"),
    ("intent_runner.py", r"DEFAULT_SYNC_SECONDS", "❗派生同步必须周期性自证"),
]

FORBIDDEN_RULES = [
    # ❗做 T 守望的 signal_type 必须让决策中心认得出来：
    # side_from_signal_type 只认 BUY/SELL，传别的会归成 none，
    # 意愿权重白算 —— 而这恰恰不报错。
    ("rotation.py", r'"signal_type":\s*"TRIM"',
     "❗signal_type 不能是 TRIM（决策中心只认 BUY/SELL）"),
    # 页面上不许出现**下单调用**。
    # ❗只匹配调用而不是「下单」二字：说明文档里写「这里没有任何下单按钮」
    # 是必要的自证，把它也禁掉等于逼着删掉纪律说明。
    ("ui.py", r"place_order\s*\(|submit_order\s*\(|execute_order\s*\(",
     "❗守望台页面出现下单调用 —— 守望台只等和问，不碰账户"),
]


# ─────────────────────────────────────────────────────────────
# 行为用例
# ─────────────────────────────────────────────────────────────

def _desk(asker=None):
    box = {"raw": {"action_type": "act_carefully", "manas_score": 0.7,
                   "timestamp": 1000.0}}
    return W.WatchDesk(
        lens=W.ManasLens(provider=lambda: box["raw"]),
        quote_fn=lambda c: None, asker=asker, heartbeat_sec=0.0,
    ), box


def behavior_checks() -> list:
    f: list = []
    R = W.RotationIntent
    A = W.Allocation

    # ① 三种方向都能构造，且归一化
    for side in ("sell_t", "buy_t", "repay"):
        try:
            r1 = R("qqq", "us", t_side=side)
        except Exception as e:  # noqa: BLE001
            f.append(f"① 方向 {side} 构造失败：{type(e).__name__}: {e}")
            continue
        if r1.code != "QQQ" or r1.market != "US":
            f.append(f"① 方向 {side} 的代码/市场没归一化")
        if r1.t_side != side:
            f.append(f"① 方向 {side} 没存住")
    if not R("QQQ", "US", t_side="repay").is_debt:
        f.append("① repay 必须被标记为债务（不是机会）")
    if R("QQQ", "US", t_side="sell_t").is_debt:
        f.append("① sell_t 不该被当成债务")

    # ② 方向认不出必须抛（不静默兜底）
    try:
        R("QQQ", "US", t_side="moon")
        f.append("② ❗认不出的做 T 方向被静默接受了")
    except ValueError:
        pass

    # ③ ❗常驻 ≠ 无限期：窗口为 0 必须抛
    try:
        R("QQQ", "US", window_seconds=0)
        f.append("③ ❗窗口为 0 也能登记 —— 等于造了一个无限期守望")
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ != "MissingSettlementPoint":
            f.append(f"③ 抛的异常类型不对：{type(e).__name__}")

    # ④ 封顶：传 100 也拿不到 1.0
    if float(R("QQQ", "US", confidence=100).confidence) > CONFIDENCE_CAP + 1e-9:
        f.append("④ ❗做 T 守望的意愿强度没封顶（能拖成放行键）")

    # ⑤ signal_type 必须让决策中心认得：卖 T→SELL、买 T→BUY、回购→BUY
    from deva.naja.watch.rotation import to_objective as rot_obj

    st_sell = rot_obj(R("QQQ", "US", t_side="sell_t")).params.get("signal_type")
    st_buy = rot_obj(R("QQQ", "US", t_side="buy_t")).params.get("signal_type")
    st_repay = rot_obj(R("QQQ", "US", t_side="repay")).params.get("signal_type")
    if st_sell != "SELL":
        f.append(f"⑤ ❗卖 T 的 signal_type 应为 SELL，实际 {st_sell!r}")
    if st_buy != "BUY":
        f.append(f"⑤ ❗买 T 的 signal_type 应为 BUY，实际 {st_buy!r}")
    if st_repay != "BUY":
        f.append(f"⑤ ❗回购的 signal_type 应为 BUY，实际 {st_repay!r}")

    # ⑥ ★常驻守望：问过一次 → 结算成 reached → 立刻重挂
    desk6, _ = _desk(asker=lambda o, c, s: (True, "放行"))
    w6 = W.declare_rotation(desk6.registry, R("QQQ", "US", t_side="sell_t"),
                            now=6000.0)
    if not w6.standing:
        f.append("⑥ ❗做 T 守望不是常驻（standing=False）")
    if w6.recurring:
        f.append("⑥ ❗做 T 守望不该同时是循环（续期时机冲突）")
    w6.acknowledge(True, "放行", now=6001.0)
    if w6.settlement is None or w6.settlement.value != "reached":
        f.append(f"⑥ ❗问过一次后没结算成 reached：{w6.settlement}")
    before_armed = w6.armed_at
    desk6.registry.renew(now=6002.0)
    if w6.state.value != "armed":
        f.append(f"⑥ ❗问完之后没重新挂起（state={w6.state.value}）")
    if w6.armed_at <= before_armed:
        f.append("⑥ ❗arm 没重置 armed_at（下一轮立刻又到期）")
    if w6.cycles < 1:
        f.append("⑥ 期数没加")

    # ⑦ ★没人去问 → 不许结算成「这期抓到了」（假成功）
    desk7, _ = _desk()
    w7 = W.declare_rotation(desk7.registry, R("QQQ", "US", t_side="buy_t"),
                            now=7000.0)
    w7.record_ask(None, "没人去问", now=7001.0)
    w7.acknowledge(None, "没人去问", now=7001.0)
    if w7.settlement is not None:
        f.append(f"⑦ ❗没人去问却被记成 {w7.settlement.value}（假成功）")

    # ⑧ ★撤下是真终止：abandoned 不许被续期复活
    desk8, _ = _desk()
    w8 = W.declare_rotation(desk8.registry, R("QQQ", "US", t_side="sell_t"),
                            now=8000.0)
    w8.settle("abandoned", "人工撤下", now=8001.0)
    desk8.registry.renew(now=8002.0)
    if w8.state.value != "settled":
        f.append(f"⑧ ❗撤下的常驻守望被续期复活了（state={w8.state.value}）")

    # ⑨ 到期（没轮到）也要能续 —— 常驻就是「一直等下一次」
    desk9, _ = _desk()
    w9 = W.declare_rotation(desk9.registry,
                            R("QQQ", "US", t_side="sell_t",
                              window_seconds=60.0),
                            now=9000.0)
    desk9.registry.due(9100.0, settle=True)
    if w9.settlement is None or w9.settlement.value != "expired":
        f.append(f"⑨ ❗到期没结算：{w9.settlement}")
    desk9.registry.renew(9101.0)
    if w9.state.value != "armed":
        f.append("⑨ ❗到期之后没重新挂起（常驻守望断了）")

    # ⑩ ★锚定：目标未设定 → 默认锚定当前持仓
    a10 = A("QQQ", "US", name="纳指ETF")
    if a10.target_set:
        f.append("⑩ 新建配置不该自带目标")
    a10b, newly = W.anchor_if_needed(a10, 900.0, now=10000.0)
    if not newly:
        f.append("⑩ ❗目标未设定时没有锚定当前持仓")
    if not a10b.target_set:
        f.append("⑩ 锚定之后仍判定为目标未设定")
    if float(a10b.anchor_shares or 0) != 900.0:
        f.append(f"⑩ 锚定份额不对：{a10b.anchor_shares}")
    if a10b.anchor_source != "holdings":
        f.append(f"⑩ ❗锚定来源没留痕：{a10b.anchor_source!r}")

    # ⑪ ★锚定只做一次：目标不随做 T 浮动
    a11, again = W.anchor_if_needed(a10b, 880.0, now=11000.0)
    if again:
        f.append("⑪ ❗已锚定的又被重新锚了一次")
    if float(a11.anchor_shares or 0) != 900.0:
        f.append(f"⑪ ❗目标被自己的操作拖着走：{a11.anchor_shares}（卖 T 后掉到 880）")

    # ⑫ ★锚不上就如实说锚不上，❗不拿 0 顶替
    a12, anchored = W.anchor_if_needed(A("QQQ", "US"), 0.0, now=12000.0)
    if anchored or a12.target_set:
        f.append("⑫ ❗持仓为 0 时被锚成「目标 0 份」（空仓≠目标是空仓）")
    a12b, anchored2 = W.anchor_if_needed(A("QQQ", "US"), None, now=12000.0)
    if anchored2 or a12b.target_set:
        f.append("⑫ ❗取不到持仓时被锚定（读不到≠0）")

    # ⑬ 目标没定 → 算不出缺口（❗None 不是 0）
    a13 = A("QQQ", "US")
    if a13.target_shares() is not None:
        f.append("⑬ ❗目标没定时 target_shares 应返回 None，实际有值")
    if a13.gap_shares(100.0) is not None:
        f.append("⑬ ❗目标没定时 gap_shares 应返回 None —— "
                 "返回 0 会被下游读成「已达标」")

    # ⑭ 锚定后缺口算得出来
    a14 = A("QQQ", "US").with_anchor(900.0, now=14000.0, source="user")
    if a14.gap_shares(800.0) != 100.0:
        f.append(f"⑭ 缺口算错：{a14.gap_shares(800.0)}")
    if a14.gap_shares(900.0) != 0.0:
        f.append("⑭ 已到位时缺口应为 0")
    if a14.gap_shares(950.0) != 0.0:
        f.append("⑭ ❗超额持有算出了负缺口")

    # ⑮ ★派生：有持仓 → 卖 T + 买 T；有缺口 → 补缺口
    a15 = A("QQQ", "US").with_anchor(900.0, now=15000.0, source="holdings")
    specs15 = W.derive_watches(a15, 800.0)
    roles15 = sorted(str(s.get("role")) for s in specs15)
    if roles15 != ["buy_t", "gap", "sell_t"]:
        f.append(f"⑮ ❗派生守望组不对：{roles15}（应为 gap + 卖T + 买T）")
    for s in specs15:
        if s.get("role") == "gap":
            if not s.get("recurring"):
                f.append("⑮ 补缺口守望应是循环（每期看看还差多少）")
            if s.get("standing"):
                f.append("⑮ ❗补缺口守望不该是常驻（补满就该不挂）")
        else:
            if not s.get("standing"):
                f.append("⑮ ❗做 T 守望必须是常驻（一直等下一次机会）")
            if s.get("recurring"):
                f.append("⑮ ❗做 T 守望不该是循环（等回顾周期太慢）")

    # ⑯ ★空仓不派生做 T（搓的是已有持仓的价差）
    a16 = A("QQQ", "US").with_anchor(900.0, now=16000.0, source="user")
    specs16 = W.derive_watches(a16, 0.0)
    if any(s.get("role") in ("sell_t", "buy_t") for s in specs16):
        f.append("⑯ ❗空仓也派生了做 T 守望（没持仓搓什么价差）")

    # ⑰ 已到位 → 不挂补缺口守望
    specs17 = W.derive_watches(a16, 900.0)
    if any(s.get("role") == "gap" for s in specs17):
        f.append("⑰ ❗已到位还挂着补缺口守望（造出一条无事可做的假守望）")

    # ⑱ 派生守望必须带 alloc_id —— 否则页面上只剩散落的「卖 T」
    for s in W.derive_watches(a15, 800.0):
        if not (s["objective"].params or {}).get("alloc_id"):
            f.append(f"⑱ ❗派生守望 {s['objective'].id} 没带 alloc_id，"
                     "挂不回它的目标")

    # ⑲ ★同步**：已挂的守望只更新参数，绝不重建**
    import deva.naja.bandit.intent_runner as ir

    runner19 = ir.IntentRunner(enabled=False)
    spec19 = W.derive_watches(a15, 800.0)[0]
    if not runner19._ensure_watch(spec19):
        f.append("⑲ 首次挂载应返回 True")
    w19 = runner19.desk.registry.get(spec19["objective"].id)
    w19.asked, w19.scans = 7, 42
    if runner19._ensure_watch(spec19):
        f.append("⑲ ❗二次同步又重建了守望（历史上演：统计被抹掉）")
    w19b = runner19.desk.registry.get(spec19["objective"].id)
    if w19b.asked != 7 or w19b.scans != 42:
        f.append(f"⑲ ❗统计被抹掉了：asked={w19b.asked} scans={w19b.scans}")

    # ⑳ ★撤下要分清「补到了」与「没持仓了」
    runner20 = ir.IntentRunner(enabled=False)
    a20 = A("QQQ", "US").with_anchor(900.0, now=20000.0, source="user")
    for s in W.derive_watches(a20, 800.0):
        runner20._ensure_watch(s)
    import time as _time

    n20 = runner20._retire_stale(a20, set(), _time.time())
    if n20 != 3:
        f.append(f"⑳ ❗撤下数量不对：{n20}（3 个派生守望都该撤）")
    gap_w = runner20.desk.registry.get("gap:US:QQQ")
    rot_w = runner20.desk.registry.get("rotation:US:QQQ:sell_t")
    if gap_w is None or gap_w.settlement is None:
        f.append("⑳ 缺口守望没结算")
    elif gap_w.settlement.value != "reached":
        f.append(f"⑳ ❗缺口守望撤下应记成 reached（补到目标了），"
                 f"实际 {gap_w.settlement.value}")
    if rot_w is None or rot_w.settlement is None:
        f.append("⑳ 做 T 守望没结算")
    elif rot_w.settlement.value != "abandoned":
        f.append(f"⑳ ❗做 T 守望撤下应记成 abandoned（没持仓了），"
                 f"实际 {rot_w.settlement.value}")

    # ㉑ UI：派生守望不许混进一次性意向区（同一件事两处显示会显示成两个数字）
    runner21 = ir.IntentRunner(enabled=False)
    for s in W.derive_watches(a15, 800.0):
        runner21._ensure_watch(s)
    import deva.naja.watch.ui as ui_mod

    ui_mod.put_buttons = lambda *a, **k: "<操作>"
    try:
        rows21 = ui_mod._watch_rows(runner21.desk, 21000.0)
    except Exception as e:  # noqa: BLE001
        f.append(f"㉑ 页面渲染抛异常：{type(e).__name__}: {e}")
        rows21 = []
    if rows21:
        f.append(f"㉑ ❗派生守望混进了一次性意向区（{len(rows21)} 行）")

    # ㉒ UI：长期配置区必须列出旗下的守望，且标出「常驻」
    arow = A("QQQ", "US").with_anchor(900.0, now=22000.0, source="user")
    runner22 = ir.IntentRunner(enabled=False)
    for s in W.derive_watches(arow, 800.0):
        runner22._ensure_watch(s)
    try:
        html22 = ui_mod._derived_html(
            runner22.desk, "allocation:US:QQQ", 22000.0, 800.0
        )
    except Exception as e:  # noqa: BLE001
        f.append(f"㉒ 派生守望渲染抛异常：{type(e).__name__}: {e}")
        html22 = ""
    for word in ("补缺口", "卖 T", "买 T", "常驻"):
        if word not in html22:
            f.append(f"㉒ ❗「旗下的守望」缺「{word}」")

    # ㉓ UI：目标未设定且没持仓 → 必须说清楚原因，❗不许写成「已到位」
    empty23 = ui_mod._derived_html(runner22.desk, "allocation:US:ZZZ",
                                   23000.0, 0.0)
    if "已到位" in empty23:
        f.append("㉓ ❗没持仓且目标未定，却显示「已到位」（合法的空掩盖真问题）")

    # ㉔ 落盘：锚定必须写回清单（只改内存的话重启就丢）
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "allocations.json"
        a24 = A("QQQ", "US").with_anchor(900.0, now=24000.0, source="holdings")
        ir.upsert_allocation(a24, p)
        row24 = json.loads(p.read_text(encoding="utf-8"))[0]
        if row24.get("anchor_shares") != 900.0:
            f.append(f"㉔ ❗锚定份额没写回清单：{row24.get('anchor_shares')}")
        if row24.get("anchor_source") != "holdings":
            f.append("㉔ ❗锚定来源没写回清单")
        # 读回来还得认得
        back = ir.load_allocations(p)
        if not back or not back[0].target_set:
            f.append("㉔ ❗锚定读回来就丢了（重启即回到未设定）")

    return f


# ─────────────────────────────────────────────────────────────
# 静态检查
# ─────────────────────────────────────────────────────────────

def static_checks() -> list:
    f: list = []
    files = {
        "rotation.py": ROTATION_PY, "allocation.py": ALLOC_PY,
        "watch.py": WATCH_PY, "registry.py": REGISTRY_PY,
        "desk.py": DESK_PY, "ui.py": UI_PY,
        "intent_runner.py": RUNNER_PY,
    }
    for name, pattern, why in REQUIRED_RULES:
        path = files.get(name)
        if path is None or not path.exists():
            f.append(f"文件不存在：{name}")
            continue
        import re

        if not re.search(pattern, path.read_text(encoding="utf-8"), re.M):
            f.append(f"[{name}] {why}")

    for name, pattern, why in FORBIDDEN_RULES:
        path = files.get(name)
        if path is None or not path.exists():
            continue
        import re

        if re.search(pattern, path.read_text(encoding="utf-8")):
            f.append(f"[{name}] {why}")
    return f


# ─────────────────────────────────────────────────────────────
# 负向注入
# ─────────────────────────────────────────────────────────────

INJECTIONS = [
    {
        "name": "❗常驻守望做成一次性（做成一次就消失）",
        "file": ROTATION_PY,
        "old": "        standing=True,\n    )",
        "new": "        standing=False,\n    )",
        "count": -1,
    },
    {
        "name": "❗没人去问也算「这期抓到了」（假成功）",
        "file": WATCH_PY,
        "old": "        if self.standing and granted is not None:",
        "new": "        if self.standing:",
        "count": -1,
    },
    {
        "name": "❗撤下的常驻守望被续期复活",
        "file": REGISTRY_PY,
        "old": "                if w.settlement == Settlement.ABANDONED:\n                    # 撤下是真终止 —— 常驻守望也必须能被真正停掉\n                    continue",
        "new": "                if False:\n                    pass",
        "count": -1,
    },
    {
        "name": "❗允许无限期的做 T 守望（窗口可为 0）",
        "file": ROTATION_PY,
        "old": "        if wait <= 0:",
        "new": "        if False:",
        "count": -1,
    },
    {
        "name": "❗recurring 与 standing 互斥校验被拿掉（续期时机无法判定）",
        "file": WATCH_PY,
        "old": "        if self.recurring and self.standing:",
        "new": "        if False:",
        "count": -1,
    },
    {
        "name": "❗目标被自己的操作拖着走（每轮重新锚定当前持仓）",
        "file": ALLOC_PY,
        "old": "    if alloc.target_set:\n        return alloc, False",
        "new": "    if False:\n        return alloc, False",
        "count": -1,
    },
    {
        "name": "❗取不到持仓时拿 0 顶替锚定（空仓≠目标是空仓）",
        "file": ALLOC_PY,
        "old": "    if committed_shares is None or float(committed_shares) <= 0:\n        return alloc, False",
        "new": "    return alloc.with_anchor(0.0, now=now, source='holdings'), True",
        "count": -1,
    },
    {
        "name": "❗空仓也派生做 T 守望（没持仓搓什么价差）",
        "file": ALLOC_PY,
        "old": "        if shares <= 0:\n            return []",
        "new": "        if False:\n            return []",
        "count": -1,
    },
    {
        "name": "❗同步时重建守望（把「问过几次」一笔勾销）",
        "file": RUNNER_PY,
        # ❗锚点必须带上面那行注释：`_ensure_allocation_watch` 里有**一模一样**
        # 的三行，只匹配三行会替换到另一个函数去 —— 那条注入永远抓不到。
        "old": (
            "        # ❗只改参数与说明，不动统计 —— 重建会把守望的历史抹掉\n"
            "        watch.objective.params.update(obj.params)\n"
            "        watch.objective.note = obj.note\n"
            "        return False"
        ),
        "new": (
            "        reg.declare(obj, spec['opportunities'], "
            "recurring=bool(spec.get('recurring')), "
            "standing=bool(spec.get('standing')))\n"
            "        return False"
        ),
        "count": 1,
    },
    {
        "name": "❗补到目标被记成「没等到」（那天恰恰最该庆祝）",
        "file": RUNNER_PY,
        "old": '                watch.settle("reached", "已补到目标，缺口守望完成", now=now)',
        "new": '                watch.settle("expired", "已补到目标，缺口守望完成", now=now)',
        "count": -1,
    },
    {
        "name": "❗卖 T 的 signal_type 写成 BUY（决策中心归成 none，权重白算）",
        "file": ROTATION_PY,
        "old": '"signal_type": "SELL" if intent.t_side == "sell_t" else "BUY",',
        "new": '"signal_type": "BUY",',
        "count": -1,
    },
    {
        "name": "❗没人领的票被记成「问过了」（acknowledge 传 False 而非 None）",
        "file": DESK_PY,
        "old": "            watch.acknowledge(None, reason, now=now)",
        "new": "            watch.acknowledge(False, reason, now=now)",
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
    path.write_text(
        text.replace(old, new) if n == -1 else text.replace(old, new, n),
        encoding="utf-8",
    )
    return True


def _reload_all() -> None:
    """按依赖序重载。顺序错了会造出两份类，每条注入都「被捕获」的假绿。"""
    for mod in ("deva.naja.watch.manas_lens", "deva.naja.watch.objective",
                "deva.naja.watch.opportunity", "deva.naja.watch.watch",
                "deva.naja.watch.registry", "deva.naja.watch.intent",
                "deva.naja.watch.rotation", "deva.naja.watch.allocation",
                "deva.naja.watch.desk", "deva.naja.watch.ui",
                "deva.naja.watch", "deva.naja.bandit.intent_runner"):
        importlib.reload(importlib.import_module(mod))
    global W
    W = importlib.reload(W)


def exercise_injections() -> int:
    print("\n=== 负向注入：故意改坏代码，验证守卫不是摆设 ===")
    caught = 0

    # ❗自证第零步：什么都不改先重载一遍，用例必须仍然全绿。
    _reload_all()
    baseline = behavior_checks() + static_checks()
    if baseline:
        print("   ❌ 纯 reload 下用例就不绿了（守卫自己的 bug）：")
        for x in baseline[:5]:
            print("      -", x)
        return 1
    print("   ✅ 基线：纯 reload 后用例仍然全绿")

    for inj in INJECTIONS:
        backup = inj["file"].read_text(encoding="utf-8")
        try:
            if not _apply(inj):
                print(f"   ⚠️ 跳过（锚点缺失）：{inj['name']}")
                continue
            try:
                _reload_all()
                bad = behavior_checks() + static_checks()
            except (SyntaxError, IndentationError) as e:
                # ❗注入把代码改得连语法都不通 —— 那是**用例**的 bug，
                # 不能当成「产品被抓到」，也不能让整个脚本崩掉停在这里。
                print(f"   ⚠️ 注入破坏了语法（用例 bug，需修锚点）：{inj['name']}")
                print(f"      → {e}")
                continue
            if bad:
                print(f"   ✅ 被捕获：{inj['name']}")
                print(f"      → {bad[0][:72]}")
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

    failures = static_checks() + behavior_checks()
    if failures:
        print("❌ 做 T 常驻守望守卫发现 %d 项问题：" % len(failures))
        for x in failures:
            print("   -", x)
        return 1
    print("✅ 做 T 常驻守望守卫全绿"
          "（常驻≠无限期 · 抓到才续 · 没人问不算 · 锚定只一次）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
