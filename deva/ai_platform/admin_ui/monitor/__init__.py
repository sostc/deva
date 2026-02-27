"""Monitor module - 监控管理."""

from .monitor_ui import (
    render_monitor_home as admin_monitor_ui,
)

from .monitor_routes import (
    monitor_route_handlers as admin_monitor_routes,
)

__all__ = [
    # Monitor UI (aliased for admin.py compatibility)
    'admin_monitor_ui',
    # Monitor Routes (aliased for admin.py compatibility)
    'admin_monitor_routes',
]
