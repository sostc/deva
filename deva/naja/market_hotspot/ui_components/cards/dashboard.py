"""热点系统 UI - 仪表板摘要组件"""

import logging
from typing import Dict, Any
from deva.naja.register import SR
from deva.naja.market_hotspot.ui_components.styles import (
    heat_level,
    GRADIENT_US_MARKET, GRADIENT_INFO, GRADIENT_PINK, GRADIENT_SUCCESS,
    GRADIENT_NEUTRAL_DARK, GRADIENT_NEUTRAL, GRADIENT_WARNING,
    GRADIENT_PURPLE, GRADIENT_DANGER,
)

log = logging.getLogger(__name__)

def render_key_metrics_summary(report: Dict, strategy_stats: Dict) -> str:
    """核心指标摘要 - 放在最顶部"""
    from ..common import get_history_tracker

    global_hotspot = report.get('global_hotspot', 0)
    processed = report.get('processed_snapshots', 0)

    tracker = get_history_tracker()
    hotspot_count = len(tracker.block_hotspot_events_medium) if tracker else 0

    signal_count = strategy_stats.get('total_signals_generated', 0)

    if global_hotspot >= 0.7:
        ga_color = "#dc2626"
        ga_emoji = "🔥"
        ga_text = "极高"
    elif global_hotspot >= 0.5:
        ga_color = "#ea580c"
        ga_emoji = "⚡"
        ga_text = "高"
    elif global_hotspot >= 0.3:
        ga_color = "#ca8a04"
        ga_emoji = "👁️"
        ga_text = "中"
    else:
        ga_color = "#16a34a"
        ga_emoji = "💤"
        ga_text = "低"

    return f"""
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px;">
        <div style="background: linear-gradient(135deg, {ga_color}15, {ga_color}08); border: 2px solid {ga_color}; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 4px;">{ga_emoji}</div>
            <div style="font-size: 32px; font-weight: bold; color: {ga_color};">{global_hotspot:.2f}</div>
            <div style="font-size: 11px; color: #64748b;">末那识活跃度 · {ga_text}</div>
        </div>
        <div style="background: {GRADIENT_WARNING}; border: 2px solid #f59e0b; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 4px;">🔥</div>
            <div style="font-size: 32px; font-weight: bold; color: #b45309;">{hotspot_count}</div>
            <div style="font-size: 11px; color: #64748b;">热点事件</div>
        </div>
        <div style="background: {GRADIENT_INFO}; border: 2px solid #3b82f6; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 4px;">📡</div>
            <div style="font-size: 32px; font-weight: bold; color: #1d4ed8;">{signal_count}</div>
            <div style="font-size: 11px; color: #64748b;">交易信号</div>
        </div>
        <div style="background: {GRADIENT_PURPLE}; border: 2px solid #8b5cf6; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 4px;">📊</div>
            <div style="font-size: 32px; font-weight: bold; color: #6d28d9;">{processed//1000}k</div>
            <div style="font-size: 11px; color: #64748b;">处理数据</div>
        </div>
    </div>
    """


def render_live_hotspots() -> str:
    """实时热点 - 最重要的信息"""
    from ..common import get_history_tracker

    tracker = get_history_tracker()
    if not tracker:
        return ""

    hot_blocks = list(tracker.current_hot_blocks.items())[:5]
    hot_symbols = list(tracker.current_hot_symbols.items())[:8]

    if not hot_blocks and not hot_symbols:
        return ""

    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-bottom: 16px;">
        <div style="font-weight: 600; margin-bottom: 12px; color: #1e293b; font-size: 14px;">🔥 实时热点</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
    """

    if hot_blocks:
        html += '<div><div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">热门题材</div>'
        for i, (block_id, weight) in enumerate(hot_blocks, 1):
            block_name = tracker.get_block_name(block_id) if tracker else block_id
            color = "#dc2626" if weight > 0.7 else "#ea580c" if weight > 0.5 else "#ca8a04"
            html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; margin-bottom: 4px; background: #f8fafc; border-radius: 6px; font-size: 12px;">
                <span><span style="color: #94a3b8; margin-right: 6px;">{i}.</span>{block_name}</span>
                <span style="color: {color}; font-weight: 600;">{weight:.2f}</span>
            </div>
            """
        html += '</div>'

    if hot_symbols:
        html += '<div><div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">热门个股</div>'
        for i, (symbol, weight) in enumerate(hot_symbols, 1):
            symbol_name = tracker.get_symbol_name(symbol) if tracker else symbol
            color = "#dc2626" if weight > 5 else "#ea580c" if weight > 3 else "#ca8a04"
            html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; margin-bottom: 4px; background: #f8fafc; border-radius: 6px; font-size: 12px;">
                <span><span style="color: #94a3b8; margin-right: 6px;">{i}.</span>{symbol} {symbol_name if symbol_name != symbol else ''}</span>
                <span style="color: {color}; font-weight: 600;">{weight:.1f}</span>
            </div>
            """
        html += '</div>'

    html += '</div></div>'
    return html


def render_collapsible_system_status(report: Dict, strategy_stats: Dict) -> str:
    """可折叠的系统状态详情"""
    freq_summary = report.get('frequency_summary', {})
    dual_summary = report.get('dual_engine_summary', {})

    high = freq_summary.get('high_frequency', 0)
    medium = freq_summary.get('medium_frequency', 0)
    low = freq_summary.get('low_frequency', 0)
    total = high + medium + low or 1

    river_stats = dual_summary.get('river_stats', {})
    pytorch_stats = dual_summary.get('pytorch_stats', {})

    return f"""
    <details style="margin-bottom: 16px;">
        <summary style="cursor: pointer; padding: 12px 16px; background: {GRADIENT_NEUTRAL}; border: 1px solid #e2e8f0; border-radius: 8px; font-weight: 500; color: #1e293b; font-size: 13px; user-select: none;">
            ⚙️ 系统状态详情 (点击展开)
        </summary>
        <div style="padding: 16px; background: white; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 8px 8px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; font-size: 12px;">
                <div>
                    <div style="font-weight: 600; margin-bottom: 8px; color: #374151;">频率分布</div>
                    <div style="display: flex; gap: 8px;">
                        <span style="padding: 4px 8px; background: #fee2e2; color: #dc2626; border-radius: 4px;">高频 {high}</span>
                        <span style="padding: 4px 8px; background: #fef3c7; color: #b45309; border-radius: 4px;">中频 {medium}</span>
                        <span style="padding: 4px 8px; background: #dcfce7; color: #16a34a; border-radius: 4px;">低频 {low}</span>
                    </div>
                </div>
                <div>
                    <div style="font-weight: 600; margin-bottom: 8px; color: #374151;">双引擎</div>
                    <div style="color: #64748b;">
                        River: {river_stats.get('processed_count', 0):,} |
                        PyTorch: {pytorch_stats.get('inference_count', 0):,}
                    </div>
                </div>
            </div>
        </div>
    </details>
    """


def render_compact_signals(limit: int = 5) -> str:
    """紧凑的最近信号"""
    from ..common import get_strategy_manager

    manager = get_strategy_manager()
    if not manager:
        return ""

    signals = manager.get_recent_signals(n=limit)
    if not signals:
        return ""

    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-weight: 600; color: #1e293b; font-size: 14px;">📡 最近信号</div>
        </div>
    """

    for signal in signals:
        emoji = "🚀" if signal.signal_type == 'buy' else "💨" if signal.signal_type == 'sell' else "👀"
        color = "#16a34a" if signal.signal_type == 'buy' else "#dc2626" if signal.signal_type == 'sell' else "#64748b"

        html += f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; margin-bottom: 6px; background: #f8fafc; border-radius: 6px; font-size: 12px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="color: {color};">{emoji}</span>
                <span style="font-weight: 500;">{signal.symbol}</span>
                <span style="color: #94a3b8;">{signal.strategy_name}</span>
            </div>
            <span style="color: {color}; font-weight: 600; text-transform: uppercase;">{signal.signal_type}</span>
        </div>
        """

    html += '</div>'
    return html


def render_compact_noise_filter() -> str:
    """简化的噪音过滤状态"""
    try:
        hotspot_system = SR('hotspot_system')
        noise_filter = hotspot_system.noise_filter
        stats = noise_filter.get_stats()

        total = stats.get('total_processed', 0)
        filtered = stats.get('total_filtered', 0)
        filter_rate = stats.get('filter_rate', '0.00%')

        return f"""
        <div style="display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #f0f9ff; border-radius: 6px; font-size: 11px; color: #0369a1; margin-bottom: 16px;">
            <span>🔇</span>
            <span>噪音过滤: 已处理 {total:,} 条, 过滤 {filtered} 条 ({filter_rate})</span>
        </div>
        """
    except:
        return ""
