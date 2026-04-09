"""市场热点系统 UI 组件"""

from .common import (
    get_market_hotspot_integration,
    get_strategy_manager,
    get_history_tracker,
    get_hot_blocks_and_stocks,
    get_hotspot_report,
    get_strategy_stats,
    get_hotspot_changes,
    register_stock_names,
    is_hotspot_system_initialized,
    initialize_hotspot_system,
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
    render_hotspot_timeline,
    render_block_hotspot_timeline,
    render_multi_threshold_timeline,
    render_hotspot_changes,
    render_hotspot_shift_report,
    render_recent_signals,
    render_block_trading_timeline,
)

from .admin import render_market_hotspot_admin

from .flow import (
    render_hotspot_flow_ui,
    render_hotspot_layers_detail,
    render_noise_filter_panel,
    render_strategy_status_panel,
    render_dual_engine_panel,
)

from .intelligence import render_intelligence_panels

from .us_market import (
    get_us_hotspot_data,
    render_us_market_panel,
    render_market_index_panel,
    render_cross_market_predictions,
    get_us_market_summary,
    render_us_market_summary,
)

__all__ = [
    "get_market_hotspot_integration",
    "get_strategy_manager",
    "get_history_tracker",
    "get_hot_blocks_and_stocks",
    "get_hotspot_report",
    "get_strategy_stats",
    "get_hotspot_changes",
    "register_stock_names",
    "is_hotspot_system_initialized",
    "initialize_hotspot_system",
    "render_market_state_panel",
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
    "render_hotspot_timeline",
    "render_block_hotspot_timeline",
    "render_multi_threshold_timeline",
    "render_hotspot_changes",
    "render_hotspot_shift_report",
    "render_recent_signals",
    "render_block_trading_timeline",
    "render_market_hotspot_admin",
    "render_hotspot_flow_ui",
    "render_hotspot_layers_detail",
    "render_noise_filter_panel",
    "render_strategy_status_panel",
    "render_dual_engine_panel",
    "render_intelligence_panels",
    "get_us_hotspot_data",
    "render_us_market_panel",
    "render_market_index_panel",
    "render_cross_market_predictions",
    "get_us_market_summary",
    "render_us_market_summary",
]
