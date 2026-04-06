"""
Supply Chain 组件
"""

from datetime import datetime


def render_supply_chain(ui):
    try:
        from deva.naja.cognition import get_supply_chain_linker
        linker = get_supply_chain_linker()

        hot_narratives = linker.get_hot_narratives(8)
        recent_events = linker.get_recent_events(5)
        summary = linker.get_supply_chain_summary()

        if not hot_narratives and not recent_events:
            return

        hot_html = ""
        for narrative, importance in hot_narratives:
            intensity = min(1.0, importance / 3.0)
            bg_alpha = 0.2 + intensity * 0.6
            hot_html += f'''
            <span style="background: rgba(239, 68, 68, {bg_alpha}); padding: 3px 10px; border-radius: 14px; font-size: 11px; color: white; margin: 2px; display: inline-block;">
                {narrative} ({importance:.1f})
            </span>'''

        events_html = ""
        for event in recent_events[-5:]:
            dt = datetime.fromtimestamp(event.timestamp)
            time_str = dt.strftime("%m-%d %H:%M")
            risk_color = "#ef4444" if event.risk_level.value in ["high", "critical"] else "#ca8a04"
            events_html += f'''
            <div style="background: rgba(255,255,255,0.03); border-radius: 6px; padding: 8px; margin-bottom: 6px; border-left: 3px solid {risk_color};">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #f1f5f9; font-size: 12px;">{event.description}</span>
                    <span style="color: #64748b; font-size: 10px;">{time_str}</span>
                </div>
                <div style="font-size: 10px; color: #64748b; margin-top: 4px;">
                    关联: {', '.join(event.narratives[:4])}
                </div>
            </div>'''

        from pywebio.output import put_html
        put_html(f'''
        <div style="
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
            border-radius: 12px;
            padding: 16px;
            margin: 12px 0;
            border: 1px solid rgba(59, 130, 246, 0.2);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <h3 style="margin: 0; color: #f1f5f9; font-size: 14px;">
                    🔗 供应链-叙事联动
                </h3>
                <div style="font-size: 11px; color: #64748b;">
                    {summary['total_narratives']} 叙事 | {summary['total_stocks_mapped']} 股票 | {summary['recent_events_count']} 事件
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                <div>
                    <div style="font-size: 11px; color: #94a3b8; margin-bottom: 8px;">🔥 最热叙事</div>
                    <div style="max-height: 120px; overflow-y: auto;">
                        {hot_html or '<span style="color: #64748b; font-size: 12px;">暂无热度数据</span>'}
                    </div>
                </div>
                <div>
                    <div style="font-size: 11px; color: #94a3b8; margin-bottom: 8px;">⚠️ 最近风险事件</div>
                    <div style="max-height: 120px; overflow-y: auto;">
                        {events_html or '<span style="color: #64748b; font-size: 12px;">暂无风险事件</span>'}
                    </div>
                </div>
            </div>

            <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 10px; color: #64748b;">
                    💡 叙事热点自动关联供应链股票，高风险事件自动提升相关叙事重要性
                </div>
            </div>
        </div>
        ''')
    except Exception:
        pass