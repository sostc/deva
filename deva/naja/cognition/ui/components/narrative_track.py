"""叙事追踪 —— 系统正在追哪些市场故事、各自处在什么阶段

2026-10-19 重写（原文件名 ``narrative_value.py``）。旧版有两个毛病：

1. **空态是假的**：取数写的是 ``engine._news_mind._narrative_tracker``（多了个
   下划线），真实属性名是 ``narrative_tracker``（``cognition/core.py`` L154）→
   AttributeError 被 ``except Exception: pass`` 吞掉，长年显示「叙事追踪器未
   就绪」，而追踪器其实一直在跑（NB 库 ``naja_narrative_tracker_state`` 里
   每分钟都在落库叙事状态）。
2. **名不副实**：它讲的是「供需 → 机会映射表 / 解决者追踪 / BUY-WATCH 推荐」，
   不是「市场在讲什么故事、热不热」。

现在主视图换成叙事榜：名称 / 阶段 / 热度 / 趋势 / 关键词 / 最近更新；
供需价值那套降级成本卡内的折叠块，不再单独占一行空态。

❗两个 tracker 实例并存：``get_narrative_tracker()`` 是事件总线订阅的单例
（event_registrar / llm_reflection 在消费），``engine._news_mind.narrative_tracker``
是认知引擎内的实例（process_record 在喂）。两者都 ingest，却往同一张 NB 表
落库互相覆盖。这里取**当前有数据的那个**，并在「数据来源诊断」折叠块里如实
列出两边条数 —— 不合并、不假装只有一个。

❗趋势数字不能直接上屏：``trend = (recent - prev) / max(prev, 1)``，prev=0 时
退化为 ``trend == recent_count``（实测 376 → 会显示 +37600%）。prev=0 一律
显示「新出现」。
"""

import html
import time

from pywebio.output import put_html

from .layout import card, fold, legend_bar, report_empty


# 阶段 → 颜色。❗这是"叙事生命周期"不是股价涨跌：
# 高潮 = 过热（红）/ 扩散 = 机会在扩散（绿）/ 萌芽 = 中性（蓝）/ 消退 = 退场（灰）
_STAGE_STYLE = {
    "高潮": ("#ef4444", "🔥"),
    "扩散": ("#22c55e", "🌱"),
    "萌芽": ("#3b82f6", "🌱"),
    "消退": ("#94a3b8", "💤"),
}
_STAGE_FALLBACK = ("#94a3b8", "❓")

_TREND_UP = "#fb923c"
_TREND_DOWN = "#60a5fa"
_TREND_FLAT = "#94a3b8"

_TOP_N = 5


def _collect_trackers(ui):
    """收集候选 tracker，返回 ``([(来源名, tracker 或 None)], [(来源名, 异常文案)])``。

    ❗不要用 ``except Exception: pass`` 把取数失败抹平 —— 旧版就是这样把
    "属性名写错"埋成"长期正常"。拿不到要落到诊断信息里。
    """
    candidates = []
    errors = []

    # 1) 认知引擎内实例（与 llm_reflection 读流动性结构的是同一个）
    try:
        candidates.append(("引擎内", getattr(ui.engine._news_mind, "narrative_tracker", None)))
    except Exception as e:
        errors.append(("引擎内", f"{type(e).__name__}: {e}"))

    # 2) 事件总线订阅的全局单例
    try:
        from deva.naja.cognition.narrative.tracker import get_narrative_tracker

        candidates.append(("事件总线", get_narrative_tracker()))
    except Exception as e:
        errors.append(("事件总线", f"{type(e).__name__}: {e}"))

    return candidates, errors


def _read_narratives(tracker):
    """从 tracker 读出活跃叙事。返回 ``(list, err_msg)``。

    ❗优先 ``get_summary()`` 而不是 ``get_active_narratives()``：后者只返回
    6 个字段，**没有 keywords 和 last_updated**，上屏就是「无关键词 · 从未更新」
    （实测出来的，不是猜的）。拿不到再回落前者。
    """
    if tracker is None:
        return [], "实例为 None"

    errors: list = []
    rows: list = []
    try:
        rows = list(tracker.get_summary(limit=200) or [])
    except Exception as e:
        errors.append(f"get_summary 失败：{type(e).__name__}")
        rows = []

    if not rows:
        try:
            rows = list(tracker.get_active_narratives() or [])
        except Exception as e:
            errors.append(f"get_active_narratives 失败：{type(e).__name__}")
            rows = []

    rows = [r for r in rows if float(r.get("attention_score") or 0.0) > 0]
    return rows, "；".join(errors)


def _score_bar(label: str, pct: int, color: str, note: str) -> str:
    return f"""
    <div style="background: {color}0f; border: 1px solid {color}26; padding: 9px 12px; border-radius: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 5px;">
            <span style="font-size: 11px; color: #94a3b8;">{label}</span>
            <span style="font-size: 14px; color: {color}; font-weight: 700;">{pct}%</span>
        </div>
        <div style="height: 5px; background: rgba(255,255,255,.06); border-radius: 3px; overflow: hidden;">
            <div style="width: {max(pct, 1)}%; height: 100%; background: {color}; border-radius: 3px;"></div>
        </div>
        <div style="font-size: 11px; color: #64748b; margin-top: 3px;">{note}</div>
    </div>
    """


def _ago(ts: float) -> str:
    """相对时间。❗ts<=0 表示从未更新过，不许显示成「刚刚」。"""
    try:
        ts = float(ts or 0)
    except (TypeError, ValueError):
        return "时间未知"
    if ts <= 0:
        return "从未更新"
    delta = max(time.time() - ts, 0)
    if delta < 60:
        return f"{int(delta)} 秒前"
    if delta < 3600:
        return f"{int(delta // 60)} 分钟前"
    if delta < 86400:
        return f"{int(delta // 3600)} 小时前"
    return f"{int(delta // 86400)} 天前"


def _trend_cell(trend, recent_count) -> str:
    """趋势单元格。

    ❗``prev_count == 0`` 时 trend 被算成 ``recent_count``（除零饱和），
    这时百分比没有意义。也不许显示成「新出现」—— 实测服务重启后 15 条叙事
    全部 prev=0（持久化只留每个叙事最近 50 条命中，``MAX_PERSIST_HITS``），
    而它们显然不是新叙事（「流动性紧张」6 小时内命中 376 次）。prev=0 的真实
    含义是**上一窗口没有可比数据**，就这么写。
    """
    try:
        t = float(trend or 0.0)
    except (TypeError, ValueError):
        t = 0.0
    try:
        recent = int(recent_count or 0)
    except (TypeError, ValueError):
        recent = 0

    if t > 0 and recent > 0 and abs(t - recent) < 1e-6:
        return (
            f'<span style="font-size: 11px; color: {_TREND_FLAT};" '
            'title="上一对比窗口无命中（服务重启后常见），无法计算变化率">↑ 无可比</span>'
        )
    if abs(t) < 0.05:
        return f'<span style="font-size: 11px; color: {_TREND_FLAT};">→ 持平</span>'
    if t > 0:
        return f'<span style="font-size: 11px; color: {_TREND_UP};">↑ {min(int(t * 100), 999)}%</span>'
    return f'<span style="font-size: 11px; color: {_TREND_DOWN};">↓ {min(int(-t * 100), 999)}%</span>'


def _narrative_row(item: dict) -> str:
    name = html.escape(str(item.get("name") or item.get("narrative") or "?"))
    stage = str(item.get("stage") or "?")
    color, icon = _STAGE_STYLE.get(stage, _STAGE_FALLBACK)
    score = float(item.get("attention_score") or 0.0)
    pct = min(int(score * 100), 100)
    keywords = [html.escape(str(k)) for k in (item.get("keywords") or [])][:3]
    kw_html = (
        " ".join(
            f'<span class="cog-pill" style="background: rgba(148,163,184,.12); '
            f'color: #94a3b8;">{k}</span>'
            for k in keywords
        )
        if keywords
        else '<span style="font-size: 11px; color: #475569;">无关键词</span>'
    )
    return f"""
    <div style="display: grid; grid-template-columns: 1.4fr 66px 1fr 78px; gap: 10px;
                align-items: center; padding: 5px 0;
                border-bottom: 1px solid rgba(255,255,255,.04);">
        <div>
            <div style="font-size: 12px; color: #e2e8f0;">{name}</div>
            <div style="line-height: 1.9; margin-top: 2px;">{kw_html}</div>
        </div>
        <div style="font-size: 11px; color: {color}; text-align: center;">
            {icon} {html.escape(stage)}
        </div>
        <div>
            <div style="display: flex; align-items: center; gap: 6px;">
                <div style="flex: 1; height: 4px; background: rgba(255,255,255,.07);
                            border-radius: 2px; overflow: hidden;">
                    <div style="width: {max(pct, 2)}%; height: 100%;
                                background: #38bdf8; border-radius: 2px;"></div>
                </div>
                <span style="font-size: 11px; color: #7b8aa0;
                             min-width: 30px; text-align: right;">{score:.2f}</span>
            </div>
            <div style="font-size: 11px; color: #475569; margin-top: 2px;">
                命中 <b style="color: #94a3b8; font-weight: 500;">{int(item.get("recent_count") or 0)}</b> 次
                · {_ago(item.get("last_updated") or item.get("last_stage_change") or 0)}
            </div>
        </div>
        <div style="text-align: right;">
            {_trend_cell(item.get("trend") or 0.0, item.get("recent_count") or 0)}
        </div>
    </div>
    """


def _saturation_note(rows: list) -> str:
    """阶段饱和提示。

    ❗实测 15 条叙事里 14 条判为「高潮」：阈值是「≥8 次命中即高潮」，而窗口
    内实际命中 47~376 次 → 阶段徽标几乎没有区分度。与其假装"都很热"，不如
    把原因写出来，让用户知道该改看热度/趋势。

    ❗判据不能写成「全部相同」：15 条里只要混进 1 条「萌芽」，整条提示就消失
    （实测踩过，第一版就是这样漏掉的）。按占比判：同阶段占 ≥80% 就算饱和。
    """
    if len(rows) < 3:
        return ""
    counts_by_stage: dict = {}
    for r in rows:
        key = str(r.get("stage") or "?")
        counts_by_stage[key] = counts_by_stage.get(key, 0) + 1
    stage, hit = max(counts_by_stage.items(), key=lambda kv: kv[1])
    if hit / len(rows) < 0.8:
        return ""

    counts = [int(r.get("recent_count") or 0) for r in rows]
    share = "全部" if hit == len(rows) else f"{hit}/{len(rows)} 条"
    return f"""
    <div style="margin-top: 8px; padding: 7px 10px; border-radius: 6px;
                background: rgba(245,158,11,.06); border-left: 2px solid rgba(245,158,11,.4);
                font-size: 11px; color: #cbd5e1; line-height: 1.7;">
        ⚠️ {share}叙事判为「{html.escape(stage)}」：阶段阈值是
        <b style="color: #f59e0b;">窗口内 ≥8 次命中</b>，而当前命中
        {min(counts)}~{max(counts)} 次 —— 阈值已饱和，<b>阶段暂时没有区分度</b>，
        请按热度与趋势分辨强弱。
    </div>
    """


def _source_diagnostics(picked_from: str, rows: list, others: list) -> str:
    lines = ""
    for name, count, err in others:
        status = (
            f'<span style="color: #22c55e;">{count} 条活跃</span>'
            if count
            else f'<span style="color: #f59e0b;">0 条（{html.escape(err or "无数据")}）</span>'
        )
        lines += f"""
        <div style="display: flex; gap: 8px; align-items: baseline; padding: 3px 0;
                    font-size: 11px; color: #94a3b8;">
            <span style="min-width: 66px;">{html.escape(name)}</span>
            <span>{status}</span>
        </div>
        """
    return (
        f'<div style="font-size: 11px; color: #64748b; line-height: 1.7; margin-bottom: 6px;">'
        f'当前展示来源：<b style="color: #b6c2d2;">{html.escape(picked_from)}</b>'
        f'（{len(rows)} 条）。两个 tracker 实例并存是历史遗留：它们各自 ingest，'
        f'却往同一张持久化表落库、互相覆盖。</div>{lines}'
    )


def _render_value_block(tracker) -> str:
    """供需价值评分 / 活跃供需机会 / 映射表 / 解决者追踪。

    ❗这块讲的是"叙事带来的供需机会"，不是叙事本身，所以整体折叠。
    """
    try:
        from deva.naja.cognition.narrative.tracker import (
            OPPORTUNITY_TYPES, RESOLVERS
        )
        po_summary = tracker.get_problem_opportunity_summary() or {}
        vm_summary = tracker.get_value_market_summary() or {}
    except Exception as e:
        return (
            '<div class="cog-empty"><b>供需价值数据不可用</b>'
            f'<span>{html.escape(str(e))}</span></div>'
        )

    problems = po_summary.get("problems", []) or []
    opportunities = po_summary.get("opportunities", []) or []
    resolvers = po_summary.get("resolvers", []) or []

    value_score = float(vm_summary.get("value_score") or 0.0)
    market_score = float(vm_summary.get("market_narrative_score") or 0.0)
    recommendation = str(vm_summary.get("recommendation") or "")
    vm_reason = str(vm_summary.get("reason") or "")

    rec_color, rec_icon = {
        "BUY": ("#22c55e", "🟢"),
        "WATCH": ("#f59e0b", "🟡"),
        "HOLD": ("#3b82f6", "🔵"),
        "SELL": ("#ef4444", "🔴"),
        "AVOID": ("#ef4444", "🔴"),
    }.get(recommendation, ("#94a3b8", "⚪"))

    value_color = "#22c55e" if value_score >= 0.6 else ("#f59e0b" if value_score >= 0.3 else "#94a3b8")
    market_color = "#3b82f6" if market_score >= 0.6 else ("#f59e0b" if market_score >= 0.3 else "#94a3b8")

    block = f"""
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
        {_score_bar("💎 供需价值", min(int(value_score * 100), 100), value_color, "主动价值发现")}
        {_score_bar("📊 市场叙事", min(int(market_score * 100), 100), market_color, "市场情绪参考")}
    </div>
    """
    if recommendation:
        block += (
            '<div style="margin-top: 8px; font-size: 11px; color: #94a3b8;">'
            f'推荐 <b style="color: {rec_color};">{rec_icon} {html.escape(recommendation)}</b></div>'
        )
    if vm_reason:
        block += (
            '<div style="margin-top: 6px; padding: 6px 9px; border-radius: 6px;'
            ' background: rgba(255,255,255,.02); font-size: 11px; color: #86efac;'
            f' line-height: 1.6;">{html.escape(vm_reason)}</div>'
        )

    if not opportunities:
        block += (
            '<div class="cog-empty" style="margin-top: 10px;">'
            '<b>暂无活跃供需机会</b><span>扫描中</span></div>'
        )
    else:
        items = ""
        for opp in opportunities:
            cat = html.escape(str(opp.get("category", "?")))
            opp_name = html.escape(str(opp.get("opportunity", "?")))
            desc = html.escape(str(opp.get("description", "")))
            badges = " ".join(
                f'<span class="cog-pill" style="background: rgba(34,197,94,.15); '
                f'color: #22c55e;">{html.escape(str(b))}</span>'
                for b in (opp.get("beneficiaries") or [])[:6]
            )
            items += f"""
            <div style="padding: 7px 9px; border-bottom: 1px solid rgba(255,255,255,.04);">
                <div style="font-size: 11px; margin-bottom: 3px;">
                    <span style="color: #f59e0b; font-weight: 600;">⚡ {cat}</span>
                    <span style="color: #22c55e;"> → {opp_name}</span>
                </div>
                <div style="font-size: 11px; color: #64748b; line-height: 1.5;">{desc}</div>
                <div style="line-height: 2;">{badges}</div>
            </div>
            """
        block += (
            '<div style="margin-top: 10px; font-size: 11px; color: #94a3b8; '
            f'margin-bottom: 5px;">🎯 活跃供需机会（{len(opportunities)} 个）</div>'
            '<div style="background: rgba(34,197,94,.04); border: 1px solid rgba(34,197,94,.1);'
            f' border-radius: 8px; overflow: hidden;">{items}</div>'
        )

    if OPPORTUNITY_TYPES:
        rows_html = ""
        for problem_type, info in OPPORTUNITY_TYPES.items():
            is_active = any(p.get("category") == problem_type for p in problems)
            dot = '<span style="color: #22c55e;">●</span>' if is_active else '<span style="color: #475569;">○</span>'
            bens = ", ".join((info.get("beneficiaries") or [])[:3])
            rows_html += f"""
            <div style="display: grid; grid-template-columns: 18px 1.6fr 1.3fr 1.8fr; gap: 6px;
                        padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,.03);
                        align-items: center; font-size: 11px;">
                <div style="text-align: center;">{dot}</div>
                <div style="color: #e2e8f0;">{html.escape(str(problem_type))}</div>
                <div style="color: #22c55e;">{html.escape(str(info.get('opportunity', '')))}</div>
                <div style="color: #64748b; overflow: hidden; text-overflow: ellipsis;
                            white-space: nowrap;">{html.escape(bens)}</div>
            </div>
            """
        block += fold(
            "供需 → 机会 映射表", f"<div>{rows_html}</div>",
            meta=f"{len(OPPORTUNITY_TYPES)} 类 · ● 为当前命中",
        )

    if RESOLVERS:
        cards_html = ""
        for name, info in RESOLVERS.items():
            is_active = any(r.get("name") == name for r in resolvers)
            border = "rgba(34,197,94,.25)" if is_active else "rgba(255,255,255,.06)"
            badges = " ".join(
                f'<span style="font-size: 11px; color: #94a3b8;">{html.escape(str(k))}: '
                f'<span style="color: #f59e0b;">{html.escape(str(v))}</span></span>'
                for k, v in (info.get("progress") or {}).items()
            )
            cards_html += f"""
            <div style="background: rgba(255,255,255,.02); border: 1px solid {border};
                        padding: 6px 8px; border-radius: 6px;">
                <div style="font-size: 11px; color: #e2e8f0; font-weight: 600;">
                    {html.escape(str(name))}</div>
                <div style="font-size: 11px; color: #64748b; margin: 2px 0 4px;">
                    🔧 {html.escape(str(info.get('problem', '')))} → {html.escape(str(info.get('opportunity', '')))}</div>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">{badges}</div>
            </div>
            """
        block += fold(
            "解决者追踪",
            f'<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">{cards_html}</div>',
        )

    return block


def render_narrative_track(ui):
    """渲染「叙事追踪」卡（②思考节）"""
    trackers, errors = _collect_trackers(ui)

    picked, picked_from, rows = None, "", []
    others = []
    for name, tracker in trackers:
        got, err = _read_narratives(tracker)
        if got and picked is None:
            picked, picked_from, rows = tracker, name, got
        else:
            others.append((name, len(got), err))

    # ── 三态空态：❗「拿不到 tracker」≠「tracker 有但 0 条」 ──
    if picked is None:
        have_instance = any(t is not None for _, t in trackers)
        if not have_instance:
            detail = "；".join(f"{n} {e}" for n, e in errors)
            report_empty(
                "📖", "叙事追踪", "两个 tracker 实例都没拿到",
                detail or "引擎内实例与事件总线单例均未初始化",
            )
        else:
            detail = "；".join(f"{n}: {e}" for n, _, e in others if e)
            report_empty(
                "📖", "叙事追踪", "追踪器已接入但窗口内无活跃叙事",
                detail or "尚未积累到衰减窗口内的命中",
            )
        return

    rows = sorted(rows, key=lambda r: float(r.get("attention_score") or 0.0), reverse=True)
    top, rest = rows[:_TOP_N], rows[_TOP_N:]

    body = "".join(_narrative_row(r) for r in top)
    if rest:
        body += fold(
            f"其余 {len(rest)} 条叙事",
            "".join(_narrative_row(r) for r in rest),
            meta="按热度排序",
        )

    body += _saturation_note(rows)

    # ❗阶段徽标用了风险色，必须带图例，否则会被按股价涨跌读反
    body += (
        '<div style="margin-top: 10px;">'
        + legend_bar()
        + '<div style="font-size: 11px; color: #475569; margin-top: 4px;">'
        "阶段色标是叙事生命周期（高潮＝过热），不是股价涨跌；"
        "热度条（蓝）＝注意力强度，与风险无关；趋势 ↑ 升温 / ↓ 降温；"
        "「↑ 无可比」= 上一窗口无命中（服务重启后常见），不是新叙事。</div>"
        "</div>"
    )

    body += fold(
        "数据来源诊断",
        _source_diagnostics(picked_from, rows, others),
        meta="两个 tracker 实例",
    )

    # ── 供需价值发现（原「叙事价值发现」主体，降级为折叠） ──
    value_block = _render_value_block(picked)
    if value_block:
        body += fold("💎 供需价值发现（原叙事价值）", value_block)

    # 头部直接给阶段分布（10 高潮 / 3 扩散 / 2 消退）：Top5 全是高潮时，
    # 用户不然会以为"所有叙事都在高潮"，而分布只占一行、不加高度。
    stage_dist: dict = {}
    for r in rows:
        key = str(r.get("stage") or "?")
        stage_dist[key] = stage_dist.get(key, 0) + 1
    dist = " · ".join(
        f"{n} {s}" for s, n in sorted(stage_dist.items(), key=lambda kv: -kv[1])
    )

    meta = f"{dist} ｜ 共 {len(rows)} 条 · 来源 {html.escape(picked_from)}"
    put_html(card(title="叙事追踪", icon="📖", meta=meta, body=body))
