"""
认知 UI 组件
"""

from .supply_chain import render_supply_chain
from .event_bus import render_event_bus
from .semantic import render_semantic
from .insight import render_insight
from .cognition_summary import render_cognition_summary
from .control_panel import render_control_panel
from .daily_review import render_daily_review, render_daily_review_empty
from ...narrative.ui import lifecycle as narrative_lifecycle
from ...narrative.ui import svg as narrative_svg
from .merrill_clock import render_merrill_clock
from .propagation import render_propagation
from .cross_signal import render_cross_signal
from .storage import render_storage
from .help import render_help

render_narrative_lifecycle = narrative_lifecycle.render_narrative_lifecycle
render_narrative_svg = narrative_svg.render_narrative_svg

__all__ = [
    "render_supply_chain",
    "render_event_bus",
    "render_semantic",
    "render_insight",
    "render_cognition_summary",
    "render_control_panel",
    "render_daily_review",
    "render_daily_review_empty",
    "render_narrative_lifecycle",
    "render_narrative_svg",
    "render_merrill_clock",
    "render_propagation",
    "render_cross_signal",
    "render_storage",
    "render_help",
]
