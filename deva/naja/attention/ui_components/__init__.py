"""注意力系统 UI 组件"""

from .common import (
    get_attention_integration,
    get_strategy_manager,
    get_history_tracker,
    get_hot_blocks_and_stocks,
    get_attention_report,
    get_strategy_stats,
    get_attention_changes,
    get_attention_shift_report,
    register_stock_names,
    is_attention_initialized,
    initialize_attention_system,
)

from .cards import (
    render_market_state_panel,
    render_frequency_distribution,
    render_strategy_status,
    render_dual_engine_status,
    render_noise_filter_status,
    render_pytorch_patterns,
    render_hot_blocks_and_stocks,
    render_key_metrics_summary,
    render_live_hotspots,
    render_collapsible_system_status,
    render_compact_signals,
    render_compact_noise_filter,
)

from .timeline import (
    render_block_trends,
    render_attention_timeline,
    render_block_hotspot_timeline,
    render_multi_threshold_timeline,
    render_attention_changes,
    render_attention_shift_report,
    render_recent_signals,
    render_sector_trading_timeline,
)

from .intelligence import render_intelligence_panels

from .admin import render_attention_admin

from .flow import (
    render_attention_flow_ui,
    render_attention_layers_detail,
    # render_data_frequency_panel,  # 已删除
    render_noise_filter_panel,
    render_strategy_status_panel,
    render_dual_engine_panel,
)

from .kernel import (
    render_kernel_dashboard,
    render_query_state_panel,
    render_multi_head_panel,
    render_memory_panel,
    render_feedback_panel,
    render_kernel_live_view,
    render_attention_flow_diagram,
)

from .us_market import (
    get_us_attention_data,
    render_us_market_panel,
    render_market_index_panel,
    render_cross_market_predictions,
    get_us_market_summary,
    render_us_market_summary,
)

__all__ = [
    "get_attention_integration",
    "get_strategy_manager",
    "get_history_tracker",
    "get_hot_blocks_and_stocks",
    "get_attention_report",
    "get_strategy_stats",
    "get_attention_changes",
    "get_attention_shift_report",
    "register_stock_names",
    "is_attention_initialized",
    "initialize_attention_system",
    "render_market_state_panel",
    "render_market_index_panel",
    "render_cross_market_predictions",
    "render_frequency_distribution",
    "render_strategy_status",
    "render_dual_engine_status",
    "render_noise_filter_status",
    "render_pytorch_patterns",
    "render_hot_blocks_and_stocks",
    "render_key_metrics_summary",
    "render_live_hotspots",
    "render_collapsible_system_status",
    "render_compact_signals",
    "render_compact_noise_filter",
    "render_block_trends",
    "render_attention_timeline",
    "render_block_hotspot_timeline",
    "render_multi_threshold_timeline",
    "render_attention_changes",
    "render_attention_shift_report",
    "render_recent_signals",
    "render_sector_trading_timeline",
    "render_intelligence_panels",
    "render_attention_admin",
    "render_attention_flow_ui",
    "render_attention_layers_detail",
    # "render_data_frequency_panel",  # 已删除
    "render_noise_filter_panel",
    "render_kernel_dashboard",
    "render_attention_flow_diagram",
    "get_us_attention_data",
    "render_us_market_panel",
    "get_us_market_summary",
    "render_us_market_summary",
]
