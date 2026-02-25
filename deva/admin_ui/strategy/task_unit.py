"""任务模块统一架构(Task Module Unified Architecture)

为任务模块提供与策略和数据源模块统一的架构设计，实现代码复用和功能增强。

================================================================================
架构设计
================================================================================

【任务单元架构】
┌─────────────────────────────────────────────────────────────────────────────┐
│  TaskUnit (任务单元)                                                       │
│  ├── 元数据 (TaskMetadata)                                                  │
│  │   ├── id: 唯一标识                                                       │
│  │   ├── name: 名称                                                         │
│  │   ├── description: 描述                                                  │
│  │   ├── task_type: 任务类型(interval/cron)                               │
│  │   ├── schedule_config: 调度配置                                         │
│  │   └── created_at: 创建时间                                               │
│  │                                                                          │
│  ├── 状态 (TaskState)                                                       │
│  │   ├── status: 运行状态                                                   │
│  │   ├── last_run_time: 最后执行时间                                        │
│  │   ├── next_run_time: 下次执行时间                                        │
│  │   ├── run_count: 执行次数                                                │
│  │   └── error_count: 错误次数                                              │
│  │                                                                          │
│  ├── 统计 (TaskStats)                                                       │
│  │   ├── total_duration: 总执行时长                                         │
│  │   ├── avg_duration: 平均执行时长                                         │
│  │   ├── success_rate: 成功率                                               │
│  │   └── retry_count: 重试次数                                               │
│  │                                                                          │
│  └── 执行 (TaskExecution)                                                    │
│       ├── job_code: Python异步函数代码                                       │
│       ├── retry_config: 重试配置                                             │
│       └── execution_history: 执行历史                                        │
└─────────────────────────────────────────────────────────────────────────────┘

【继承体系】
TaskUnit → ExecutableUnit → 统一的代码执行、生命周期管理、错误处理
TaskManager → BaseManager → 统一的注册、启动、停止、统计管理
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from deva import log

from .base import BaseMetadata, BaseState, BaseStats, BaseManager
from .executable_unit import ExecutableUnit, ExecutableUnitMetadata, ExecutableUnitState
from .error_handler import ErrorHandler, ErrorLevel, ErrorCategory
from .persistence import get_global_persistence_manager


class TaskType(str, Enum):
    """任务类型"""
    INTERVAL = "interval"  # 间隔任务
    CRON = "cron"         # 定时任务
    ONE_TIME = "one_time"  # 一次性任务


class TaskStatus(str, Enum):
    """任务状态"""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"  # 一次性任务完成


@dataclass
class TaskMetadata(ExecutableUnitMetadata):
    """任务元数据"""
    task_type: TaskType = TaskType.INTERVAL
    schedule_config: Dict[str, Any] = field(default_factory=dict)
    retry_config: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["task_type"] = self.task_type.value
        data["schedule_config"] = self.schedule_config
        data["retry_config"] = self.retry_config
        return data


@dataclass
class TaskState(ExecutableUnitState):
    """任务状态"""
    last_run_time: float = 0
    next_run_time: float = 0
    run_count: int = 0
    error_count: int = 0
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["last_run_time"] = self.last_run_time
        data["next_run_time"] = self.next_run_time
        data["run_count"] = self.run_count
        data["error_count"] = self.error_count
        return data


@dataclass
class TaskStats(BaseStats):
    """任务统计"""
    total_duration: float = 0
    avg_duration: float = 0
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data["total_duration"] = self.total_duration
        data["avg_duration"] = self.avg_duration
        data["success_count"] = self.success_count
        data["failure_count"] = self.failure_count
        data["retry_count"] = self.retry_count
        data["success_rate"] = self.success_count / (self.success_count + self.failure_count) if (self.success_count + self.failure_count) > 0 else 0
        return data


@dataclass
class TaskExecution:
    """任务执行信息"""
    job_code: str = ""
    compiled_func: Optional[Callable] = None
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    max_history_size: int = 100
    
    def add_history_entry(self, entry: Dict[str, Any]):
        """添加执行历史记录"""
        self.execution_history.append(entry)
        # 限制历史记录数量
        if len(self.execution_history) > self.max_history_size:
            self.execution_history = self.execution_history[-self.max_history_size:]
    
    def get_recent_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的执行历史"""
        return self.execution_history[-limit:] if self.execution_history else []


class TaskUnit(ExecutableUnit):
    """任务单元
    
    继承自ExecutableUnit，获得统一的代码执行、生命周期管理、错误处理能力
    """
    
    def __init__(
        self,
        metadata: TaskMetadata,
        state: TaskState,
        execution: TaskExecution,
        stats: TaskStats = None
    ):
        """
        Args:
            metadata: 任务元数据
            state: 任务状态
            execution: 任务执行信息
            stats: 任务统计
        """
        # 调用父类构造函数
        super().__init__(
            metadata=metadata,
            state=state,
            func_name="execute",  # 任务函数名
            stream_cache_size=50  # 流缓存大小
        )
        
        self.metadata: TaskMetadata = metadata
        self.state: TaskState = state
        self.execution: TaskExecution = execution
        self.stats: TaskStats = stats or TaskStats()
        
        # 错误处理器
        self.error_handler = ErrorHandler(self)
        
        # 调度器相关
        self._scheduler_job = None
        self._scheduler = None
        
        # 重试配置
        self._retry_count = self.metadata.retry_config.get("max_retries", 0)
        self._retry_interval = self.metadata.retry_config.get("retry_interval", 5)
    
    # ==========================================================================
    # 任务特定方法
    # ==========================================================================
    
    def _validate_function(self, func: Callable) -> Dict[str, Any]:
        """验证任务函数
        
        任务函数必须是异步函数，接收上下文参数
        
        Returns:
            {"success": bool, "error": str}
        """
        import inspect
        
        # 检查是否为协程函数
        if not inspect.iscoroutinefunction(func):
            return {
                "success": False,
                "error": "任务函数必须是异步函数(async def)"
            }
        
        # 检查参数数量
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        
        # 任务函数应该接收context参数
        if len(params) < 1:
            return {
                "success": False,
                "error": "任务函数必须至少接收一个参数(上下文)"
            }
        
        return {"success": True}
    
    async def execute_task(self, context: Dict[str, Any] = None) -> Any:
        """执行任务
        
        Args:
            context: 执行上下文
            
        Returns:
            任务执行结果
        """
        if not self.is_running:
            raise RuntimeError(f"任务 {self.name} 未在运行状态")
        
        if self._func is None:
            raise RuntimeError(f"任务 {self.name} 没有可执行的函数")
        
        start_time = time.time()
        start_datetime = datetime.now()
        
        try:
            # 更新状态
            self.state.status = TaskStatus.RUNNING
            self.state.last_activity_ts = start_time
            
            # 执行函数
            if context:
                result = await self._func(context)
            else:
                result = await self._func()
            
            # 更新统计
            duration = time.time() - start_time
            self.stats.total_duration += duration
            self.stats.success_count += 1
            self.stats.avg_duration = self.stats.total_duration / (self.stats.success_count + self.stats.failure_count)
            self.state.run_count += 1
            
            # 记录历史
            history_entry = {
                "start_time": start_datetime.isoformat(),
                "end_time": datetime.now().isoformat(),
                "duration": round(duration, 2),
                "status": "success",
                "output": str(result) if result else "",
                "error": ""
            }
            self.execution.add_history_entry(history_entry)
            
            # 对于一次性任务，标记为完成
            if self.metadata.task_type == TaskType.ONE_TIME:
                self.state.status = TaskStatus.COMPLETED
            else:
                self.state.status = TaskStatus.RUNNING
            
            log.info(f"任务执行成功: {self.name} (耗时: {duration:.2f}s)")
            return result
            
        except Exception as e:
            # 错误处理
            duration = time.time() - start_time
            error_msg = str(e)
            
            # 更新统计
            self.stats.failure_count += 1
            self.state.error_count += 1
            
            # 记录错误历史
            history_entry = {
                "start_time": start_datetime.isoformat(),
                "end_time": datetime.now().isoformat(),
                "duration": round(duration, 2),
                "status": "failed",
                "output": "",
                "error": error_msg
            }
            self.execution.add_history_entry(history_entry)
            
            # 使用统一的错误处理
            self.error_handler.handle_error(
                e,
                context=f"任务执行失败: {self.name}",
                level=ErrorLevel.HIGH,
                category=ErrorCategory.CODE_EXECUTION
            )
            
            # 更新状态
            self.state.status = TaskStatus.ERROR
            
            log.error(f"任务执行失败: {self.name} - {error_msg}")
            raise
    
    def get_schedule_description(self) -> str:
        """获取调度描述"""
        if self.metadata.task_type == TaskType.INTERVAL:
            interval = self.metadata.schedule_config.get("interval", 60)
            return f"每 {interval} 秒执行一次"
        elif self.metadata.task_type == TaskType.CRON:
            hour = self.metadata.schedule_config.get("hour", 0)
            minute = self.metadata.schedule_config.get("minute", 0)
            return f"每天 {hour:02d}:{minute:02d} 执行"
        elif self.metadata.task_type == TaskType.ONE_TIME:
            return "一次性任务"
        else:
            return "未知调度类型"
    
    def get_next_run_time(self) -> Optional[float]:
        """计算下次执行时间"""
        if self.metadata.task_type == TaskType.ONE_TIME:
            return None
        
        current_time = time.time()
        
        if self.metadata.task_type == TaskType.INTERVAL:
            interval = self.metadata.schedule_config.get("interval", 60)
            if self.state.last_run_time > 0:
                return self.state.last_run_time + interval
            else:
                return current_time + interval
        
        elif self.metadata.task_type == TaskType.CRON:
            # 简化的cron时间计算
            hour = self.metadata.schedule_config.get("hour", 0)
            minute = self.metadata.schedule_config.get("minute", 0)
            
            # 计算下次执行时间（简化版本）
            now = datetime.now()
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if next_run <= now:
                next_run = next_run.replace(day=next_run.day + 1)
            
            return next_run.timestamp()
        
        return None
    
    # ==========================================================================
    # 重写父类方法
    # ==========================================================================
    
    def _do_start(self) -> Dict[str, Any]:
        """执行具体的启动逻辑
        
        Returns:
            {"success": bool, "error": str}
        """
        try:
            # 编译代码（如果还没编译）
            if self.execution.compiled_func is None and self.metadata.func_code:
                compile_result = self.compile_code(self.metadata.func_code, "execute")
                if not compile_result["success"]:
                    return compile_result
                self.execution.compiled_func = compile_result["func"]
                self._func = compile_result["func"]
            
            # 检查函数
            if self._func is None:
                return {"success": False, "error": "没有可执行的任务函数"}
            
            # 更新下次执行时间
            next_run_time = self.get_next_run_time()
            if next_run_time:
                self.state.next_run_time = next_run_time
            
            log.info(f"任务启动成功: {self.name}")
            return {"success": True, "message": "任务启动成功"}
            
        except Exception as e:
            error_msg = f"任务启动失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    def _do_stop(self) -> Dict[str, Any]:
        """执行具体的停止逻辑
        
        Returns:
            {"success": bool, "error": str}
        """
        try:
            # 如果有调度器任务，需要取消
            if self._scheduler_job:
                # 这里需要调用调度器的移除方法
                # 具体实现取决于使用的调度器
                pass
            
            log.info(f"任务停止成功: {self.name}")
            return {"success": True, "message": "任务停止成功"}
            
        except Exception as e:
            error_msg = f"任务停止失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    def _do_delete(self) -> Dict[str, Any]:
        """执行具体的删除逻辑
        
        Returns:
            {"success": bool, "error": str}
        """
        try:
            # 清理执行历史
            self.execution.execution_history.clear()
            
            log.info(f"任务删除成功: {self.name}")
            return {"success": True, "message": "任务删除成功"}
            
        except Exception as e:
            error_msg = f"任务删除失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    # ==========================================================================
    # 工具方法
    # ==========================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "metadata": self.metadata.to_dict(),
            "state": self.state.to_dict(),
            "stats": self.stats.to_dict(),
            "execution": {
                "job_code": self.execution.job_code,
                "history_count": len(self.execution.execution_history),
                "recent_history": self.execution.get_recent_history(5)
            },
            "schedule_description": self.get_schedule_description(),
            "is_running": self.is_running,
            "next_run_time": self.state.next_run_time,
        }
    
    def save(self):
        """保存到持久化存储"""
        try:
            persistence = get_global_persistence_manager()
            persistence.save_unit("task", self.id, self.to_dict())
            log.debug(f"任务已保存: {self.name}")
        except Exception as e:
            log.error(f"任务保存失败: {self.name} - {e}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskUnit':
        """从字典创建任务单元"""
        # 解析元数据
        metadata_data = data.get("metadata", {})
        metadata = TaskMetadata(
            id=metadata_data.get("id", ""),
            name=metadata_data.get("name", ""),
            description=metadata_data.get("description", ""),
            func_code=metadata_data.get("func_code", ""),
            version=metadata_data.get("version", 1),
            task_type=TaskType(metadata_data.get("task_type", "interval")),
            schedule_config=metadata_data.get("schedule_config", {}),
            retry_config=metadata_data.get("retry_config", {}),
            tags=metadata_data.get("tags", []),
            created_at=metadata_data.get("created_at", time.time()),
            updated_at=metadata_data.get("updated_at", time.time())
        )
        
        # 解析状态
        state_data = data.get("state", {})
        state = TaskState(
            status=state_data.get("status", TaskStatus.STOPPED),
            start_time=state_data.get("start_time", 0),
            processed_count=state_data.get("processed_count", 0),
            last_activity_ts=state_data.get("last_activity_ts", 0),
            last_run_time=state_data.get("last_run_time", 0),
            next_run_time=state_data.get("next_run_time", 0),
            run_count=state_data.get("run_count", 0),
            error_count=state_data.get("error_count", 0),
            last_error=state_data.get("last_error", ""),
            last_error_ts=state_data.get("last_error_ts", 0)
        )
        
        # 解析统计
        stats_data = data.get("stats", {})
        stats = TaskStats(
            start_time=stats_data.get("start_time", 0),
            total_duration=stats_data.get("total_duration", 0),
            avg_duration=stats_data.get("avg_duration", 0),
            success_count=stats_data.get("success_count", 0),
            failure_count=stats_data.get("failure_count", 0),
            retry_count=stats_data.get("retry_count", 0)
        )
        
        # 解析执行信息
        execution_data = data.get("execution", {})
        execution = TaskExecution(
            job_code=execution_data.get("job_code", ""),
            execution_history=execution_data.get("execution_history", [])
        )
        
        # 创建任务单元
        task_unit = cls(metadata, state, execution, stats)
        
        # 如果任务代码存在，进行编译
        if task_unit.metadata.func_code:
            try:
                compile_result = task_unit.compile_code(task_unit.metadata.func_code, "execute")
                if compile_result["success"]:
                    task_unit.execution.compiled_func = compile_result["func"]
                    task_unit._func = compile_result["func"]
            except Exception as e:
                log.error(f"任务代码编译失败: {e}")
        
        return task_unit