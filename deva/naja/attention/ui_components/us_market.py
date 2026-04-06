"""美股市场注意力 UI 组件

复用手游 UI 组件实现美股数据混合展示
"""

from typing import Dict, Any, List, Tuple
import logging

log = logging.getLogger(__name__)


def get_us_attention_data() -> Dict[str, Any]:
    """获取美股注意力数据"""
    try:
        from deva.naja.attention.integration import get_attention_integration
        integration = get_attention_integration()
        log.debug(f"[US-UI] get_us_attention_data: integration={integration is not None}")

        if integration is None:
            log.warning("[US-UI] integration 为 None")
            return {}

        log.debug(f"[US-UI] integration._initialized={getattr(integration, '_initialized', 'N/A')}")
        log.debug(f"[US-UI] integration.attention_system={getattr(integration, 'attention_system', 'N/A')}")

        if integration.attention_system is None:
            log.warning("[US-UI] attention_system 为 None")
            return {}

        result = integration.attention_system.get_us_attention_state()
        log.debug(f"[US-UI] get_us_attention_state() = {result}")
        return result
    except Exception as e:
        log.error(f"[US-UI] 获取美股注意力数据失败: {e}")
        import traceback
        traceback.print_exc()
    return {}


def render_us_market_panel(us_data: Dict[str, Any] = None) -> str:
    """渲染美股市场总览面板

    复用手游的 render_market_state_panel 样式，但展示美股数据
    """
    if us_data is None:
        us_data = get_us_attention_data()

    if not us_data:
        from .common import get_market_phase_summary, get_ui_mode_context
        phase_summary = get_market_phase_summary()
        mode_ctx = get_ui_mode_context()
        us_info = phase_summary.get('us', {})
        phase_name = us_info.get('phase_name', '休市')
        next_phase = us_info.get('next_phase_name', '')
        next_time = us_info.get('next_change_time', '')
        next_hint = f" →{next_phase} {next_time}" if us_info.get('phase') == 'closed' and next_time else ""
        mode_label = mode_ctx.get('mode_label', '实盘模式')
        time_hint = mode_ctx.get('market_time_str', '') if mode_ctx.get('is_replay') else ""
        return f"""<div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%); border-radius: 12px; padding: 20px; margin-top: 16px;">
<div style="color: #94a3b8; font-size: 14px;">📊 美股市场注意力</div>
<div style="color: #64748b; font-size: 12px; margin-top: 8px;">当前状态: {phase_name}{next_hint} | {mode_label} {time_hint}</div>
</div>"""

    global_attention = us_data.get('global_attention', 0.5)
    activity = us_data.get('activity', 0.5)
    sector_attention = us_data.get('block_attention', {})
    symbol_weights = us_data.get('symbol_weights', {})

    sorted_sectors = sorted(sector_attention.items(), key=lambda x: x[1], reverse=True)[:8]
    top_stocks = sorted(symbol_weights.items(), key=lambda x: x[1], reverse=True)[:15]

    attention_color = "#22c55e" if global_attention > 0.6 else ("#eab308" if global_attention > 0.4 else "#ef4444")
    activity_color = "#22c55e" if activity > 0.6 else ("#eab308" if activity > 0.4 else "#ef4444")

    html = f"""<div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%); border-radius: 12px; padding: 20px; margin-top: 16px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
<div style="color: #f8fafc; font-size: 16px; font-weight: 600;">🇺🇸 美股市场</div>
<div style="display: flex; gap: 16px;">
<div style="text-align: center;">
<div style="color: #94a3b8; font-size: 10px;">注意力</div>
<div style="color: {attention_color}; font-size: 18px; font-weight: 700;">{global_attention:.3f}</div>
</div>
<div style="text-align: center;">
<div style="color: #94a3b8; font-size: 10px;">活跃度</div>
<div style="color: {activity_color}; font-size: 18px; font-weight: 700;">{activity:.3f}</div>
</div>
</div>
</div>
<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">"""

    if sorted_sectors:
        html += """<div><div style="color: #7c3aed; font-size: 12px; font-weight: 600; margin-bottom: 10px;">📊 热门题材</div>"""
        max_sector_weight = sorted_sectors[0][1] if sorted_sectors else 1
        for sector, weight in sorted_sectors[:5]:
            pct = weight / max_sector_weight * 100 if max_sector_weight > 0 else 0
            bar_color = "#dc2626" if weight > 0.5 else ("#ea580c" if weight > 0.3 else "#22c55e")
            html += f"""<div style="margin-bottom: 8px;">
<div style="display: flex; justify-content: space-between; color: #e2e8f0; font-size: 11px; margin-bottom: 4px;">
<span>{sector}</span><span style="color: {bar_color};">{weight:.3f}</span>
</div>
<div style="background: #334155; height: 4px; border-radius: 2px; overflow: hidden;">
<div style="background: {bar_color}; height: 100%; width: {pct}%; border-radius: 2px;"></div>
</div>
</div>"""
        html += "</div>"

    if top_stocks:
        html += """<div><div style="color: #2563eb; font-size: 12px; font-weight: 600; margin-bottom: 10px;">📈 热门股票</div><div style="display: flex; flex-wrap: wrap; gap: 4px;">"""
        for symbol, weight in top_stocks[:10]:
            if weight > 3:
                bg = "#fef2f2"
                color = "#dc2626"
            elif weight > 2:
                bg = "#fff7ed"
                color = "#ea580c"
            elif weight > 1:
                bg = "#fef3c7"
                color = "#ca8a04"
            else:
                bg = "#f0fdf4"
                color = "#16a34a"
            html += f"""<div style="background: {bg}; color: {color}; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: 500;">{symbol.upper()} {weight:.1f}</div>"""
        html += "</div></div>"

    html += "</div></div>"

    return html


def render_us_hot_sectors_and_stocks(us_data: Dict[str, Any] = None) -> str:
    """渲染美股热门题材和股票（复用手游组件样式）

    直接复用 render_hot_blocks_and_stocks 的样式逻辑
    """
    if us_data is None:
        us_data = get_us_attention_data()

    if not us_data:
        return ""

    sector_attention = us_data.get('block_attention', {})
    symbol_weights = us_data.get('symbol_weights', {})

    sorted_sectors = sorted(sector_attention.items(), key=lambda x: x[1], reverse=True)[:10]
    sorted_stocks = sorted(symbol_weights.items(), key=lambda x: x[1], reverse=True)[:20]

    sectors = sorted_sectors
    stocks = [(sym, w) for sym, w in sorted_stocks]

    if not sectors and not stocks:
        return ""

    html = """<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;"><div style="font-weight: 600; margin-bottom: 16px; color: #1e293b; font-size: 16px;">🇺🇸 美股热门题材与股票 <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">市场热点排名</span></div><div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">"""

    if sectors:
        html += """<div><div style="font-weight: 600; color: #7c3aed; margin-bottom: 12px; font-size: 14px;">📊 美股热门题材 Top 10</div>"""
        max_sector_weight = max([w for _, w in sectors[:10]]) if sectors else 1

        for i, (sector_id, weight) in enumerate(sectors[:10], 1):
            if weight > 0.7:
                color, status, bg_gradient = "#dc2626", "🔥 极高", "linear-gradient(90deg, #fee2e2, #fecaca)"
            elif weight > 0.5:
                color, status, bg_gradient = "#ea580c", "⚡ 高", "linear-gradient(90deg, #ffedd5, #fed7aa)"
            elif weight > 0.3:
                color, status, bg_gradient = "#ca8a04", "👁️ 中", "linear-gradient(90deg, #fef3c7, #fde68a)"
            else:
                color, status, bg_gradient = "#16a34a", "💤 低", "linear-gradient(90deg, #dcfce7, #bbf7d0)"

            progress_width = (weight / max_sector_weight * 100) if max_sector_weight > 0 else 0

            html += f"""<div style="padding: 10px 12px; margin-bottom: 8px; background: {bg_gradient}; border-radius: 8px; border-left: 3px solid {color};"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;"><div style="display: flex; align-items: center; gap: 8px;"><span style="color: #64748b; font-weight: 600; min-width: 20px;">{i}.</span><span style="font-weight: 500; color: #1e293b;">{sector_id}</span></div><div style="text-align: right;"><span style="color: {color}; font-weight: 700; font-size: 14px;">{weight:.3f}</span><span style="font-size: 10px; color: {color}; margin-left: 4px;">{status}</span></div></div><div style="background: rgba(255,255,255,0.5); height: 4px; border-radius: 2px; overflow: hidden;"><div style="background: {color}; height: 100%; width: {progress_width}%; border-radius: 2px;"></div></div></div>"""
        html += "</div>"

    if stocks:
        html += """<div><div style="font-weight: 600; color: #2563eb; margin-bottom: 12px; font-size: 14px;">📈 美股热门股票 Top 20</div><div style="display: flex; flex-wrap: wrap; gap: 6px;">"""
        for i, stock_item in enumerate(stocks[:20], 1):
            if isinstance(stock_item, dict):
                symbol = stock_item.get("symbol", "")
                weight = stock_item.get("weight", 0)
                symbol_name = stock_item.get("name", symbol)
            else:
                symbol, weight = stock_item
                symbol_name = symbol

            if weight > 5:
                color, bg_color, border_color = "#dc2626", "#fef2f2", "#fecaca"
            elif weight > 3:
                color, bg_color, border_color = "#ea580c", "#fff7ed", "#fed7aa"
            elif weight > 2:
                color, bg_color, border_color = "#ca8a04", "#fef3c7", "#fde68a"
            elif weight > 1:
                color, bg_color, border_color = "#16a34a", "#f0fdf4", "#bbf7d0"
            else:
                color, bg_color, border_color = "#64748b", "#f8fafc", "#e2e8f0"

            html += f"""<div style="background: {bg_color}; border: 1px solid {border_color}; padding: 6px 10px; border-radius: 6px; display: inline-flex; flex-direction: column; align-items: center; min-width: 60px;">
<div style="font-weight: 600; color: #1e293b; font-size: 11px;">{symbol_name.upper() if len(symbol_name) <= 6 else symbol_name[:6]}</div>
<div style="color: {color}; font-size: 12px; font-weight: 700;">{weight:.2f}</div>
</div>"""
        html += "</div></div>"

    html += "</div></div>"

    return html


def get_us_market_summary() -> Dict[str, Any]:
    """获取美股市场摘要（包含涨跌统计）"""
    us_data = get_us_attention_data()
    log.debug(f"[US-UI] get_us_market_summary: us_data={us_data}")

    if not us_data:
        return {
            'stock_count': 0,
            'up_count': 0,
            'down_count': 0,
            'flat_count': 0,
            'up_ratio': 0,
            'global_attention': 0.5,
            'activity': 0.5,
        }

    sector_attention = us_data.get('block_attention', {})
    symbol_weights = us_data.get('symbol_weights', {})

    total = len(symbol_weights)
    up_count = sum(1 for w in symbol_weights.values() if w > 0.3)
    down_count = sum(1 for w in symbol_weights.values() if w < -0.3)
    flat_count = total - up_count - down_count
    up_ratio = up_count / total if total > 0 else 0

    return {
        'stock_count': total,
        'up_count': up_count,
        'down_count': down_count,
        'flat_count': flat_count,
        'up_ratio': up_ratio,
        'global_attention': us_data.get('global_attention', 0.5),
        'activity': us_data.get('activity', 0.5),
        'sector_count': len(sector_attention),
    }


def render_us_market_summary() -> str:
    """渲染美股市场摘要（涨跌分布）"""
    summary = get_us_market_summary()

    if summary['stock_count'] == 0:
        from .common import get_market_phase_summary, get_ui_mode_context
        phase_summary = get_market_phase_summary()
        mode_ctx = get_ui_mode_context()
        us_info = phase_summary.get('us', {})
        phase_name = us_info.get('phase_name', '休市')
        next_phase = us_info.get('next_phase_name', '')
        next_time = us_info.get('next_change_time', '')
        next_hint = f" →{next_phase} {next_time}" if us_info.get('phase') == 'closed' and next_time else ""
        mode_label = mode_ctx.get('mode_label', '实盘模式')
        time_hint = mode_ctx.get('market_time_str', '') if mode_ctx.get('is_replay') else ""
        return f"""<div style="background: #1e3a5f; border-radius: 8px; padding: 16px; margin-top: 12px;">
<div style="color: #94a3b8; font-size: 12px;">🇺🇸 美股状态: {phase_name}{next_hint} | {mode_label} {time_hint}</div>
</div>"""

    global_attention = summary['global_attention']
    activity = summary['activity']
    up_count = summary['up_count']
    down_count = summary['down_count']
    flat_count = summary['flat_count']
    total = summary['stock_count']

    up_pct = up_count / total * 100 if total > 0 else 0
    down_pct = down_count / total * 100 if total > 0 else 0
    flat_pct = flat_count / total * 100 if total > 0 else 0

    attention_bar = global_attention * 100
    activity_bar = activity * 100

    html = f"""<div style="background: #1e3a5f; border-radius: 8px; padding: 16px; margin-top: 12px;">
<div style="display: flex; justify-content: space-between; margin-bottom: 12px;">
<div style="color: #f8fafc; font-size: 14px; font-weight: 600;">🇺🇸 美股涨跌分布</div>
<div style="color: #94a3b8; font-size: 11px;">{total} 只股票</div>
</div>
<div style="display: flex; gap: 4px; height: 24px; border-radius: 4px; overflow: hidden; margin-bottom: 12px;">
<div style="background: #22c55e; width: {up_pct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px; font-weight: 600;" title="上涨 {up_count} 只">{up_pct:.0f}%</div>
<div style="background: #64748b; width: {flat_pct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px; font-weight: 600;" title="平盘 {flat_count} 只">{flat_pct:.0f}%</div>
<div style="background: #ef4444; width: {down_pct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px; font-weight: 600;" title="下跌 {down_count} 只">{down_pct:.0f}%</div>
</div>
<div style="display: flex; justify-content: space-between; font-size: 11px;">
<div style="color: #94a3b8;">注意力</div>
<div style="color: #94a3b8;">活跃度</div>
</div>
<div style="display: flex; gap: 8px; margin-top: 4px;">
<div style="flex: 1; background: #334155; height: 6px; border-radius: 3px; overflow: hidden;">
<div style="background: #22c55e; height: 100%; width: {attention_bar}%;"></div>
</div>
<div style="flex: 1; background: #334155; height: 6px; border-radius: 3px; overflow: hidden;">
<div style="background: #3b82f6; height: 100%; width: {activity_bar}%;"></div>
</div>
</div>
<div style="display: flex; justify-content: space-between; font-size: 10px; margin-top: 4px;">
<div style="color: #22c55e;">{global_attention:.3f}</div>
<div style="color: #3b82f6;">{activity:.3f}</div>
</div>
</div>"""

    return html
