"""
Narrative Lifecycle 组件
"""

from ....common.ui_style import format_timestamp


def render_narrative_lifecycle(ui):
    if not ui.engine:
        return

    report = ui.engine.get_memory_report()
    narratives_data = report.get('narratives', {})
    narrative_summary = narratives_data.get('summary', [])
    narrative_graph = narratives_data.get('graph', {})
    narrative_events = narratives_data.get('events', [])

    if not narrative_summary:
        return

    from pywebio.output import put_html

    stage_colors = {
        '萌芽': '#60a5fa',
        '扩散': '#818cf8',
        '高潮': '#f87171',
        '消退': '#fb923c',
    }
    stage_order = ['萌芽', '扩散', '高潮', '消退']

    put_html("""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #60a5fa; margin-bottom: 4px;">
            🌊 叙事生命周期
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            叙事阶段：萌芽 → 扩散 → 高潮 → 消退
        </div>

        <div style="border-left: 2px solid rgba(96,165,250,0.3); padding-left: 12px; margin-bottom: 14px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                <span style="color: #60a5fa;">📋</span> 叙事列表
            </div>
    """)
    for nar in narrative_summary[:5]:
        name = nar.get('narrative', '未知')
        stage = nar.get('stage', '萌芽')
        attention = float(nar.get('attention_score', 0))
        trend = float(nar.get('trend', 0))
        recent_count = int(nar.get('recent_count', 0))
        keywords = nar.get('keywords', [])[:3]
        stage_idx = stage_order.index(stage) if stage in stage_order else 0
        stage_color = stage_colors.get(stage, '#60a5fa')

        trend_icon = '↑' if trend > 0 else ('↓' if trend < 0 else '→')
        trend_color = '#4ade80' if trend > 0 else ('#f87171' if trend < 0 else '#6b7280')

        bar_width = min(100, int(attention * 100))

        kw_tags = ''.join([
            f'<span style="display: inline-block; padding: 2px 6px; background: rgba(255,255,255,0.08); color: #94a3b8; border-radius: 4px; font-size: 10px; margin-right: 4px;">{kw}</span>'
            for kw in keywords
        ]) if keywords else ''

        put_html(f"""
        <div style="background: rgba(255,255,255,0.02); border-radius: 10px; padding: 12px; margin-bottom: 10px; border-left: 3px solid {stage_color};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-size: 13px; font-weight: 600; color: #cbd5e1;">{name}</div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="padding: 2px 8px; background: {stage_color}; color: #0f172a; border-radius: 4px; font-size: 10px; font-weight: 600;">{stage}</span>
                    <span style="font-size: 11px; color: {trend_color}; font-weight: 600;">{trend_icon} {abs(trend):.2f}</span>
                    <span style="font-size: 10px; color: #475569;">{recent_count}次/6h</span>
                </div>
            </div>
            <div style="margin-bottom: 8px;">
                <div style="display: flex; height: 6px; border-radius: 4px; overflow: hidden; gap: 2px;">
                    <div style="flex: {bar_width}; background: linear-gradient(90deg, {stage_color}, {stage_color}dd); border-radius: 4px 0 0 4px;"></div>
                    <div style="flex: {100 - bar_width}; background: rgba(255,255,255,0.1); border-radius: 0 4px 4px 0;"></div>
                </div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-size: 10px; color: #475569;">注意力 <b style="color: {stage_color};">{attention:.2f}</b></div>
                {kw_tags}
            </div>
        </div>
        """)
    put_html('</div>')

    if narrative_events:
        put_html("""
        <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.08);">
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 10px;">
                <div style="width: 8px; height: 8px; border-radius: 2px; background: linear-gradient(135deg, #4ade80, #6ee7b7);"></div>
                <div style="font-size: 11px; font-weight: 600; color: #4ade80;">📍 子模块：最近阶段变化</div>
            </div>
            <div style="border-left: 2px solid rgba(74,222,128,0.3); padding-left: 12px;">
        """)
        recent_events = narrative_events[-5:] if len(narrative_events) > 5 else narrative_events
        for evt in reversed(recent_events):
            evt_type = evt.get('event_type', '')
            evt_nar = evt.get('narrative', '')
            evt_stage = evt.get('stage', '')
            evt_ts = format_timestamp(float(evt.get('timestamp', 0)))
            evt_attention = float(evt.get('attention_score', 0))
            evt_trend = float(evt.get('trend', 0))
            evt_keywords = evt.get('keywords', [])[:2]
            evt_blocks = (evt.get('linked_blocks') or evt.get('linked_blocks') or [])[:2]

            if 'stage_change' in evt_type:
                evt_color = '#4ade80' if evt_stage == '高潮' else ('#a855f7' if evt_stage == '扩散' else ('#fb923c' if evt_stage == '消退' else '#60a5fa'))
                evt_icon = '🔄'
                trend_icon = '📈' if evt_trend > 0 else '📉' if evt_trend < 0 else '➡️'
                kw_str = ' '.join([f'<span style="padding: 1px 4px; background: rgba(255,255,255,0.08); color: #94a3b8; border-radius: 3px; font-size: 9px; margin-right: 2px;">{kw}</span>' for kw in evt_keywords]) if evt_keywords else ''
                block_str = ' '.join([f'<span style="padding: 1px 4px; background: rgba(249,115,22,0.15); color: #fb923c; border-radius: 3px; font-size: 9px; margin-right: 2px;">{s}</span>' for s in evt_blocks]) if evt_blocks else ''
                evt_desc = f'<span style="color: {evt_color}; font-weight: 600;">{evt_nar}</span> → <span style="padding: 1px 6px; background: {evt_color}; color: #0f172a; border-radius: 4px; font-size: 10px; font-weight: 600;">{evt_stage}</span> {trend_icon} {int(evt_attention*100)}%'
                if kw_str or block_str:
                    evt_desc += f'<br><span style="margin-top: 4px; display: inline-block;">{kw_str} {block_str}</span>'
            else:
                evt_color = '#60a5fa'
                evt_icon = '🔥'
                evt_desc = f"{evt_nar} 飙升"
            put_html(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 11px; border-bottom: 1px solid rgba(255,255,255,0.05);">
                <span><span style="color: {evt_color};">{evt_icon}</span> {evt_desc}</span>
                <span style="color: #475569; font-size: 10px;">{evt_ts[-8:]}</span>
            </div>
            """)
        put_html('</div></div>')

    if narrative_graph.get('nodes') and narrative_graph.get('edges'):
        nodes = narrative_graph.get('nodes', [])
        edges = narrative_graph.get('edges', [])
        svg_html = ui._render_narrative_svg(nodes, edges)
        put_html(f"""
        <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.08);">
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 10px;">
                <div style="width: 8px; height: 8px; border-radius: 2px; background: linear-gradient(135deg, #818cf8, #a78bfa);"></div>
                <div style="font-size: 11px; font-weight: 600; color: #818cf8;">🔗 叙事关联图</div>
            </div>
            <div style="display: flex; justify-content: center; padding: 8px; background: rgba(255,255,255,0.02); border-radius: 8px;">
                {svg_html}
            </div>
        </div>
        """)

    put_html('</div>')
