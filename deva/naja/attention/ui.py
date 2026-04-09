"""注意力调度系统 UI

注意：市场热点相关 UI 已迁移到 market_hotspot/ui/
"""

from .ui_components import (
    render_kernel_dashboard,
    render_query_state_panel,
    render_multi_head_panel,
    render_memory_panel,
    render_feedback_panel,
    render_kernel_live_view,
    render_attention_flow_diagram,
    render_tuning_monitor_panel,
    render_frequency_monitor_panel,
    render_datasource_tuning_panel,
    render_supply_chain_risk_card,
    render_narrative_supply_chain_panel,
    render_supply_chain_narrative_detail,
    render_supply_chain_graph_mini,
    render_supply_chain_knowledge_graph_page,
    render_awakening_status,
)

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
