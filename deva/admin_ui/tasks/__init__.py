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

from .enhanced_task_panel import (
    show_enhanced_create_task_dialog,
    show_enhanced_edit_task_dialog,
    validate_task_code,
)

__all__ = [
    # Core classes
    'TaskUnit',
    'TaskType',
    'TaskMetadata',
    'TaskState',
    'TaskStats',
    'TaskManager',
    'get_task_manager',
    # Enhanced UI
    'show_enhanced_create_task_dialog',
    'show_enhanced_edit_task_dialog',
    'validate_task_code',
]
