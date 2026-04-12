"""热点系统 UI 时间线组件"""

from datetime import datetime
from typing import List, Dict, Any

from deva.naja.market_hotspot.ui_components.common import get_history_tracker

def render_block_trends() -> str:
    """渲染题材热点变化曲线"""
    tracker = get_history_tracker()
    if not tracker or len(tracker.snapshots) < 2:
        return "<div style='color: #64748b; text-align: center; padding: 20px;'>数据不足，无法显示趋势</div>"

    recent_snapshots = list(tracker.snapshots)[-30:]

    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            📊 题材热度变化曲线
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">最近30个时间点</span>
        </div>
    """

    all_blocks_with_weight = []
    for snapshot in recent_snapshots:
        for block_id, weight in snapshot.block_weights.items():
            all_blocks_with_weight.append((block_id, weight))

    block_weights_sum = {}
    for block_id, weight in all_blocks_with_weight:
        block_weights_sum[block_id] = block_weights_sum.get(block_id, 0) + weight

    top5_blocks = sorted(block_weights_sum.items(), key=lambda x: x[1], reverse=True)[:5]
    top5_block_ids = [s[0] for s in top5_blocks]

    block_colors = {
        'tech': '#3b82f6', 'finance': '#10b981', 'healthcare': '#f59e0b',
        'energy': '#ef4444', 'consumer': '#8b5cf6',
    }

    for block_id in top5_block_ids:
        block_name = tracker.get_block_name(block_id)
        color = block_colors.get(block_id, '#64748b')

        block_data = []
        for snapshot in recent_snapshots:
            weight = snapshot.block_weights.get(block_id, 0)
            time_str = datetime.fromtimestamp(snapshot.timestamp).strftime("%H:%M")
            block_data.append((time_str, weight))

        if not block_data:
            continue

        current_weight = block_data[-1][1]
        prev_weight = block_data[0][1] if len(block_data) > 1 else current_weight
        change_pct = ((current_weight - prev_weight) / prev_weight * 100) if prev_weight > 0 else 0

        max_weight = max([w for _, w in block_data]) if block_data else 1
        trend_bars = ""
        for time_str, weight in block_data:
            height_pct = (weight / max_weight * 100) if max_weight > 0 else 0
            trend_bars += f"""
                <div style="flex: 1; background: {color}; height: {height_pct}%; min-height: 2px; margin: 0 1px; border-radius: 1px; opacity: {0.4 + (height_pct / 200)};" title="{time_str}: {weight:.3f}"></div>
            """

        top_symbols = []
        if recent_snapshots:
            latest_snapshot = recent_snapshots[-1]
            sorted_symbols = sorted(latest_snapshot.symbol_weights.items(), key=lambda x: x[1], reverse=True)[:3]
            for symbol, weight in sorted_symbols:
                symbol_name = tracker.get_symbol_name(symbol)
                display = f"{symbol}" if symbol_name == symbol else f"{symbol} {symbol_name}"
                top_symbols.append(f"{display}({weight:.1f})")

        symbols_str = ", ".join(top_symbols) if top_symbols else "暂无数据"

        change_emoji = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡️"
        change_color = "#16a34a" if change_pct > 0 else "#dc2626" if change_pct < 0 else "#64748b"

        html += f"""
        <div style="margin-bottom: 16px; padding: 12px; background: linear-gradient(135deg, #f8fafc, #f1f5f9); border-radius: 10px; border-left: 4px solid {color};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-weight: 600; color: #1e293b; font-size: 14px;">{block_name}</span>
                    <span style="font-size: 11px; color: #64748b;">({block_id})</span>
                </div>
                <div style="text-align: right;">
                    <span style="font-weight: 700; color: {color}; font-size: 16px;">{current_weight:.3f}</span>
                    <span style="font-size: 11px; color: {change_color}; margin-left: 4px;">{change_emoji} {change_pct:+.1f}%</span>
                </div>
            </div>
            <div style="display: flex; align-items: flex-end; height: 40px; margin: 8px 0; padding: 4px; background: rgba(255,255,255,0.5); border-radius: 4px;">
                {trend_bars}
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-top: 2px;">
                <span>{block_data[0][0]}</span>
                <span>{block_data[len(block_data)//2][0]}</span>
                <span>{block_data[-1][0]}</span>
            </div>
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e2e8f0;">
                <span style="font-size: 11px; color: #64748b;">热门个股: </span>
                <span style="font-size: 11px; color: #374151;">{symbols_str}</span>
            </div>
        </div>
        """

    html += "</div>"
    return html


