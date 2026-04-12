"""热点系统 UI 时间线组件"""

from datetime import datetime
from typing import List, Dict, Any

from deva.naja.market_hotspot.ui_components.common import get_history_tracker

def render_block_trading_timeline() -> str:
    """题材炒作时间轴 - 展示每天各题材随时间的涨跌变化"""
    tracker = get_history_tracker()

    today = datetime.now().strftime("%m-%d")
    today_events = []
    has_real_data = False

    if tracker and tracker.block_hotspot_events_medium:
        all_events = list(tracker.block_hotspot_events_medium)

        for event in all_events:
            event_date = datetime.fromtimestamp(event.timestamp).strftime("%m-%d")
            if event_date == today:
                today_events.append(event)

        if today_events:
            has_real_data = True
        else:
            today_events = all_events[-15:]

        today_events.sort(key=lambda x: x.timestamp)

    using_sample_data = not has_real_data and not today_events
    if using_sample_data:
        today_events = _get_sample_events()

    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-weight: 600; color: #1e293b; font-size: 14px;">
                📈 题材炒作时间轴
                <span style="font-size: 11px; color: #64748b; font-weight: normal; margin-left: 8px;">今日题材起落</span>
            </div>
            <div style="font-size: 11px; color: #94a3b8;">{len(today_events)}个事件</div>
        </div>
        {"" if has_real_data else """
        <div style="margin-bottom: 12px; padding: 8px 12px; background: linear-gradient(135deg, #fef3c7, #fde68a); border: 1px solid #f59e0b; border-radius: 6px; font-size: 12px; color: #92400e;">
            <strong>⚠️ 样例数据展示</strong> - 当前暂无实时数据，以下为示例效果。
        </div>
        """}
        <div style="margin-bottom: 12px; padding: 8px 12px; background: #f0f9ff; border-radius: 6px; font-size: 11px; color: #0369a1; line-height: 1.5;">
            <strong>📊 事件说明:</strong> 🔥新热点 | ❄️热点消退 | 📈拉升 | 📉回调
        </div>
    """

    time_periods = [
        ("09:30", "10:00", "早盘开盘", "#dc2626"),
        ("10:00", "10:30", "早盘活跃", "#ea580c"),
        ("10:30", "11:00", "早盘震荡", "#ca8a04"),
        ("11:00", "11:30", "早盘收尾", "#ca8a04"),
        ("13:00", "13:30", "午后开盘", "#3b82f6"),
        ("13:30", "14:00", "午后活跃", "#2563eb"),
        ("14:00", "14:30", "午后震荡", "#1d4ed8"),
        ("14:30", "15:00", "尾盘决战", "#7c3aed"),
    ]

    event_styles = {
        'new_hot': ('🔥', '#dc2626', '新热点'),
        'cooled': ('❄️', '#3b82f6', '热点消退'),
        'rise': ('📈', '#16a34a', '拉升'),
        'fall': ('📉', '#f59e0b', '回调'),
    }

    period_events = {i: [] for i in range(len(time_periods))}

    for event in today_events:
        try:
            if hasattr(event, 'market_time') and event.market_time:
                time_str = event.market_time
            else:
                time_str = datetime.fromtimestamp(event.timestamp).strftime("%H:%M")

            hour, minute = map(int, time_str.split(':'))
            time_val = hour * 100 + minute

            for i, (start, end, label, color) in enumerate(time_periods):
                start_h, start_m = map(int, start.split(':'))
                end_h, end_m = map(int, end.split(':'))
                start_val = start_h * 100 + start_m
                end_val = end_h * 100 + end_m

                if start_val <= time_val < end_val:
                    period_events[i].append((time_str, event))
                    break
        except:
            continue

    for i, (start, end, label, period_color) in enumerate(time_periods):
        events_in_period = period_events[i]
        has_events = len(events_in_period) > 0

        if has_events:
            header_bg = f"linear-gradient(135deg, {period_color}15, {period_color}08)"
            header_border = period_color
            event_count_text = f"{len(events_in_period)}个事件"
        else:
            header_bg = "#f8fafc"
            header_border = "#e2e8f0"
            event_count_text = "暂无数据"

        html += f"""
        <div style="margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding: 6px 10px; background: {header_bg}; border-left: 3px solid {header_border}; border-radius: 0 6px 6px 0;">
                <span style="font-weight: 600; color: {period_color if has_events else '#94a3b8'}; font-size: 12px;">{label}</span>
                <span style="color: #94a3b8; font-size: 11px;">{start}-{end}</span>
                <span style="margin-left: auto; color: {'#64748b' if has_events else '#94a3b8'}; font-size: 11px;">{event_count_text}</span>
            </div>
            <div style="padding-left: 16px; border-left: 2px dashed #e2e8f0; margin-left: 6px;">
        """

        if has_events:
            for time_str, event in events_in_period:
                emoji, evt_color, evt_label = event_styles.get(event.event_type, ('•', '#64748b', '变化'))
                change_sign = '+' if event.change_percent > 0 else ''

                if abs(event.change_percent) >= 10:
                    bg_color = '#fef2f2' if event.change_percent > 0 else '#eff6ff'
                    border_color = '#dc2626' if event.change_percent > 0 else '#3b82f6'
                elif abs(event.change_percent) >= 5:
                    bg_color = '#fff7ed' if event.change_percent > 0 else '#f0f9ff'
                    border_color = '#ea580c' if event.change_percent > 0 else '#0ea5e9'
                else:
                    bg_color = '#f8fafc'
                    border_color = evt_color

                top_symbols = getattr(event, 'top_symbols', [])[:3]

                html += f"""
                <div style="display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px; margin-bottom: 6px; background: {bg_color}; border-radius: 6px; border-left: 3px solid {border_color}; font-size: 12px;">
                    <div style="min-width: 40px;">
                        <span style="color: #94a3b8; font-family: monospace; font-size: 11px;">{time_str}</span>
                    </div>
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                            <span style="font-size: 14px;">{emoji}</span>
                            <span style="font-weight: 500; color: #1e293b;">{event.block_name}</span>
                            <span style="font-size: 10px; color: {evt_color};">{evt_label}</span>
                            <span style="color: {border_color}; font-weight: 600; font-size: 13px; margin-left: auto;">{change_sign}{event.change_percent:.1f}%</span>
                        </div>
                        {f'''<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; padding-top: 6px; border-top: 1px dashed {border_color}40;">
                            <span style="font-size: 10px; color: #64748b;">领涨/领跌:</span>
                            {''.join([f"<span style='font-size: 10px; padding: 2px 6px; background: {'#fef2f2' if s.get('change_pct', 0) > 0 else '#eff6ff'}; color: {'#dc2626' if s.get('change_pct', 0) > 0 else '#3b82f6'}; border-radius: 4px; white-space: nowrap;'>{s.get('symbol', '')} {s.get('name', '')[:4]} {s.get('change_pct', 0):+.1f}%</span>" for s in top_symbols])}
                        </div>''' if top_symbols else ''}
                    </div>
                </div>
                """
        else:
            html += """
            <div style="padding: 12px 10px; margin-bottom: 6px; background: #f8fafc; border-radius: 6px; border-left: 3px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center;">等待数据...</div>
            """

        html += "</div></div>"

    html += '</div>'
    return html
