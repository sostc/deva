"""Task - 基于 RecoverableUnit 抽象

拆分结构：
  models.py  — TaskMetadata, TaskState, 常量
  entry.py   — TaskEntry (RecoverableUnit 子类)
  manager.py — TaskManager (单例管理器)
"""

from .models import TaskMetadata, TaskState, TASK_TABLE, TASK_HISTORY_TABLE
from .entry import TaskEntry
from .manager import TaskManager

__all__ = [
    "TaskMetadata",
    "TaskState",
    "TaskEntry",
    "TaskManager",
    "TASK_TABLE",
    "TASK_HISTORY_TABLE",
]
