"""供应链 UI - 叙事面板"""

from typing import List, Dict, Tuple
from datetime import datetime

from pywebio.output import (
    put_html, put_row, put_column, put_text, put_button, put_table,
    put_scope, use_scope, clear_scope
)
from pywebio.session import run_js
import math

def render_narrative_supply_chain_panel() -> None:
    """渲染叙事供应链联动面板"""
    from deva.naja.cognition import get_supply_chain_linker
    from deva.naja.attention.kernel.manas_engine import ManasEngine

    linker = get_supply_chain_linker()

    hot_narratives = linker.get_hot_narratives(10)
    recent_events = linker.get_recent_events(5)
    summary = linker.get_supply_chain_summary()

    html_parts = []
    html_parts.append("""
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 16px; margin: 8px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <h3 style="margin: 0; color: #f1f5f9; font-size: 16px;">🔗 叙事-供应链联动</h3>
            <span style="background: #3b82f6; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px;">""")
    html_parts.append(f"{len(linker._narrative_stock_link)} 个叙事映射")
    html_parts.append("""</span>
        </div>
    """)

    html_parts.append("""
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px;">
            <div style="background: rgba(59, 130, 246, 0.1); border-radius: 8px; padding: 12px; text-align: center;">
                <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">""")
    html_parts.append(f"{len(linker._stock_narrative_link)}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">映射股票</div>
            </div>
            <div style="background: rgba(239, 68, 68, 0.1); border-radius: 8px; padding: 12px; text-align: center;">
                <div style="font-size: 24px; font-weight: bold; color: #ef4444;">""")
    html_parts.append(f"{len(recent_events)}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">风险事件</div>
            </div>
            <div style="background: rgba(34, 197, 94, 0.1); border-radius: 8px; padding: 12px; text-align: center;">
                <div style="font-size: 24px; font-weight: bold; color: #22c55e;">""")
    html_parts.append(f"{summary['recent_events_count']}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">总事件</div>
            </div>
        </div>
    """)

    if hot_narratives:
        html_parts.append("""
        <div style="margin-bottom: 16px;">
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">🔥 最热叙事</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            """)
        for narrative, importance in hot_narratives[:6]:
            intensity = min(1.0, importance / 3.0)
            bg_color = f"rgba(239, 68, 68, {0.3 + intensity * 0.7})"
            html_parts.append(f"""
                <span style="background: {bg_color}; padding: 4px 10px; border-radius: 16px; font-size: 12px; color: white;">
                    {narrative} ({importance:.1f})
                </span>
            """)
        html_parts.append("""
            </div>
        </div>
        """)

    if recent_events:
        html_parts.append("""
        <div>
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">⚠️ 最近风险事件</div>
            <div style="max-height: 150px; overflow-y: auto;">
            """)
        for event in recent_events[-5:]:
            dt = datetime.fromtimestamp(event.timestamp)
            time_str = dt.strftime("%m-%d %H:%M")
            risk_color = "#ef4444" if event.risk_level.value in ["high", "critical"] else "#ca8a04"
            html_parts.append(f"""
                <div style="background: rgba(255,255,255,0.05); border-radius: 6px; padding: 8px; margin-bottom: 6px; border-left: 3px solid {risk_color};">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                        <span style="color: #f1f5f9; font-size: 13px;">{event.description}</span>
                        <span style="color: #94a3b8; font-size: 11px;">{time_str}</span>
                    </div>
                    <div style="font-size: 11px; color: #64748b;">
                        关联: {', '.join(event.narratives[:3])}
                    </div>
                </div>
            """)
        html_parts.append("""
            </div>
        </div>
        """)

    html_parts.append("</div>")

    put_html("".join(html_parts))


def render_supply_chain_narrative_detail(narrative: str = None) -> None:
    """渲染特定叙事的供应链详情"""
    from deva.naja.cognition import get_supply_chain_linker

    linker = get_supply_chain_linker()

    if narrative:
        summary = linker.get_supply_chain_for_narrative(narrative)
        stocks = linker.get_stocks_by_narrative(narrative)
    else:
        summary = linker.get_supply_chain_summary()
        stocks = list(linker._stock_narrative_link.keys())
        narrative = "全部叙事"

    html_parts = []
    html_parts.append(f"""
    <div style="background: #1e293b; border-radius: 12px; padding: 16px; margin: 8px 0;">
        <h4 style="margin: 0 0 16px 0; color: #f1f5f9; font-size: 14px;">
            📊 供应链分析: {narrative}
        </h4>
    """)

    if 'importance' in summary:
        html_parts.append(f"""
        <div style="display: flex; gap: 16px; margin-bottom: 16px;">
            <div style="flex: 1; background: rgba(59, 130, 246, 0.1); border-radius: 8px; padding: 12px;">
                <div style="font-size: 20px; font-weight: bold; color: #3b82f6;">{summary['importance']:.2f}</div>
                <div style="font-size: 11px; color: #94a3b8;">叙事重要性</div>
            </div>
            <div style="flex: 1; background: rgba(239, 68, 68, 0.1); border-radius: 8px; padding: 12px;">
                <div style="font-size: 20px; font-weight: bold; color: #ef4444;">{summary['total_risk']}</div>
                <div style="font-size: 11px; color: #94a3b8;">风险等级</div>
            </div>
            <div style="flex: 1; background: rgba(34, 197, 94, 0.1); border-radius: 8px; padding: 12px;">
                <div style="font-size: 20px; font-weight: bold; color: #22c55e;">{len(stocks)}</div>
                <div style="font-size: 11px; color: #94a3b8;">关联股票</div>
            </div>
        </div>
        """)

    if stocks:
        html_parts.append("""
        <div style="margin-bottom: 16px;">
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">💼 核心股票</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            """)
        for code in stocks[:12]:
            node = linker._graph.get_stock_node(code)
            if node:
                market_icon = "🇨🇳" if node.metadata.get("market") == "A" else "🇺🇸"
                html_parts.append(f"""
                    <span style="background: rgba(255,255,255,0.1); padding: 4px 10px; border-radius: 16px; font-size: 12px; color: #e2e8f0;">
                        {market_icon} {node.name}({node.stock_code})
                    </span>
                """)
        html_parts.append("""
            </div>
        </div>
        """)

    if summary.get('upstream_stocks'):
        html_parts.append("""
        <div style="margin-bottom: 16px;">
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">🏭 上游供应商</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            """)
        for code in summary['upstream_stocks'][:8]:
            node = linker._graph.get_stock_node(code)
            if node:
                html_parts.append(f"""
                    <span style="background: rgba(251, 146, 60, 0.2); padding: 4px 10px; border-radius: 16px; font-size: 12px; color: #fb923c;">
                        ↑ {node.name}
                    </span>
                """)
        html_parts.append("""
            </div>
        </div>
        """)

    if summary.get('downstream_stocks'):
        html_parts.append("""
        <div>
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">💰 下游客户</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            """)
        for code in summary['downstream_stocks'][:8]:
            node = linker._graph.get_stock_node(code)
            if node:
                html_parts.append(f"""
                    <span style="background: rgba(34, 197, 94, 0.2); padding: 4px 10px; border-radius: 16px; font-size: 12px; color: #4ade80;">
                        ↓ {node.name}
                    </span>
                """)
        html_parts.append("""
            </div>
        </div>
        """)

    html_parts.append("</div>")

    put_html("".join(html_parts))


