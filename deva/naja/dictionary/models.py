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


# ❗这里原先漏了 `@dataclass` —— 而同族的 `DataSourceMetadata` /
# `TaskMetadata` / `StrategyMetadata` **全都有**。后果不是"少几个字段"：
# 没有装饰器时下面 14 行只是**普通类属性**，Annotations 不会被
# `dataclasses.fields()` 收集，`__init__` 也仍然只认基类那 6 个参数 ——
# 于是凡原先不必存在的构造调用（`DictionaryEntry.from_dict` /
# `DictionaryManager.create_dictionary` 都在传这 14 个具名字段）**必然 TypeError**，
# `naja_dictionary_entries` 至今 0 行（payload 表只剩重构前的化石数据）。
# 同时 `DictionaryEntry.to_dict()` 里那一串 `getattr(m, k, 默认值)` 读到的
# 永远是类默认值 —— 这是一处「用兜底默认值掩盖字段根本没接上」的静默失效。
# 加上装饰器后：字段成为真实实例属性，构造不再 TypeError，getattr 也就真能读到值了。
@dataclass
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


