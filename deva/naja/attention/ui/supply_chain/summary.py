"""供应链 UI - 摘要"""

from typing import List, Dict, Tuple
from datetime import datetime

from pywebio.output import (
    put_html, put_row, put_column, put_text, put_button, put_table,
    put_scope, use_scope, clear_scope
)
from pywebio.session import run_js
import math

def get_supply_chain_summary_html() -> str:
    """获取供应链摘要的 HTML（用于嵌入其他页面）"""
    from deva.naja.cognition import get_supply_chain_linker

    linker = get_supply_chain_linker()
    summary = linker.get_supply_chain_summary()
    hot = linker.get_hot_narratives(3)

    hot_html = ""
    if hot:
        for narrative, importance in hot:
            hot_html += f'<span style="background: rgba(239,68,68,0.2); padding: 2px 8px; border-radius: 12px; font-size: 11px; color: #fca5a5; margin-right: 4px;">{narrative} {importance:.1f}</span>'

    return f"""
    <div style="background: rgba(59,130,246,0.1); border-radius: 8px; padding: 12px; margin: 8px 0;">
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">🔗 供应链叙事</div>
        <div style="display: flex; gap: 16px; flex-wrap: wrap;">
            <div><span style="color: #3b82f6; font-weight: bold;">{summary['total_narratives']}</span> <span style="color: #64748b; font-size: 11px;">叙事</span></div>
            <div><span style="color: #22c55e; font-weight: bold;">{summary['total_stocks_mapped']}</span> <span style="color: #64748b; font-size: 11px;">股票</span></div>
            <div><span style="color: #ef4444; font-weight: bold;">{summary['recent_events_count']}</span> <span style="color: #64748b; font-size: 11px;">事件</span></div>
        </div>
        <div style="margin-top: 8px;">{hot_html}</div>
    </div>
    """
