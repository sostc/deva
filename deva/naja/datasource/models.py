"""DataSource 数据模型与常量"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict

from ..infra.runtime.recoverable import (
    UnitMetadata,
    UnitState,
    UnitStatus,
)
from ..scheduler import SchedulerManager


DS_TABLE = "naja_datasources"
DS_LATEST_DATA_TABLE = "naja_ds_latest_data"

_scheduler_manager = SchedulerManager()


@dataclass
class DataSourceMetadata(UnitMetadata):
    """数据源元数据"""
    source_type: str = "custom"
    config: Dict[str, Any] = field(default_factory=dict)
    interval: float = 5.0
    execution_mode: str = "timer"
    scheduler_trigger: str = "interval"
    cron_expr: str = ""
    run_at: str = ""
    event_source: str = "log"
    event_condition: str = ""
    event_condition_type: str = "contains"


@dataclass
class DataSourceState(UnitState):
    """数据源状态"""
    last_data_ts: float = 0
    total_emitted: int = 0
    pid: int = 0
    # ❗「按设计跳过」必须有独立字段，不能和「失败」共用一个计数器。
    # 盘中行情源在收盘后本来就取不到数；把它记进 error_count，页面上的
    # 67 次故障全是收盘造成的，真正的抓取失败反而埋在里面看不见。
    last_skip_ts: float = 0
    last_skip_reason: str = ""

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "last_data_ts": self.last_data_ts,
            "total_emitted": self.total_emitted,
            "pid": self.pid,
            "last_skip_ts": self.last_skip_ts,
            "last_skip_reason": self.last_skip_reason,
        })
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "DataSourceState":
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
            last_data_ts=data.get("last_data_ts", 0),
            total_emitted=data.get("total_emitted", 0),
            pid=data.get("pid", 0),
            last_skip_ts=data.get("last_skip_ts", 0),
            last_skip_reason=data.get("last_skip_reason", ""),
        )

