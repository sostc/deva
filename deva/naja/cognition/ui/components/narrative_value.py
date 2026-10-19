"""Narrative Value 组件 —— 叙事价值发现

展示 OPPORTUNITY_TYPES 供需映射表（token 供给不足→扩产机会等）、
当前检测到的供需问题和投资机会、受益标的列表、RESOLVERS 解决者进展。

2026-10-19 重排：空态从 230px 的大卡片压成一行；映射表与解决者追踪属于
"全景解释"，默认折叠；删掉「供需问题 → 投资机会 → 受益标的 → 解决者追踪」
这类模块说明行。
"""

import html

from pywebio.output import put_html

from .layout import card, fold, report_empty


_REC_CONFIG = {
    "BUY": ("#22c55e", "🟢"),
    "WATCH": ("#f59e0b", "🟡"),
    "HOLD": ("#3b82f6", "🔵"),
    "SELL": ("#ef4444", "🔴"),
    "AVOID": ("#ef4444", "🔴"),
}


def _score_bar(label: str, pct: int, color: str, note: str) -> str:
    return f"""
    <div style="background: {color}0f; border: 1px solid {color}26; padding: 9px 12px; border-radius: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 5px;">
            <span style="font-size: 11px; color: #94a3b8;">{label}</span>
            <span style="font-size: 14px; color: {color}; font-weight: 700;">{pct}%</span>
        </div>
        <div style="height: 5px; background: rgba(255,255,255,.06); border-radius: 3px; overflow: hidden;">
            <div style="width: {pct}%; height: 100%; background: {color}; border-radius: 3px;"></div>
        </div>
        <div style="font-size: 11px; color: #64748b; margin-top: 3px;">{note}</div>
    </div>
    """


def render_narrative_value(ui):
    has_data = False
    tracker = None
    po_summary = None
    vm_summary = None
    OPPORTUNITY_TYPES = None
    RESOLVERS = None

    try:
        tracker = ui.engine._news_mind._narrative_tracker
    except Exception:
        pass

    if tracker:
        try:
            from deva.naja.cognition.narrative.tracker import (
                OPPORTUNITY_TYPES, RESOLVERS
            )
            po_summary = tracker.get_problem_opportunity_summary()
            vm_summary = tracker.get_value_market_summary()
            problems = po_summary.get("problems", [])
            opportunities = po_summary.get("opportunities", [])
            has_data = (len(problems) > 0 or len(opportunities) > 0)
        except Exception:
            pass

    vm_recommendation = "WATCH"
    rec_color, rec_icon = "#94a3b8", "⚪"
    if vm_summary:
        vm_recommendation = vm_summary.get("recommendation", "WATCH")
        rec_color, rec_icon = _REC_CONFIG.get(vm_recommendation, ("#94a3b8", "⚪"))

    meta = f'推荐 <b style="color: {rec_color};">{rec_icon} {vm_recommendation}</b>'

    # ── 空态 ──
    if not tracker:
        report_empty("💎", "叙事价值发现", "叙事追踪器未就绪", "等待系统初始化")
        return

    if not po_summary or not vm_summary:
        report_empty("💎", "叙事价值发现", "等待数据流入", "尚未积累到可评估样本")
        return

    if not has_data:
        report_empty("💎", "叙事价值发现", "暂无活跃供需机会", "扫描中")
        return

    problems = po_summary.get("problems", [])
    opportunities = po_summary.get("opportunities", [])
    resolvers = po_summary.get("resolvers", [])

    value_score = vm_summary.get("value_score", 0)
    market_score = vm_summary.get("market_narrative_score", 0)
    vm_reason = vm_summary.get("reason", "")

    value_pct = min(int(value_score * 100), 100) if value_score else 0
    market_pct = min(int(market_score * 100), 100) if market_score else 0
    value_color = "#22c55e" if value_score >= 0.6 else ("#f59e0b" if value_score >= 0.3 else "#94a3b8")
    market_color = "#3b82f6" if market_score >= 0.6 else ("#f59e0b" if market_score >= 0.3 else "#94a3b8")

    body = f"""
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
        {_score_bar("💎 供需价值", value_pct, value_color, "Dynamics · 主动价值发现")}
        {_score_bar("📊 市场叙事", market_pct, market_color, "Sentiment · 市场情绪参考")}
    </div>
    """

    if vm_reason:
        body += f"""
        <div style="margin-top: 10px; background: rgba(34,197,94,.05);
                    border-left: 3px solid rgba(34,197,94,.35); padding: 7px 10px;
                    border-radius: 0 6px 6px 0; font-size: 11px; color: #86efac; line-height: 1.6;">
            {html.escape(str(vm_reason))}
        </div>
        """

    # ── 活跃供需机会 ──
    if opportunities:
        items = ""
        for opp in opportunities:
            cat = html.escape(str(opp.get("category", "?")))
            opp_name = html.escape(str(opp.get("opportunity", "?")))
            beneficiaries = opp.get("beneficiaries", []) or []
            desc = html.escape(str(opp.get("description", "")))
            badges = " ".join(
                f'<span class="cog-pill" style="background: rgba(34,197,94,.15); color: #22c55e;">{html.escape(str(b))}</span>'
                for b in beneficiaries[:6]
            )
            items += f"""
            <div style="padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,.04);">
                <div style="display: flex; justify-content: space-between; gap: 8px; margin-bottom: 4px;">
                    <span style="font-size: 11px; color: #f59e0b; font-weight: 600;">⚡ {cat}</span>
                    <span style="font-size: 11px; color: #22c55e;">→ {opp_name}</span>
                </div>
                <div style="font-size: 11px; color: #64748b; margin-bottom: 5px; line-height: 1.5;">{desc}</div>
                <div style="line-height: 2;">{badges}</div>
            </div>
            """
        body += f"""
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06);">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">
                🎯 活跃供需机会 <span style="color: #475569;">({len(opportunities)} 个)</span>
            </div>
            <div style="background: rgba(34,197,94,.04); border: 1px solid rgba(34,197,94,.1);
                        border-radius: 8px; overflow: hidden;">{items}</div>
        </div>
        """

    # ── 映射表 / 解决者：默认折叠 ──
    if OPPORTUNITY_TYPES:
        rows = ""
        for problem_type, info in OPPORTUNITY_TYPES.items():
            is_active = any(p.get("category") == problem_type for p in problems)
            dot = '<span style="color: #22c55e;">●</span>' if is_active else '<span style="color: #475569;">○</span>'
            bens = ", ".join(info.get("beneficiaries", [])[:3])
            rows += f"""
            <div style="display: grid; grid-template-columns: 18px 1.6fr 1.3fr 1.8fr; gap: 6px;
                        padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,.03); align-items: center;">
                <div style="font-size: 11px; text-align: center;">{dot}</div>
                <div style="font-size: 11px; color: #e2e8f0;">{html.escape(str(problem_type))}</div>
                <div style="font-size: 11px; color: #22c55e;">{html.escape(str(info.get('opportunity', '')))}</div>
                <div style="font-size: 11px; color: #64748b; overflow: hidden;
                            text-overflow: ellipsis; white-space: nowrap;">{html.escape(bens)}</div>
            </div>
            """
        body += fold("供需 → 机会 映射表", f'<div>{rows}</div>',
                     meta=f"{len(OPPORTUNITY_TYPES)} 类·● 为当前命中")

    if RESOLVERS:
        cards = ""
        for name, info in RESOLVERS.items():
            is_active = any(r.get("name") == name for r in resolvers)
            border = "rgba(34,197,94,.25)" if is_active else "rgba(255,255,255,.06)"
            progress = info.get("progress", {}) or {}
            badges = " ".join(
                f'<span style="font-size: 11px; color: #94a3b8;">{html.escape(str(k))}: '
                f'<span style="color: #f59e0b;">{html.escape(str(v))}</span></span>'
                for k, v in progress.items()
            )
            cards += f"""
            <div style="background: rgba(255,255,255,.02); border: 1px solid {border};
                        padding: 7px 9px; border-radius: 6px;">
                <div style="font-size: 11px; color: #e2e8f0; font-weight: 600; margin-bottom: 3px;">
                    {html.escape(str(name))}</div>
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">
                    🔧 {html.escape(str(info.get('problem', '')))} → {html.escape(str(info.get('opportunity', '')))}</div>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">{badges}</div>
            </div>
            """
        body += fold("解决者追踪", f'<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">{cards}</div>')

    put_html(card(title="叙事价值发现", icon="💎", meta=meta, body=body))
