"""Radar UI."""

from datetime import datetime

from pywebio.output import put_html, put_table, use_scope, set_scope

from ..common.ui_style import apply_strategy_like_styles, render_empty_state
from .engine import get_radar_engine


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


async def render_radar_admin(ctx: dict):
    set_scope("radar_content")
    apply_strategy_like_styles(ctx, scope="radar_content", include_compact_table=True)

    radar = get_radar_engine()
    summary = radar.summarize(window_seconds=600)
    events = summary.get("events", []) or []

    ctx["put_html"](
        f"""
        <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
            <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#0ea5e9,#38bdf8);
                        padding:18px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(14,165,233,0.25);">
                <div style="font-size:12px;opacity:0.9;margin-bottom:4px;">最近 10 分钟事件</div>
                <div style="font-size:28px;font-weight:700;">{summary.get("event_count", 0)}</div>
            </div>
            <div style="flex:2;min-width:220px;background:#fff;padding:16px;border-radius:12px;
                        box-shadow:0 2px 10px rgba(0,0,0,0.06);">
                <div style="font-size:13px;color:#666;margin-bottom:6px;">事件分布</div>
                <div style="font-size:12px;color:#333;">
                    {", ".join([f"{k}:{v}" for k, v in (summary.get("event_type_counts") or {}).items()]) or "暂无"}
                </div>
            </div>
        </div>
        """,
        scope="radar_content",
    )

    if not events:
        ctx["put_html"](render_empty_state("暂无雷达事件"), scope="radar_content")
        return

    table_data = [["时间", "事件", "分数", "策略", "信号类型", "说明"]]
    for e in events[:50]:
        table_data.append(
            [
                _fmt_ts(float(e.get("timestamp", 0))),
                e.get("event_type", "-"),
                f"{float(e.get('score', 0)):.2f}" if e.get("score") is not None else "-",
                e.get("strategy_name", "-"),
                e.get("signal_type", "-"),
                e.get("message", "-"),
            ]
        )

    ctx["put_table"](table_data, scope="radar_content")
