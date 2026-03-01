"""Compatibility wrapper for monitor UI."""

from __future__ import annotations

from .monitor.shared_ui import (
    exec_command,
    render_all_streams,
    render_all_tables,
    render_monitor_home,
    view_stream,
    view_table_keys,
    view_table_value,
)

__all__ = [
    "render_monitor_home",
    "exec_command",
    "render_all_streams",
    "render_all_tables",
    "view_table_keys",
    "view_table_value",
    "view_stream",
]
