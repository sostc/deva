"""注意力调度系统 UI

展示注意力系统的实时状态和变化
"""

from .ui_components import (
    get_attention_integration,
    get_strategy_manager,
    get_history_tracker,
    get_hot_sectors_and_stocks,
    get_attention_report,
    get_strategy_stats,
    get_attention_changes,
    get_attention_shift_report,
    register_stock_names,
    is_attention_initialized,
    initialize_attention_system,
    render_market_state_panel,
    render_frequency_distribution,
    render_strategy_status,
    render_dual_engine_status,
    render_noise_filter_status,
    render_pytorch_patterns,
    render_hot_sectors_and_stocks,
    render_sector_trends,
    render_attention_timeline,
    render_sector_hotspot_timeline,
    render_multi_threshold_timeline,
    render_attention_changes,
    render_attention_shift_report,
    render_recent_signals,
    render_intelligence_panels,
    render_attention_admin,
    render_attention_flow_ui,
    render_attention_layers_detail,
    render_data_frequency_panel,
    render_noise_filter_panel,
    render_strategy_status_panel,
    render_dual_engine_panel,
)

from .ui_components.common import get_attention_integration as _get_att, get_strategy_manager as _get_sm


def _get_attention_integration():
    return _get_att()


def _get_strategy_manager():
    return _get_sm()


__all__ = [
    "get_attention_integration",
    "get_strategy_manager",
    "get_history_tracker",
    "get_hot_sectors_and_stocks",
    "get_attention_report",
    "get_strategy_stats",
    "get_attention_changes",
    "get_attention_shift_report",
    "register_stock_names",
    "is_attention_initialized",
    "initialize_attention_system",
    "render_market_state_panel",
    "render_frequency_distribution",
    "render_strategy_status",
    "render_dual_engine_status",
    "render_noise_filter_status",
    "render_pytorch_patterns",
    "render_hot_sectors_and_stocks",
    "render_sector_trends",
    "render_attention_timeline",
    "render_sector_hotspot_timeline",
    "render_multi_threshold_timeline",
    "render_attention_changes",
    "render_attention_shift_report",
    "render_recent_signals",
    "render_intelligence_panels",
    "render_attention_admin",
    "render_attention_flow_ui",
    "render_attention_layers_detail",
    "render_data_frequency_panel",
    "render_noise_filter_panel",
]
