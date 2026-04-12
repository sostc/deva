"""Dictionary Entry - RecoverableUnit 子类"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from deva import NB

from ..common.recoverable import (
    RecoverableUnit,
    UnitStatus,
)
from ..scheduler import (
    daily_time_to_cron,
    normalize_execution_mode,
)
from .models import (
    DICT_ENTRY_TABLE,
    DICT_PAYLOAD_TABLE,
    DictionaryMetadata,
    DictionaryState,
)
from .helpers import (
    _normalize_source_mode,
    _task_type_from_refresh_config,
    _build_refresh_task_code,
)
from deva.naja.register import SR


class DictionaryEntry(RecoverableUnit):
    """字典条目"""

    def __init__(
        self,
        metadata: DictionaryMetadata = None,
        state: DictionaryState = None,
    ):
        super().__init__(
            metadata=metadata or DictionaryMetadata(),
            state=state or DictionaryState(),
        )

        self._payload_db = NB(DICT_PAYLOAD_TABLE)

    def _get_func_name(self) -> str:
        return "fetch_data"

    def _do_compile(self, code: str) -> Callable:
        env = self._build_execution_env()
        exec(code, env)

        func = env.get(self._get_func_name())
        if not func or not callable(func):
            raise ValueError(f"函数 '{self._get_func_name()}' 未在代码中定义")

        return func

    def apply_fresh_data(self, data: Any):
        self._save_payload(data)
        self._state.last_status = "success"
        self._state.last_update_ts = time.time()
        self._state.record_success()
        self.save()

    def mark_refresh_error(self, error: str):
        self._state.last_status = "error"
        self._state.record_error(str(error))
        self.save()

    def _has_refresh_task(self) -> bool:
        return bool(getattr(self._metadata, "refresh_enabled", False) and getattr(self._metadata, "refresh_task_id", ""))

    def start(self) -> dict:
        if self._has_refresh_task():

            with self._execution_lock:
                if self.is_running:
                    return {"success": True, "message": "Already running"}

                task_id = str(self._metadata.refresh_task_id or "")
                result = SR('task_manager').start(task_id)
                if not result.get("success"):
                    self._state.status = UnitStatus.ERROR.value
                    self._state.record_error(result.get("error", "refresh task start failed"))
                    self.save()
                    return result

                self._state.status = UnitStatus.RUNNING.value
                self._state.start_time = time.time()
                self._was_running = True
                self.save()
                return {"success": True, "status": self._state.status}
        return super().start()

    def stop(self) -> dict:
        if self._has_refresh_task():

            with self._execution_lock:
                if not self.is_running:
                    return {"success": True, "message": "Not running"}

                task_id = str(self._metadata.refresh_task_id or "")
                SR('task_manager').stop(task_id)
                self._state.status = UnitStatus.STOPPED.value
                self._was_running = False
                self.save()
                return {"success": True, "status": self._state.status}
        return super().stop()

    def _do_start(self, func: Callable) -> dict:
        # legacy fallback: no linked refresh task时沿用旧逻辑
        try:
            interval = max(5, int(getattr(self._metadata, "interval_seconds", 300) or 300))

            def run_and_reschedule():
                if self._stop_event.is_set():
                    return

                self._execute_once(func)

                if not self._stop_event.is_set():
                    self._thread = threading.Timer(interval, run_and_reschedule)
                    self._thread.daemon = True
                    self._thread.start()

            self._thread = threading.Timer(0.1, run_and_reschedule)
            self._thread.daemon = True
            self._thread.start()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _do_stop(self) -> dict:
        if self._thread and hasattr(self._thread, "cancel"):
            self._thread.cancel()
        return {"success": True}

    def _execute_once(self, func: Callable):
        """legacy执行一次"""
        try:
            import asyncio

            is_async = asyncio.iscoroutinefunction(func)

            if is_async:
                loop = asyncio.new_event_loop()
                try:
                    data = loop.run_until_complete(func())
                finally:
                    loop.close()
            else:
                data = func()
                if asyncio.iscoroutine(data):
                    loop = asyncio.new_event_loop()
                    try:
                        data = loop.run_until_complete(data)
                    finally:
                        loop.close()

            self.apply_fresh_data(data)
            self._log("INFO", "fetch_data executed", id=self.id)

        except Exception as e:
            self.mark_refresh_error(str(e))
            self._log("ERROR", "fetch_data failed", id=self.id, error=str(e))

    def _save_payload(self, data: Any):
        """保存数据"""
        try:
            payload_key = self._state.payload_key or f"{self.id}:latest"
            self._state.payload_key = payload_key

            self._payload_db[payload_key] = {
                "data": data,
                "ts": time.time(),
                "entry_id": self.id,
                "entry_name": self.name,
            }

            try:
                self._state.data_size_bytes = len(str(data).encode("utf-8"))
            except Exception:
                self._state.data_size_bytes = 0

        except Exception as e:
            self._log("ERROR", "Save payload failed", error=str(e))

    def get_payload(self) -> Any:
        """获取数据"""
        payload = self._payload_db.get(self._state.payload_key)
        if isinstance(payload, dict):
            return payload.get("data")
        return None

    def clear_payload(self) -> dict:
        """清除数据"""
        try:
            if self._state.payload_key and self._state.payload_key in self._payload_db:
                del self._payload_db[self._state.payload_key]

            self._state.last_status = "cleared"
            self._state.last_update_ts = 0
            self._state.data_size_bytes = 0
            self.save()

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_once(self) -> dict:
        """手动执行一次"""
        if self._has_refresh_task():

            task_id = str(self._metadata.refresh_task_id or "")
            return SR('task_manager').run_once(task_id)

        if not self._compiled_func:
            result = self.ensure_compiled()
            if not result["success"]:
                return result

        try:
            self._execute_once(self._compiled_func)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_config(
        self,
        name: str = None,
        description: str = None,
        dict_type: str = None,
        source_mode: str = None,
        refresh_enabled: bool = None,
        func_code: str = None,
    ) -> dict:
        if name is not None:
            self._metadata.name = name
        if description is not None:
            self._metadata.description = description
        if dict_type is not None:
            self._metadata.dict_type = dict_type
        if source_mode is not None:
            self._metadata.source_mode = source_mode
        if refresh_enabled is not None:
            self._metadata.refresh_enabled = bool(refresh_enabled)

        if func_code is not None:
            self._func_code = func_code
            self._compiled_func = None
            if func_code.strip():
                if self._get_func_name() not in func_code:
                    return {"success": False, "error": f"代码必须包含 {self._get_func_name()} 函数"}
                result = self.compile_code()
                if not result["success"]:
                    return result

        self.save()
        return {"success": True}

    def save(self) -> dict:
        try:
            db = NB(DICT_ENTRY_TABLE)
            db[self.id] = self.to_dict()
            return {"success": True, "id": self.id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def to_dict(self) -> dict:
        return {
            "metadata": {
                "id": self._metadata.id,
                "name": self._metadata.name,
                "description": self._metadata.description,
                "tags": self._metadata.tags,
                "dict_type": getattr(self._metadata, "dict_type", "dimension"),
                "schedule_type": getattr(self._metadata, "schedule_type", "interval"),
                "interval_seconds": getattr(self._metadata, "interval_seconds", 300),
                "daily_time": getattr(self._metadata, "daily_time", "03:00"),
                "source_mode": getattr(self._metadata, "source_mode", "task"),
                "refresh_enabled": bool(getattr(self._metadata, "refresh_enabled", True)),
                "refresh_task_id": getattr(self._metadata, "refresh_task_id", ""),
                "execution_mode": getattr(self._metadata, "execution_mode", "timer"),
                "scheduler_trigger": getattr(self._metadata, "scheduler_trigger", "interval"),
                "cron_expr": getattr(self._metadata, "cron_expr", ""),
                "run_at": getattr(self._metadata, "run_at", ""),
                "event_source": getattr(self._metadata, "event_source", "log"),
                "event_condition": getattr(self._metadata, "event_condition", ""),
                "event_condition_type": getattr(self._metadata, "event_condition_type", "contains"),
                "created_at": self._metadata.created_at,
                "updated_at": self._metadata.updated_at,
            },
            "state": self._state.to_dict(),
            "func_code": self._func_code,
            "was_running": self._was_running,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DictionaryEntry":
        metadata_data = data.get("metadata", {})
        schedule_type = metadata_data.get("schedule_type", "interval")
        daily_time = metadata_data.get("daily_time", "03:00")

        execution_mode = metadata_data.get("execution_mode")
        scheduler_trigger = metadata_data.get("scheduler_trigger")
        cron_expr = metadata_data.get("cron_expr", "")

        if not execution_mode:
            if schedule_type == "daily":
                execution_mode = "scheduler"
                scheduler_trigger = "cron"
                if not cron_expr:
                    try:
                        cron_expr = _daily_time_to_cron(daily_time)
                    except Exception:
                        cron_expr = "0 3 * * *"
            else:
                execution_mode = "timer"
                scheduler_trigger = "interval"

        metadata = DictionaryMetadata(
            id=metadata_data.get("id", ""),
            name=metadata_data.get("name", "unnamed"),
            description=metadata_data.get("description", ""),
            tags=metadata_data.get("tags", []),
            dict_type=metadata_data.get("dict_type", "dimension"),
            schedule_type=schedule_type,
            interval_seconds=metadata_data.get("interval_seconds", 300),
            daily_time=daily_time,
            source_mode=metadata_data.get("source_mode", "task"),
            refresh_enabled=bool(metadata_data.get("refresh_enabled", bool(metadata_data.get("refresh_task_id")))),
            refresh_task_id=metadata_data.get("refresh_task_id", ""),
            execution_mode=execution_mode,
            scheduler_trigger=scheduler_trigger or "interval",
            cron_expr=cron_expr,
            run_at=metadata_data.get("run_at", ""),
            event_source=metadata_data.get("event_source", "log"),
            event_condition=metadata_data.get("event_condition", ""),
            event_condition_type=metadata_data.get("event_condition_type", "contains"),
            created_at=metadata_data.get("created_at", time.time()),
            updated_at=metadata_data.get("updated_at", time.time()),
        )

        state_data = data.get("state", {})
        state = DictionaryState.from_dict(state_data)

        entry = cls(metadata=metadata, state=state)

        func_code = data.get("func_code", "")
        if func_code:
            entry._func_code = func_code
            try:
                entry.compile_code()
            except Exception:
                pass

        entry._was_running = data.get("was_running", False)
        entry._state.status = UnitStatus.STOPPED.value

        return entry

