"""
WakeSync System - 系统唤醒同步系统

系统唤醒时自动检测上次休眠/退出后的数据缺失，并进行同步。

核心设计：
1. SystemStateManager - 持久化系统状态（上次活跃时间、任务执行记录）
2. WakeSyncManager - 统一管理需要同步的组件
3. 各组件通过 WakeSyncable 协议注册同步逻辑

存储位置：deva/naja/system_state/
"""

from .system_state import SystemStateManager
from .wake_sync_manager import WakeSyncManager, WakeSyncable

__all__ = [
    "SystemStateManager",
    "WakeSyncManager",
    "WakeSyncable",
]
