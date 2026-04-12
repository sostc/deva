"""Dictionary 数据模型与常量"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..infra.runtime.recoverable import (
    UnitMetadata,
    UnitState,
    UnitStatus,
)


DICT_ENTRY_TABLE = "naja_dictionary_entries"
DICT_PAYLOAD_TABLE = "naja_dictionary_payloads"


class DictionaryMetadata(UnitMetadata):
    """字典元数据"""

    dict_type: str = "dimension"
    schedule_type: str = "interval"
    interval_seconds: int = 300
    daily_time: str = "03:00"

    source_mode: str = "task"
    refresh_enabled: bool = True
    refresh_task_id: str = ""

    execution_mode: str = "timer"
    scheduler_trigger: str = "interval"
    cron_expr: str = ""
    run_at: str = ""
    event_source: str = "log"
    event_condition: str = ""
    event_condition_type: str = "contains"


@dataclass
class DictionaryState(UnitState):
    """字典状态"""

    last_status: str = ""
    last_update_ts: float = 0
    payload_key: str = ""
    data_size_bytes: int = 0

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "last_status": self.last_status,
                "last_update_ts": self.last_update_ts,
                "payload_key": self.payload_key,
                "data_size_bytes": self.data_size_bytes,
            }
        )
        return base

    @classmethod
    def from_dict(cls, data: dict) -> "DictionaryState":
        if isinstance(data, cls):
            return data
        base = UnitState.from_dict(data)
        return cls(
            status=base.status,
            start_time=base.start_time,
            last_activity_ts=base.last_activity_ts,
            error_count=base.error_count,
            last_error=base.last_error,
            last_error_ts=base.last_error_ts,
            run_count=base.run_count,
            last_status=data.get("last_status", ""),
            last_update_ts=data.get("last_update_ts", 0),
            payload_key=data.get("payload_key", ""),
            data_size_bytes=data.get("data_size_bytes", 0),
        )


