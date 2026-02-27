"""Config module - 配置管理."""

from .config_ui import (
    render_config_admin as admin_config_ui,
)

from ..contexts import config_ui_ctx

__all__ = [
    # Main UI (aliased as admin_config_ui for admin.py compatibility)
    'admin_config_ui',
    # Context
    'config_ui_ctx',
]
