"""
Event Bus 组件
"""

from ....common.ui_style import format_timestamp


def render_event_bus(ui, source_counts=None, recent_by_source=None, recent_insights=None):
    """渲染认知事件流 - 展示一切皆流的理念

    Args:
        ui: CognitionUI 实例
        source_counts: 各数据源的计数
        recent_by_source: 按数据源分组的最近洞察
        recent_insights: 最近的洞察列表
    """
    try:
        from ....cognition.cognition_bus import get_cognition_bus
        bus = get_cognition_bus()
        bus_len = len(bus) if hasattr(bus, '__len__') else 0
        cache_max = getattr(bus, 'cache_max_len', 1000)
        cache_age = getattr(bus, 'cache_max_age_seconds', 3600)
    except Exception:
        bus_len = 0
        cache_max = 1000
        cache_age = 3600

    if source_counts is None:
        source_counts = {}
    if recent_by_source is None:
        recent_by_source = {}

    DATA_SOURCES = [
        {"type": "news", "name": "新闻事件", "icon": "📡", "color": "#f97316"},
        {"type": "market", "name": "行情", "icon": "📊", "color": "#14b8a6"},
        {"type": "cognitive", "name": "认知", "icon": "🧠", "color": "#8b5cf6"},
    ]

    event_type_cards = ""
    for ds in DATA_SOURCES:
        color = ds["color"]
        count = source_counts.get(ds['type'], 0)

        event_type_cards += f"""
        <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(255,255,255,0.02); border-radius: 4px; margin-bottom: 4px; border-left: 3px solid {color};">
            <span style="font-size: 12px;">{ds['icon']}</span>
            <div style="flex: 1; min-width: 0;">
                <div style="font-size: 10px; color: #cbd5e1;">{ds['name']}</div>
            </div>
            <div style="text-align: right;">
                <span style="font-size: 10px; color: {color}; font-weight: 600;">{count}</span>
            </div>
        </div>
        """

    source_recent_items = ""
    for ds in DATA_SOURCES:
        insights = recent_by_source.get(ds['type'], [])[:2]
        if not insights:
            continue
        items = ""
        for item in insights:
            ts = format_timestamp(float(item.get('ts', 0)))
            theme = item.get('theme', '-')[:25]
            items += f"""
            <div style="display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8; padding: 2px 0;">
                <span style="color: {ds['color']};">{ts[-8:]}</span>
                <span style="flex: 1; margin-left: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{theme}</span>
            </div>
            """
        source_recent_items += f"""
        <div style="background: rgba(255,255,255,0.02); border-radius: 4px; padding: 6px; margin-bottom: 6px;">
            <div style="font-size: 9px; color: {ds['color']}; font-weight: 600; margin-bottom: 4px;">{ds['icon']} {ds['name']}</div>
            {items}
        </div>
        """

    flow_items = """
    <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(20,184,166,0.1); border-radius: 4px; margin-bottom: 6px;">
        <span style="font-size: 12px;">📡</span>
        <span style="font-size: 10px; color: #14b8a6;">雷达</span>
        <span style="color: #475569;">→</span>
        <span style="font-size: 10px; color: #94a3b8;">事件入队</span>
    </div>
    <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(168,85,247,0.1); border-radius: 4px; margin-bottom: 6px;">
        <span style="font-size: 12px;">🔄</span>
        <span style="font-size: 10px; color: #a855f7;">跨信号</span>
        <span style="color: #475569;">→</span>
        <span style="font-size: 10px; color: #94a3b8;">共振检测</span>
    </div>
    <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(14,165,233,0.1); border-radius: 4px; margin-bottom: 6px;">
        <span style="font-size: 12px;">🤖</span>
        <span style="font-size: 10px; color: #0ea5e9;">LLM反思</span>
        <span style="color: #475569;">→</span>
        <span style="font-size: 10px; color: #94a3b8;">深度洞察</span>
    </div>
    <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(74,222,128,0.1); border-radius: 4px;">
        <span style="font-size: 12px;">📊</span>
        <span style="font-size: 10px; color: #4ade80;">反馈</span>
        <span style="color: #475569;">→</span>
        <span style="font-size: 10px; color: #94a3b8;">注意力调度</span>
    </div>
    """

    from pywebio.output import put_html
    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #14b8a6;">
                🌊 认知事件流
            </div>
            <div style="font-size: 10px; color: #475569;">
                缓冲: {bus_len}/{cache_max} | 生命周期: {cache_age}s
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 12px;">
            一切皆流，无物永驻 — 事件驱动，实时处理
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
            <div>
                <div style="font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 6px;">
                    📥 事件来源 ({len([k for k in source_counts if source_counts.get(k, 0) > 0])} 种活跃)
                </div>
                {event_type_cards}
            </div>
            <div>
                <div style="font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 6px;">
                    🔄 处理流程
                </div>
                {flow_items}
            </div>
            <div>
                <div style="font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 6px;">
                    📋 最近事件
                </div>
                {source_recent_items or '<div style="color: #64748b; font-size: 10px;">暂无数据</div>'}
            </div>
        </div>
    </div>
    """)
