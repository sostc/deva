#!/usr/bin/env python3
"""守卫：守望台 / 意向登记 / Manas 读数透镜（「我想买英伟达」这条线）。

守什么
------
2026-10-14 用户的原话：

    「我想买入英伟达，但可能现在价格高，我决定不了什么时候买入，但是我确实
     想买入 —— 这个想法应该进入守望台。等待一个机会来买入。那这个机会是怎么
     出现的呢？数据最后会汇聚到 Manas 决策中心，其实机会应该是在这里出现的。」

对应的四个部件，本守卫逐个盯：

    watch/manas_lens.py   机会的**发源地**：向 Manas 主动要一份廉价读数
    watch/intent.py       「我想买」变成可被等待的目标（必带结算点）
    watch/desk.py         守望台桌面：谁按什么节拍问、票有没有人领
    bandit/intent_runner.py 常驻运行器 + 容器接线

❗反方向用例（「一项保护会掩盖另一项缺失」）
------------------------------------------
只证明「守得住」是假绿 —— 一个永远沉默的守望同样能通过。每条保护都配反向用例：

* 意向必须有结算点 → 但**认不出的市场也不能静默兜底**（猜错市场整套参数都错）；
* Manas 读数能出档位 → 但**没有时间戳的读数必须算看不清**（假新鲜比异常更毒）；
* 桌面会开票 → 但**没人消费必须喊**（否则「UI 写好了链路没接」重演）；
* 运行器接了心跳节拍 → 但**节拍必须真的传到守望台**（配置项写了没人读 =
  同一种静默失效）。

用法
----
    python scripts/verify/verify_intent_watch.py
    python scripts/verify/verify_intent_watch.py --strict
    python scripts/verify/verify_intent_watch.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import logging
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import deva.naja.watch as W  # noqa: E402

WATCH_DIR = REPO / "deva/naja/watch"
LENS_PY = WATCH_DIR / "manas_lens.py"
INTENT_PY = WATCH_DIR / "intent.py"
DESK_PY = WATCH_DIR / "desk.py"
RUNNER_PY = REPO / "deva/naja/bandit/intent_runner.py"
CONTAINER_PY = REPO / "deva/naja/application/container.py"


REQUIRED_RULES = [
    # -- 机会发源地 ---------------------------------------------------
    ("manas_lens.py", r"ACTION_LADDER = \(",
     "缺行动档位阶梯（机会要按档位比大小）"),
    ("manas_lens.py", r"stamped: bool = False",
     "读数缺「时间戳可信」标记（没有时刻的读数不能自称新鲜）"),
    ("manas_lens.py", r"def ladder_index",
     "缺档位序号换算（无法比较强弱）"),
    ("manas_lens.py", r"rsplit\([\"']\.[\"'], 1\)\[-1\]",
     "❗不剥 ``ActionType.HOLD`` 的类名前缀，整套判据恒为「认不出档位」"),
    # ❗1e11 在 unparse 后会变成 100000000000.0，只认 "val > 1" 更稳
    ("manas_lens.py", r"val > 1",
     "不认毫秒戳会把刚算出的读数当成 1970 年的陈货"),
    ("manas_lens.py", r"def _unknown",
     "拿不到读数时没有自证计数（连着看不清却不喊 = 静默失效）"),
    ("manas_lens.py", r"fail_streak",
     "缺连续失败计数（Manas 长期不可用会和「一直很安静」混在一起）"),
    ("manas_lens.py", r"threading\.Lock\(\)",
     "读数在轮询线程里跑，必须串行"),
    # -- 意向 ---------------------------------------------------------
    ("intent.py", r"raise MissingSettlementPoint",
     "意向缺结算点必须报错（「还没想好」不等于「永远等下去」）"),
    ("intent.py", r"KNOWN_MARKETS = \(",
     "缺市场白名单（猜错市场会让每手/收盘整套参数跟着错）"),
    ("intent.py", r"raise ValueError\(\s*f[\"\']\{code\} 的市场",
     "认不出的市场必须报错，不许静默兜底"),
    ("intent.py", r"[\"\']kind[\"\']: [\"\']manas_window[\"\']",
     "❗意向的默认机会源必须是 Manas（用户说机会在那里出现）"),
    # -- 桌面 ---------------------------------------------------------
    ("desk.py", r"WatchRegistry\(heartbeat_sec=heartbeat_sec\)",
     "❗心跳节拍没传进守望台（配置项写了没人读 = 静默失效）"),
    ("desk.py", r"watch\.scan\(ctx, now=t\)",
     "❗扫描时刻必须显式传（ctx 缺失时会退回墙上时钟，与 armed_at 混算）"),
    # ❗ast.unparse 输出的是**单引号**，两种引号都要认
    ("desk.py", r"log\.warning\([\"\']\[WatchDesk\] %s 机会成立",
     "票没人消费必须喊 WARNING（不许静默丢掉）"),
    ("desk.py", r"watch\.acknowledge\(granted, reason, now=now\)",
     "问过之后必须回执给守望（否则沉默催问会一直触发）"),
    # -- 运行器与接线 -------------------------------------------------
    ("intent_runner.py", r"ENV_ENABLED = [\"']NAJA_INTENT_WATCH_ENABLED[\"']",
     "缺总回滚开关"),
    ("intent_runner.py", r"ENV_HEARTBEAT = [\"']NAJA_INTENT_HEARTBEAT_SEC[\"']",
     "缺心跳节拍开关"),
    ("intent_runner.py", r"heartbeat_sec=self\._beat_sec",
     "❗读到的心跳节拍没往下传（又是「配置写了没人读」）"),
    ("intent_runner.py", r"self\._desk\.asker = self\._asker",
     "❗外部注入的桌面没接执行器时必须补上（否则「接了执行器」被静默丢掉）"),
    # ❗只搜名字不够：import 那一行也会命中。要盯**调用**那一行。
    ("intent_runner.py", r"ask_decision_center\(spec, price\)",
     "❗必须复用决策中心留痕路径，另写一份等于绕过 DecisionPlan"),
    ("intent_runner.py", r"log\.info\([\"\']\[IntentRunner\] %s[\"\'], beat\)",
     "心跳文本没落日志（Manas 镜头与未消费票数只在桌面那一行里）"),
    ("intent_runner.py", r"threading\.Thread",
     "运行器没有常驻线程（守望没人驱动 = 摆设）"),
    ("intent_runner.py", r"seeded = self\.seed\(\)",
     "❗启动时没读声明式清单（守望纯内存，别的进程登记不进服务进程）"),
    ("intent_runner.py", r"def load_intents",
     "缺声明式意向清单装载（「我想买英伟达」没地方写）"),
    ("container.py", r"get_intent_runner\(\)",
     "❗容器没启动意向守望运行器（注册进单例表不等于会跑）"),
    ("container.py", r"intent_runner\.start\(\)",
     "❗容器没有显式 start()（注册进单例表不等于会跑）"),
]

FORBIDDEN_RULES = [
    # 守望这一整条线都只有「该不该问」的资格，没有放行权，更没有下单权
    ("desk.py", r"place_order|open_position|\.buy\(|\.sell\(",
     "桌面不许下单（机会 ≠ 放行）"),
    ("intent_runner.py", r"place_order|open_position|\.buy\(|\.sell\(",
     "运行器不许下单（批了只是拿到许可，落单要另一道授权）"),
    ("intent.py", r"place_order|open_position",
     "意向层不许下单（它只登记愿望）"),
    # 守望是运行期视图，落盘就是事故
    ("desk.py", r"\bopen\s*\(|_save|write_text|json\.dump",
     "桌面不许落盘（守望是内存视图，重启后重新登记）"),
    ("intent.py", r"\bopen\s*\(|write_text|json\.dump",
     "意向层不许落盘（登记是运行期动作）"),
    ("manas_lens.py", r"\bopen\s*\(|write_text",
     "透镜不许落盘（只读 Manas 输出）"),
]


# ─────────────────────────────────────────────────────────────
# 行为用例
# ─────────────────────────────────────────────────────────────
def _reading(action="hold", taken=100.0, score=0.5, source="injected"):
    return W.ManasReading(
        action_type=action, manas_score=score, taken_at=taken,
        stamped=True, source=source,
    )


def _lens(raw_map):
    box = {"raw": dict(raw_map)}
    return W.ManasLens(provider=lambda: box["raw"]), box


def behavior_checks() -> list:
    f = []

    # ① 意向没有结算点 → 必须报错
    try:
        W.BuyIntent("NVDA", "US", max_wait_seconds=0)
        f.append("① 意向缺结算点竟然没报错（允许无限期守望）")
    except Exception as e:  # noqa: BLE001 - 按类名认：reload 后异常 identity 会变
        if type(e).__name__ != "MissingSettlementPoint":
            raise

    # ②【反方向】认不出的市场必须报错，不许静默兜底
    try:
        W.BuyIntent("NVDA", "us", max_wait_seconds=100.0)
        # 小写 us 会被 upper() 归一化，这里换个真不认识的
        W.BuyIntent("NVDA", "JP", max_wait_seconds=100.0)
        f.append("② 认不出的市场被静默接受了（猜错市场整套参数都会错）")
    except ValueError:
        pass

    # ③ 意向的默认机会源必须是 Manas
    intent = W.BuyIntent("NVDA", "US", max_wait_seconds=3 * 86400.0,
                         budget=5000.0, rationale="看好 AI")
    kinds = [o.get("kind") if isinstance(o, dict) else getattr(o, "kind", "")
             for o in W.intent.__dict__.get("opportunities_for", lambda i: [])(intent)]
    if "manas_window" not in kinds:
        f.append("③ 意向默认机会源不是 Manas（用户说机会在那里出现）")

    # ④ 无时间戳的读数 = 看不清（假新鲜比异常更毒）
    lens4, _ = _lens({"action_type": "act_fully", "manas_score": 0.9})
    if lens4.read(now=1000.0) is not None:
        f.append("④ 没有时间戳的读数被当成可用了（不敢冒充新鲜读数）")
    if lens4.unknown_reads < 1 or lens4.fail_streak < 1:
        f.append("④ 看不清却没有自证计数（会和「Manas 一直很安静」混在一起）")

    # ⑤ py3.11+ 的 str(Enum) 形态必须认得
    lens5, _ = _lens({"action_type": "ActionType.ACT_CAREFULLY",
                      "manas_score": 0.6, "timestamp": 1000.0})
    r5 = lens5.read(now=1000.0)
    if r5 is None or r5.action_type != "act_carefully":
        f.append("⑤ 认不出 ``ActionType.ACT_CAREFULLY`` 这种形态（档位恒为不识别）")

    # ⑥ ManasWindow 三态：hold=no / 升档=yes / 没读数=unknown
    opp = W.build_opportunity({"kind": "manas_window",
                               "min_action": "act_minimally"})
    hold = opp.check(W.WatchContext(now=1000.0,
                                    extras={"manas_reading": _reading("hold")}))
    if not hold.no:
        f.append("⑥ hold 档不该算机会成立")
    up = opp.check(W.WatchContext(now=1000.0, extras={
        "manas_reading": _reading("act_carefully")}))
    if not up.yes:
        f.append("⑥ 行动门开到 act_carefully 应当算机会成立")
    # 沿变：同一档位再来一次不该再开一次票（否则每 30s 问一次决策中心）
    again = opp.check(W.WatchContext(now=1001.0, extras={
        "manas_reading": _reading("act_carefully")}))
    if not again.no:
        f.append("⑥ 同一档位重复出现不该再算机会（机会是档位变化，不是档位持续）")
    blind = opp.check(W.WatchContext(now=1000.0))
    if not blind.unclear:
        f.append("⑥❗没读数必须算看不清（None ≠ []，沉默不等于没机会）")
    stale = opp.check(W.WatchContext(now=1000.0, extras={
        "manas_reading": _reading("act_fully", taken=0.0)}))
    if not stale.unclear:
        f.append("⑥ 过期读数必须算看不清（拿陈货当现在有机会最危险）")

    # ⑦ 桌面：不接执行器 → 票开出来但没人消费，且必须喊
    lens7, box7 = _lens({"action_type": "act_carefully",
                         "manas_score": 0.7, "timestamp": 1000.0})
    desk7 = W.WatchDesk(lens=lens7, quote_fn=lambda c: None)
    desk7.declare_intent(intent, now=1000.0)
    with _capture() as rec:
        tks7 = desk7.poll(now=1001.0)
    if not tks7:
        f.append("⑦ 行动门开了却没开票（守望没被驱动）")
    elif not tks7[0].unanswered:
        f.append("⑦ 没接执行器却说有人消费了（会假装成「决策中心不放行」）")
    if not any("机会成立" in r for r in rec):
        f.append("⑦ 票没人消费没有喊 WARNING（静默丢掉 = 死线程长得一样）")

    # ⑧ 桌面：接了执行器 → 结论要回执给守望，且不再重复开票
    granted = {"v": True}
    # ❗读数时刻要跟着 now 走：ManasWindow 的保鲜期是 600s，
    # 拿 1000s 那份去扫 2001s 会先被判过期（这是设计如此，不是 bug）
    box7["raw"] = {"action_type": "act_carefully",
                   "manas_score": 0.7, "timestamp": 2000.0}
    desk8 = W.WatchDesk(
        lens=lens7, quote_fn=lambda c: None,
        asker=lambda o, c, s: (granted["v"], "测试用放行" if granted["v"] else "测试用否决"),
    )
    w8 = desk8.declare_intent(intent, now=2000.0)
    tks8 = desk8.poll(now=2001.0)
    if len(tks8) != 1 or tks8[0].granted is not True:
        f.append("⑧ 行动门开了且执行器放行，票上却不是 granted=True")
    # 回执之后同一档位不该再开票（否则每轮都问 = 旧行为）
    tks8b = desk8.poll(now=2002.0)
    if tks8b:
        f.append("⑧ 已回执的守望还在重复开票（沉默催问的回执没生效）")
    granted["v"] = False
    box7["raw"] = {"action_type": "act_fully", "manas_score": 0.8,
                   "timestamp": 2100.0}
    tks8c = desk8.poll(now=2100.0)
    if not tks8c or tks8c[0].granted is not False:
        f.append("⑧ 执行器否决时票上必须是 granted=False")
    del w8

    # ⑨ 心���节拍必须真的传到守望台（0 = 关，不该再自报）
    desk9 = W.WatchDesk(lens=lens7, quote_fn=lambda c: None, heartbeat_sec=0.0)
    if desk9.heartbeat(now=3000.0) is not None:
        f.append("⑨ 心跳设为 0 却还在自报 —— 节拍没传进守望台（配置写了没人读）")
    desk9b = W.WatchDesk(lens=lens7, quote_fn=lambda c: None, heartbeat_sec=50.0)
    if desk9b.heartbeat(now=3000.0) is None:
        f.append("⑨ 设了心跳却报不出来（守望台自证缺失）")

    # ⑩ 扫描时刻必须显式传（观测面里塞一个错的时间也不能带偏）
    desk10 = W.WatchDesk(lens=lens7, quote_fn=lambda c: None)
    w10 = desk10.declare_intent(intent, now=4000.0)
    desk10.register_observer(
        "buy_intent",
        lambda watch, now: W.WatchContext(now=0.0, price=1.0, anchor=1.0),
    )
    desk10.poll(now=4100.0)
    if w10.last_scan_at != 4100.0:
        f.append(f"⑩ 扫描用了观测面里的时刻（{w10.last_scan_at}）—— "
                 "now 必须显式传，否则与 armed_at 混算")

    # ⑪ 到期必须显式结算，不能无声消失
    desk11 = W.WatchDesk(lens=lens7, quote_fn=lambda c: None)
    short = W.BuyIntent("NVDA", "US", max_wait_seconds=60.0)
    w11 = desk11.declare_intent(short, now=5000.0)
    desk11.poll(now=5001.0)
    desk11.poll(now=5100.0)
    if w11.state != W.WatchState.SETTLED or w11.settlement.value != "expired":
        f.append("⑪ 到期意向没被结算成 expired（会无声消失）")

    # ⑫ 运行器接线：关掉不起、起得来、会自报
    from deva.naja.bandit.intent_runner import IntentRunner  # noqa: E402

    off = IntentRunner(enabled=False, poll_seconds=1, heartbeat_sec=0)
    if off.start() is not False or off.running:
        f.append("⑫ NAJA_INTENT_WATCH_ENABLED=0 时运行器不该启动")

    runner = IntentRunner(
        desk=W.WatchDesk(lens=lens7, quote_fn=lambda c: None,
                         heartbeat_sec=0.0),
        asker=lambda o, c, s: (True, "测试放行"),
        poll_seconds=1, heartbeat_sec=0,
    )
    # ❗用逻辑时钟登记：declare 默认取墙上时钟（1.7e9），
    # 与 tick 的 6000 混算会让「已等多久」变成负数，用例就测不出东西了
    box7["raw"] = {"action_type": "act_carefully",
                   "manas_score": 0.7, "timestamp": 5990.0}
    runner.desk.declare_intent(
        W.BuyIntent("NVDA", "US", max_wait_seconds=3600.0), now=5990.0,
    )
    if not runner.start() or not runner.running:
        f.append("⑫ 运行器起不来（守望没人驱动 = 摆设）")
    runner.tick(now=6000.0)
    if runner.stats["polls"] != 1:
        f.append("⑫ tick 没有真正扫一轮")
    runner.stop()
    if runner.running:
        f.append("⑫ stop() 之后线程还在跑")
    if runner.stats["granted"] < 1:
        f.append("⑫ 行动门开着却一次都没去问（链路没接）")

    # ⑮ 缓存缺失时必须自己同步补抓（否则价格类判据永远「看不清」）
    import deva.naja.bandit.market_data_bus as bus_mod  # noqa: E402

    class _FakeQuote:
        current = 199.0
        prev_close = 197.0
        age = 1.0

    class _FakeBus:
        def __init__(self):
            self.fetched = []
            self._q = {}

        def get_quote(self, code, allow_stale=True):
            return self._q.get(code)

        def fetch(self, codes):
            self.fetched.extend(codes)
            for c in codes:
                self._q[c] = _FakeQuote()
            return {c: 199.0 for c in codes}

    fake = _FakeBus()
    orig_bus = bus_mod.get_market_data_bus
    bus_mod.get_market_data_bus = lambda: fake
    try:
        desk15 = W.WatchDesk(lens=lens7, heartbeat_sec=0.0)
        price15, anchor15 = desk15._price_and_anchor("NVDA", "US")
    finally:
        bus_mod.get_market_data_bus = orig_bus
    if price15 != 199.0:
        f.append("⑮ 缓存缺失时没补抓到价格（价格类判据会永远「看不清」）")
    if not fake.fetched:
        f.append("⑮ 缓存缺失时没有触发同步补抓")

    # ⑭ 声明式清单：单条坏了只跳过那一条，其余照挂
    import json  # noqa: E402
    import tempfile  # noqa: E402
    from deva.naja.bandit.intent_runner import (  # noqa: E402
        IntentRunner as _IR, load_intents,
    )
    tmp = Path(tempfile.mkdtemp()) / "intents.json"
    tmp.write_text(json.dumps([
        {"code": "NVDA", "market": "US", "side": "buy",
         "max_wait_seconds": 3 * 86400, "budget": 5000, "rationale": "看好 AI"},
        {"code": "OOPS", "market": "JP", "max_wait_seconds": 100},
        {"code": "00700", "market": "HK", "side": "trim",
         "max_wait_seconds": 86400},
    ]), encoding="utf-8")
    with _capture("deva.naja.bandit.intent_runner") as rec14:
        rows14 = load_intents(tmp)
    if len(rows14) != 2:
        f.append(f"⑭ 清单里 1 条坏掉应只跳过那一条，实际装载 {len(rows14)} 条")
    if not any("不可用" in r and "OOPS" in r for r in rec14):
        f.append("⑭ 坏掉的那条没有喊出来（静默跳过 = 想买的想法不见了）")
    r14 = _IR(poll_seconds=1, heartbeat_sec=0)
    if r14.seed(tmp) != 2:
        f.append("⑭ 启动播种的条数不对")
    if len(r14.desk.watches()) != 2:
        f.append("⑭ 播种后守望台上的守望数不对")
    # 文件不存在是合法的空，不能报错
    if load_intents(Path(tempfile.mkdtemp()) / "nope.json"):
        f.append("⑭ 清单文件不存在应当返回空列表（合法的空）")

    # ⑬ 默认询问器必须真的走决策中心（另写一份等于绕过 DecisionPlan 留痕）
    import deva.naja.bandit.core_establish_gate as gate_mod  # noqa: E402
    from deva.naja.bandit.intent_runner import (  # noqa: E402
        decision_center_asker,
    )
    calls = []
    orig = gate_mod.ask_decision_center
    gate_mod.ask_decision_center = lambda spec, price: (
        calls.append((getattr(spec, "code", "?"), price)) or {
            "plan": {"size_hint": 0.5}, "action_type": "act_carefully",
            "approved": True,
        }
    )
    try:
        granted13, _why = decision_center_asker(
            W.to_objective(intent), W.WatchContext(now=7000.0, price=199.0), None,
        )
    finally:
        gate_mod.ask_decision_center = orig
    if not calls:
        f.append("⑬ 默认询问器没有真的去问决策中心（绕过 DecisionPlan 留痕）")
    elif not granted13:
        f.append("⑬ 决策中心批准又不给额度时应当是 granted=True，"
                 f"实际 False（{_why}）")
    return f


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class _capture:
    def __init__(self, logger_name: str = "deva.naja.watch.desk"):
        self._h = _Capture()
        self._name = logger_name

    def __enter__(self):
        self._h.lines.clear()
        # ❗main() 里 logging.disable(CRITICAL) 会把要抓的 WARNING 一起关掉，
        # 抓之前必须先把闸门打开，否则「喊了但没抓到」会被误判成「没喊」。
        self._prev_disable = logging.root.manager.disable
        logging.disable(logging.NOTSET)
        self._log = logging.getLogger(self._name)
        self._prev_level = self._log.level
        self._log.setLevel(logging.WARNING)
        self._log.addHandler(self._h)
        return self._h.lines

    def __exit__(self, *a):
        self._log.removeHandler(self._h)
        self._log.setLevel(self._prev_level)
        logging.disable(self._prev_disable)
        return False


# ─────────────────────────────────────────────────────────────
# 静态
# ─────────────────────────────────────────────────────────────
def code_only(path: Path) -> str:
    """去注释 + 剥 docstring —— 否则扫到文档里「禁止下单」四个字就误报。"""
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
        "manas_lens.py": LENS_PY, "intent.py": INTENT_PY, "desk.py": DESK_PY,
        "intent_runner.py": RUNNER_PY, "container.py": CONTAINER_PY,
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
        "name": "意向缺结算点不再报错（允许无限期守望）",
        "file": INTENT_PY,
        "old": "        if wait is None or float(wait) <= 0:",
        "new": "        if False:",
        "count": -1,
    },
    {
        "name": "认不出的市场被静默兜底成 US",
        "file": INTENT_PY,
        "old": "        if market not in KNOWN_MARKETS:",
        "new": "        if False:\n            pass\n        if market not in KNOWN_MARKETS:\n            market = \"US\"\n        if False:",
        "count": 1,
    },
    {
        "name": "❗无时间戳的读数冒充新鲜（假新鲜比异常更毒）",
        "file": LENS_PY,
        "old": "            return None, \"Manas 输出没有可信时刻（不敢冒充新鲜读数）\"",
        "new": "            taken = time.time()",
        "count": -1,
    },
    {
        "name": "不剥 ActionType. 前缀（档位恒为不识别）",
        "file": LENS_PY,
        "old": "        text = text.rsplit(\".\", 1)[-1]",
        "new": "        pass",
        "count": -1,
    },
    {
        "name": "❗心跳节拍不往下传（配置项写了没人读）",
        "file": DESK_PY,
        "old": "        self.registry: WatchRegistry = registry or WatchRegistry(\n            heartbeat_sec=heartbeat_sec\n        )",
        "new": "        self.registry: WatchRegistry = registry or WatchRegistry()",
        "count": -1,
    },
    {
        "name": "❗扫描不显式传 now（与 armed_at 混算）",
        "file": DESK_PY,
        "old": "            scan = watch.scan(ctx, now=t)",
        "new": "            scan = watch.scan(ctx)",
        "count": -1,
    },
    {
        "name": "票没人消费时静默丢掉（不喊）",
        "file": DESK_PY,
        "old": "                log.warning(\n                    \"[WatchDesk] %s 机会成立（%s）—— %s\",\n                    watch.watch_id, scan.why(), reason,\n                )",
        "new": "                pass",
        "count": -1,
    },
    {
        "name": "❗外部注入的桌面不再补挂执行器（接了也等于没接）",
        "file": RUNNER_PY,
        "old": "            elif self._asker is not None and self._desk.asker is None:",
        "new": "            elif False:",
        "count": -1,
    },
    {
        "name": "清单里坏掉的那条被静默跳过（想买的想法无声消失）",
        "file": RUNNER_PY,
        "old": "            log.warning(\"[IntentRunner] 意向清单第 %d 条（%s）不可用：%s:%s\",\n                        i + 1, row.get(\"code\"), type(e).__name__, e)",
        "new": "            pass",
        "count": -1,
    },
    {
        "name": "❗启动时不再读声明式清单（守望永远为空）",
        "file": RUNNER_PY,
        "old": "            seeded = self.seed()",
        "new": "            seeded = 0",
        "count": -1,
    },
    {
        "name": "❗缓存缺失时不再同步补抓（价格类判据永远看不清）",
        "file": DESK_PY,
        "old": "            self._sync_fetch(bus, bus_code)",
        "new": "            pass",
        "count": -1,
    },
    {
        "name": "❗运行器不再复用决策中心（绕过 DecisionPlan 留痕）",
        "file": RUNNER_PY,
        "old": "        raw = ask_decision_center(spec, price)",
        "new": "        raw = {\"plan\": {}, \"approved\": True}",
        "count": -1,
    },
    {
        "name": "运行器心跳不落日志（镜头自证丢失）",
        "file": RUNNER_PY,
        "old": "        if beat:\n            log.info(\"[IntentRunner] %s\", beat)",
        "new": "        if beat:\n            pass",
        "count": -1,
    },
    {
        "name": "容器不再启动意向守望运行器",
        "file": CONTAINER_PY,
        "old": "            intent_runner.start()",
        "new": "            pass",
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
    """按依赖序重载整条链（顺序错了会造出两份类，用例自己崩）。"""
    for mod in ("deva.naja.watch.manas_lens", "deva.naja.watch.objective",
                "deva.naja.watch.opportunity", "deva.naja.watch.watch",
                "deva.naja.watch.registry", "deva.naja.watch.intent",
                "deva.naja.watch.desk", "deva.naja.watch",
                "deva.naja.bandit.intent_runner"):
        importlib.reload(importlib.import_module(mod))
    global W
    W = importlib.reload(W)


def exercise_injections() -> int:
    print("\n=== 负向注入：故意改坏代码，验证守卫不是摆设 ===")
    caught = 0

    # ❗自证第零步：**什么都不改**先重载一遍，用例必须仍然全绿。
    # 不加这一步，reload 顺序搞错时每条注入都会「被捕获」—— 抓的是守卫
    # 自己的 bug，11/11 假绿。这个坑当天真踩过一次。
    _reload_all()
    baseline = behavior_checks() + static_checks()
    if baseline:
        print("   ❌ 纯 reload 下用例就不绿了（守卫自己的 bug，注入结果不可信）：")
        for x in baseline[:5]:
            print("      -", x)
        return 1
    print("   ✅ 基线：纯 reload 后用例仍然全绿")

    for inj in INJECTIONS:
        backup = inj["file"].read_text(encoding="utf-8")
        try:
            if not _apply(inj):
                print(f"   ⚠️ 跳过（锚点缺失，属于用例 bug 不是产品 bug）：{inj['name']}")
                continue
            # ❗必须 reload：模块早就在内存里了，不重载会拿到被污染的旧对象。
            # ❗顺序必须是**依赖序**：manas_lens / objective 先，desk 最后。
            # 顺序错了的两种死法（都踩过）：
            #   * objective 在 intent 之后重载 → intent 抱着旧异常类，
            #     except 认不出来，用例自己崩；
            #   * manas_lens 在 opportunity 之后重载 → 两份 ManasReading 类，
            #     isinstance 恒为假，判据永远报「读数类型不对」。
            for mod in ("deva.naja.watch.manas_lens", "deva.naja.watch.objective",
                        "deva.naja.watch.opportunity", "deva.naja.watch.watch",
                        "deva.naja.watch.registry", "deva.naja.watch.intent",
                        "deva.naja.watch.desk", "deva.naja.watch",
                        "deva.naja.bandit.intent_runner"):
                try:
                    importlib.reload(importlib.import_module(mod))
                except Exception:
                    pass
            global W
            W = importlib.reload(W)
            bad = behavior_checks() + static_checks()
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

    failures = static_checks() + behavior_checks()
    if failures:
        print("❌ 守望台守卫发现 %d 项问题：" % len(failures))
        for x in failures:
            print("   -", x)
        return 1
    print("✅ 守望台守卫全绿（Manas 透镜 + 意向 + 桌面 + 运行器接线）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
