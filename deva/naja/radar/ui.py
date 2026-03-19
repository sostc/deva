"""Radar UI."""

from datetime import datetime

from pywebio.output import put_html, put_table, use_scope, set_scope, put_collapse

from ..common.ui_style import apply_strategy_like_styles, render_empty_state
from ..page_help import render_help_collapse
from .engine import get_radar_engine


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _get_experiment_banner_html() -> str:
    """获取实验模式提示横幅的 HTML"""
    try:
        from deva.naja.strategy import get_strategy_manager
        mgr = get_strategy_manager()
        exp_info = mgr.get_experiment_info()

        if not exp_info.get("active"):
            return ""

        # 获取数据源名称
        from deva.naja.datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        ds_mgr.load_from_db()
        ds_id = exp_info.get("datasource_id", "")
        ds_entry = ds_mgr.get(ds_id)
        ds_name = ds_entry.name if ds_entry else ds_id[:8] + "..."

        categories = exp_info.get("categories", [])
        categories_text = "、".join(categories) if categories else "-"
        target_count = int(exp_info.get("target_count", 0))

        return f"""
        <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;
                    background:linear-gradient(135deg,#fff3cd,#ffe8a1);
                    border:1px solid #f5d37a;color:#7a5a00;font-size:13px;">
            <strong>🧪 实验模式已开启</strong><br>
            类别：{categories_text} ｜ 数据源：{ds_name} ｜ 策略数：{target_count}
        </div>
        """
    except Exception:
        return ""


def _render_event_type_badge(event_type: str) -> str:
    """渲染事件类型徽章"""
    badges = {
        "pattern": {"icon": "📊", "color": "#2563eb", "bg": "rgba(37,99,235,0.1)", "label": "模式"},
        "drift": {"icon": "📉", "color": "#d97706", "bg": "rgba(217,119,6,0.1)", "label": "漂移"},
        "anomaly": {"icon": "⚡", "color": "#dc2626", "bg": "rgba(220,38,38,0.1)", "label": "异常"},
    }
    info = badges.get(event_type, {"icon": "❓", "color": "#6b7280", "bg": "rgba(107,114,128,0.1)", "label": event_type})
    return f'''<span style="display:inline-flex;align-items:center;gap:3px;padding:3px 8px;border-radius:4px;font-size:12px;font-weight:500;background:{info['bg']};color:{info['color']};">
        {info['icon']} {info['label']}
    </span>'''


def _render_signal_type_badge(signal_type: str) -> str:
    """渲染信号类型徽章"""
    signal_lower = signal_type.lower() if signal_type else ""
    
    if "anomaly" in signal_lower or "fast" in signal_lower:
        color, bg, icon = "#dc2626", "rgba(220,38,38,0.1)", "⚡"
    elif "drift" in signal_lower:
        color, bg, icon = "#9333ea", "rgba(147,51,234,0.1)", "📉"
    elif "breakout" in signal_lower or "volume" in signal_lower:
        color, bg, icon = "#d97706", "rgba(217,119,6,0.1)", "📈"
    elif "rotation" in signal_lower or "block" in signal_lower:
        color, bg, icon = "#2563eb", "rgba(37,99,235,0.1)", "🔄"
    elif "trend" in signal_lower:
        color, bg, icon = "#16a34a", "rgba(22,163,74,0.1)", "📊"
    else:
        color, bg, icon = "#6b7280", "rgba(107,114,128,0.1)", "📌"
    
    return f'''<span style="display:inline-flex;align-items:center;gap:2px;padding:2px 6px;border-radius:3px;font-size:11px;background:{bg};color:{color};">
        {icon} {signal_type}
    </span>'''


def _render_radar_help():
    """渲染雷达帮助说明"""
    return render_help_collapse("radar")


async def render_radar_admin(ctx: dict):
    set_scope("radar_content")
    apply_strategy_like_styles(ctx, scope="radar_content", include_compact_table=True)

    # 显示实验模式提示
    experiment_banner = _get_experiment_banner_html()
    if experiment_banner:
        ctx["put_html"](experiment_banner, scope="radar_content")

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

    _render_radar_help()

    if not events:
        ctx["put_html"](render_empty_state("暂无雷达事件"), scope="radar_content")
        return

    table_data = [["时间", "事件", "分数", "策略", "信号类型", "说明"]]
    for e in events[:50]:
        event_type = e.get("event_type", "-")
        signal_type = e.get("signal_type", "-")
        
        table_data.append(
            [
                _fmt_ts(float(e.get("timestamp", 0))),
                ctx["put_html"](_render_event_type_badge(event_type)),
                f"{float(e.get('score', 0)):.2f}" if e.get("score") is not None else "-",
                e.get("strategy_name", "-"),
                ctx["put_html"](_render_signal_type_badge(signal_type)),
                e.get("message", "-"),
            ]
        )

    ctx["put_table"](table_data, scope="radar_content")
