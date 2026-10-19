"""Cognition Summary 组件 —— 认知中枢指标条

2026-10-19 重排：删掉了紧随其后的「雷达快照 / 洞察摘要」双卡
（同一批数字在首屏重复了三次），并把"输入 X → 输出 Y"式的设计说明
从卡片里移除——运行时页面只显示运行时信息。
"""

from pywebio.output import put_html

from .layout import card


def _get_insight_pool():
    """获取 InsightPool（AppContainer 优先，SR fallback 仅开发用）"""
    from deva.naja.application.container import get_app_container
    container = get_app_container()
    if container is not None:
        ip = getattr(container, 'insight_pool', None)
        if ip is not None:
            return ip
    from deva.naja.register import SR
    return SR('insight_pool')


def _tile(label: str, value: str, sub: str, color: str) -> str:
    return f"""
    <div style="background: {color}12; border: 1px solid {color}33; border-radius: 10px;
                padding: 9px 14px; min-width: 92px; text-align: center;">
        <div style="font-size: 11px; color: #64748b; margin-bottom: 3px;">{label}</div>
        <div style="font-size: 18px; font-weight: 700; color: {color}; white-space: nowrap;">{value}</div>
        <div style="font-size: 11px; color: #64748b; margin-top: 2px;">{sub}</div>
    </div>
    """


def _strip(label: str, value: str, color: str) -> str:
    return f"""
    <div style="flex: 1; padding: 6px 10px; background: {color}18; border-radius: 6px; text-align: center;">
        <span style="font-size: 11px; color: #94a3b8;">{label}</span>
        <span style="font-size: 12px; font-weight: 600; color: {color}; margin-left: 6px;">{value}</span>
    </div>
    """


def render_cognition_summary(ui):
    from ....radar.engine import get_radar_engine
    from ....market_hotspot.ui_components.common import get_hotspot_report

    radar = get_radar_engine()
    radar_summary = radar.summarize(window_seconds=600) if radar else {}
    radar_events = radar_summary.get("event_count", 0)

    attention_report = get_hotspot_report() or {}
    global_attention = float(attention_report.get("global_hotspot", 0))

    insight_pool = _get_insight_pool()
    insight_stats = insight_pool.get_stats() if insight_pool else {"total_insights": 0}

    memory_report = ui.engine.get_memory_report() if ui.engine else {}
    stats = memory_report.get('stats', {})
    total_events = stats.get('total_events', 0)
    filtered_events = stats.get('filtered_events', 0)
    memory_layers = memory_report.get('memory_layers', {})
    short_layer = memory_layers.get('short', {})
    short_size = short_layer.get('size', 0)
    short_cap = short_layer.get('capacity', 0)
    mid_size = memory_layers.get('mid', {}).get('size', 0)

    if global_attention >= 0.6:
        attention_icon, attention_color, attention_level = "🔥", "#ef4444", "焦点集中"
    elif global_attention >= 0.3:
        attention_icon, attention_color, attention_level = "📊", "#f59e0b", "温和"
    else:
        attention_icon, attention_color, attention_level = "💤", "#64748b", "低迷"

    tiles = "".join([
        _tile("📡 雷达", str(radar_events), "10 分钟事件", "#f59e0b"),
        _tile("👁️ 注意力", f"{attention_icon} {global_attention:.2f}", attention_level, attention_color),
        _tile("💡 洞察", str(insight_stats.get('total_insights', 0)),
              f"活跃主题 {insight_stats.get('active_themes', 0)}", "#14b8a6"),
        _tile("🧠 记忆", f"{short_size}/{short_cap or '-'}", f"中期 {mid_size}", "#a855f7"),
    ])

    strip = "".join([
        _strip("📥 接收", str(total_events + filtered_events), "#f59e0b"),
        _strip("🚫 过滤", str(filtered_events), "#ef4444"),
        _strip("⚡ 短期", str(short_size), "#3b82f6"),
        _strip("📦 中期", str(mid_size), "#10b981"),
    ])

    body = f"""
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;">{tiles}</div>
    <div style="display: flex; gap: 8px; margin-top: 12px; padding-top: 12px;
                border-top: 1px solid rgba(255,255,255,.06);">{strip}</div>
    """

    meta = ('<a href="/cognition_glossary" target="_blank" '
            'style="color:#a78bfa;text-decoration:none;">📖 名词解释</a>')

    put_html(card(
        title="认知中枢",
        icon="🧠",
        meta=meta,
        body=body,
    ))
