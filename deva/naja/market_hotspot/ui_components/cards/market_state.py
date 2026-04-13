"""热点系统 UI - 市场状态面板"""

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


def render_hotspot_details_card(details: Dict[str, Any]) -> str:
    """渲染热点计算详细数据（人类友好的算法展示）"""
    if not details or details.get('error'):
        return """
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 12px; color: #1e293b;">🧮 热点计算详情</div>
            <div style="color: #64748b; text-align: center; padding: 20px;">暂无详细数据</div>
        </div>
        """

    total = details.get('total_stocks', 0)
    up_count = details.get('up_count', 0)
    down_count = details.get('down_count', 0)
    flat_count = details.get('flat_count', 0)
    up_ratio = details.get('up_ratio', 0)
    down_ratio = details.get('down_ratio', 0)
    flat_ratio = details.get('flat_ratio', 0)
    mean_abs_return = details.get('mean_abs_return', 0)
    volatility = details.get('volatility', 0)
    hotspot = details.get('hotspot', 0)
    activity = details.get('activity', 0)
    hotspot_level = details.get('hotspot_level', details.get('hotspot_level', '未知'))
    activity_level = details.get('activity_level', '未知')
    hotspot_formula = details.get('hotspot_formula', '')
    activity_formula = details.get('activity_formula', '')

    hotspot_color = "#dc2626" if hotspot >= 0.6 else ("#ca8a04" if hotspot >= 0.3 else "#16a34a")
    activity_color = "#dc2626" if activity >= 0.7 else ("#ca8a04" if activity >= 0.15 else "#16a34a")

    up_bar_width = max(int(up_ratio * 100), 2)
    down_bar_width = max(int(down_ratio * 100), 2)
    flat_bar_width = max(int(flat_ratio * 100), 2)

    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b; display: flex; align-items: center; gap: 8px;">
            🧮 热点计算详情
            <span style="font-size: 11px; color: #64748b; font-weight: normal;">(算法解释)</span>
        </div>

        <div style="background: #f8fafc; border-radius: 8px; padding: 12px; margin-bottom: 16px;">
            <div style="font-size: 13px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">
                📊 市场分布 ({total} 只股票)
            </div>
            <div style="display: flex; gap: 8px; margin-bottom: 8px;">
                <div style="flex: 1; text-align: center;">
                    <div style="background: #16a34a; height: 24px; border-radius: 4px; width: {up_bar_width}%; min-width: 4px;"></div>
                    <div style="font-size: 11px; color: #16a34a; font-weight: 600; margin-top: 4px;">上涨 {up_count}只</div>
                    <div style="font-size: 10px; color: #64748b;">{up_ratio:.1%}</div>
                </div>
                <div style="flex: 1; text-align: center;">
                    <div style="background: #dc2626; height: 24px; border-radius: 4px; width: {down_bar_width}%; min-width: 4px;"></div>
                    <div style="font-size: 11px; color: #dc2626; font-weight: 600; margin-top: 4px;">下跌 {down_count}只</div>
                    <div style="font-size: 10px; color: #64748b;">{down_ratio:.1%}</div>
                </div>
                <div style="flex: 1; text-align: center;">
                    <div style="background: #94a3b8; height: 24px; border-radius: 4px; width: {flat_bar_width}%; min-width: 4px;"></div>
                    <div style="font-size: 11px; color: #64748b; font-weight: 600; margin-top: 4px;">平盘 {flat_count}只</div>
                    <div style="font-size: 10px; color: #64748b;">{flat_ratio:.1%}</div>
                </div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px;">
            <div style="background: #fefce8; padding: 10px; border-radius: 6px;">
                <div style="font-size: 11px; color: #64748b;">📐 活跃度参数</div>
                <div style="font-size: 12px; color: #1e293b; margin-top: 4px;">
                    均值绝对值: <strong>{mean_abs_return:.4f}</strong><br>
                    波动率: <strong>{volatility:.4f}</strong>
                </div>
            </div>
            <div style="background: #f0f9ff; padding: 10px; border-radius: 6px;">
                <div style="font-size: 11px; color: #64748b;">📋 分类阈值</div>
                <div style="font-size: 12px; color: #1e293b; margin-top: 4px;">
                    上涨: &gt;0.1%<br>
                    下跌: &lt;-0.1%<br>
                    平盘: 其他
                </div>
            </div>
        </div>

        <div style="border-top: 1px solid #e2e8f0; padding-top: 12px;">
            <div style="font-size: 12px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">
                🔍 计算公式解释
            </div>
            <div style="background: #f0fdf4; padding: 10px; border-radius: 6px; margin-bottom: 8px;">
                <div style="font-size: 11px; color: #16a34a; font-weight: 600; margin-bottom: 4px;">热点 = {hotspot:.3f}</div>
                <div style="font-size: 11px; color: #64748b;">{hotspot_formula}</div>
            </div>
            <div style="background: #f0f9ff; padding: 10px; border-radius: 6px;">
                <div style="font-size: 11px; color: #0284c7; font-weight: 600; margin-bottom: 4px;">活跃度 = {activity:.3f}</div>
                <div style="font-size: 11px; color: #64748b;">{activity_formula}</div>
            </div>
        </div>
    </div>
    """

    return html


def render_market_state_panel() -> str:
    """渲染当前市场热点状态面板（支持A股+美股混合展示）"""
    from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
    from ..common import get_market_phase_summary, get_ui_mode_context, get_hot_blocks_and_stocks
    from ..us_market import get_us_hotspot_data, get_us_market_summary

    tracker = get_history_tracker()
    phase_summary = get_market_phase_summary()
    cn_info = phase_summary.get('cn', {})
    us_info = phase_summary.get('us', {})

    is_cn = cn_info.get('active', False)
    is_us = us_info.get('active', False)

    market_mode = "A" if is_cn else ("US" if is_us else "idle")
    log.debug(f"[Cards-UI] render_market_state_panel: is_cn={is_cn}, is_us={is_us}, mode={market_mode}")

    if not tracker:
        return """<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;"><div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">👁️ 市场热点状态</div><div style="color: #64748b; text-align: center; padding: 20px;">历史追踪器未初始化</div></div>"""

    state_info = tracker.get_market_state_info()
    state = state_info.get('state', 'unknown')
    description = state_info.get('description', '等待数据...')
    global_attn = state_info.get('global_hotspot', 0)
    market_time = state_info.get('market_time', '')

    state_config = {
        'active': {'color': '#dc2626', 'bg': '#fef2f2', 'emoji': '🔥', 'label': '焦点集中'},
        'moderate': {'color': '#ca8a04', 'bg': '#fefce8', 'emoji': '⚡', 'label': '焦点较集中'},
        'quiet': {'color': '#0284c7', 'bg': '#f0f9ff', 'emoji': '👁️', 'label': '焦点分散'},
        'very_quiet': {'color': '#16a34a', 'bg': '#f0fdf4', 'emoji': '💤', 'label': '焦点涣散'},
        'unknown': {'color': '#64748b', 'bg': '#f8fafc', 'emoji': '❓', 'label': '未知状态'}
    }
    config = state_config.get(state, state_config['unknown'])

    hot_blocks_data = get_hot_blocks_and_stocks()
    hot_blocks = [(item['block_id'], item['weight']) for item in hot_blocks_data.get("blocks", [])]
    hot_symbols = [(item['symbol'], item['weight']) for item in hot_blocks_data.get("stocks", [])][:10]

    us_nq_pct = us_es_pct = us_ym_pct = None
    cn_sh_pct = cn_hs300_pct = cn_chinext_pct = None
    us_up_pct = us_down_pct = us_flat_pct = 0
    us_total = us_up = us_down = us_flat = 0

    try:
        asys = SR('hotspot_system')
        if asys:
            futures = asys.get_us_futures_indices()
            us_nq_pct = futures.get('NQ')
            us_es_pct = futures.get('ES')
            us_ym_pct = futures.get('YM')

            cn_idx = asys.get_cn_indices()
            cn_sh_pct = cn_idx.get('SH')
            cn_hs300_pct = cn_idx.get('HS300')
            cn_chinext_pct = cn_idx.get('CHINEXT')

        from ..us_market import get_us_market_summary
        summary = get_us_market_summary()
        us_total = summary.get('stock_count', 0)
        us_up = summary.get('up_count', 0)
        us_down = summary.get('down_count', 0)
        us_flat = summary.get('flat_count', 0)
        if us_total > 0:
            us_up_pct = us_up / us_total * 100
            us_down_pct = us_down / us_total * 100
            us_flat_pct = us_flat / us_total * 100
    except Exception:
        pass

    def _fmt_idx(pct):
        if pct is None: return "--"
        return f"{pct:+.2f}%"
    def _idx_color(pct):
        if pct is None: return "#64748b"
        return "#16a34a" if pct >= 0 else "#dc2626"
    from deva.naja.market_hotspot.ui_components.styles import format_market_line

    cn_line = format_market_line("🇨🇳 A股", cn_info)
    us_line = format_market_line("🇺🇸 美股", us_info)

    mode_ctx = get_ui_mode_context()
    mode_label = mode_ctx.get('mode_label', '实盘模式')
    if mode_ctx.get('is_replay') and mode_ctx.get('market_time_str'):
        time_display = f"📅 {mode_ctx.get('market_time_str')} | {cn_line} | {us_line} | {mode_label}"
    elif market_time:
        time_display = f"📅 {market_time} | {cn_line} | {us_line} | {mode_label}"
    else:
        time_display = f"📅 等待行情数据... | {cn_line} | {us_line} | {mode_label}"

    us_data = get_us_hotspot_data()
    us_summary = get_us_market_summary() if us_data else {}
    has_us_data = us_data and us_data.get('global_hotspot', 0) > 0

    log.debug(f"[Cards-UI] DEBUG render_market_state_panel: us_data={us_data}, has_us_data={has_us_data}, is_cn={is_cn}, is_us={is_us}")

    # 根据市场时间决定显示模式
    if is_us and not is_cn:
        # 纯美股时间：只显示美股数据
        show_us_only = True
        show_cn_only = False
    elif is_cn and not is_us:
        # 纯A股时间：只显示A股数据
        show_us_only = False
        show_cn_only = True
    elif is_us and is_cn:
        # 同时交易：混合显示
        show_us_only = False
        show_cn_only = False
    else:
        # 非交易时间：根据数据判断
        show_us_only = has_us_data and not tracker.current_hot_blocks
        show_cn_only = bool(tracker.current_hot_blocks) and not has_us_data
        us_blocks = us_data.get('block_hotspot', {})
        sorted_us_blocks = sorted(us_blocks.items(), key=lambda x: x[1], reverse=True)[:5]

    if has_us_data and not show_us_only:
        cn_hotspot = global_attn
        us_hotspot = us_data.get('global_hotspot', 0)
        combined_hotspot = (cn_hotspot + us_hotspot) / 2
        time_display = f"📅 {market_time} | {cn_line} | {us_line} | {mode_label}"

    panel_title = "🇺🇸 美股市场热点" if show_us_only else ("🇨🇳 A股市场热点" if show_cn_only else "👁️ 市场热点")

    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-weight: 600; color: #1e293b;">{panel_title}</div>
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="font-size: 12px; color: #64748b;">{time_display}</div>
                <div style="background: {config['bg']}; color: {config['color']}; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">{config['emoji']} {config['label']}</div>
            </div>
        </div>
    """

    # 美股数据展示（美股时间 或 混合时间）
    if has_us_data and not show_cn_only:
        us_blocks = us_data.get('block_hotspot', {})
        us_symbols = us_data.get('symbol_weights', {})
        us_changes = us_data.get('symbol_changes', {})
        us_global = us_data.get('global_hotspot', 0)
        us_activity = us_data.get('activity', 0)

        sorted_us_blocks = sorted(us_blocks.items(), key=lambda x: x[1], reverse=True)[:5]
        sorted_us_symbols = sorted(us_symbols.items(), key=lambda x: x[1], reverse=True)[:10]

        html += f"""
        <div style="background: {GRADIENT_US_MARKET}; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="color: #f8fafc; font-size: 13px; font-weight: 600;">🇺🇸 美股市场</div>
                <div style="display: flex; gap: 16px; align-items: center;">
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <span style="color: #94a3b8; font-size: 10px;">纳指</span>
                        <span style="color: {_idx_color(us_nq_pct)}; font-size: 11px; font-weight: 600;">{_fmt_idx(us_nq_pct)}</span>
                        <span style="color: #94a3b8; font-size: 10px;">标普</span>
                        <span style="color: {_idx_color(us_es_pct)}; font-size: 11px; font-weight: 600;">{_fmt_idx(us_es_pct)}</span>
                        <span style="color: #94a3b8; font-size: 10px;">道指</span>
                        <span style="color: {_idx_color(us_ym_pct)}; font-size: 11px; font-weight: 600;">{_fmt_idx(us_ym_pct)}</span>
                    </div>
                    <div style="display: flex; gap: 12px; border-left: 1px solid #334155; padding-left: 12px;">
                        <div style="text-align: center;">
                            <div style="color: #94a3b8; font-size: 9px;">热点度</div>
                            <div style="color: #22c55e; font-size: 14px; font-weight: 700;">{us_global:.3f}</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: #94a3b8; font-size: 9px;">活跃度</div>
                            <div style="color: #3b82f6; font-size: 14px; font-weight: 700;">{us_activity:.3f}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """

        if sorted_us_blocks:
            html += """<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #7c3aed; margin-bottom: 8px;">🇺🇸 美股热门题材</div><div style="display: flex; flex-wrap: wrap; gap: 8px;">"""
            for block_id, weight in sorted_us_blocks:
                bar_width = min(weight * 20, 100)
                color = "#dc2626" if weight > 0.5 else ("#ca8a04" if weight > 0.3 else "#16a34a")
                html += f"""<div style="background: #f1f5f9; border-radius: 8px; padding: 10px 14px; min-width: 140px;"><div style="font-size: 14px; font-weight: 600; color: #1e293b;">{block_id}</div><div style="display: flex; align-items: center; gap: 8px; margin-top: 6px;"><div style="background: {color}; height: 6px; border-radius: 3px; width: {bar_width}px; min-width: 6px;"></div><span style="font-size: 13px; font-weight: 600; color: #1e293b;">{weight:.2f}</span></div></div>"""
            html += "</div></div>"

        if sorted_us_symbols:
            html += """<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #2563eb; margin-bottom: 8px;">🇺🇸 美股热门股票</div><div style="display: flex; flex-wrap: wrap; gap: 6px;">"""
            for symbol, weight in sorted_us_symbols:
                color = "#dc2626" if weight > 5 else ("#ea580c" if weight > 3 else ("#ca8a04" if weight > 2 else "#16a34a"))
                bg_color = "#fef2f2" if weight > 5 else ("#fff7ed" if weight > 3 else ("#fef3c7" if weight > 2 else "#f0fdf4"))
                change = us_changes.get(symbol)
                change_str = f"{change:+.2f}%" if change is not None else ""
                change_color = "#16a34a" if change and change > 0 else ("#dc2626" if change and change < 0 else "#64748b")
                html += f"""<div style="background: {bg_color}; border-radius: 6px; padding: 6px 10px; font-size: 11px; display: flex; align-items: center; gap: 4px;"><span style="color: #1e293b; font-weight: 600;">{symbol.upper()}</span>{f'<span style="font-size: 10px; color: {change_color}; font-weight: 600;">{change_str}</span>' if change_str else ''}<span style="color: {color}; font-weight: 600;">{weight:.1f}</span></div>"""
            html += "</div></div>"

        if us_total > 0:
            html += f"""<div style="background: #f1f5f9; border-radius: 6px; padding: 8px 12px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
<span style="font-size: 11px; color: #64748b;">🇺🇸 美股涨跌分布 ({us_total}只)</span>
<span style="font-size: 10px; color: #64748b;">🔼{us_up} 🔽{us_down} ➡️{us_flat}</span>
</div>
<div style="display: flex; gap: 2px; height: 18px; border-radius: 4px; overflow: hidden;">
<div style="background: #22c55e; width: {us_up_pct:.0f}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 9px; font-weight: 600;">{us_up_pct:.0f}%</div>
<div style="background: #94a3b8; width: {us_flat_pct:.0f}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 9px; font-weight: 600;">{us_flat_pct:.0f}%</div>
<div style="background: #ef4444; width: {us_down_pct:.0f}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 9px; font-weight: 600;">{us_down_pct:.0f}%</div>
</div>
</div>"""

    # A股数据展示（A股时间 或 混合时间 或 非交易时间有A股数据）
    if not show_us_only:
        cn_description = description if description != '等待数据...' else "等待A股行情数据..."
        html += f"""<div style="background: {config['bg']}; border-left: 4px solid {config['color']}; padding: 12px 16px; margin-bottom: 16px; border-radius: 0 8px 8px 0;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-size: 13px; color: #1e293b; line-height: 1.5;"><strong>📊 {cn_description}</strong></div>
                <div style="display: flex; gap: 10px; align-items: center;">
                    <span style="color: #64748b; font-size: 10px;">上证</span>
                    <span style="color: {_idx_color(cn_sh_pct)}; font-size: 11px; font-weight: 600;">{_fmt_idx(cn_sh_pct)}</span>
                    <span style="color: #64748b; font-size: 10px;">沪深300</span>
                    <span style="color: {_idx_color(cn_hs300_pct)}; font-size: 11px; font-weight: 600;">{_fmt_idx(cn_hs300_pct)}</span>
                    <span style="color: #64748b; font-size: 10px;">创业板</span>
                    <span style="color: {_idx_color(cn_chinext_pct)}; font-size: 11px; font-weight: 600;">{_fmt_idx(cn_chinext_pct)}</span>
                </div>
            </div>
            <div style="font-size: 12px; color: #64748b; margin-top: 6px;">A股市场热点指数: <strong>{global_attn:.3f}</strong></div>
        </div>"""
    else:
        html += """<div style="background: #f8fafc; border-left: 4px solid #94a3b8; padding: 12px 16px; margin-bottom: 16px; border-radius: 0 8px 8px 0;">
            <div style="font-size: 13px; color: #64748b; line-height: 1.5;"><strong>🇨🇳 A股已休市</strong></div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 6px;">A股市场热点指数: <strong>--</strong></div>
        </div>"""

    if not show_us_only and hot_blocks:
        from deva.naja.dictionary.blocks import get_block_dictionary
        html += """<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 8px;">📈 A股交易热点题材 Top5</div><div style="display: flex; flex-wrap: wrap; gap: 8px;">"""
        bd = get_block_dictionary()
        for block_id, weight in hot_blocks:
            block_name = tracker.get_block_name(block_id)
            if not block_name or block_name == "默认" or block_name == "0.0":
                info = bd.get_block_info(block_id, 'CN')
                if info:
                    block_name = info.name
                else:
                    continue  # 跳过无效的题材
            bar_width = min(weight * 20, 100)
            html += f"""<div style="background: #f1f5f9; border-radius: 8px; padding: 10px 14px; min-width: 140px;"><div style="font-size: 14px; font-weight: 600; color: #1e293b;">{block_name}</div><div style="display: flex; align-items: center; gap: 8px; margin-top: 6px;"><div style="background: {config['color']}; height: 6px; border-radius: 3px; width: {bar_width}px; min-width: 6px;"></div><span style="font-size: 13px; font-weight: 600; color: #1e293b;">{weight:.4f}</span></div></div>"""
        html += "</div></div>"

    if not show_us_only and hot_symbols:
        from deva.naja.dictionary.blocks import get_stock_name
        html += """<div><div style="font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 8px;">🔥 A股交易热点个股 Top10</div><div style="display: flex; flex-wrap: wrap; gap: 6px;">"""
        for symbol, weight in hot_symbols:
            symbol_name = get_stock_name(symbol) or tracker.get_symbol_name(symbol) or symbol
            change = tracker.get_symbol_change(symbol)
            change_str = f"{change:+.2f}%" if change is not None else ""
            change_color = "#16a34a" if change and change > 0 else ("#dc2626" if change and change < 0 else "#64748b")
            html += f"""<div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 6px; padding: 4px 8px; font-size: 11px; display: flex; align-items: center; gap: 4px; min-width: 0;"><span style="color: #92400e; font-weight: 600;">{symbol}</span><span style="color: #1e293b; max-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{symbol_name}</span>{f'<span style="font-size: 10px; color: {change_color}; font-weight: 600;">{change_str}</span>' if change_str else ''}<span style="color: #92400e; font-weight: 600;">{weight:.1f}</span></div>"""
        html += "</div></div>"

    if not hot_blocks and not hot_symbols and not has_us_data and not show_us_only:
        html += """<div style="background: #f8fafc; border-radius: 8px; padding: 24px; text-align: center; color: #64748b;"><div style="font-size: 24px; margin-bottom: 8px;">📊</div><div>暂无市场热点数据</div><div style="font-size: 12px; margin-top: 4px;">等待市场数据输入...</div></div>"""

    html += "</div>"
    return html
