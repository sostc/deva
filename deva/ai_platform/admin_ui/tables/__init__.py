"""Tables module - 数据表管理."""

from .tables import (
    refresh_table_display,
    delete_table,
    create_new_table,
    edit_data_popup,
    delete_string,
    add_string,
)

from ..contexts import tables_ctx as admin_tables

__all__ = [
    # Context (aliased as admin_tables for admin.py compatibility)
    'admin_tables',
    # Main functions
    'refresh_table_display',
    'delete_table',
    'create_new_table',
    'edit_data_popup',
    'delete_string',
    'add_string',
]
