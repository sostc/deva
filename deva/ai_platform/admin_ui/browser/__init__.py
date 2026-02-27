"""Browser module - 浏览器管理."""

from .browser_ui import (
    render_browser_ui as admin_browser_ui,
)

from ..contexts import browser_ui_ctx

__all__ = [
    # Main UI (aliased as admin_browser_ui for admin.py compatibility)
    'admin_browser_ui',
    # Context
    'browser_ui_ctx',
]
