"""注意力系统 UI 组件"""

from .kernel import (
    render_kernel_dashboard,
    render_query_state_panel,
    render_multi_head_panel,
    render_memory_panel,
    render_feedback_panel,
    render_kernel_live_view,
    render_attention_flow_diagram,
)

from .auto_tuning_monitor import (
    render_tuning_monitor_panel,
    render_frequency_monitor_panel,
    render_datasource_tuning_panel,
)

from .supply_chain import (
    render_supply_chain_risk_card,
    render_narrative_supply_chain_panel,
    render_supply_chain_narrative_detail,
    render_supply_chain_graph_mini,
    render_supply_chain_knowledge_graph_page,
)

from .awakening import render_awakening_status

__all__ = [
    "render_kernel_dashboard",
    "render_query_state_panel",
    "render_multi_head_panel",
    "render_memory_panel",
    "render_feedback_panel",
    "render_kernel_live_view",
    "render_attention_flow_diagram",
    "render_tuning_monitor_panel",
    "render_frequency_monitor_panel",
    "render_datasource_tuning_panel",
    "render_supply_chain_risk_card",
    "render_narrative_supply_chain_panel",
    "render_supply_chain_narrative_detail",
    "render_supply_chain_graph_mini",
    "render_supply_chain_knowledge_graph_page",
    "render_awakening_status",
]
