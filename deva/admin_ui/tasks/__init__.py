"""Tasks module - 定时任务管理."""

from .tasks import (
    watch_topic,
    create_task,
    manage_tasks,
    stop_task,
    start_task,
    delete_task,
    recover_task,
    remove_task_forever,
    restore_tasks_from_db,
)

from .task_manager import (
    TaskManager,
    get_task_manager,
)

from .task_unit import (
    TaskUnit,
    TaskType,
    TaskMetadata,
    TaskState,
    TaskStats,
)

from .enhanced_task_panel import (
    show_enhanced_create_task_dialog,
    show_enhanced_edit_task_dialog,
    validate_task_code,
)

from ..contexts import tasks_ctx as admin_tasks

__all__ = [
    # Context (aliased as admin_tasks for admin.py compatibility)
    'admin_tasks',
    # Core classes
    'TaskUnit',
    'TaskType',
    'TaskMetadata',
    'TaskState',
    'TaskStats',
    'TaskManager',
    # Main functions
    'watch_topic',
    'create_task',
    'manage_tasks',
    'stop_task',
    'start_task',
    'delete_task',
    'recover_task',
    'remove_task_forever',
    'restore_tasks_from_db',
    'get_task_manager',
    # Enhanced UI
    'show_enhanced_create_task_dialog',
    'show_enhanced_edit_task_dialog',
    'validate_task_code',
]
