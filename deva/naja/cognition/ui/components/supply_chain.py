"""Supply Chain 组件 —— 供应链-叙事联动

2026-10-19 重排：删掉卡片底部那段「💡 功能说明：叙事热点自动关联供应链股票…」
（它解释的是模块职责，不是当前状态，却常驻占高）；空态改一行式。
"""

import html
from datetime import datetime

from pywebio.output import put_html

from .layout import card, report_empty


def render_supply_chain(ui):
    try:
        from deva.naja.cognition import get_supply_chain_linker
        linker = get_supply_chain_linker()

        hot_narratives = linker.get_hot_narratives(8)
        recent_events = linker.get_recent_events(5)
        summary = linker.get_supply_chain_summary()
        has_data = bool((hot_narratives and len(hot_narratives) > 0)
                        or (recent_events and len(recent_events) > 0))
    except Exception:
        hot_narratives = []
        recent_events = []
        summary = {'total_narratives': 0, 'total_stocks_mapped': 0, 'recent_events_count': 0}
        has_data = False

    meta = (f"{summary['total_narratives']} 叙事 · "
            f"{summary['total_stocks_mapped']} 股票 · "
            f"{summary['recent_events_count']} 事件")

    if not has_data:
        report_empty("🔗", "供应链-叙事联动", "等待供应链数据", "需新闻流入且叙事追踪激活")
        return

    hot_html = ""
    for narrative, importance in hot_narratives:
        bg_alpha = 0.2 + min(1.0, importance / 3.0) * 0.6
        hot_html += f"""
        <span style="background: rgba(239,68,68,{bg_alpha:.2f}); padding: 3px 10px; border-radius: 14px;
                     font-size: 11px; color: #fff; margin: 0 4px 4px 0; display: inline-block;">
            {html.escape(str(narrative))} ({importance:.1f})
        </span>"""

    events_html = ""
    for event in recent_events[-5:]:
        time_str = datetime.fromtimestamp(event.timestamp).strftime("%m-%d %H:%M")
        risk_color = "#ef4444" if event.risk_level.value in ("high", "critical") else "#ca8a04"
        events_html += f"""
        <div style="background: rgba(255,255,255,.02); border-radius: 6px; padding: 7px 9px;
                    margin-bottom: 5px; border-left: 3px solid {risk_color};">
            <div style="display: flex; justify-content: space-between; gap: 8px;">
                <span style="color: #e2e8f0; font-size: 11px;">{html.escape(str(event.description))}</span>
                <span style="color: #64748b; font-size: 11px; flex-shrink: 0;">{time_str}</span>
            </div>
            <div style="font-size: 11px; color: #64748b; margin-top: 3px;">
                关联 {html.escape(', '.join(event.narratives[:4]))}
            </div>
        </div>"""

    body = f"""
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 18px;">
        <div>
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 7px;">🔥 最热叙事</div>
            <div style="max-height: 132px; overflow-y: auto;">
                {hot_html or '<span style="color:#64748b;font-size:11px;">暂无热度数据</span>'}
            </div>
        </div>
        <div>
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 7px;">⚠️ 最近风险事件</div>
            <div style="max-height: 132px; overflow-y: auto;">
                {events_html or '<span style="color:#64748b;font-size:11px;">暂无风险事件</span>'}
            </div>
        </div>
    </div>
    """

    put_html(card(title="供应链-叙事联动", icon="🔗", meta=meta, body=body))
