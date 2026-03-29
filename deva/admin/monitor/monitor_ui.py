"""Monitor UI exported from shared implementation."""

from __future__ import annotations

from .shared_ui import (
    exec_command,
    render_all_streams,
    render_all_tables,
    render_monitor_home,
    view_stream,
    view_table_keys,
    view_table_value,
    render_tuning_monitor_home,
)


def render_tuning_monitor():
    try:
        from deva.naja.attention.ui_components.auto_tuning_monitor import (
            render_tuning_monitor_panel,
            render_frequency_monitor_panel,
            render_datasource_tuning_panel,
        )
        html = render_tuning_monitor_panel()
        html += render_frequency_monitor_panel()
        html += render_datasource_tuning_panel()
        return html
    except Exception as e:
        return f'<div style="color: #f87171; padding: 20px;">加载调优监控失败: {str(e)}</div>'


__all__ = [
    "render_monitor_home",
    "exec_command",
    "render_all_streams",
    "render_all_tables",
    "view_table_keys",
    "view_table_value",
    "view_stream",
    "render_tuning_monitor",
]
