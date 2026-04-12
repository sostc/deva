"""Radar UI — 事件类型分布 + 事件时间线"""

from pywebio.output import put_html

from .constants import _fmt_time, _render_event_badge


def render_stats_overview(engine):
    """渲染事件类型分布 - 淡色风格"""
    if not engine:
        return

    summary_10m = engine.summarize(window_seconds=600)
    type_counts = summary_10m.get("event_type_counts", {})

    if not type_counts:
        return

    type_bars = ""
    max_count = max(type_counts.values()) if type_counts else 1
    for etype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        width = int(count / max_count * 100)
        icon, color = {
            "pattern": ("📊", "#60a5fa"),
            "drift": ("📉", "#c084fc"),
            "anomaly": ("⚡", "#f87171"),
            "block_anomaly": ("🔥", "#fb923c"),
        }.get(etype, ("📌", "#94a3b8"))

        type_bars += f'''
        <div style="margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
                <span style="color: #94a3b8;">{icon} {etype}</span>
                <span style="font-weight: 600; color: {color};">{count}</span>
            </div>
            <div style="height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
                <div style="width: {width}%; height: 100%; background: {color}; border-radius: 2px;"></div>
            </div>
        </div>'''

    put_html(f'''
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 12px;">
            📈 事件类型分布（10分钟）
        </div>
        {type_bars}
    </div>
    ''')


def render_event_timeline(engine):
    """渲染事件时间线 - 淡色风格"""
    if not engine:
        return

    summary = engine.summarize(window_seconds=3600)
    events = summary.get("events", [])[:30]

    if not events:
        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
            text-align: center;
        ">
            <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 6px;">🕐 最近事件（1小时）</div>
            <div style="color: #475569; font-size: 11px;">暂无雷达事件</div>
        </div>
        """)
        return

    event_items = ""
    for event in events:
        event_type = event.get("event_type", "unknown")
        score = float(event.get("score", 0.5))
        message = event.get("message", "-")
        ts = float(event.get("timestamp", 0))
        ts_str = _fmt_time(ts)

        badge_html = _render_event_badge(event_type, score)
        score_color = "#f87171" if score > 0.7 else ("#fb923c" if score > 0.5 else "#60a5fa")

        event_items += f'''
        <div style="
            display: flex;
            gap: 10px;
            padding: 10px;
            background: rgba(255,255,255,0.02);
            border-radius: 6px;
            margin-bottom: 6px;
            border: 1px solid rgba(255,255,255,0.04);
        ">
            <div style="font-size: 10px; color: #475569; min-width: 45px; padding-top: 2px;">{ts_str}</div>
            <div style="flex: 1;">
                <div style="margin-bottom: 4px;">{badge_html}</div>
                <div style="font-size: 11px; color: #94a3b8; line-height: 1.4;">{message[:80]}</div>
            </div>
            <div style="text-align: right; min-width: 40px;">
                <div style="font-size: 11px; font-weight: 600; color: {score_color};">{score:.2f}</div>
            </div>
        </div>'''

    put_html(f'''
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 12px;">
            🕐 最近事件（1小时）
        </div>
        {event_items}
    </div>
    ''')
