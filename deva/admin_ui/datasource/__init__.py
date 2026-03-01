"""Datasource module - 数据源管理."""

from .datasource import (
    DataSource,
    DataSourceStatus,
    DataSourceType,
    DataSourceMetadata,
    DataSourceState,
    DataSourceStats,
    DataSourceManager,
    get_ds_manager,
    create_timer_source,
    create_stream_source,
    create_replay_source,
)

from .datasource_panel import (
    render_datasource_admin as admin_datasource_ui,
    render_datasource_admin_panel,
)

from .datasource_v2 import (
    DataSourceEntry,
    DataSourceManager as DataSourceManagerV2,
    get_datasource_manager as get_datasource_manager_v2,
)

from ..contexts import datasource_ctx

__all__ = [
    # Core classes
    'DataSource',
    'DataSourceStatus',
    'DataSourceType',
    'DataSourceMetadata',
    'DataSourceState',
    'DataSourceStats',
    'DataSourceManager',
    # Factory functions
    'get_ds_manager',
    'create_timer_source',
    'create_stream_source',
    'create_replay_source',
    # Admin UI (aliased for admin.py compatibility)
    'admin_datasource_ui',
    'render_datasource_admin_panel',
    # V2
    'DataSourceEntry',
    'DataSourceManagerV2',
    'get_datasource_manager_v2',
    # Context
    'datasource_ctx',
]
