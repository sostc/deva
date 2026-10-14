#!/usr/bin/env python3
"""守卫：守望台 UI + 执行记录 + 意愿强度可调（2026-10-14 用户要的那块）。

守什么
------
用户原话：「增加一点守望台的 UI 吧，以及手动想买想卖的 UI，可以调整卖出或
买入的意愿力度，守望台有该意愿的执行记录情况。」

拆成四件事，本守卫逐个盯：

1. **页面接进来了**：``/watchdesk`` 有路由、有页面函数、导航里有入口。
   少任何一处都是「UI 写好了、链路没接」—— 本仓库头号病理。
2. **执行记录看得见**：每个守望记了「问过几次 / 放行 · 被否 · 没人去问」，
   桌面另有一份全局开票流水。没有它，「在等」和「线程死了」长得一样。
3. **意愿强度可调，但调不出天花板**：UI 能改，改了要落到台上**和**清单里；
   给 0.99 也只拿到 0.75 —— 主动意愿是加权，不是放行键。
4. **页面上没有下单按钮**：守望台只「等」和「问」，不碰账户。

❗反方向用例（「一项保护会掩盖另一项缺失」）
------------------------------------------
* 能调力度 → 但**上限必须还在**（拖到底也不是放行）；
* 登记能落盘 → 但**撤下也要真的从清单里删掉**（否则重启诈尸）；
* 执行记录有字段 → 但**「没人去问」必须跟「问了被否」分开**（三态，不是两态）；
* 页面能渲染 → 但**不许出现整页定时 reload**（会把填到一半的表单冲掉）。

用法
----
    python scripts/verify/verify_watch_desk_ui.py
    python scripts/verify/verify_watch_desk_ui.py --strict
    python scripts/verify/verify_watch_desk_ui.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import logging
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import os
# ❗守卫用例必须**确定性**：守望台默认开着市场时钟，闭市时守望会被闸门
# 跳过 —— 于是「现在几点」决定了用例的成败（半夜跑绿、收盘后跑红）。
# 市场时钟自身的行为由 verify_watch_awakener / 市场时钟守卫负责，
# 这里的用例只测守望语义，一律关掉闸门。
os.environ["NAJA_WATCH_MARKET_CLOCK"] = "0"

import deva.naja.watch as W  # noqa: E402

WATCH_DIR = REPO / "deva/naja/watch"
UI_PY = WATCH_DIR / "ui.py"
WATCH_PY = WATCH_DIR / "watch.py"
DESK_PY = WATCH_DIR / "desk.py"
RUNNER_PY = REPO / "deva/naja/bandit/intent_runner.py"
ROUTES_PY = REPO / "deva/naja/web_ui/routes.py"
PAGES_PY = REPO / "deva/naja/web_ui/pages.py"
THEME_PY = REPO / "deva/naja/infra/ui/ui_theme.py"

#: ❗判定基准写死在守卫里，**不去读被测模块**的常量：
#: 否则注入把上限改高时守卫跟着一起变，用例照样绿。
CONFIDENCE_CAP = 0.75

REQUIRED_RULES = [
    # -- 页面接进来（缺一处就是「UI 写好了链路没接」） -----------------
    ("ui.py", r"async def render_watch_desk",
     "缺守望台页面入口"),
    # ❗ast.unparse 会丢掉 r 前缀，只认路径本身
    ("routes.py", r"[\"']/watchdesk[\"']",
     "❗守望台没有路由（页面写得再好也打不开）"),
    ("routes.py", r"watchdesk",
     "❗路由表没 import watchdesk"),
    ("pages.py", r"async def watchdesk",
     "❗缺页面函数 watchdesk"),
    ("ui_theme.py", r"/watchdesk",
     "❗导航菜单里没有守望台入口（用户找不到）"),
    # -- 执行记录 -----------------------------------------------------
    ("watch.py", r"def record_ask",
     "守望缺问询留痕（「问过几次、结论是什么」无处可查）"),
    ("watch.py", r"ASK_LOG_MAXLEN\s*=",
     "问询日志没有长度上限（会无限膨胀）"),
    ("watch.py", r"verdict is None:\s*\n?\s*self\.unanswered_count \+= 1",
     "❗「没人去问」没被单独计数（会和「问了被否」混成一种）"),
    ("watch.py", r"def ask_history",
     "缺按守望取记录的接口（UI 无从展示）"),
    ("desk.py", r"def ticket_log",
     "桌面缺全局开票流水（守望撤下后痕迹就没了）"),
    ("desk.py", r"TICKET_LOG_MAXLEN\s*=",
     "开票流水没有长度上限"),
    ("desk.py", r"watch\.record_ask\(",
     "❗开票之后没有给守望留痕（UI 上的「问询记录」永远是 0 次）"),
    ("desk.py", r"self\._log_ticket\(tk, t\)",
     "❗票没有落进全局流水（只有返回值，进程内查不到）"),
    # -- 意愿强度可调，但封顶还在 ---------------------------------------
    ("desk.py", r"def set_confidence",
     "缺调意愿强度的接口（UI 无从下手）"),
    ("desk.py", r"conf = clamp_confidence\(value\)",
     "❗调力度没走封顶（UI 就成了绕过上限的后门）"),
    ("desk.py", r"raise KeyError\(f[\"']守望 \{watch_id\} 不在台上",
     "认不出的守望必须报错，不许静默返回"),
    ("ui.py", r"CONFIDENCE_SLIDER_MAX = 0\.75",
     "❗滑块上限不是 0.75（页面上能拖到放行阈值就是放行键）"),
    ("ui.py", r"desk\.set_confidence\(",
     "❗UI 调力度没走内核接口（自己改参数会绕过封顶）"),
    # -- 登记 / 撤下必须真的落到清单里 ----------------------------------
    ("ui.py", r"upsert_intent\(",
     "❗登记/改力度没写回声明式清单（重启就什么都没发生过）"),
    ("ui.py", r"remove_intent\(",
     "❗撤下没从清单里删掉（重启会诈尸）"),
    ("intent_runner.py", r"def save_intents",
     "缺清单写回"),
    ("intent_runner.py", r"def upsert_intent",
     "缺按标的更新一条"),
    ("intent_runner.py", r"def remove_intent",
     "缺按标的删一条"),
    ("intent_runner.py", r"os\.replace\(tmp, p\)",
     "❗写回不是原子替换（写一半崩掉会把整份清单抹掉）"),
    # -- 展示 ---------------------------------------------------------
    ("ui.py", r"put_table\(",
     "页面没有表格（守望列表/执行记录无处展示）"),
    ("ui.py", r"desk\.ticket_log\(",
     "❗页面没读开票流水（执行记录这一栏是空的）"),
    ("ui.py", r"watch\.ask_history\(",
     "❗页面没读单个守望的执行记录"),
    ("ui.py", r"CONFIDENCE_DEFAULT_SLIDER",
     "登记表单缺意愿强度默认值"),
]

FORBIDDEN_RULES = [
    # 守望台只有「等」和「问」，没有下单权
    ("ui.py", r"place_order|submit_order|create_order|OpenSecTradeContext"
              r"|\.buy\(|\.sell\(|open_position",
     "❗守望台页面上出现下单动作（这里只登记愿望，不碰账户）"),
    ("watch.py", r"place_order|submit_order|create_order",
     "守望内核不许下单"),
    # UI 不许自己实现封顶逻辑（封顶只有一处，就是内核的 clamp_confidence）
    ("ui.py", r"clamp_confidence\(",
     "UI 不该自己算封顶（绕过内核就会有第二个上限）"),
    # 定时整页刷新会冲掉弹窗里填到一半的表单
    ("ui.py", r"setInterval|location\.reload",
     "❗页面有定时整页刷新（会把调力度/登记意向的表单冲掉）"),
    # 守望与内核是内存视图，落盘就是事故（清单落盘在 intent_runner，那是配置）
    ("watch.py", r"\bopen\s*\(|write_text|json\.dump",
     "守望本体不许落盘（运行期视图）"),
]


# ─────────────────────────────────────────────────────────────
# 行为用例
# ─────────────────────────────────────────────────────────────
def _reading(action="act_carefully", taken=1000.0, score=0.7):
    return W.ManasReading(action_type=action, manas_score=score,
                          taken_at=taken, stamped=True, source="injected")


def _lens(raw):
    box = {"raw": dict(raw)}
    return W.ManasLens(provider=lambda: box["raw"]), box


def _desk(action="act_carefully", ts=1000.0, asker=None):
    """造一个假桌面。

    ❗读数时刻必须**贴近用例的逻辑时钟**：ManasWindow 的保鲜期是 600s，
    拿 1000s 的读数去扫 3001s 会先被判过期（设计如此），票根本开不出来，
    用例就会「因为没开票」而假绿。
    """
    lens, box = _lens({"action_type": action, "manas_score": 0.7,
                       "timestamp": ts})
    return W.WatchDesk(lens=lens, quote_fn=lambda c: None,
                       asker=asker, heartbeat_sec=0.0), box


def behavior_checks() -> list:
    f = []
    intent = W.BuyIntent("NVDA", "US", max_wait_seconds=3 * 86400.0,
                         rationale="看好 AI")

    # ① record_ask 三态：放行 / 被否 / 没人去问，各计各的
    desk1, _ = _desk()
    w1 = desk1.declare_intent(intent, now=1000.0)
    w1.record_ask(True, "放行", now=1001.0)
    w1.record_ask(False, "再等等", now=1002.0)
    w1.record_ask(None, "没人领", now=1003.0)
    if (w1.asked, w1.granted_count, w1.denied_count, w1.unanswered_count) != (3, 1, 1, 1):
        f.append(f"① 三态计数错了：asked={w1.asked} ✓{w1.granted_count} "
                 f"✗{w1.denied_count} ?{w1.unanswered_count}")
    if w1.last_granted is not None:
        f.append("① 最后一次是「没人去问」，last_granted 必须是 None（三态，不是两态）")
    hist = w1.ask_history(10)
    if len(hist) != 3 or hist[0]["verdict"] != "没人去问":
        f.append(f"① ask_history 顺序/结论不对：{[h['verdict'] for h in hist]}")
    if any(h["verdict"] == "未批准" and "放行" in h["verdict"] for h in hist):
        f.append("① 结论文案串了")

    # ② 环形上限：记爆了也只留 ASK_LOG_MAXLEN 条，但总次数不能回退
    desk2, _ = _desk()
    w2 = desk2.declare_intent(intent, now=2000.0)
    cap2 = int(getattr(W, "ASK_LOG_MAXLEN", 30))
    for i in range(cap2 + 12):
        w2.record_ask(False, f"第{i}次", now=2000.0 + i)
    if len(w2.ask_log) != cap2:
        f.append(f"② 问询日志没截断：{len(w2.ask_log)} != {cap2}")
    if w2.asked != cap2 + 12:
        f.append(f"② 总问询次数不该被截断抹掉：{w2.asked}")

    # ③ 桌面没接执行器 → 票是 unanswered，且守望记成「没人去问」
    desk3, _ = _desk(ts=3000.0, asker=None)
    w3 = desk3.declare_intent(intent, now=3000.0)
    tks3 = desk3.poll(now=3001.0)
    if not tks3 or tks3[0].granted is not None:
        f.append("③ 没接执行器时票的 granted 必须是 None（三态）")
    if w3.unanswered_count != 1:
        f.append(f"③ 没人消费没有被记进守望：?{w3.unanswered_count}")

    # ④ 接了执行器 → 放行/否决分别留痕
    verdict = {"v": True}
    desk4, box4 = _desk(ts=4000.0, asker=lambda o, c, s: (verdict["v"], "测试结论"))
    w4 = desk4.declare_intent(intent, now=4000.0)
    desk4.poll(now=4001.0)
    verdict["v"] = False
    box4["raw"] = {"action_type": "act_fully", "manas_score": 0.9,
                   "timestamp": 4100.0}
    desk4.poll(now=4101.0)
    if (w4.granted_count, w4.denied_count) != (1, 1):
        f.append(f"④ 放行/否决留痕不对：✓{w4.granted_count} ✗{w4.denied_count}")

    # ⑤ 全局开票流水：有记录、有结论、有上限
    if len(desk4.ticket_log(50)) < 2:
        f.append("⑤ 开票流水没记（撤下之后就查无实据）")
    # ❗链路没数据时守卫要「如实记一条」而不是崩：注入第 4 条就是把流水
    #   整个拿掉，守卫自己抛 IndexError 的话，抓到的就不是产品 bug 了
    top = desk4.ticket_log(1)[0] if desk4.ticket_log(1) else {}
    for key in ("ts", "subject", "verdict", "reason", "watch_id"):
        if key not in top:
            f.append(f"⑤ 开票流水缺字段 {key}（或压根没有流水）")
    cap5 = int(getattr(W, "TICKET_LOG_MAXLEN", 200))
    desk5, box5 = _desk(ts=5000.0, asker=lambda o, c, s: (True, "x"))
    for i in range(cap5 + 5):
        # 档位交替 → 每个守望每轮都有「档位变化」可开票，流水才涨得起来
        box5["raw"] = {"action_type": "act_fully" if i % 2 else "act_carefully",
                       "manas_score": 0.9, "timestamp": 5000.0 + i}
        desk5.declare_intent(
            W.BuyIntent(f"C{i}", "US", max_wait_seconds=86400.0), now=5000.0 + i)
        desk5.poll(now=5000.0 + i)
    if len(desk5._ticket_log) > cap5:
        f.append(f"⑤ 开票流水没截断：{len(desk5._ticket_log)} > {cap5}")

    # ⑥ 快照/行里必须带执行记录（UI 与心跳同一个口径）
    row6 = w4.to_row(4200.0)
    for key in ("asked", "granted_count", "denied_count", "unanswered_count",
                "recent_asks"):
        if key not in row6:
            f.append(f"⑥ to_row 缺执行记录字段 {key}")
    if "tickets_recent" not in desk4.snapshot(4200.0):
        f.append("⑥ 桌面快照缺 tickets_recent（页面读不到流水）")

    # ⑦ 调力度：封顶还在（给 0.99 / 9.9 都只拿到 CAP）
    desk7, _ = _desk()
    w7 = desk7.declare_intent(intent, now=7000.0)
    got7 = desk7.set_confidence(w7.watch_id, 0.99)
    if got7 > CONFIDENCE_CAP + 1e-9:
        f.append(f"⑦ 意愿强度没封顶：{got7} > {CONFIDENCE_CAP}（UI 成了放行键）")
    if desk7.set_confidence(w7.watch_id, 9.9) > CONFIDENCE_CAP + 1e-9:
        f.append("⑦ 传 9.9 也拿到超限的值（封顶形同虚设）")
    if w7.objective.params.get("confidence") != got7:
        f.append("⑦ 台上拿到的强度与返回值不一致（UI 显示会说谎）")
    if not w7.objective.params.get("confidence_explicit"):
        f.append("⑦ 人工改过却没标 explicit（审计分不出默认与手改）")

    # ⑧【反方向】调力度只动强度：标的/方向/市场不许被顺手改掉
    desk8, _ = _desk()
    w8 = desk8.declare_intent(
        W.Intent(code="00700", market="HK", side="trim",
                 max_wait_seconds=86400.0), now=8000.0)
    before8 = (w8.objective.subject, w8.objective.market,
               str(w8.objective.params.get("side")))
    desk8.set_confidence(w8.watch_id, 0.3)
    after8 = (w8.objective.subject, w8.objective.market,
              str(w8.objective.params.get("side")))
    if before8 != after8:
        f.append(f"⑧ 调力度把标的/方向改了：{before8} → {after8}")

    # ⑨ 认不出的守望 → 必须报错，不许静默成功
    desk9, _ = _desk()
    try:
        desk9.set_confidence("intent:buy:US:NOPE", 0.6)
        f.append("⑨ 给不存在的守望调力度竟然成功了（UI 会以为改了）")
    except KeyError:
        pass

    # ⑩ 清单落盘：登记 → 改 → 撤下，逐条可验
    from deva.naja.bandit.intent_runner import (  # noqa: E402
        load_intents, read_intent_rows, remove_intent, upsert_intent,
    )
    tmpdir = Path(tempfile.mkdtemp())
    tmp = tmpdir / "intents.json"
    tmp.write_text(json.dumps([
        {"code": "NVDA", "market": "US", "side": "buy",
         "max_wait_seconds": 259200, "confidence": 0.65},
        {"code": "00700", "market": "HK", "side": "sell",
         "max_wait_seconds": 86400},
    ]), encoding="utf-8")

    new_one = W.BuyIntent("QQQ", "US", max_wait_seconds=86400.0,
                          rationale="等一个像样的回调", confidence=0.7)
    if upsert_intent(new_one, tmp) != "added":
        f.append("⑩ 新登记应当返回 added")
    if upsert_intent(W.BuyIntent("QQQ", "US", max_wait_seconds=86400.0,
                                 confidence=0.7), tmp) != "updated":
        f.append("⑩ 同标的再登记应当返回 updated（否则清单会被写成一堆重复）")
    rows10 = read_intent_rows(tmp)
    if len(rows10) != 3:
        f.append(f"⑩ 落盘后条目数不对：{len(rows10)}")
    loaded10 = load_intents(tmp)
    if len(loaded10) != 3:
        f.append(f"⑩ 落盘后读回来条数不对：{len(loaded10)}（存进去自己读不懂）")
    q10 = [i for i in loaded10 if i.code == "QQQ"]
    if not q10 or abs(float(q10[0].confidence) - 0.7) > 1e-9:
        f.append("⑩ 强度没被如实写回清单")

    # ⑪【反方向】改一条不许把别的条目冲掉
    old_700 = [r for r in rows10 if str(r.get("code")).upper() == "00700"]
    upsert_intent(new_one, tmp)
    rows11 = read_intent_rows(tmp)
    new_700 = [r for r in rows11 if str(r.get("code")).upper() == "00700"]
    if old_700 != new_700 or not new_700:
        f.append(f"⑪ 改一条把别的条目改了/弄丢了：{new_700}")

    # ⑫ 撤下：从清单里真的删掉，且只删那一条
    if remove_intent("QQQ", "US", "buy", tmp) is not True:
        f.append("⑫ 撤下返回 False（清单里明明有）")
    rows12 = read_intent_rows(tmp)
    if len(rows12) != 2 or any(str(r.get("code")).upper() == "QQQ" for r in rows12):
        f.append(f"⑫ 撤下后清单里还有它：{rows12}")
    if remove_intent("NOPE", "US", "buy", tmp) is not False:
        f.append("⑫ 删一个不存在的条目应当返回 False（「本来就没有」不是错误）")
    # 写坏的文件不该让写回把整份变成空
    try:
        json.loads(tmp.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        f.append(f"⑫ 写回后清单不是合法 JSON：{e}")

    # ⑬ 条目只写「装载方认得」的键（存一堆读不懂的字段 = 幽灵配置）
    row13 = {k: v for k, v in
             __import__("deva.naja.bandit.intent_runner",
                        fromlist=["x"]).intent_row_of(new_one).items()}
    known = {"code", "market", "side", "max_wait_seconds", "min_action",
             "reading_max_age", "name", "budget", "note", "rationale",
             "confidence"}
    extra = set(row13) - known
    if extra:
        f.append(f"⑬ 写进了装载方不认的键：{sorted(extra)}")

    # ⑭ UI 渲染逻辑：不崩、列数对、统计文案在
    import deva.naja.watch.ui as ui_mod  # noqa: E402

    # ❗必须先换掉 ``put_buttons``：PyWebIO 的按钮要注册回调并等待事件，
    # 在**没有会话**的脚本模式下它会真的起一个 tornado server 并阻塞在退出处
    # —— 守卫不是被产品代码卡住，是被测试自己的交互控件卡住。
    orig_buttons = ui_mod.put_buttons
    ui_mod.put_buttons = lambda *a, **k: "<操作>"
    try:
        if not inspect.iscoroutinefunction(ui_mod.render_watch_desk):
            f.append("⑭ render_watch_desk 不是 async（页面函数不被 await 就报错）")
        desk14, box14 = _desk(ts=9000.0, asker=lambda o, c, s: (True, "测试放行"))
        desk14.declare_intent(intent, now=9000.0)
        desk14.poll(now=9001.0)
        try:
            rows14 = ui_mod._watch_rows(desk14, 9002.0)
            tk_rows14 = ui_mod._ticket_rows(desk14)
            ov14 = ui_mod._overview_html(None, desk14)
        except Exception as e:  # noqa: BLE001
            f.append(f"⑭ 页面渲染逻辑抛异常：{type(e).__name__}: {e}")
            rows14, tk_rows14, ov14 = [], [], ""
        if not rows14:
            f.append("⑭ 有守望却渲染出 0 行（表格是空的）")
        elif len(rows14[0]) != 9:
            f.append(f"⑭ 守望表列数不对：{len(rows14[0])}")
        if not tk_rows14:
            f.append("⑭ 开了票却渲染不出流水（执行记录这一栏永远是空的）")
        for word in ("守望", "开票", "Manas"):
            if word not in ov14:
                f.append(f"⑭ 概览卡缺「{word}」（页面上最关键的自证没了）")
        # 页面上必须能看出三态：放行 / 未批准 / 没人去问
        # ❗断言的是**纯文案函数**而不是表格单元格：单元格是 put_html 的 Output
        # 对象，str() 出来拿不到里面的字（会假绿）
        w14 = desk14.watches()
        summary = ui_mod._ask_summary(w14[0].to_row(9002.0)) if w14 else ""
        for mark in ("放行", "未批准", "没人去问"):
            if mark not in summary:
                f.append(f"⑭ 守望表里看不到「{mark}」计数（三态执行记录缺一角）")

        # ⑮ 滑块的可见上限必须等于内核封顶（写死基准，不读被测模块）
        try:
            slider_max = float(ui_mod.CONFIDENCE_SLIDER_MAX)
        except Exception as e:  # noqa: BLE001
            f.append(f"⑮ 读不到滑块上限：{e}")
            slider_max = 99.0
        if slider_max > CONFIDENCE_CAP + 1e-9:
            f.append(f"⑮ 滑块能拖到 {slider_max} > {CONFIDENCE_CAP}"
                     "（页面上就能把意愿拖成放行键）")

        # ⑯ 空台面：不崩，且给一句人话（「合法的空」要看得出来）
        desk16, _ = _desk()
        try:
            if ui_mod._watch_rows(desk16, 9500.0):
                f.append("⑯ 空守望台渲染出了行")
            ov16 = ui_mod._overview_html(None, desk16)
        except Exception as e:  # noqa: BLE001
            f.append(f"⑯ 空守望台渲染抛异常：{type(e).__name__}: {e}")
            ov16 = ""
        if "0 在等" not in ov16:
            f.append("⑯ 空台面的概览没写清楚「0 个在等」")
    finally:
        ui_mod.put_buttons = orig_buttons

    return f


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
        "ui.py": UI_PY, "watch.py": WATCH_PY, "desk.py": DESK_PY,
        "intent_runner.py": RUNNER_PY, "routes.py": ROUTES_PY,
        "pages.py": PAGES_PY, "ui_theme.py": THEME_PY,
    }
    for name, pattern, why in REQUIRED_RULES:
        path = lookup.get(name)
        if path is None:
            failures.append(f"[静态] 未登记的 {name}")
            continue
        if not path.exists():
            failures.append(f"[静态] 文件不存在：{name}")
            continue
        if not re.search(pattern, code_of(path)):
            failures.append(f"[静态] {name}: {why}")
    for name, pattern, why in FORBIDDEN_RULES:
        path = lookup.get(name)
        if path is None or not path.exists():
            continue
        if re.search(pattern, code_of(path)):
            failures.append(f"[禁止] {name}: {why}")
    return failures


INJECTIONS = [
    {
        "name": "❗UI 滑块上限抬到 1.0（页面上就能把意愿拖成放行键）",
        "file": UI_PY,
        "old": "CONFIDENCE_SLIDER_MAX = 0.75",
        "new": "CONFIDENCE_SLIDER_MAX = 1.0",
        "count": -1,
    },
    {
        "name": "❗调力度不走封顶（UI 变成绕过上限的后门）",
        "file": DESK_PY,
        "old": "        conf = clamp_confidence(value)",
        "new": "        conf = float(value)",
        "count": -1,
    },
    {
        "name": "❗开票后不给守望留痕（执行记录永远是 0 次）",
        "file": DESK_PY,
        "old": "        watch.record_ask(\n            granted, reason, now=now, fired_kinds=scan.fired_kinds\n        )",
        "new": "        pass",
        "count": -1,
    },
    {
        "name": "❗票不落进全局流水（撤下后查无实据）",
        "file": DESK_PY,
        "old": "            self._log_ticket(tk, t)",
        "new": "            pass",
        "count": -1,
    },
    {
        "name": "❗「没人去问」被记成「问了被否」（三态塌成两态）",
        "file": WATCH_PY,
        "old": "        if verdict is None:",
        "new": "        if False:",
        "count": -1,
    },
    {
        "name": "❗问询计数不增长（页面上永远显示 0 次）",
        "file": WATCH_PY,
        "old": "        self.asked += 1",
        "new": "        pass",
        "count": -1,
    },
    {
        "name": "❗撤下不从清单里删（重启诈尸）",
        "file": RUNNER_PY,
        "old": "    left = [r for r in rows if _row_key(r) != key]",
        "new": "    left = rows",
        "count": -1,
    },
    {
        "name": "❗写回不是原子替换（写一半崩掉会抹掉整份清单）",
        "file": RUNNER_PY,
        "old": "    os.replace(tmp, p)",
        "new": "    p.write_text(tmp.read_text(encoding='utf-8'), encoding='utf-8'); tmp.unlink()",
        "count": -1,
    },
    {
        "name": "❗认不出的守望被静默接受（UI 会以为改成功了）",
        "file": DESK_PY,
        "old": "        if watch is None:\n            raise KeyError(f\"守望 {watch_id} 不在台上，改不了它的意愿强度\")",
        "new": "        if watch is None:\n            return 0.0",
        "count": -1,
    },
    {
        "name": "❗登记不写回清单（重启就什么都没发生过）",
        "file": UI_PY,
        "old": "        upsert_intent(intent)",
        "new": "        pass",
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
                "deva.naja.watch.desk", "deva.naja.watch.ui", "deva.naja.watch",
                "deva.naja.bandit.intent_runner"):
        importlib.reload(importlib.import_module(mod))
    global W
    W = importlib.reload(W)


def exercise_injections() -> int:
    print("\n=== 负向注入：故意改坏代码，验证守卫不是摆设 ===")
    caught = 0

    # ❗自证第零步：什么都不改先重载一遍，用例必须仍然全绿。
    # 少了这一步，reload 顺序搞错时每条注入都「被捕获」—— 抓的是守卫自己的 bug。
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
                print(f"   ⚠️ 跳过（锚点缺失，是用例 bug 不是产品 bug）：{inj['name']}")
                continue
            _reload_all()
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
        print("❌ 守望台 UI 守卫发现 %d 项问题：" % len(failures))
        for x in failures:
            print("   -", x)
        return 1
    print("✅ 守望台 UI 守卫全绿（页面接线 + 执行记录 + 意愿强度可调且封顶）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
