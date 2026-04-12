"""Naja 系统监控与管理模块

提供系统级的监控、健康检查、故障恢复和状态管理功能。

拆分自原 supervisor.py (832行):
- core.py: NajaSupervisor 基础（单例+初始化+组件注册）
- monitoring.py: 监控功能 Mixin
- status.py: 状态查询 Mixin
- recovery.py: 恢复与生命周期 Mixin
- bootstrap.py: 模块级启动/停止函数
"""

from .core import NajaSupervisor
from .bootstrap import (
    get_naja_supervisor,
    stop_supervisor,
    start_supervisor,
    get_supervisor,
)

__all__ = [
    "NajaSupervisor",
    "get_naja_supervisor",
    "stop_supervisor",
    "start_supervisor",
    "get_supervisor",
]
