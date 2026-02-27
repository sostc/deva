"""Follow module - 关注管理."""

from .follow_ui import (
    render_follow_ui as admin_follow_ui,
)

from ..contexts import follow_ui_ctx

__all__ = [
    # Main UI (aliased as admin_follow_ui for admin.py compatibility)
    'admin_follow_ui',
    # Context
    'follow_ui_ctx',
]
