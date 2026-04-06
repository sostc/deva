"""
Backfill System - 统一补执行系统

系统启动时自动检测上次休眠/退出后的数据缺失，并进行补执行。

核心设计：
1. SystemStateManager - 持久化系统状态（上次活跃时间、任务执行记录）
2. BackfillManager - 统一管理需要补执行的组件
3. 各组件通过 Backfillable 协议注册补执行逻辑

存储位置：deva/naja/system_state/
"""

from .system_state import SystemStateManager, get_system_state_manager
from .backfill_manager import BackfillManager, Backfillable, get_backfill_manager

__all__ = [
    "SystemStateManager",
    "get_system_state_manager",
    "BackfillManager",
    "Backfillable",
    "get_backfill_manager",
]