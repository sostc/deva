"""Tasks module - 定时任务管理."""

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

from .task_dialog import (
    show_create_task_dialog,
    show_edit_task_dialog,
    validate_task_code,
)

from .task_admin import (
    render_task_admin,
)

from .task_v2 import (
    TaskEntry,
    TaskManager as TaskManagerV2,
    get_task_manager as get_task_manager_v2,
)

__all__ = [
    'TaskUnit',
    'TaskType',
    'TaskMetadata',
    'TaskState',
    'TaskStats',
    'TaskManager',
    'get_task_manager',
    'show_create_task_dialog',
    'show_edit_task_dialog',
    'validate_task_code',
    'render_task_admin',
    # V2
    'TaskEntry',
    'TaskManagerV2',
    'get_task_manager_v2',
]
