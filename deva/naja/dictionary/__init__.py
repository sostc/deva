"""Dictionary V2 - 基于 RecoverableUnit 抽象"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from deva import NB

from ..common.recoverable import (
    RecoverableUnit,
    UnitMetadata,
    UnitState,
    UnitStatus,
)
from ..scheduler import (
    daily_time_to_cron,
    normalize_execution_mode,
)

from .tongdaxin_blocks import (
    get_stock_blocks,
    get_block_info,
    get_block_stocks,
    get_all_blocks,
    get_blocks_by_keyword,
    get_stock_block_mapping,
    get_dataframe,
)


DICT_ENTRY_TABLE = "naja_dictionary_entries"
DICT_PAYLOAD_TABLE = "naja_dictionary_payloads"


def _normalize_source_mode(source_mode: Optional[str], has_upload: bool, has_code: bool) -> str:
    raw = str(source_mode or "").strip().lower()
    if raw in {"upload", "task", "upload_and_task"}:
        return raw
    if has_upload and has_code:
        return "upload_and_task"
    if has_upload:
        return "upload"
    return "task"


def _task_type_from_refresh_config(execution_mode: str, scheduler_trigger: str) -> str:
    """从刷新配置推断任务类型（用于向后兼容）"""
    mode = normalize_execution_mode(execution_mode)
    trig = str(scheduler_trigger or "interval").strip().lower()
    if mode == "scheduler" and trig == "date":
        return "once"
    if mode == "event_trigger":
        return "event_trigger"
    if mode == "scheduler":
        return "schedule"
    return "interval"


def _build_refresh_task_code(entry_id: str, fetch_code: str) -> str:
    return f'''{fetch_code}

def _resolve_awaitable(value):
    import asyncio
    import inspect
    import threading

    if not inspect.isawaitable(value):
        return value

    try:
        running_loop = asyncio.get_running_loop()
        loop_running = running_loop.is_running()
    except RuntimeError:
        loop_running = False

    if not loop_running:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(value)
        finally:
            loop.close()

    box = {{"value": None, "error": None}}

    def _runner():
        loop = asyncio.new_event_loop()
        try:
            box["value"] = loop.run_until_complete(value)
        except Exception as e:
            box["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if box["error"] is not None:
        raise box["error"]
    return box["value"]

def execute(event=None):
    from deva.naja.dictionary import get_dictionary_manager

    mgr = get_dictionary_manager()
    entry = mgr.get("{entry_id}")
    if entry is None:
        return "dictionary_not_found"

    try:
        data = fetch_data()
        data = _resolve_awaitable(data)
        entry.apply_fresh_data(data)
        return "ok"
    except Exception as e:
        entry.mark_refresh_error(str(e))
        raise
'''


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
            from ..tasks import get_task_manager

            with self._execution_lock:
                if self.is_running:
                    return {"success": True, "message": "Already running"}

                task_id = str(self._metadata.refresh_task_id or "")
                result = get_task_manager().start(task_id)
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
            from ..tasks import get_task_manager

            with self._execution_lock:
                if not self.is_running:
                    return {"success": True, "message": "Not running"}

                task_id = str(self._metadata.refresh_task_id or "")
                get_task_manager().stop(task_id)
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
            from ..tasks import get_task_manager

            task_id = str(self._metadata.refresh_task_id or "")
            return get_task_manager().run_once(task_id)

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


class DictionaryManager:
    """字典管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._items: Dict[str, DictionaryEntry] = {}
        self._items_lock = threading.Lock()
        self._initialized = True

    def _sync_legacy_schedule_fields(self, entry: DictionaryEntry):
        mode = str(getattr(entry._metadata, "execution_mode", "timer") or "timer").strip().lower()
        trig = str(getattr(entry._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()

        if mode == "scheduler" and trig == "cron" and getattr(entry._metadata, "cron_expr", ""):
            entry._metadata.schedule_type = "daily"
            entry._metadata.daily_time = getattr(entry._metadata, "daily_time", "03:00") or "03:00"
        else:
            entry._metadata.schedule_type = "interval"

    def _upsert_refresh_task(
        self,
        entry: DictionaryEntry,
        *,
        func_code: str,
        execution_mode: str,
        interval_seconds: int,
        scheduler_trigger: str,
        cron_expr: str,
        run_at: str,
        event_source: str,
        event_condition: str,
        event_condition_type: str,
    ) -> dict:
        from ..tasks import get_task_manager

        task_mgr = get_task_manager()
        wrapper_code = _build_refresh_task_code(entry.id, func_code)
        task_type = _task_type_from_refresh_config(execution_mode, scheduler_trigger)
        task_name = f"dict_refresh_{entry.name}_{entry.id}"

        existing_task_id = str(getattr(entry._metadata, "refresh_task_id", "") or "")
        existing_task = task_mgr.get(existing_task_id) if existing_task_id else None

        if existing_task:
            return existing_task.update_config(
                name=task_name,
                description=f"字典 {entry.name} 鲜活任务",
                task_type=task_type,
                execution_mode=execution_mode,
                interval_seconds=float(interval_seconds),
                scheduler_trigger=scheduler_trigger,
                cron_expr=cron_expr,
                run_at=run_at,
                event_source=event_source,
                event_condition=event_condition,
                event_condition_type=event_condition_type,
                func_code=wrapper_code,
            )

        create_result = task_mgr.create(
            name=task_name,
            func_code=wrapper_code,
            task_type=task_type,
            execution_mode=execution_mode,
            interval_seconds=float(interval_seconds),
            scheduler_trigger=scheduler_trigger,
            cron_expr=cron_expr,
            run_at=run_at,
            event_source=event_source,
            event_condition=event_condition,
            event_condition_type=event_condition_type,
            description=f"字典 {entry.name} 鲜活任务",
        )
        if create_result.get("success"):
            entry._metadata.refresh_task_id = create_result.get("id", "")
        return create_result

    def _remove_refresh_task(self, entry: DictionaryEntry):
        task_id = str(getattr(entry._metadata, "refresh_task_id", "") or "")
        if not task_id:
            return
        from ..tasks import get_task_manager

        task_mgr = get_task_manager()
        try:
            task_mgr.stop(task_id)
        except Exception:
            pass
        try:
            task_mgr.delete(task_id)
        except Exception:
            pass

    def create(
        self,
        name: str,
        func_code: str = "",
        schedule_type: str = "interval",
        interval_seconds: int = None,
        daily_time: str = None,
        description: str = "",
        tags: List[str] = None,
        dict_type: str = "dimension",
        source_mode: str = "",
        uploaded_data: Any = None,
        execution_mode: str = "timer",
        scheduler_trigger: str = "interval",
        cron_expr: str = "",
        run_at: str = "",
        event_source: str = "log",
        event_condition: str = "",
        event_condition_type: str = "contains",
    ) -> dict:
        from ..config import get_dictionary_config

        import hashlib

        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

        dict_config = get_dictionary_config()
        if interval_seconds is None:
            interval_seconds = int(dict_config.get("default_interval", 300))
        if daily_time is None:
            daily_time = str(dict_config.get("default_daily_time", "03:00"))

        if schedule_type == "daily" and not cron_expr:
            try:
                execution_mode = "scheduler"
                scheduler_trigger = "cron"
                cron_expr = _daily_time_to_cron(daily_time)
            except Exception:
                pass

        has_upload = uploaded_data is not None
        has_code = bool(str(func_code or "").strip())
        mode = _normalize_source_mode(source_mode, has_upload, has_code)

        if mode == "upload" and not has_upload:
            return {"success": False, "error": "上传模式需要提供初始数据"}
        if mode in {"task", "upload_and_task"} and not has_code:
            return {"success": False, "error": "鲜活任务模式需要提供 fetch_data 代码"}
        if has_code and "fetch_data" not in func_code:
            return {"success": False, "error": "代码必须包含 fetch_data 函数"}

        metadata = DictionaryMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            dict_type=dict_type,
            schedule_type=schedule_type,
            interval_seconds=int(interval_seconds),
            daily_time=daily_time,
            source_mode=mode,
            refresh_enabled=(mode in {"task", "upload_and_task"}),
            execution_mode=execution_mode,
            scheduler_trigger=scheduler_trigger,
            cron_expr=cron_expr,
            run_at=run_at,
            event_source=event_source,
            event_condition=event_condition,
            event_condition_type=event_condition_type,
        )

        entry = DictionaryEntry(metadata=metadata)
        entry._func_code = func_code or ""

        if has_code:
            result = entry.compile_code()
            if not result["success"]:
                return {"success": False, "error": f"编译失败: {result['error']}"}

        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"字典名称已存在: {name}"}
            self._items[entry_id] = entry

        if has_upload:
            entry.apply_fresh_data(uploaded_data)

        if metadata.refresh_enabled:
            task_result = self._upsert_refresh_task(
                entry,
                func_code=func_code,
                execution_mode=execution_mode,
                interval_seconds=int(interval_seconds),
                scheduler_trigger=scheduler_trigger,
                cron_expr=cron_expr,
                run_at=run_at,
                event_source=event_source,
                event_condition=event_condition,
                event_condition_type=event_condition_type,
            )
            if not task_result.get("success"):
                with self._items_lock:
                    self._items.pop(entry_id, None)
                return {"success": False, "error": f"创建鲜活任务失败: {task_result.get('error')}"}

        self._sync_legacy_schedule_fields(entry)
        entry.save()

        self._log("INFO", "Dictionary created", id=entry_id, name=name, mode=mode)
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}

    def update(
        self,
        entry_id: str,
        *,
        name: str = None,
        description: str = None,
        dict_type: str = None,
        source_mode: str = None,
        uploaded_data: Any = None,
        func_code: str = None,
        execution_mode: str = None,
        interval_seconds: int = None,
        scheduler_trigger: str = None,
        cron_expr: str = None,
        run_at: str = None,
        event_source: str = None,
        event_condition: str = None,
        event_condition_type: str = None,
    ) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}

        if name is not None:
            new_name = name.strip()
            if not new_name:
                return {"success": False, "error": "名称不能为空"}
            with self._items_lock:
                duplicated = any(e.id != entry.id and e.name == new_name for e in self._items.values())
            if duplicated:
                return {"success": False, "error": f"字典名称已存在: {new_name}"}
            entry._metadata.name = new_name

        if description is not None:
            entry._metadata.description = description
        if dict_type is not None:
            entry._metadata.dict_type = dict_type

        if uploaded_data is not None:
            entry.apply_fresh_data(uploaded_data)

        if func_code is not None:
            if func_code.strip() and "fetch_data" not in func_code:
                return {"success": False, "error": "代码必须包含 fetch_data 函数"}
            entry._func_code = func_code
            entry._compiled_func = None
            if func_code.strip():
                compile_result = entry.compile_code()
                if not compile_result.get("success"):
                    return {"success": False, "error": f"编译失败: {compile_result.get('error')}"}

        effective_mode = _normalize_source_mode(
            source_mode if source_mode is not None else entry._metadata.source_mode,
            uploaded_data is not None or entry.get_payload() is not None,
            bool((func_code if func_code is not None else entry.func_code or "").strip()),
        )

        entry._metadata.source_mode = effective_mode
        entry._metadata.refresh_enabled = effective_mode in {"task", "upload_and_task"}

        if execution_mode is not None:
            entry._metadata.execution_mode = execution_mode
        if interval_seconds is not None:
            entry._metadata.interval_seconds = max(5, int(interval_seconds))
        if scheduler_trigger is not None:
            entry._metadata.scheduler_trigger = scheduler_trigger
        if cron_expr is not None:
            entry._metadata.cron_expr = cron_expr
        if run_at is not None:
            entry._metadata.run_at = run_at
        if event_source is not None:
            entry._metadata.event_source = event_source
        if event_condition is not None:
            entry._metadata.event_condition = event_condition
        if event_condition_type is not None:
            entry._metadata.event_condition_type = event_condition_type

        if entry._metadata.refresh_enabled:
            code_for_task = (entry.func_code or "").strip()
            if not code_for_task:
                return {"success": False, "error": "鲜活任务模式需要 fetch_data 代码"}
            task_result = self._upsert_refresh_task(
                entry,
                func_code=code_for_task,
                execution_mode=entry._metadata.execution_mode,
                interval_seconds=int(entry._metadata.interval_seconds),
                scheduler_trigger=entry._metadata.scheduler_trigger,
                cron_expr=entry._metadata.cron_expr,
                run_at=entry._metadata.run_at,
                event_source=entry._metadata.event_source,
                event_condition=entry._metadata.event_condition,
                event_condition_type=entry._metadata.event_condition_type,
            )
            if not task_result.get("success"):
                return {"success": False, "error": f"更新鲜活任务失败: {task_result.get('error')}"}
        else:
            self._remove_refresh_task(entry)
            entry._metadata.refresh_task_id = ""

        self._sync_legacy_schedule_fields(entry)
        return entry.save()

    def get(self, entry_id: str) -> Optional[DictionaryEntry]:
        return self._items.get(entry_id)

    def get_by_name(self, name: str) -> Optional[DictionaryEntry]:
        for entry in self._items.values():
            if entry.name == name:
                return entry
        return None

    def list_all(self) -> List[DictionaryEntry]:
        return list(self._items.values())

    def list_all_dict(self) -> List[dict]:
        return [entry.to_dict() for entry in self._items.values()]

    def delete(self, entry_id: str) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}

        entry.stop()
        self._remove_refresh_task(entry)
        entry.clear_payload()

        with self._items_lock:
            self._items.pop(entry_id, None)

        db = NB(DICT_ENTRY_TABLE)
        if entry_id in db:
            del db[entry_id]

        self._log("INFO", "Dictionary deleted", id=entry_id, name=entry.name)
        return {"success": True}

    def start(self, entry_id: str) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.start()

    def stop(self, entry_id: str) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.stop()

    def run_once(self, entry_id: str) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.run_once()

    def run_once_async(self, entry_id: str) -> dict:
        """异步执行一次（不阻塞UI）"""
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}

        def _run_in_thread():
            try:
                entry.run_once()
            except Exception as e:
                self._log("ERROR", "Async run failed", id=entry_id, error=str(e))

        t = threading.Thread(
            target=_run_in_thread,
            daemon=True,
            name=f"dict_run_once_{entry_id}",
        )
        t.start()

        self._log("INFO", "Dictionary refresh queued", id=entry_id)
        return {"success": True, "queued": True, "entry_id": entry_id}

    def load_from_db(self) -> int:
        db = NB(DICT_ENTRY_TABLE)
        count = 0

        with self._items_lock:
            self._items.clear()

            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue

                try:
                    entry = DictionaryEntry.from_dict(data)
                    if not entry.id:
                        continue

                    self._items[entry.id] = entry
                    count += 1

                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

        self._log("INFO", "Load from db finished", count=count)
        return count

    def restore_running_states(self) -> dict:
        restored_count = 0
        failed_count = 0
        results = []

        with self._items_lock:
            entries_to_check = list(self._items.values())

        for entry in entries_to_check:
            try:
                prep = entry.prepare_for_recovery()

                if not prep.get("can_recover"):
                    results.append(
                        {
                            "entry_id": entry.id,
                            "entry_name": entry.name,
                            "success": False,
                            "reason": prep.get("reason"),
                        }
                    )
                    continue

                result = entry.start()

                if result.get("success"):
                    restored_count += 1
                    results.append(
                        {
                            "entry_id": entry.id,
                            "entry_name": entry.name,
                            "success": True,
                        }
                    )
                else:
                    failed_count += 1
                    results.append(
                        {
                            "entry_id": entry.id,
                            "entry_name": entry.name,
                            "success": False,
                            "error": result.get("error"),
                        }
                    )

            except Exception as e:
                failed_count += 1
                results.append(
                    {
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "error": str(e),
                    }
                )

        self._log("INFO", "Restore finished", restored=restored_count, failed=failed_count)

        return {
            "success": True,
            "restored_count": restored_count,
            "failed_count": failed_count,
            "results": results,
        }

    def get_all_recovery_info(self) -> List[dict]:
        info = []
        for entry in self._items.values():
            prep = entry.prepare_for_recovery()
            info.append(
                {
                    "id": entry.id,
                    "name": entry.name,
                    "was_running": entry.was_running,
                    "can_recover": prep.get("can_recover"),
                    "reason": prep.get("reason"),
                }
            )
        return info

    def get_stats(self) -> dict:
        entries = self.list_all()
        running = sum(1 for e in entries if e.is_running)
        success = sum(1 for e in entries if e._state.last_status == "success")
        error = sum(1 for e in entries if e._state.last_status == "error")

        return {
            "total": len(entries),
            "running": running,
            "success": success,
            "error": error,
        }

    def _log(self, level: str, message: str, **extra):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[{ts}][DictionaryManager][{level}] {message} | {extra_str}")


_dict_manager: Optional[DictionaryManager] = None
_dict_manager_lock = threading.Lock()


def get_dictionary_manager() -> DictionaryManager:
    global _dict_manager
    if _dict_manager is None:
        with _dict_manager_lock:
            if _dict_manager is None:
                _dict_manager = DictionaryManager()
    return _dict_manager


def create_tongdaxin_blocks_dict(
    name: str = "通达信概念板块", 
    interval_seconds: int = 86400,
    blocks_file: str = None
) -> dict:
    """创建通达信概念板块字典
    
    鲜活任务会定期读取 infoharbor_block.dat 文件来更新数据
    
    Args:
        name: 字典名称
        interval_seconds: 自动刷新间隔（秒），默认24小时
        blocks_file: 板块数据文件路径，默认使用项目根目录的 infoharbor_block.dat
    
    Returns:
        创建结果
    """
    from pathlib import Path
    from deva.naja.dictionary.tongdaxin_blocks import BLOCKS_FILE
    
    file_path = blocks_file or BLOCKS_FILE
    
    func_code = f'''import pandas as pd
from pathlib import Path

def fetch_data():
    blocks_file = "{file_path}"
    from deva.naja.dictionary.tongdaxin_blocks import get_dataframe
    return get_dataframe(filepath=blocks_file)
'''
    
    mgr = get_dictionary_manager()
    return mgr.create(
        name=name,
        description=f"通达信概念板块数据，从 {Path(file_path).name} 文件读取，包含股票与所属板块的映射关系",
        dict_type="stock_basic_block",
        source_mode="task",
        func_code=func_code,
        execution_mode="timer",
        interval_seconds=interval_seconds,
    )


def enrich_stock_with_blocks(df: pd.DataFrame, code_column: str = "code") -> pd.DataFrame:
    """为股票DataFrame补充板块信息
    
    Args:
        df: 包含股票代码的DataFrame
        code_column: 股票代码列名
    
    Returns:
        补充了blocks列的DataFrame
    """
    from .tongdaxin_blocks import get_stock_blocks
    
    df = df.copy()
    df[code_column] = df[code_column].astype(str).str.zfill(6)
    df["blocks"] = df[code_column].apply(lambda x: "|".join(get_stock_blocks(x)))
    df["block_count"] = df["blocks"].apply(lambda x: len(x.split("|")) if x else 0)
    return df
