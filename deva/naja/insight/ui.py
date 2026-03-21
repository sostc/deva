"""Insight UI."""

from datetime import datetime
from pywebio.output import put_html, set_scope

from ..common.ui_style import apply_strategy_like_styles, render_empty_state
from .engine import get_insight_pool


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


async def render_insight_page(ctx: dict):
    set_scope("insight_content")
    apply_strategy_like_styles(ctx, scope="insight_content", include_compact_table=True)

    pool = get_insight_pool()
    stats = pool.get_stats()
    top_insights = pool.get_top_insights(limit=5)
    recent = pool.get_recent_insights(limit=15)

    ctx["put_html"](
        f"""
        <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
            <div style="flex:1;min-width:160px;background:linear-gradient(135deg,#0f766e,#14b8a6);
                        padding:18px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(20,184,166,0.25);">
                <div style="font-size:12px;opacity:0.9;margin-bottom:4px;">洞察总数</div>
                <div style="font-size:28px;font-weight:700;">{stats.get("total_insights", 0)}</div>
            </div>
            <div style="flex:1;min-width:160px;background:#fff;padding:16px;border-radius:12px;
                        box-shadow:0 2px 10px rgba(0,0,0,0.06);">
                <div style="font-size:12px;color:#666;margin-bottom:4px;">活跃主题</div>
                <div style="font-size:24px;font-weight:700;color:#111827;">{stats.get("active_themes", 0)}</div>
                <div style="font-size:12px;color:#6b7280;margin-top:6px;">平均用户分</div>
                <div style="font-size:16px;font-weight:600;color:#0f766e;">{stats.get("avg_user_score", 0):.3f}</div>
            </div>
        </div>
        """,
        scope="insight_content",
    )

    if not top_insights:
        ctx["put_html"](render_empty_state("暂无洞察，等待策略输出生成洞察"), scope="insight_content")
        return

    ctx["put_html"](
        """
        <div style="font-size:15px;font-weight:600;margin:6px 0 10px;color:#111827;">Top 洞察</div>
        """,
        scope="insight_content",
    )

    for item in top_insights:
        theme = item.get("theme", "-")
        summary = item.get("summary", "")
        score = float(item.get("user_score", 0))
        system_attention = float(item.get("system_attention", 0))
        confidence = float(item.get("confidence", 0))
        actionability = float(item.get("actionability", 0))
        novelty = float(item.get("novelty", 0))
        symbols = ", ".join(item.get("symbols", [])[:6]) or "-"
        sectors = ", ".join(item.get("sectors", [])[:6]) or "-"
        ts = _fmt_ts(float(item.get("ts", 0)))

        ctx["put_html"](
            f"""
            <div style="background:#fff;border-radius:12px;padding:16px;margin-bottom:10px;
                        box-shadow:0 2px 10px rgba(0,0,0,0.06);border-left:4px solid #14b8a6;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <div style="font-size:15px;font-weight:600;color:#111827;">{theme}</div>
                    <div style="font-size:12px;color:#6b7280;">{ts}</div>
                </div>
                <div style="font-size:13px;color:#374151;margin-bottom:6px;">{summary}</div>
                <div style="font-size:12px;color:#6b7280;margin-bottom:6px;">
                    标的: {symbols} ｜ 板块: {sectors}
                </div>
                <div style="display:flex;flex-wrap:wrap;gap:8px;font-size:12px;color:#111827;">
                    <span style="padding:2px 6px;border-radius:6px;background:#ecfeff;">用户分 {score:.2f}</span>
                    <span style="padding:2px 6px;border-radius:6px;background:#f1f5f9;">系统注意力 {system_attention:.2f}</span>
                    <span style="padding:2px 6px;border-radius:6px;background:#f8fafc;">置信度 {confidence:.2f}</span>
                    <span style="padding:2px 6px;border-radius:6px;background:#fef3c7;">可行动 {actionability:.2f}</span>
                    <span style="padding:2px 6px;border-radius:6px;background:#e2e8f0;">新颖度 {novelty:.2f}</span>
                </div>
            </div>
            """,
            scope="insight_content",
        )

    ctx["put_html"](
        """
        <div style="font-size:14px;font-weight:600;margin:14px 0 8px;color:#111827;">最近洞察</div>
        """,
        scope="insight_content",
    )

    rows = []
    for item in recent:
        rows.append(
            {
                "时间": _fmt_ts(float(item.get("ts", 0))),
                "主题": item.get("theme", "-"),
                "摘要": item.get("summary", "-")[:60],
                "用户分": f"{float(item.get('user_score', 0)):.2f}",
            }
        )

    if rows:
        try:
            ctx["put_table"](rows, scope="insight_content")
        except Exception:
            put_html("<div>洞察表格渲染失败</div>", scope="insight_content")
