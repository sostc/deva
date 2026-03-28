"""Task - 基于 RecoverableUnit 抽象"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from deva import NB, EventTrigger, bus, log

from ..common.recoverable import (
    RecoverableUnit,
    UnitMetadata,
    UnitState,
    UnitStatus,
)
from ..scheduler import (
    SchedulerManager,
    normalize_execution_mode,
    parse_cron_expr,
    build_event_condition_checker,
)


TASK_TABLE = "naja_tasks"
TASK_HISTORY_TABLE = "naja_task_history"

# 共享调度管理器实例
_scheduler_manager = SchedulerManager()


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


class TaskEntry(RecoverableUnit):
    """任务条目"""

    def __init__(
        self,
        metadata: TaskMetadata = None,
        state: TaskState = None,
    ):
        super().__init__(
            metadata=metadata or TaskMetadata(),
            state=state or TaskState(),
        )

        self._timer_handle = None
        self._scheduler_job_name: Optional[str] = None
        self._event_sink = None
        self._execution_count: int = 0

    def _get_func_name(self) -> str:
        return "execute"

    def _do_compile(self, code: str) -> Callable:
        env = self._build_execution_env()
        exec(code, env)

        func = env.get(self._get_func_name())
        if not func or not callable(func):
            raise ValueError(f"函数 '{self._get_func_name()}' 未在代码中定义")

        return func

    def _do_start(self, func: Callable) -> dict:
        try:
            mode = normalize_execution_mode(
                getattr(self._metadata, "execution_mode", ""),
                getattr(self._metadata, "task_type", ""),
            )
            self._clear_runtime_handles()

            if mode == "timer":
                self._start_timer(func)
            elif mode == "scheduler":
                self._start_scheduler(func)
            elif mode == "event_trigger":
                self._start_event_trigger(func)
            else:
                return {"success": False, "error": f"不支持的执行方式: {mode}"}

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _do_stop(self) -> dict:
        try:
            self._clear_runtime_handles()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _start_timer(self, func: Callable):
        """启动定时器（使用共享调度管理器）"""
        interval = max(0.1, float(getattr(self._metadata, "interval_seconds", 60.0) or 60.0))
        _scheduler_manager.start_timer(
            name=f"task_timer_{self.id}",
            interval=interval,
            func=lambda: self._execute_once(func),
        )

    def _start_scheduler(self, func: Callable):
        """启动调度器（使用共享调度管理器）"""
        trigger = (getattr(self._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()
        raw_task_type = (getattr(self._metadata, "task_type", "") or "").strip().lower()

        if raw_task_type == "once" and trigger == "interval":
            trigger = "date"

        job_name = f"naja_task_{self.id}"

        if trigger == "interval":
            interval = max(1.0, float(getattr(self._metadata, "interval_seconds", 60.0) or 60.0))
            _scheduler_manager.add_scheduler_job(
                name=job_name,
                func=lambda: self._execute_once(func),
                trigger="interval",
                seconds=interval,
            )
        elif trigger == "cron":
            cron_expr = str(getattr(self._metadata, "cron_expr", "") or "").strip()
            if not cron_expr:
                raise ValueError("scheduler=cron 时 cron_expr 不能为空")
            _scheduler_manager.add_scheduler_job(
                name=job_name,
                func=lambda: self._execute_once(func),
                trigger="cron",
                **parse_cron_expr(cron_expr),
            )
        elif trigger == "date":
            run_at_raw = str(getattr(self._metadata, "run_at", "") or "").strip()
            run_at = datetime.fromisoformat(run_at_raw) if run_at_raw else datetime.now() + timedelta(seconds=1)
            _scheduler_manager.add_scheduler_job(
                name=job_name,
                func=lambda: self._execute_once(func),
                trigger="date",
                run_date=run_at,
            )
        else:
            raise ValueError(f"不支持的 scheduler trigger: {trigger}")

        self._scheduler_job_name = job_name

    def _start_event_trigger(self, func: Callable):
        """启动事件触发（使用共享调度管理器）"""
        source_name = (getattr(self._metadata, "event_source", "log") or "log").strip().lower()
        source = bus if source_name == "bus" else log
        
        condition_type = (getattr(self._metadata, "event_condition_type", "contains") or "contains").strip().lower()
        condition = str(getattr(self._metadata, "event_condition", "") or "")
        
        checker = build_event_condition_checker(condition_type, condition)
        
        event_sink = EventTrigger(condition=checker, source=source).then(
            lambda x: self._execute_once(func, event_payload=x)
        )
        
        _scheduler_manager.register_event_sink(f"task_event_{self.id}", event_sink)

    def _clear_runtime_handles(self):
        """清除所有调度资源（使用共享调度管理器）"""
        # 停止定时器
        _scheduler_manager.stop_timer(f"task_timer_{self.id}")

        # 移除调度作业
        if self._scheduler_job_name:
            _scheduler_manager.remove_scheduler_job(self._scheduler_job_name)
            self._scheduler_job_name = None

        # 注销事件接收器
        _scheduler_manager.unregister_event_sink(f"task_event_{self.id}")
        
        # 清理旧的事件接收器引用（向后兼容）
        if self._event_sink is not None:
            try:
                self._event_sink.destroy()
            except Exception:
                pass
            self._event_sink = None

    def _invoke_user_func(self, func: Callable, event_payload: Any = None):
        if event_payload is None:
            return func()

        try:
            import inspect

            sig = inspect.signature(func)
            params = list(sig.parameters.values())
        except Exception:
            return func(event_payload)

        if not params:
            return func()

        has_var_pos = any(p.kind == p.VAR_POSITIONAL for p in params)
        has_var_kw = any(p.kind == p.VAR_KEYWORD for p in params)
        positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]

        if positional or has_var_pos:
            return func(event_payload)

        if "event" in sig.parameters:
            return func(event=event_payload)

        if has_var_kw:
            return func(event=event_payload)

        return func()

    def _execute_once(self, func: Callable, event_payload: Any = None):
        """执行一次任务"""
        start_time = time.time()
        is_success = False
        result_text = ""
        error_msg = ""

        try:
            result = self._invoke_user_func(func, event_payload=event_payload)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(asyncio.run, result)
                        result = future.result(timeout=30)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(result)
                    finally:
                        loop.close()

            self._state.success_count += 1
            self._state.last_result = str(result)[:500] if result is not None else "None"
            self._state.record_success()

            is_success = True
            result_text = str(result)[:500] if result is not None else ""
            self._save_history(True, time.time() - start_time, result_text)

        except Exception as e:
            self._state.failure_count += 1
            self._state.last_result = f"Error: {str(e)}"
            self._state.record_error(str(e))

            error_msg = str(e)
            result_text = str(e)
            self._save_history(False, time.time() - start_time, result_text)

        # 计算执行时间
        execution_time_ms = (time.time() - start_time) * 1000
        
        # 记录性能指标
        try:
            from ..performance import record_component_execution, ComponentType
            record_component_execution(
                component_id=self.id,
                component_name=self.name,
                component_type=ComponentType.TASK,
                execution_time_ms=execution_time_ms,
                success=is_success,
                error=error_msg,
            )
        except Exception:
            pass  # 性能监控不应影响主流程

        self._state.last_run_time = time.time()
        self._execution_count += 1

        mode = normalize_execution_mode(
            getattr(self._metadata, "execution_mode", ""),
            getattr(self._metadata, "task_type", ""),
        )
        trigger = (getattr(self._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()
        if mode == "scheduler" and trigger == "date":
            self._clear_runtime_handles()
            self._state.status = UnitStatus.STOPPED.value
            self._was_running = False

        self.save()

        return result_text if is_success else None

    def _save_history(self, success: bool, duration: float, result: str):
        """保存执行历史（精简为仅流化记录，默认不落库）。

        设计目标：
        - 任务面板主要关注「计数 + 最近一次结果」，这些已经在 TaskState 中维护；
        - 避免为每次任务执行都写入 DB，从而降低锁竞争与磁盘占用。
        - 如需审计/回放，可后续引入专门的任务日志流或按需持久化，而不是每次都写 DB。
        """
        # 目前仅更新 TaskState，保留扩展点，避免频繁 DB 写入。
        # 如果后续需要，可以在这里将摘要写入某个日志流（例如 NS('naja_task_log')）。
        return

    def run_once(self) -> dict:
        """手动执行一次"""
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
        task_type: str = None,
        execution_mode: str = None,
        interval_seconds: float = None,
        scheduler_trigger: str = None,
        cron_expr: str = None,
        run_at: str = None,
        event_source: str = None,
        event_condition: str = None,
        event_condition_type: str = None,
        func_code: str = None,
    ) -> dict:
        if name is not None:
            self._metadata.name = name
        if description is not None:
            self._metadata.description = description
        if task_type is not None:
            self._metadata.task_type = task_type
        if execution_mode is not None or task_type is not None:
            self._metadata.execution_mode = normalize_execution_mode(execution_mode, task_type)
        if interval_seconds is not None:
            self._metadata.interval_seconds = max(0.1, float(interval_seconds))
        if scheduler_trigger is not None:
            self._metadata.scheduler_trigger = str(scheduler_trigger).strip().lower()
        if cron_expr is not None:
            self._metadata.cron_expr = str(cron_expr).strip()
        if run_at is not None:
            self._metadata.run_at = str(run_at).strip()
        if event_source is not None:
            self._metadata.event_source = str(event_source).strip().lower()
        if event_condition is not None:
            self._metadata.event_condition = str(event_condition)
        if event_condition_type is not None:
            self._metadata.event_condition_type = str(event_condition_type).strip().lower()

        if func_code is not None:
            if self._get_func_name() not in func_code:
                return {"success": False, "error": f"代码必须包含 {self._get_func_name()} 函数"}

            self._func_code = func_code
            self._compiled_func = None

            result = self.compile_code()
            if not result["success"]:
                return result

        self.save()
        return {"success": True}

    def save(self) -> dict:
        try:
            db = NB(TASK_TABLE)
            db[self.id] = self.to_dict()
            return {"success": True, "id": self.id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def to_dict(self) -> dict:
        mode = normalize_execution_mode(
            getattr(self._metadata, "execution_mode", ""),
            getattr(self._metadata, "task_type", ""),
        )
        return {
            "metadata": {
                "id": self._metadata.id,
                "name": self._metadata.name,
                "description": self._metadata.description,
                "tags": self._metadata.tags,
                "task_type": getattr(self._metadata, "task_type", mode),
                "execution_mode": mode,
                "interval_seconds": getattr(self._metadata, "interval_seconds", 60.0),
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
    def from_dict(cls, data: dict) -> "TaskEntry":
        metadata_data = data.get("metadata", {})
        legacy_task_type = metadata_data.get("task_type", "interval")
        execution_mode = normalize_execution_mode(metadata_data.get("execution_mode", ""), legacy_task_type)

        scheduler_trigger = metadata_data.get("scheduler_trigger")
        if not scheduler_trigger:
            if legacy_task_type == "once":
                scheduler_trigger = "date"
            elif metadata_data.get("cron_expr"):
                scheduler_trigger = "cron"
            else:
                scheduler_trigger = "interval"

        run_at = metadata_data.get("run_at", "")
        if legacy_task_type == "once" and not run_at:
            run_at = (datetime.now() + timedelta(seconds=1)).isoformat(timespec="seconds")

        metadata = TaskMetadata(
            id=metadata_data.get("id", ""),
            name=metadata_data.get("name", "unnamed"),
            description=metadata_data.get("description", ""),
            tags=metadata_data.get("tags", []),
            task_type=legacy_task_type,
            execution_mode=execution_mode,
            interval_seconds=metadata_data.get("interval_seconds", 60.0),
            scheduler_trigger=scheduler_trigger,
            cron_expr=metadata_data.get("cron_expr", ""),
            run_at=run_at,
            event_source=metadata_data.get("event_source", "log"),
            event_condition=metadata_data.get("event_condition", ""),
            event_condition_type=metadata_data.get("event_condition_type", "contains"),
            created_at=metadata_data.get("created_at", time.time()),
            updated_at=metadata_data.get("updated_at", time.time()),
        )

        state_data = data.get("state", {})
        state = TaskState.from_dict(state_data)

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


class TaskManager:
    """任务管理器

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局唯一性：任务系统是全局资源，只能有一个实例管理所有任务的生命周期。
       如果存在多个实例，可能导致任务状态不一致。

    2. 资源管理：TaskManager 持有任务字典（_items）和数据库连接（NB），
       这些资源应该全局共享，而非重复创建。

    3. 生命周期：Manager 的生命周期与系统一致，随系统启动和关闭。

    4. 依赖注入支持：如需测试，可以注入 mock 对象。

    5. Manager 类本身不是资源，而是通往资源的入口点。真正的系统资源
       （如 NB 数据库连接）是单例的，而 Manager 类保持单例是为了方便
       访问这些资源。
    ================================================================================
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._init_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        pass

    def _ensure_initialized(self):
        if getattr(self, '_initialized', False):
            return
        with self._init_lock:
            if getattr(self, '_initialized', False):
                return
            self._items: Dict[str, TaskEntry] = {}
            self._items_lock = threading.Lock()
            self.load_from_db()
            self._initialized = True

    def create(
        self,
        name: str,
        func_code: str,
        task_type: str = "interval",
        execution_mode: str = None,
        interval_seconds: float = 60.0,
        scheduler_trigger: str = "interval",
        cron_expr: str = "",
        run_at: str = "",
        event_source: str = "log",
        event_condition: str = "",
        event_condition_type: str = "contains",
        description: str = "",
        tags: List[str] = None,
    ) -> dict:
        from ..config import get_task_config

        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

        task_config = get_task_config()
        if interval_seconds is None:
            interval_seconds = task_config.get("default_interval", 60)

        if "execute" not in func_code:
            return {"success": False, "error": "代码必须包含 execute 函数"}

        mode = normalize_execution_mode(execution_mode, task_type)
        metadata = TaskMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            task_type=task_type,
            execution_mode=mode,
            interval_seconds=interval_seconds,
            scheduler_trigger=(scheduler_trigger or "interval").strip().lower(),
            cron_expr=(cron_expr or "").strip(),
            run_at=(run_at or "").strip(),
            event_source=(event_source or "log").strip().lower(),
            event_condition=event_condition or "",
            event_condition_type=(event_condition_type or "contains").strip().lower(),
        )

        if task_type == "once" and not metadata.run_at:
            metadata.scheduler_trigger = "date"
            metadata.run_at = (datetime.now() + timedelta(seconds=1)).isoformat(timespec="seconds")

        entry = TaskEntry(metadata=metadata)
        entry._func_code = func_code

        result = entry.compile_code()
        if not result["success"]:
            return {"success": False, "error": f"编译失败: {result['error']}"}

        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"任务名称已存在: {name}"}
            self._items[entry_id] = entry

        entry.save()

        self._log("INFO", "Task created", id=entry_id, name=name, mode=mode)
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}

    def get(self, entry_id: str) -> Optional[TaskEntry]:
        self._ensure_initialized()
        return self._items.get(entry_id)

    def get_by_name(self, name: str) -> Optional[TaskEntry]:
        self._ensure_initialized()
        for entry in self._items.values():
            if entry.name == name:
                return entry
        return None

    def list_all(self) -> List[TaskEntry]:
        self._ensure_initialized()
        return list(self._items.values())

    def list_all_dict(self) -> List[dict]:
        self._ensure_initialized()
        return [entry.to_dict() for entry in self._items.values()]

    def delete(self, entry_id: str) -> dict:
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}

        entry.stop()

        with self._items_lock:
            self._items.pop(entry_id, None)

        db = NB(TASK_TABLE)
        if entry_id in db:
            del db[entry_id]

        self._log("INFO", "Task deleted", id=entry_id, name=entry.name)
        return {"success": True}

    def start(self, entry_id: str) -> dict:
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.start()

    def stop(self, entry_id: str) -> dict:
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.stop()

    def run_once(self, entry_id: str) -> dict:
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.run_once()

    def run_once_async(self, entry_id: str) -> dict:
        """异步执行一次（不阻塞UI）"""
        self._ensure_initialized()
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
            name=f"task_run_once_{entry_id}",
        )
        t.start()
        return {"success": True, "message": "已提交执行任务"}

    def load_from_db(self) -> int:
        db = NB(TASK_TABLE)
        count = 0

        if not hasattr(self, '_items') or self._items is None:
            self._items = {}
        if not hasattr(self, '_items_lock') or self._items_lock is None:
            self._items_lock = threading.Lock()

        with self._items_lock:
            self._items.clear()

            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue

                try:
                    entry = TaskEntry.from_dict(data)
                    if not entry.id:
                        continue

                    self._items[entry.id] = entry
                    count += 1

                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

        return count

    def load_prefer_files(self) -> int:
        """优先从文件加载任务配置，NB 数据作为兜底

        加载策略：
        1. 先扫描 config/tasks/ 目录下的文件配置
        2. 如果文件存在，优先使用文件配置
        3. 如果文件不存在但 NB 中有，则使用 NB 数据
        4. 合并去重，以文件配置优先

        Returns:
            加载的任务数量
        """
        from deva.naja.config.file_config import get_file_config_manager

        file_mgr = get_file_config_manager('task')
        file_names = set(file_mgr.list_names())

        db = NB(TASK_TABLE)
        loaded_count = 0

        if not hasattr(self, '_items') or self._items is None:
            self._items = {}
        if not hasattr(self, '_items_lock') or self._items_lock is None:
            self._items_lock = threading.Lock()

        with self._items_lock:
            self._items.clear()

            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue

                try:
                    entry = TaskEntry.from_dict(data)
                    if not entry.id:
                        continue

                    name = entry.name
                    if name in file_names:
                        file_item = file_mgr.get(name)
                        if file_item and file_item.metadata.source == 'file':
                            existing_time = getattr(entry._metadata, 'updated_at', 0) or 0
                            file_time = file_item.metadata.updated_at or 0
                            if file_time >= existing_time:
                                file_entry = self._create_entry_from_file_config(file_item)
                                if file_entry:
                                    self._items[file_entry.id] = file_entry
                                    loaded_count += 1
                                    continue

                    self._items[entry.id] = entry
                    loaded_count += 1

                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

            for name in file_names:
                file_item = file_mgr.get(name)
                if not file_item:
                    continue

                name_already_loaded = any(e.name == name for e in self._items.values())
                if name_already_loaded:
                    continue

                try:
                    file_entry = self._create_entry_from_file_config(file_item)
                    if file_entry:
                        self._items[file_entry.id] = file_entry
                        loaded_count += 1
                except Exception as e:
                    self._log("ERROR", f"Load from file failed: {name}", error=str(e))

        return loaded_count

    def _create_entry_from_file_config(self, file_item) -> Optional[TaskEntry]:
        """从文件配置创建 TaskEntry"""
        from deva.naja.config.file_config import ConfigFileItem

        if not isinstance(file_item, ConfigFileItem):
            return None

        file_metadata = file_item.metadata
        file_config = file_item.config

        execution_mode = normalize_execution_mode(
            file_config.get('execution_mode', ''),
            file_config.get('task_type', 'timer')
        )

        scheduler_trigger = file_config.get('scheduler_trigger', 'interval')
        if scheduler_trigger == 'interval' and file_config.get('cron_expr'):
            scheduler_trigger = 'cron'

        metadata = TaskMetadata(
            id=file_metadata.id or file_item.name,
            name=file_item.name,
            description=file_metadata.description or '',
            tags=file_metadata.tags or [],
            task_type=file_config.get('task_type', 'timer'),
            execution_mode=execution_mode,
            interval_seconds=file_config.get('interval_seconds', 60.0),
            scheduler_trigger=scheduler_trigger,
            cron_expr=file_config.get('cron_expr', ''),
            run_at=file_config.get('run_at', ''),
            event_source=file_config.get('event_source', 'log'),
            event_condition=file_config.get('event_condition', ''),
            event_condition_type=file_config.get('event_condition_type', 'contains'),
            created_at=file_metadata.created_at or time.time(),
            updated_at=file_metadata.updated_at or time.time(),
        )

        state = TaskState()
        entry = TaskEntry(metadata=metadata, state=state)

        if file_item.func_code:
            entry._func_code = file_item.func_code
            try:
                entry.compile_code()
            except Exception:
                pass

        return entry

    def restore_running_states(self) -> dict:
        restored_count = 0
        failed_count = 0
        results = []

        with self._items_lock:
            entries_to_check = list(self._items.values())

        for entry in entries_to_check:
            if entry.name == "llm_auto_adjust":
                results.append(
                    {
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": True,
                        "skipped": True,
                        "reason": "llm_auto_adjust excluded from auto start",
                    }
                )
                continue

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

        return {
            "success": True,
            "restored_count": restored_count,
            "failed_count": failed_count,
            "results": results,
        }

    def get_all_recovery_info(self) -> List[dict]:
        self._ensure_initialized()
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
        self._ensure_initialized()
        entries = self.list_all()
        running = sum(1 for e in entries if e.is_running)

        total_success = sum(e._state.success_count for e in entries)
        total_failure = sum(e._state.failure_count for e in entries)

        return {
            "total": len(entries),
            "running": running,
            "stopped": len(entries) - running,
            "total_success": total_success,
            "total_failure": total_failure,
        }

    def _log(self, level: str, message: str, **extra):
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[TaskManager][{level}] {message} | {extra_str}")


_task_manager: Optional[TaskManager] = None
_task_manager_lock = threading.Lock()


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        with _task_manager_lock:
            if _task_manager is None:
                _task_manager = TaskManager()
    return _task_manager
