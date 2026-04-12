"""Task 数据模型 - TaskMetadata / TaskState"""

from __future__ import annotations

from dataclasses import dataclass

from ..common.recoverable import UnitMetadata, UnitState, UnitStatus


TASK_TABLE = "naja_tasks"
TASK_HISTORY_TABLE = "naja_task_history"


@dataclass
class TaskMetadata(UnitMetadata):
    """任务元数据"""

    task_type: str = "timer"
    execution_mode: str = "timer"
    interval_seconds: float = 60.0
    scheduler_trigger: str = "interval"
    cron_expr: str = ""
    run_at: str = ""
    event_source: str = "log"
    event_condition: str = ""
    event_condition_type: str = "contains"


@dataclass
class TaskState(UnitState):
    """任务状态"""

    last_run_time: float = 0
    success_count: int = 0
    failure_count: int = 0
    last_result: str = ""

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "last_run_time": self.last_run_time,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "last_result": self.last_result,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TaskState":
        if isinstance(data, cls):
            return data
        return cls(
            status=data.get("status", UnitStatus.STOPPED.value),
            start_time=data.get("start_time", 0),
            last_activity_ts=data.get("last_activity_ts", 0),
            error_count=data.get("error_count", 0),
            last_error=data.get("last_error", ""),
            last_error_ts=data.get("last_error_ts", 0),
            run_count=data.get("run_count", 0),
            last_run_time=data.get("last_run_time", 0),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            last_result=data.get("last_result", ""),
        )
