"""Attention System UI

统一的注意力系统 UI 组件入口。
"""

from .components import (
    render_kernel_dashboard,
    render_query_state_panel,
    render_multi_head_panel,
    render_memory_panel,
    render_feedback_panel,
    render_kernel_live_view,
    render_attention_flow_diagram,
    render_manas_engine_status,
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

from .dashboard import (
    get_attention_monitor_data,
    render_attention_monitor_page,
)

__all__ = [
    # Kernel components
    "render_kernel_dashboard",
    "render_query_state_panel",
    "render_multi_head_panel",
    "render_memory_panel",
    "render_feedback_panel",
    "render_kernel_live_view",
    "render_attention_flow_diagram",
    "render_manas_engine_status",
    # Auto tuning
    "render_tuning_monitor_panel",
    "render_frequency_monitor_panel",
    "render_datasource_tuning_panel",
    # Supply chain
    "render_supply_chain_risk_card",
    "render_narrative_supply_chain_panel",
    "render_supply_chain_narrative_detail",
    "render_supply_chain_graph_mini",
    "render_supply_chain_knowledge_graph_page",
    # Awakening
    "render_awakening_status",
    # Dashboard
    "get_attention_monitor_data",
    "render_attention_monitor_page",
]
