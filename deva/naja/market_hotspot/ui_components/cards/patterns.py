"""热点系统 UI - 模式识别与热门题材"""

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

def render_pytorch_patterns() -> str:
    """渲染 PyTorch 模式识别结果"""
    from ..common import get_market_hotspot_integration

    try:
        integration = get_market_hotspot_integration()
        if not integration or not integration.hotspot_system:
            return ""

        dual_engine = integration.hotspot_system.dual_engine
        if not dual_engine or not dual_engine.pytorch:
            return ""

        pytorch = dual_engine.pytorch
        pattern_cache = pytorch._pattern_cache

        if not pattern_cache:
            return ""

        patterns = sorted(pattern_cache.values(), key=lambda x: x.timestamp, reverse=True)[:10]

        html = """<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;"><div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">🔍 PyTorch 模式识别结果 <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">深度学习异动识别</span></div>"""

        pattern_styles = {
            'breakout': ('🚀', '#dc2626', '突破'),
            'reversal': ('🔄', '#7c3aed', '反转'),
            'accumulation': ('📦', '#059669', '吸筹'),
            'distribution': ('📤', '#ea580c', '派发'),
            'volatility_expansion': ('⚡', '#f59e0b', '波动扩张'),
        }

        for pattern in patterns:
            emoji, color, label = pattern_styles.get(pattern.pattern_type, ('🔍', '#64748b', pattern.pattern_type))
            confidence = pattern.confidence
            bg_color = '#fef2f2' if confidence >= 0.8 else ('#fff7ed' if confidence >= 0.6 else '#f8fafc')
            border_color = '#fecaca' if confidence >= 0.8 else ('#fed7aa' if confidence >= 0.6 else '#e2e8f0')

            html += f"""<div style="padding: 12px; margin-bottom: 8px; background: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; border-left: 3px solid {color};"><div style="display: flex; justify-content: space-between; align-items: center;"><div style="display: flex; align-items: center; gap: 8px;"><span style="font-size: 18px;">{emoji}</span><div><div style="font-weight: 600; color: #1e293b;">{pattern.symbol}</div><div style="font-size: 11px; color: #64748b;">{label} | 得分: {pattern.pattern_score:.2f}</div></div></div><div style="text-align: right;"><div style="font-weight: 700; color: {color}; font-size: 14px;">{confidence:.1%}</div><div style="font-size: 10px; color: #94a3b8;">置信度</div></div></div></div>"""

        html += '</div>'
        return html
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"渲染 PyTorch 模式结果失败: {e}")
        return ""


def render_hot_blocks_and_stocks(hot_data: Dict[str, Any]) -> str:
    """渲染热门题材和股票"""
    blocks = hot_data.get("blocks", [])
    stocks = hot_data.get("stocks", [])

    if not blocks and not stocks:
        return ""

    from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
    tracker = get_history_tracker()

    html = """<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;"><div style="font-weight: 600; margin-bottom: 16px; color: #1e293b; font-size: 16px;">🔥 热门题材与股票 <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">市场热点排名</span></div><div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">"""

    if blocks:
        html += """<div><div style="font-weight: 600; color: #7c3aed; margin-bottom: 12px; font-size: 14px;">📊 热门题材 Top 10</div>"""
        max_block_weight = max([w["weight"] for w in blocks[:10]]) if blocks else 1

        for i, block_item in enumerate(blocks[:10], 1):
            if isinstance(block_item, dict):
                block_id = block_item.get("block_id", "")
                block_name = block_item.get("name", block_id)
                weight = block_item.get("weight", 0)
            else:
                block_id, weight = block_item
                block_name = tracker.get_block_name(block_id) if tracker else block_id

            color, status, bg_gradient = heat_level(weight)

            display_name = block_name if block_name and block_name != block_id else block_id
            progress_width = (weight / max_block_weight * 100) if max_block_weight > 0 else 0

            html += f"""<div style="padding: 10px 12px; margin-bottom: 8px; background: {bg_gradient}; border-radius: 8px; border-left: 3px solid {color};"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;"><div style="display: flex; align-items: center; gap: 8px;"><span style="color: #64748b; font-weight: 600; min-width: 20px;">{i}.</span><span style="font-weight: 500; color: #1e293b;">{display_name}</span></div><div style="text-align: right;"><span style="color: {color}; font-weight: 700; font-size: 14px;">{weight:.3f}</span><span style="font-size: 10px; color: {color}; margin-left: 4px;">{status}</span></div></div><div style="background: rgba(255,255,255,0.5); height: 4px; border-radius: 2px; overflow: hidden;"><div style="background: {color}; height: 100%; width: {progress_width}%; border-radius: 2px;"></div></div></div>"""
        html += "</div>"

    if stocks:
        html += """<div><div style="font-weight: 600; color: #2563eb; margin-bottom: 12px; font-size: 14px;">📈 热门股票 Top 20</div><div style="display: flex; flex-wrap: wrap; gap: 6px;">"""
        for i, stock_item in enumerate(stocks[:20], 1):
            if isinstance(stock_item, dict):
                symbol = stock_item.get("symbol", "")
                weight = stock_item.get("weight", 0)
                symbol_name = stock_item.get("name", symbol)
                if symbol_name == symbol and not symbol.startswith(('sh', 'sz', 'bj', 'SH', 'SZ', 'BJ')):
                    pass
            else:
                symbol, weight = stock_item
                symbol_name = tracker.get_symbol_name(symbol) if tracker else symbol

            if weight > 5:
                color, bg_color, border_color = "#dc2626", "#fef2f2", "#fecaca"
            elif weight > 3:
                color, bg_color, border_color = "#ea580c", "#fff7ed", "#fed7aa"
            elif weight > 2:
                color, bg_color, border_color = "#ca8a04", "#fefce8", "#fef08a"
            else:
                color, bg_color, border_color = "#16a34a", "#f0fdf4", "#bbf7d0"

            symbol_change = tracker.get_symbol_change(symbol) if tracker else None
            change_str = f"{symbol_change:+.2f}%" if symbol_change is not None else ""
            change_color = "#16a34a" if symbol_change and symbol_change > 0 else ("#dc2626" if symbol_change and symbol_change < 0 else "#64748b")

            html += f"""<div style="background: {bg_color}; border: 1px solid {border_color}; border-radius: 6px; padding: 4px 8px; font-size: 11px; display: flex; align-items: center; gap: 4px; min-width: 0;"><span style="color: #64748b; font-weight: 600;">{i}.</span><span style="font-weight: 600; color: #1e293b; max-width: 60px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{symbol}</span>{f'<span style="color: #475569; max-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{symbol_name}</span>' if symbol_name and symbol_name != symbol else ''}{f'<span style="font-size: 10px; color: {change_color}; font-weight: 600;">{change_str}</span>' if change_str else ''}<span style="color: {color}; font-weight: 600;">{weight:.1f}</span></div>"""
        html += "</div></div>"

    html += "</div></div>"
    return html
