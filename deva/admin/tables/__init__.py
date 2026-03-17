"""Tables module - 数据表管理."""

from .tables import (
    refresh_table_display,
    refresh_table_display_ui,
    delete_table,
    delete_table_ui,
    create_new_table,
    create_new_table_ui,
    edit_data_popup,
    delete_string,
    add_string,
    table_click,
    display_table_basic_info,
    paginate_dataframe,
)

from ..contexts import tables_ctx as admin_tables

__all__ = [
    # Context (aliased as admin_tables for admin.py compatibility)
    'admin_tables',
    # Main functions
    'refresh_table_display',
    'refresh_table_display_ui',
    'delete_table',
    'delete_table_ui',
    'create_new_table',
    'create_new_table_ui',
    'edit_data_popup',
    'delete_string',
    'add_string',
    'table_click',
    'display_table_basic_info',
    'paginate_dataframe',
]
