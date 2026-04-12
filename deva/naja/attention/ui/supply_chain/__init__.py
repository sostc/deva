"""供应链叙事 UI 组件包

在认知系统和注意力系统中展示供应链知识图谱和叙事联动
"""

from .risk_card import render_supply_chain_risk_card
from .narrative import render_narrative_supply_chain_panel, render_supply_chain_narrative_detail
from .graph import render_supply_chain_graph_mini, render_supply_chain_knowledge_graph_page
from .market_data import _render_realtime_market_data, _render_valuation_analysis
from .summary import get_supply_chain_summary_html

__all__ = [
    "render_supply_chain_risk_card",
    "render_narrative_supply_chain_panel",
    "render_supply_chain_narrative_detail",
    "render_supply_chain_graph_mini",
    "render_supply_chain_knowledge_graph_page",
    "get_supply_chain_summary_html",
]
