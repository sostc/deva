"""热点系统 UI 时间线组件"""

from datetime import datetime
from typing import List, Dict, Any

from deva.naja.market_hotspot.ui_components.common import get_history_tracker

def render_block_hotspot_timeline(threshold: str = "high") -> str:
    """渲染题材热点切换时间线"""
    tracker = get_history_tracker()
    if not tracker:
        return """
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">🔥 题材热点切换时间线</div>
            <div style="color: #64748b; text-align: center; padding: 40px 20px;">历史追踪器未初始化</div>
        </div>
        """

    threshold_config = {
        'low': {'events': tracker.block_hotspot_events_low, 'pct': 3, 'label': '低敏感度', 'color': '#16a34a'},
        'high': {'events': tracker.block_hotspot_events_high, 'pct': 10, 'label': '高敏感度', 'color': '#dc2626'},
    }

    config = threshold_config.get(threshold, threshold_config['high'])
    all_events = config['events']
    valid_events = [e for e in all_events if tracker.is_block_valid(getattr(e, 'block_id', ''))]
    pct = config['pct']
    label = config['label']
    header_color = config['color']

    if not valid_events:
        return f"""
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 16px; color: {header_color};">🔥 {label} ({pct}%阈值)</div>
            <div style="color: #64748b; text-align: center; padding: 40px 20px;">暂无有效题材变化事件（噪声题材已被过滤）</div>
        </div>
        """

    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: {header_color};">
            🔥 {label} ({pct}%阈值)
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">共{len(valid_events)}个有效事件</span>
        </div>
    """

    event_styles = {
        'new_hot': ('🔥', '#dc2626', '新热点'),
        'cooled': ('❄️', '#3b82f6', '热点消退'),
        'rise': ('📈', '#16a34a', '大幅拉升'),
        'fall': ('📉', '#f59e0b', '明显回调'),
    }

    recent_events = list(valid_events)[-15:]
    current_date = None

    for event in reversed(recent_events):
        event_date = getattr(event, 'market_date', '') or datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d")
        if event_date != current_date:
            current_date = event_date
            html += f"""
            <div style="margin: 12px 0 8px 0; padding: 4px 0; border-bottom: 1px dashed #e2e8f0; font-size: 12px; color: #94a3b8; font-weight: 500;">📅 {event_date}</div>
            """

        emoji, color, label_text = event_styles.get(event.event_type, ('•', '#64748b', event.event_type))

        bg_colors = {'new_hot': '#fef2f2', 'cooled': '#eff6ff', 'rise': '#f0fdf4', 'fall': '#fffbeb'}
        bg_color = bg_colors.get(event.event_type, '#f8fafc')

        change_sign = '+' if event.change_percent > 0 else ''

        html += f"""
        <div style="padding: 12px; margin-bottom: 10px; background: {bg_color}; border-radius: 8px; border-left: 3px solid {color};">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                        <span style="font-size: 11px; color: #64748b; font-family: monospace; min-width: 50px;">{event.market_time}</span>
                        <span style="font-size: 18px;">{emoji}</span>
                        <span style="font-weight: 600; color: #1e293b;">{event.block_name}</span>
                        <span style="font-size: 10px; color: {color}; background: rgba(255,255,255,0.6); padding: 2px 8px; border-radius: 4px;">{label_text}</span>
                    </div>
                    <div style="font-size: 12px; color: #64748b; margin-left: 58px; line-height: 1.5;">
                        权重: {event.weight_change:+.3f} ({change_sign}{event.change_percent:.1f}%)
                    </div>
                </div>
            </div>
        """

        if event.top_symbols:
            html += """
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e2e8f0;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">题材内个股:</div>
                <div style="display: flex; flex-direction: column; gap: 4px;">
            """
            for s in event.top_symbols[:3]:
                s_emoji = '📈' if s['change_pct'] > 0 else '📉'
                s_color = '#16a34a' if s['change_pct'] > 0 else '#dc2626'
                s_sign = '+' if s['change_pct'] > 0 else ''
                html += f"""
                    <div style="font-size: 11px; display: flex; justify-content: space-between; align-items: center; padding: 4px 8px; background: rgba(255,255,255,0.5); border-radius: 4px;">
                        <span>{s_emoji} <strong>{s['symbol']}</strong> {s['name']}</span>
                        <span style="color: {s_color}; font-weight: 600;">{s['old']:.2f} → {s['new']:.2f} ({s_sign}{s['change_pct']:.1f}%)</span>
                    </div>
                """
            html += "</div></div>"

        html += "</div>"

    html += "</div>"
    return html


def render_multi_threshold_timeline() -> str:
    """渲染多阈值题材热点切换时间线"""
    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 20px; color: #1e293b; font-size: 16px;">
            🔥 题材热点切换时间线
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">双阈值对比</span>
        </div>

        <div style="display: flex; gap: 16px; margin-bottom: 20px; padding: 12px 16px; background: linear-gradient(135deg, #f8fafc, #f1f5f9); border-radius: 8px; font-size: 12px;">
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="width: 12px; height: 12px; background: #16a34a; border-radius: 3px;"></span>
                <span><strong>低阈值 (3%)</strong>: 捕捉细微变化，事件较多</span>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="width: 12px; height: 12px; background: #dc2626; border-radius: 3px;"></span>
                <span><strong>高阈值 (10%)</strong>: 重大变化，事件较少</span>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
    """

    for threshold in ['low', 'high']:
        html += f'<div style="min-width: 0;">{render_single_threshold_column(threshold)}</div>'

    html += "</div></div>"
    return html


def render_single_threshold_column(threshold: str) -> str:
    """渲染单个阈值的紧凑时间线列"""
    tracker = get_history_tracker()
    if not tracker:
        return "<div style='color: #64748b; text-align: center;'>未初始化</div>"

    threshold_config = {
        'low': {'events': tracker.block_hotspot_events_low, 'pct': 3, 'label': '低敏感度', 'color': '#16a34a', 'bg': '#f0fdf4'},
        'high': {'events': tracker.block_hotspot_events_high, 'pct': 10, 'label': '高敏感度', 'color': '#dc2626', 'bg': '#fef2f2'},
    }

    config = threshold_config.get(threshold, threshold_config.get('high'))
    all_events = config['events']
    valid_events = [e for e in all_events if tracker.is_block_valid(getattr(e, 'block_id', ''))]
    events = list(valid_events)[-20:]
    pct = config['pct']
    label = config['label']
    color = config['color']
    bg = config['bg']

    if not valid_events:
        return f"""
        <div style="background: {bg}; border: 1px solid {color}33; border-radius: 8px; padding: 16px; text-align: center;">
            <div style="font-weight: 600; color: {color}; margin-bottom: 8px;">{label} ({pct}%)</div>
            <div style="font-size: 12px; color: #64748b;">暂无有效事件</div>
        </div>
        """

    html = f"""
    <div style="background: {bg}; border: 1px solid {color}33; border-radius: 8px; padding: 12px;">
        <div style="font-weight: 600; color: {color}; margin-bottom: 12px; font-size: 13px;">
            {label} ({pct}%) <span style="font-weight: normal; color: #64748b;">· {len(events)}个</span>
        </div>
    """

    event_styles = {
        'new_hot': ('🔥', '#dc2626'),
        'cooled': ('❄️', '#3b82f6'),
        'rise': ('📈', '#16a34a'),
        'fall': ('📉', '#f59e0b'),
    }

    current_date = None

    for event in reversed(events):
        full_time = datetime.fromtimestamp(event.timestamp).strftime("%m-%d %H:%M:%S")
        event_date = full_time.split(' ')[0]
        if event_date != current_date:
            current_date = event_date
            html += f'<div style="font-size: 10px; color: #94a3b8; margin: 8px 0 4px 0; padding-top: 4px; border-top: 1px dashed #e2e8f0;">{event_date}</div>'

        emoji, evt_color = event_styles.get(event.event_type, ('•', '#64748b'))
        change_sign = '+' if event.change_percent > 0 else ''

        html += f"""
        <div style="padding: 8px; margin-bottom: 6px; background: white; border-radius: 6px; border-left: 2px solid {evt_color}; font-size: 11px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                <span style="color: #64748b; font-family: monospace; font-size: 10px;">{full_time}</span>
                <span>{emoji}</span>
            </div>
            <div style="font-weight: 500; color: #1e293b; margin-bottom: 2px;">{event.block_name}</div>
            <div style="color: {evt_color}; font-size: 10px;">{change_sign}{event.change_percent:.1f}%</div>
        </div>
        """

    html += "</div>"
    return html


