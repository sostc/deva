"""守望台 UI —— 让「我在等什么、问过几次、为什么还没买」看得见。

这个页面回答的四句话
====================
1. **现在在等什么**：每个守望一句话「在等什么 / 等多久了 / 还剩多久」。
2. **问过没有**：问了几次、放行几次、被否几次、几次**压根没人去问**。
3. **最近怎么说**：最近一次决策中心给的理由（hold 就写 hold）。
4. **我想改主意**：登记新意向、调意愿强度、撤下。

❗三条纪律（与内核同源，UI 不许成为绕过它们的后门）
==================================================
* **页面上没有任何下单按钮**。守望台只负责「等」和「问」，批不批在决策中心，
  真落单还需要另一道显式授权。这里的每个按钮都只改愿望，不改账户。
* **意愿强度有硬顶**（0.75）。滑块拖到底也只是「更有分量」，
  ❗不是放行键 —— 上限由 :func:`~.intent.clamp_confidence` 兜住，UI 传 100 也没用。
* **必须回答「等到什么时候为止」**。表单里的「最多等多少小时」是必填项，
  不给就登记不上：一个永不过期的想法和一条死掉的线程长得一模一样。

落盘与在台
==========
登记/改力度/撤下会同时写回声明式清单（``~/.naja/intents.json``）与运行中的
守望台。只改内存的话，服务一重启页面就「什么都没发生过」—— 那正是本仓库
最常犯的「UI 写好了、链路没接」。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from pywebio.input import (
    NUMBER, input, input_group, select, slider, textarea,
)
from pywebio.output import (
    close_popup, popup, put_buttons, put_collapse, put_column,
    put_html, put_row, put_table, put_text, toast, use_scope,
)

log = logging.getLogger(__name__)

__all__ = ["render_watch_desk"]

_SIDE_ZH = {"buy": "买入", "sell": "卖出", "trim": "减仓"}
_STATE_ZH = {"armed": "⏳ 在等", "triggered": "🔔 待问", "settled": "🏁 已结算"}
_EMPTY_NOTE = "（守望台是空的 —— 想买想卖就点上面的「登记意向」）"

#: 滑块上限。**写死 0.75 而不是读常量**：页面上写多少，就是用户能拖到多少，
#: 它必须和内核封顶是同一个数，且不随内核改动漂移。
CONFIDENCE_SLIDER_MAX = 0.75
CONFIDENCE_DEFAULT_SLIDER = 0.6
CONFIDENCE_STEP = 0.05


# ---------------------------------------------------------------- 取数

def _get_runner():
    """取意向运行器。服务没起/没接线时返回 None，**不抛** ——
    页面要能显示「守望台没在跑」，而不是整页 500。"""
    try:
        from ..bandit.intent_runner import get_intent_runner

        return get_intent_runner()
    except Exception as e:  # noqa: BLE001
        log.warning("[WatchUI] 取意向运行器失败: %s:%s", type(e).__name__, e)
        return None


def _desk_of(runner):
    """取桌面。运行器没启动也能读（desk 是惰性装配的）。"""
    try:
        return runner.desk
    except Exception as e:  # noqa: BLE001
        log.warning("[WatchUI] 取守望台桌面失败: %s:%s", type(e).__name__, e)
        return None


def _fmt_dur(sec: Optional[float]) -> str:
    """秒 → 「3.2h / 45m / 30s」。负数要看得出来是超时。"""
    if sec is None:
        return "-"
    s = float(sec)
    sign = "-" if s < 0 else ""
    s = abs(s)
    if s >= 3600 * 24:
        return f"{sign}{s / 86400:.1f}d"
    if s >= 3600:
        return f"{sign}{s / 3600:.1f}h"
    if s >= 60:
        return f"{sign}{s / 60:.0f}m"
    return f"{sign}{s:.0f}s"


def _fmt_ts(ts: Optional[float]) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return "-"


def _h(html: str):
    """表格单元格里的 HTML。

    ❗``put_table`` 的字符串单元格是按**纯文本**渲染的（``<b>x</b>`` 会原样显示
    标签），想排版必须显式包一层 ``put_html``。
    """
    return put_html(html)


def _cut(text: Any, n: int = 60) -> str:
    s = str(text or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _conf_text(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


# ---------------------------------------------------------------- 渲染块

def _overview_html(runner, desk) -> str:
    """顶部概览卡。缺什么就写「缺什么」，不用 0 蒙混。"""
    running = bool(runner is not None and getattr(runner, "running", False))
    dot = "🟢" if running else "🔴"
    if runner is None:
        run_text = "运行器拿不到（模块未接线）"
    else:
        run_text = "轮询中" if running else "未启动"
    poll = getattr(runner, "_poll_seconds", None)
    beat = getattr(runner, "_beat_sec", None)

    if desk is None:
        return (
            "<div style='background:#1e293b;border:1px solid #334155;border-radius:"
            "10px;padding:16px;color:#e2e8f0;'>"
            f"<b>{dot} 守望台</b> —— {run_text}"
            "<div style='color:#fca5a5;margin-top:8px;'>"
            "桌面拿不到，页面上的数字无从谈起（看 naja.log 找装配失败的原因）"
            "</div></div>"
        )

    snap = desk.snapshot()
    manas = snap.get("manas") or {}
    unanswered = int(snap.get("unanswered") or 0)
    asker = "✅ 已接决策中心" if snap.get("asker_attached") else (
        "⚠️ 没接执行器（票开出去没人领）"
    )
    warn = (
        f"<div style='color:#fca5a5;margin-top:8px;'>⚠️ {unanswered} 张票没人消费"
        " —— 这不是「策略在观望」，是链路断了</div>"
        if unanswered else ""
    )
    return (
        "<div style='background:#1e293b;border:1px solid #334155;border-radius:10px;"
        "padding:16px;color:#e2e8f0;display:flex;flex-wrap:wrap;gap:24px;'>"
        f"<div><div style='color:#94a3b8;font-size:12px;'>运行器</div>"
        f"<b>{dot} {run_text}</b>"
        f"<div style='color:#94a3b8;font-size:12px;margin-top:4px;'>"
        f"轮询 {poll or '-'}s / 心跳 {beat or '-'}s</div></div>"
        f"<div><div style='color:#94a3b8;font-size:12px;'>守望</div>"
        f"<b>{snap.get('armed', 0)} 在等 · {snap.get('triggered', 0)} 待问 · "
        f"{snap.get('settled', 0)} 已结算</b>"
        f"<div style='color:#94a3b8;font-size:12px;margin-top:4px;'>"
        f"共扫 {snap.get('polls', 0)} 轮 / 判据看不清 "
        f"{snap.get('unknown_scans', 0)} 次</div></div>"
        f"<div><div style='color:#94a3b8;font-size:12px;'>Manas 镜头</div>"
        f"<b>读数 {manas.get('reads', 0)} 次 / 看不清 "
        f"{manas.get('unknown_reads', 0)} 次</b>"
        f"<div style='color:#94a3b8;font-size:12px;margin-top:4px;'>"
        f"{_cut(manas.get('last_unknown_reason') or '最近都看得清', 40)}</div></div>"
        f"<div><div style='color:#94a3b8;font-size:12px;'>开票</div>"
        f"<b>{snap.get('consumed', 0)} 张已问</b>"
        f"<div style='color:#94a3b8;font-size:12px;margin-top:4px;'>{asker}</div></div>"
        f"{warn}"
        "</div>"
    )


def _ask_summary(row: Dict[str, Any]) -> str:
    """一行守望的问询统计文案：**数据不与渲染混在一起**，守卫可以直接断言它。

    ❗三个符号各有含义：✓ 放行 / ✗ 问了但没批 / ? 票开出去没人去问。
    「?」不是「策略在观望」，是链路断了，页面上必须单独看得见。
    """
    return (
        f"{row.get('asked', 0)} 次 · 放行 {row.get('granted_count', 0)}"
        f" · 未批准 {row.get('denied_count', 0)}"
        f" · 没人去问 {row.get('unanswered_count', 0)}"
    )


def _watch_rows(desk, now: float) -> List[List[Any]]:
    """表格行。**数据一律来自 Watch.to_row**，避免 UI 自己另算一套口径。"""
    rows: List[List[Any]] = []
    for watch in desk.watches():
        r = watch.to_row(now)
        side = str(watch.objective.params.get("side") or "-")
        name14 = str(watch.objective.params.get("name") or "").strip()
        who14 = (
            f"{_cut(name14, 18)} · {watch.objective.market}" if name14
            else watch.objective.market
        )
        conf = watch.objective.params.get("confidence")
        g, d, u = (int(r.get(k, 0) or 0) for k in
                   ("granted_count", "denied_count", "unanswered_count"))
        asks = (
            f"{_ask_summary(r).split(' · ')[0]}<br>"
            f"<span style='color:#4ade80'>✓{g}</span> · "
            f"<span style='color:#f87171'>✗{d}</span> · "
            f"<span style='color:#fbbf24'>?{u}</span>"
        )
        if u:
            asks += ("<div style='color:#fbbf24;font-size:12px'>"
                     "有票没人去问 —— 查日志</div>")
        rows.append([
            _h(
                f"<b>{watch.objective.subject}</b> "
                f"{_SIDE_ZH.get(side, side)}"
                # ❗没登记名称时只显示市场，别拿市场顶替名字成「US · US」
                f"<div style='color:#94a3b8;font-size:12px;'>{who14}</div>"
            ),
            _h(
                f"<b>{_conf_text(conf)}</b>"
                f"<div style='color:#94a3b8;font-size:12px;'>"
                f"{'手改' if watch.objective.params.get('confidence_explicit') else '默认'}"
                f"</div>"
            ),
            _STATE_ZH.get(r.get("state"), r.get("state")),
            _cut(r.get("waiting_for"), 46),
            _h(
                f"已等 {_fmt_dur(r.get('age_sec'))}<br>"
                f"剩 {_fmt_dur(r.get('remaining_sec'))}"
            ),
            f"扫 {r.get('scans', 0)} / 触发 {r.get('fires', 0)}",
            _h(asks),
            _cut(r.get("last_reason") or "（还没问过）", 46),
            put_buttons(
                ["调力度", "记录", "撤下"],
                onclick=[
                    lambda w=watch: _on_tune(w),
                    lambda w=watch: _on_history(w),
                    lambda w=watch: _on_drop(w),
                ],
                small=True,
            ),
        ])
    return rows


def _ticket_rows(desk, limit: int = 20) -> List[List[Any]]:
    rows: List[List[Any]] = []
    for tk in desk.ticket_log(limit):
        color = (
            "#4ade80" if tk.get("granted") is True
            else ("#fbbf24" if tk.get("granted") is None else "#f87171")
        )
        rows.append([
            _fmt_ts(tk.get("ts")),
            f"{tk.get('subject', '')} {_SIDE_ZH.get(tk.get('side') or '', '')}".strip(),
            _conf_text(tk.get("confidence")),
            _h(f"<span style='color:{color}'>{tk.get('verdict', '')}</span>"),
            _cut(tk.get("fired") and "、".join(tk["fired"]) or "-", 28),
            _cut(tk.get("reason"), 70),
        ])
    return rows


# ---------------------------------------------------------------- 交互

def _refresh():
    """重画表格与流水。callback 里只清 scope 再画，整页不闪。"""
    render_body()


async def _on_tune(watch) -> None:
    """改一个守望的意愿强度。

    ❗**必须是 async**：页面跑在协程会话里，``input_group`` 在那里返回的是
    协程而不是结果。同步回调里直接调用它，拿到的是一个没人 await 的协程 ——
    表单永远不弹，日志里只留一句 ``never awaited``。
    """
    wid = watch.watch_id
    desk = _desk_of(_get_runner())
    if desk is None:
        toast("守望台桌面不可用", color="error")
        return
    cur = float(watch.objective.params.get("confidence") or CONFIDENCE_DEFAULT_SLIDER)
    # ❗说明写在 label / help_text 里：**input_group 的每一项都必须带 name**，
    # 往里塞 put_html 会直接 assert 失败（整页 500）。
    res = await input_group(
        f"调整意愿强度 —— {_cut(watch.objective.describe(), 40)}（现在 {cur:.2f}）",
        [
            slider(
                "意愿强度", name="conf", value=cur, min_value=0.0,
                max_value=CONFIDENCE_SLIDER_MAX, step=CONFIDENCE_STEP,
                required=True,
                help_text=(f"上限 {CONFIDENCE_SLIDER_MAX:.2f}，够不到放行阈值 1.0"
                           " —— 意愿只是加权，不是放行键"),
            ),
        ],
    )
    if res is None:
        return
    try:
        got = desk.set_confidence(wid, res["conf"])
    except KeyError as e:
        toast(f"没改成：{e}", color="error")
        return
    _persist_confidence(watch)
    toast(f"已调到 {got:.2f}（封顶 {CONFIDENCE_SLIDER_MAX:.2f}）", color="success")
    _refresh()


def _persist_confidence(watch) -> None:
    """把台上的新强度写回声明式清单。写失败要喊 —— 否则重启就悄悄回到旧值。"""
    try:
        from ..bandit.intent_runner import upsert_intent
        from .intent import Intent

        p = watch.objective.params
        intent = Intent(
            code=watch.objective.subject,
            market=watch.objective.market,
            side=str(p.get("side") or "buy"),
            name=str(p.get("name") or ""),
            budget=p.get("budget"),
            max_wait_seconds=float(watch.max_wait_seconds or 0.0),
            rationale=str(p.get("rationale") or ""),
            confidence=p.get("confidence"),
        )
        upsert_intent(intent)
    except Exception as e:  # noqa: BLE001
        log.warning("[WatchUI] 写回意向清单失败（台上已生效，重启会丢）: %s:%s",
                    type(e).__name__, e)
        toast(f"台上已生效，但写回清单失败：{type(e).__name__}", color="warn")


def _on_history(watch) -> None:
    """弹一个守望自己的执行记录。"""
    rows = [
        [_fmt_ts(a.get("ts")), a.get("verdict", ""), _cut(a.get("fired") and
         "、".join(a["fired"]) or "-", 28), _cut(a.get("reason"), 90)]
        for a in watch.ask_history(10)
    ]
    head = (
        f"<div style='color:#94a3b8;font-size:13px;margin-bottom:8px'>"
        f"{watch.watch_id}<br>共问 {watch.asked} 次：放行 "
        f"{watch.granted_count} · 未批准 {watch.denied_count} · 没人去问 "
        f"{watch.unanswered_count}</div>"
    )
    popup(
        "执行记录",
        [
            put_html(head),
            put_table(rows, header=["时间", "结论", "成立的机会", "决策中心怎么说"])
            if rows else put_text("还没问过 —— 一次都没去问，和「问了被否」是两回事"),
            put_buttons(["关闭"], onclick=lambda: close_popup(), small=True),
        ],
    )


def _on_drop(watch) -> None:
    """撤下：结算成 abandoned，并从清单里删掉。"""
    wid = watch.watch_id
    runner = _get_runner()
    desk = _desk_of(runner)
    if desk is None:
        toast("守望台桌面不可用", color="error")
        return

    def _do():
        desk.settle(wid, "abandoned", "人工在守望台页面撤下")
        try:
            from ..bandit.intent_runner import remove_intent

            remove_intent(
                watch.objective.subject,
                watch.objective.market,
                str(watch.objective.params.get("side") or "buy"),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[WatchUI] 撤下时清清单失败: %s:%s", type(e).__name__, e)
        close_popup()
        toast(f"已撤下 {wid}", color="success")
        _refresh()

    popup(
        "撤下这个守望？",
        [
            put_html(
                f"<div style='color:#e2e8f0'>{_cut(watch.objective.describe(), 80)}"
                f"<br><span style='color:#94a3b8;font-size:13px'>"
                f"撤下后不再等待，也会从意向清单里删掉（重启不会复活）。</span></div>"
            ),
            put_buttons(["确认撤下", "取消"], onclick=[_do, lambda: close_popup()],
                        small=True),
        ],
    )


async def _on_new():
    """登记一个新意向：写进守望台 + 写回清单。

    ❗async 的理由同 :func:`_on_tune`：协程会话里 ``input_group`` 必须 await。
    """
    res = await input_group("登记意向", [
        input("代码", name="code", required=True, placeholder="如 NVDA / 00700 / 600519"),
        input("名称（可选）", name="name", placeholder="英伟达"),
        select("市场", name="market", options=[
            {"label": "美股 US", "value": "US"},
            {"label": "港股 HK", "value": "HK"},
            {"label": "A 股 CN", "value": "CN"},
        ], value="US", required=True),
        select("方向", name="side", options=[
            {"label": "买入", "value": "buy"},
            {"label": "卖出", "value": "sell"},
            {"label": "减仓", "value": "trim"},
        ], value="buy", required=True),
        input("预算（可选，留空交给决策中心定量）", name="budget", type=NUMBER),
        input("最多等多少小时", name="hours", type=NUMBER, value=72.0, required=True),
        slider("意愿强度", name="conf", value=CONFIDENCE_DEFAULT_SLIDER,
               min_value=0.0, max_value=CONFIDENCE_SLIDER_MAX,
               step=CONFIDENCE_STEP, required=True,
               help_text="默认 0.60（高于系统自动补仓的 0.50）；封顶 0.75，够不到放行阈值"),
        textarea("理由（可选）", name="rationale",
                 placeholder="为什么想买 / 想卖 —— 几个月后回看得想得起来"),
    ])
    if res is None:
        return

    runner = _get_runner()
    desk = _desk_of(runner)
    if desk is None:
        toast("守望台桌面不可用，意向没登记上", color="error")
        return

    try:
        from .intent import BuyIntent, SellIntent

        factory = SellIntent if res["side"] in ("sell", "trim") else BuyIntent
        intent = factory(
            str(res["code"]).strip(),
            str(res["market"]).strip(),
            max_wait_seconds=float(res["hours"]) * 3600.0,
            name=str(res.get("name") or "").strip(),
            budget=(float(res["budget"]) if res.get("budget") else None),
            rationale=str(res.get("rationale") or "").strip(),
            confidence=res.get("conf"),
        )
    except Exception as e:  # noqa: BLE001 - 表单填坏要把原因说给人听
        log.info("[WatchUI] 意向构造失败: %s:%s", type(e).__name__, e)
        toast(f"登记失败：{type(e).__name__}: {_cut(e, 80)}", color="error")
        return

    try:
        wid = desk.declare_intent(intent).watch_id
    except Exception as e:  # noqa: BLE001
        log.warning("[WatchUI] 意向没挂上守望台: %s:%s", type(e).__name__, e,
                    exc_info=True)
        toast(f"没挂上台：{type(e).__name__}: {_cut(e, 80)}", color="error")
        return

    try:
        from ..bandit.intent_runner import upsert_intent

        upsert_intent(intent)
    except Exception as e:  # noqa: BLE001
        log.warning("[WatchUI] 意向已上台但没写进清单: %s:%s", type(e).__name__, e)
        toast(f"已进守望台，但写清单失败（重启会丢）：{type(e).__name__}", color="warn")
        _refresh()
        return

    toast(f"已进守望台：{wid}", color="success")
    _refresh()


def _on_tick():
    """手工推一轮。真跑起来的是常驻线程，这里只是「现在就问一次」。"""
    runner = _get_runner()
    if runner is None:
        toast("运行器不可用", color="error")
        return
    try:
        tickets = runner.tick()
    except Exception as e:  # noqa: BLE001
        log.warning("[WatchUI] 手工扫一轮失败: %s:%s", type(e).__name__, e,
                    exc_info=True)
        toast(f"扫一轮失败：{type(e).__name__}", color="error")
        return
    toast(f"扫完一轮，开出 {len(tickets)} 张票", color="success")
    _refresh()


# ---------------------------------------------------------------- 页面

def render_body():
    """画表格 + 流水。**整页重画只走这两个 scope**，概览与按钮不动。"""
    runner = _get_runner()
    desk = _desk_of(runner)
    now = time.time()

    with use_scope("watch_table", clear=True):
        if desk is None:
            put_text("守望台桌面拿不到 —— 页面上没有可显示的数字。")
        else:
            rows = _watch_rows(desk, now)
            if not rows:
                put_text(_EMPTY_NOTE)
            else:
                put_table(rows, header=[
                    "标的 / 方向", "意愿强度", "状态", "在等什么", "时间",
                    "扫描", "问询记录", "最近结论", "操作",
                ])

    with use_scope("watch_log", clear=True):
        if desk is None:
            return
        rows = _ticket_rows(desk)
        if not rows:
            put_text("还没有开过票 —— 要么是机会一直没成立，要么是该扫的没扫。")
        else:
            put_table(rows, header=[
                "时间", "标的", "强度", "结论", "成立的机会", "决策中心怎么说",
            ])


async def render_watch_desk(ctx: dict = None):
    """守望台页面入口（``/watchdesk``）。"""
    runner = _get_runner()
    desk = _desk_of(runner)

    # 顶部导航是 fixed 的，页面第一个元素会被它压住 —— 留一段空白
    put_html("<div style='height:64px'></div>")
    put_html("<h2 style='margin-bottom:4px'>🌗 守望台</h2>")
    put_html(
        "<div style='color:#94a3b8;font-size:13px;margin-bottom:16px'>"
        "想买 / 想卖但还没下手的，都挂在这里等机会。机会成立只买到「去问决策中心一次」的资格，"
        "批不批在决策中心，这里<b>没有任何下单按钮</b>。</div>"
    )

    put_row([
        put_column([
            put_buttons(["🔄 刷新", "⚡ 立即扫一轮", "➕ 登记意向"],
                        onclick=[_refresh, _on_tick, _on_new], small=True),
        ]),
    ], size="auto 1fr")

    put_text("")

    with use_scope("watch_overview", clear=True):
        put_html(_overview_html(runner, desk))

    put_text("")
    put_html("<h4 style='margin:12px 0 4px'>在等的守望</h4>")
    render_body()

    put_text("")
    with use_scope("watch_help"):
        put_collapse("这个页面怎么读", [
            put_html(
                "<div style='color:#94a3b8;font-size:13px;line-height:1.7'>"
                "· <b>在等</b>：机会还没成立，守望安静地等着；<b>待问</b>：刚成立，正要去问决策中心。<br>"
                "· <b>问询记录</b>：✓ 放行 / ✗ 问了但没批 / ? 票开出去<b>没人去问</b>。"
                "「?」是链路断了，跟策略在观望是两回事，看到它就要去查日志。<br>"
                "· <b>意愿强度</b>：人的主动意愿，只影响决策中心的加权，封顶 0.75 —— 拖到底也不是放行键。<br>"
                "· <b>最多等多少小时</b>：必填。到期没等到就结算成 expired，"
                "「等了三天没进场」和「从没想过要买」在复盘时是两件事。"
                "</div>"
            ),
                ], open=False)

    # ❗这里刻意**没有**自动 reload：页面上有弹窗（调力度 / 登记意向），
    # 定时整页刷新会把人填到一半的表单冲掉，而「看得见它在动」已经有
    # 「刷新」按钮和日志里的心跳两处保障了。
