"""热点系统 UI 卡片组件包"""

from .market_state import render_hotspot_details_card, render_market_state_panel
from .stats import (
    render_frequency_distribution,
    render_strategy_status,
    render_dual_engine_status,
    render_noise_filter_status,
)
from .patterns import render_pytorch_patterns, render_hot_blocks_and_stocks
from .dashboard import (
    render_key_metrics_summary,
    render_live_hotspots,
    render_collapsible_system_status,
    render_compact_signals,
    render_compact_noise_filter,
)

__all__ = [
    "render_hotspot_details_card",
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
]
