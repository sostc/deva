#!/usr/bin/env python3
"""守卫：守望台的**事件腿**（Manas 档位变化 + 交易时钟）。

为什么单独一个守卫
==================
用户原话（2026-10-14）：「这个『守望』算是一个执念……他应该是在 manas
里面有事件发生时自动去计算，而不应该是问询」。

守望原本只靠定时轮询活着，于是：

* Manas 档位变了它不知道，只能等下一轮轮询撞上；
* 开盘那一刻它正好躺在两次轮询之间，最该问的时刻反而没被问；
* 闭市后照样转，而闭市的现价是一份不动的快照。

这一层把「世界变了」直接接到守望的求值上。**最容易出的错不是报错，而是
什么都不发生** —— 事件源挂不上、签名对不上、异常被 debug 吞掉，守望都
只是「安静」，跟「没机会」长得一模一样。这正是本仓库头号病理。

❗实踩（写这个守卫之前就已经踩到）
----------------------------------
``MANAS_STATE_CHANGED`` 的通道、数据结构、订阅方**全都写好了**，唯独
生产者的调用把入参写成 ``data=``（发布函数实际叫 ``metadata``）→
TypeError → 被 ``except`` 里的 ``log.debug`` 吞掉 → **这条通道从来没
发出过一个事件**，而订阅方一直空转，谁也不知道。所以本守卫把「签名对不
对」和「不许吞异常」都钉成静态规则。

四条硬纪律（守卫盯的就是它们）
==============================
1. **事件腿不能替掉定时腿。** 纯事件驱动下「没有事件」与「链路断了」不可
   区分 —— 所以定时腿是观测设施，不是残留。守卫盯住 ``flush()`` 补做。
2. **每一次求值都要记 ``wake_reason``。** 否则事后无法回答「这个守望三天
   没问过，是没机会还是没人叫它」。
3. **订阅失败必须透出，回调绝不向外抛。**
4. **节流只延后、不取消。** 窗口内到达的唤醒要进 ``pending`` 等补做。

跑法
====
    python3 scripts/verify/verify_watch_awakener.py
    python3 scripts/verify/verify_watch_awakener.py --strict
    python3 scripts/verify/verify_watch_awakener.py --exercise-injections
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
KERNEL_DIR = ROOT / "deva" / "naja" / "attention" / "kernel"
EVENTS_DIR = ROOT / "deva" / "naja" / "events"

AWAK_PY = WATCH_DIR / "awakener.py"
DESK_PY = WATCH_DIR / "desk.py"
RUNNER_PY = BANDIT_DIR / "intent_runner.py"
MANAS_PY = KERNEL_DIR / "manas_engine.py"
COG_PY = EVENTS_DIR / "cognitive_bus.py"


# ─────────────────────────────────────────────────────────────
# 静态规则
# ─────────────────────────────────────────────────────────────

REQUIRED_RULES = [
    # -- 唤醒器本体 ----------------------------------------------------
    ("awakener.py", r"^class WatchAwakener", "缺少 WatchAwakener 类"),
    ("awakener.py", r"MANAS_STATE_CHANGED",
     "❗必须订阅 Manas 档位变化（否则守望永远只剩定时腿）"),
    ("awakener.py", r"TRADING_CLOCK_STREAM",
     "❗必须订阅交易时钟（开盘/收盘才叫得醒守望）"),
    ("awakener.py", r"wake_reason",
     "❗每次求值都要记被什么唤醒的（没它无法区分「没机会」与「没人叫」）"),
    ("awakener.py", r"self\.pending",
     "❗节流窗口内的唤醒必须进 pending 等补做（可以延后，不许消失）"),
    ("awakener.py", r"def flush", "❗缺少补做入口（合并掉的唤醒没人做）"),
    ("awakener.py", r"def quiet_suspicious",
     "❗事件腿沉默必须自证（「没变化」与「通道断了」长得一样）"),
    ("awakener.py", r"attach_errors",
     "❗订阅失败必须留原因（挂着 False 不说为什么 = 静默失效）"),
    ("awakener.py", r"exc_info=True",
     "❗回调异常必须带堆栈（光一句话事后没法查）"),
    ("awakener.py", r"def drain_tickets",
     "❗事件腿开出的票必须交给定时腿统计（否则「问过了但记 0 次」）"),
    ("awakener.py", r"CLOCK_WAKE_PHASES",
     "❗closed 时段不必叫醒守望（叫了也被闸门挡，只是噪音）"),

    # -- Manas 侧的生产者 ---------------------------------------------
    ("manas_engine.py", r"def _publish_action_type_change",
     "❗缺少档位变化的生产者（通道会一直空转）"),
    ("manas_engine.py", r"_published_action_type",
     "❗必须去重：每轮 compute 都发一次 = 把事件腿变回定时轮询"),
    ("manas_engine.py", r"metadata=state_data",
     "❗发布入参必须是 metadata（写成 data= 会 TypeError 且被吞掉）"),

    # -- 事件结构 ------------------------------------------------------
    ("cognitive_bus.py", r"def data\(",
     "❗CognitiveSignalEvent 必须给 metadata 一个 data 别名（订阅方按 "
     "event.data 读）"),

    # -- 守望台与运行器 ------------------------------------------------
    ("desk.py", r"wake_reason", "❗守望台必须接得住唤醒来源"),
    ("desk.py", r"wake_counts", "❗唤醒来源要分着计（看得出是哪条腿在起作用）"),
    ("desk.py", r"markets", "❗必须支持按市场求值（CN 开盘不必吵醒美股）"),
    ("intent_runner.py", r"_attach_awakener", "❗运行器没挂事件腿"),
    ("intent_runner.py", r"drain_tickets", "❗事件腿的票没并入统计"),
    ("intent_runner.py", r"self\._report_awakener\(",
     "❗唤醒器的自证必须有人调用（health_line 写了没人读 = 静默失效）"),
    ("awakener.py", r"被 %s 叫醒",
     "❗被事件叫醒必须留痕（否则事件腿有没有在起作用只能靠猜）"),
    # ❗要匹配**代码**而不是「bootstrap」这四个字：注释里也会提到它，
    # 光搜字样的话把 wake 那行删掉照样绿（静态扫描的老坑）。
    ("awakener.py", r'detail="bootstrap"',
     "❗挂上后必须 bootstrap 一次：首次档位变化发生在订阅之前，守望收不到"),
]

FORBIDDEN_RULES = [
    # ❗发布入参写 data= 是实踩过的坑：TypeError 被 except 吞掉 → 通道空转
    ("manas_engine.py", r"publish_cognitive_event\([^)]*\bdata=",
     "❗发布入参不能是 data=（实际叫 metadata，写错会 TypeError 并被吞）"),
    (("manas_engine.py"), r"发布状态变化事件失败.*log\.debug|"
     r"log\.debug\(.*发布状态变化事件失败",
     "❗发布失败不许只 debug（通道坏了会完全隐形）"),
    # ❗守望台与唤醒器都不许下单
    ("awakener.py", r"place_order\s*\(|submit_order\s*\(|execute_order\s*\(",
     "❗唤醒器出现下单调用 —— 它只负责叫醒，不碰账户"),
]


def static_checks() -> list:
    bad: list = []
    for fname, pat, why in REQUIRED_RULES:
        for base in (WATCH_DIR, BANDIT_DIR, KERNEL_DIR, EVENTS_DIR):
            p = base / fname
            if p.exists():
                break
        else:
            bad.append(f"{fname}: 文件不存在")
            continue
        import re
        if not re.search(pat, p.read_text(encoding="utf-8"), re.M):
            bad.append(f"{fname}: {why}")
    for fname, pat, why in FORBIDDEN_RULES:
        if isinstance(fname, tuple):
            fname = fname[0]
        for base in (WATCH_DIR, BANDIT_DIR, KERNEL_DIR, EVENTS_DIR):
            p = base / fname
            if p.exists():
                break
        else:
            continue
        import re
        if re.search(pat, p.read_text(encoding="utf-8"), re.M):
            bad.append(f"{fname}: {why}")
    return bad


# ─────────────────────────────────────────────────────────────
# 行为用例
# ─────────────────────────────────────────────────────────────

class _Spy:
    """假守望台：记录每一次求值是怎么被叫醒的。

    ❗``poll`` 必须返回**非空**的票：否则「事件腿的票有没有交出去统计」
    这条用例永远测不出来（取回空列表和被吞掉长得一样）。
    """

    def __init__(self, tickets=None):
        self.calls: list = []
        self.tickets = ["tk"] if tickets is None else list(tickets)

    def poll(self, now=None, wake_reason="", markets=None):
        self.calls.append((wake_reason, markets))
        return list(self.tickets)


def _awak(min_interval=10.0, t0=1000.0):
    from deva.naja.watch.awakener import WatchAwakener

    spy = _Spy()
    aw = WatchAwakener(spy, min_interval=min_interval, quiet_sec=1800.0,
                       clock=lambda: t0)
    return aw, spy


def _real_desk():
    box = {"raw": {"action_type": "act_carefully", "manas_score": 0.7,
                   "timestamp": 1000.0}}
    return W.WatchDesk(
        lens=W.ManasLens(provider=lambda: box["raw"]),
        quote_fn=lambda c: None, asker=lambda *a, **k: {"granted": False,
                                                        "reason": "测试"},
        heartbeat_sec=0.0,
    )


def behavior_checks() -> list:
    bad: list = []

    # 1 首次唤醒必须**立刻**求值（事件腿的价值就在「比定时腿早」）
    aw, spy = _awak()
    if not aw.wake("manas", detail="hold→act"):
        bad.append("首次唤醒没有求值 —— 事件腿等于没接")
    if not spy.calls or spy.calls[-1][0] != "manas":
        bad.append(f"求值没带上 wake_reason: {spy.calls}")

    # 2 节流窗口内**再**唤醒：不求值，但必须进 pending（不丢）
    aw2, spy2 = _awak()
    aw2.wake("manas")
    if aw2.wake("clock", market="CN"):
        bad.append("节流窗口内不该重复求值（否则事件密集时会按波动计费）")
    if "clock" not in aw2.pending:
        bad.append("❗被节流的唤醒没进 pending —— 事件被丢弃了")
    # 3 flush 太早 → 不做；够了 → 做掉并清空
    if aw2.flush(1001.0):
        bad.append("flush 不该在最小间隔内就求值")
    if not aw2.flush(1015.0):
        bad.append("flush 到了间隔却没补做 —— 合并的唤醒永远没人做")
    if aw2.pending:
        bad.append(f"flush 之后 pending 没清空: {aw2.pending}")

    # 4 closed 时段不叫醒（叫了也被闸门挡，只是噪音）
    aw3, spy3 = _awak(min_interval=0.0)
    aw3._on_clock_event({"market": "CN", "phase": "closed"})
    if spy3.calls:
        bad.append("closed 时段不该叫醒守望")

    # 5 trading 时段要叫醒，且**只叫对应市场**
    aw3._on_clock_event({"market": "CN", "phase": "trading"})
    if not spy3.calls or spy3.calls[-1][1] != {"CN"}:
        bad.append(f"时钟唤醒没限定市场: {spy3.calls}")

    # 6 phase 缺失：宁可多叫，但必须留痕（结构漂移的早期信号）
    aw4, spy4 = _awak(min_interval=0.0)
    aw4._on_clock_event({"market": "CN"})
    if not spy4.calls:
        bad.append("phase 认不出时也该唤醒（宁可多叫，不要漏掉开盘）")
    if aw4.clock_phase_unknown != 1:
        bad.append("❗phase 缺失没留痕 —— 时钟事件结构变了会静默退化")

    # 7 回调出错：不向外抛（会打断发布者），但**必须计数上报**
    aw5, _ = _awak()
    try:
        aw5._on_clock_event(object())
    except Exception as e:  # noqa: BLE001
        bad.append(f"回调把异常抛出去了，会打断发布者: {e}")
    # ❗光「不抛」不够：静默吞掉等于订阅侧故障隐形。造一个真会抛的场景。
    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    aw5.wake = _boom
    aw5._on_clock_event({"market": "CN", "phase": "trading"})
    if aw5.callback_errors != 1:
        bad.append(
            f"❗回调出错没上报（callback_errors={aw5.callback_errors}）"
            " —— 订阅侧故障会隐形"
        )

    # 8 事件腿沉默自证
    aw6, _ = _awak()
    aw6.attached["manas"] = True
    aw6.wake("manas")
    if aw6.quiet_suspicious(1010.0):
        bad.append("刚被叫醒就报可疑 —— 假警报")
    if not aw6.quiet_suspicious(1010.0 + 2000):
        bad.append("❗沉默超阈值却不报警 —— 通道断了没人知道")

    # 9 没 attach 过不许喊「事件源没挂上」（假警报比不报警更伤）
    aw7, _ = _awak()
    line = aw7.health_line()
    if line and "一个都没挂上" in line:
        bad.append(f"从未 attach 却报事件源没挂上: {line}")
    # 10 attach 全失败 → 必须喊
    aw7.attach_attempted = True
    aw7.attach_errors["manas"] = "boom"
    line2 = aw7.health_line()
    if not line2 or "一个都没挂上" not in line2:
        bad.append("❗订阅全失败却不喊 —— 守望退化成定时腿没人知道")

    # 11 事件腿开出的票必须**交得出去**，且取走后清空（不然统计两次）
    aw8, _ = _awak(min_interval=0.0)
    aw8.wake("manas")
    got = aw8.drain_tickets()
    if got != ["tk"]:
        bad.append(f"❗事件腿开出的票没交出去统计（拿到 {got}）"
                   " —— 会显示「问过 0 次」")
    if aw8.drain_tickets():
        bad.append("drain_tickets 取走之后没清空（票会被统计两次）")

    # 12 唤醒来源分着计
    aw9, _ = _awak(min_interval=0.0)
    aw9.wake("manas")
    aw9.wake("clock", market="US")
    if aw9.wake_counts.get("manas") != 1 or aw9.wake_counts.get("clock") != 1:
        bad.append(f"唤醒来源没分着计: {aw9.wake_counts}")

    # 13 真守望台：按市场过滤（❗要看「哪个守望被扫了」，只数跳过次数
    #    是分不出方向的 —— 搞反了同样会有守望被跳过）
    d = _real_desk()
    # ❗关掉市场时钟：用例不能依赖「跑的时候是几点」
    d.market_clock = None
    d.declare_intent(W.Intent(code="588200", market="CN", side="buy",
                              max_wait_seconds=1800))
    d.declare_intent(W.Intent(code="QQQ", market="US", side="buy",
                              max_wait_seconds=1800))
    ws = {w.objective.market: w for w in d.watches()}
    cn, us = ws["CN"], ws["US"]
    s_cn, s_us = cn.scans, us.scans
    d.poll(now=1000.0, wake_reason="clock", markets={"US"})
    if us.scans == s_us:
        bad.append("❗US 守望没被扫 —— 按市场求值把该扫的也过滤掉了")
    if cn.scans != s_cn:
        bad.append("❗CN 守望被扫了 —— 按市场求值没生效（CN 开盘不该吵美股）")
    if d.last_wake_reason != "clock" or d.wake_counts.get("clock") != 1:
        bad.append(f"守望台没记下唤醒来源: {d.last_wake_reason}/{d.wake_counts}")
    # ❗反方向：不传 markets 时所有守望都要被扫（行为与改动前一致）
    s_cn2, s_us2 = cn.scans, us.scans
    d.poll(now=1000.5, wake_reason="timer")
    if cn.scans == s_cn2 or us.scans == s_us2:
        bad.append("❗不传 markets 时却漏了守望 —— 破坏了原行为")
    # ❗反方向：不传 wake_reason 时不该动「上次被什么唤醒」（保持上一次
    # 的值），否则老调用方（不带 wake_reason）会把记录冲掉
    d.poll(now=1001.0)
    if d.last_wake_reason != "timer":
        bad.append(
            f"不传 wake_reason 却改了来源记录（{d.last_wake_reason}）—— "
            "破坏了原行为"
        )

    # 14 档位**没变**就不该发事件（发了 = 事件腿退化成定时轮询）
    try:
        from deva.naja.attention.kernel.manas_engine import ManasEngine

        class _Out:
            def __init__(self, t):
                self.action_type = t

        class _M:
            _published_action_type = None
            _state_change_published = 0
            _state_change_unknown = 0

            def _publish_manas_state_change(self, partial=None):
                self._state_change_published += 1
                return True

        m = _M()
        fn = ManasEngine._publish_action_type_change
        fn(m, _Out("hold"))
        fn(m, _Out("hold"))
        if m._state_change_published != 1:
            bad.append(
                f"❗档位没变却发了 {m._state_change_published} 次 —— "
                "事件腿退化成定时轮询"
            )
        fn(m, _Out("act_minimally"))
        if m._state_change_published != 2:
            bad.append("档位真的变了却没发事件（生产者哑了）")
    except Exception as e:  # noqa: BLE001
        bad.append(f"档位去重用例跑不起来（守卫自己的 bug）: {e}")

    return bad


# ─────────────────────────────────────────────────────────────
# 负向注入
# ─────────────────────────────────────────────────────────────

INJECTIONS = [
    {
        "name": "发布入参改成 data=（TypeError 被吞 → 通道空转）",
        "file": MANAS_PY,
        "old": "                metadata=state_data,",
        "new": "                data=state_data,",
    },
    {
        "name": "档位变化不去重（每轮都发 = 事件腿变回轮询）",
        "file": MANAS_PY,
        "old": "        if val == prev:\n            return False",
        "new": "        if False:\n            return False",
    },
    {
        "name": "不去抖（事件密集时按波动计费）",
        "file": AWAK_PY,
        "old": "        if self._min_interval <= 0 or self.last_eval_at is None:\n"
               "            return False\n"
               "        return (t - self.last_eval_at) < self._min_interval",
        "new": "        return False",
    },
    {
        "name": "节流的唤醒不进 pending（事件被丢弃）",
        "file": AWAK_PY,
        "old": "                if reason not in self.pending:\n"
               "                    self.pending.append(reason)",
        "new": "                pass",
    },
    {
        "name": "closed 时段也叫醒（噪音 + 白跑）",
        "file": AWAK_PY,
        "old": "            if phase and phase not in CLOCK_WAKE_PHASES:",
        "new": "            if False:",
    },
    {
        "name": "事件腿沉默不报警（通道断了没人知道）",
        "file": AWAK_PY,
        "old": "        return q > self._quiet_sec",
        "new": "        return False",
    },
    {
        "name": "票不交出去统计（问过了却记 0 次）",
        "file": AWAK_PY,
        "old": "        self._undrained.extend(tickets)",
        "new": "        pass",
    },
    {
        "name": "回调异常不上报（订阅侧故障隐形）",
        "file": AWAK_PY,
        "old": "        self.callback_errors += 1",
        "new": "        pass",
    },
    {
        "name": "按市场过滤方向搞反（只求别的市场）",
        "file": DESK_PY,
        "old": "            if markets is not None and watch.objective.market "
               "not in markets:",
        "new": "            if markets is not None and watch.objective.market "
               "in markets:",
    },
    {
        "name": "去掉 bootstrap（启动时首次档位变化收不到）",
        "file": AWAK_PY,
        "old": '            self.wake(WAKE_MANAS, detail="bootstrap")',
        "new": "            pass",
    },
    {
        "name": "唤醒器自证没人调用（health_line 写了没人读）",
        "file": RUNNER_PY,
        "old": "        self._report_awakener(t)\n",
        "new": "",
    },
    {
        "name": "删掉 data 别名（订阅方读不到载荷）",
        "file": COG_PY,
        "old": "    @property\n    def data(self) -> Dict[str, Any]:",
        "new": "    @property\n    def _data_unused(self) -> Dict[str, Any]:",
    },
]


def _apply(inj) -> bool:
    text = inj["file"].read_text(encoding="utf-8")
    if inj["old"] not in text:
        return False
    inj["file"].write_text(
        text.replace(inj["old"], inj["new"], 1), encoding="utf-8"
    )
    return True


def _reload_all() -> None:
    """按依赖序重载。顺序错了会造出两份类 → 每条注入都「被捕获」的假绿。"""
    for mod in ("deva.naja.watch.manas_lens", "deva.naja.watch.objective",
                "deva.naja.watch.opportunity", "deva.naja.watch.watch",
                "deva.naja.watch.registry", "deva.naja.watch.intent",
                "deva.naja.watch.rotation", "deva.naja.watch.allocation",
                "deva.naja.watch.desk", "deva.naja.watch.ui",
                "deva.naja.watch.awakener", "deva.naja.watch",
                "deva.naja.bandit.intent_runner",
                # ❗被注入的模块**必须**也在 reload 列表里：模块只在首次
                # import 进内存，不 reload 的话用例跑的还是没被改坏的旧
                # 代码 → 每条注入都「没抓到」的假结果。
                "deva.naja.events.cognitive_bus",
                "deva.naja.attention.kernel.manas_engine"):
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
        print("❌ 守望事件腿守卫发现 %d 项问题：" % len(failures))
        for x in failures:
            print("   -", x)
        return 1
    print("✅ 守望事件腿守卫全绿"
          "（Manas 档位 + 交易时钟 · 记来源 · 节流不丢 · 沉默自证）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
