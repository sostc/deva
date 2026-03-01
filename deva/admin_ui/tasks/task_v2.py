"""Task V2 - 基于 RecoverableUnit 抽象

统一状态保存恢复与执行函数恢复的任务实现。
"""

from __future__ import annotations

import asyncio
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB

from ..common.recoverable import (
    RecoverableUnit,
    UnitMetadata,
    UnitState,
    UnitStatus,
)


TASK_TABLE = "tasks_v2"
TASK_HISTORY_TABLE = "task_v2_history"


@dataclass
class TaskMetadata(UnitMetadata):
    """任务元数据"""
    task_type: str = "interval"
    interval_seconds: float = 60.0
    cron_expr: str = ""
    max_retries: int = 3
    timeout_seconds: float = 300.0


@dataclass
class TaskState(UnitState):
    """任务状态"""
    last_run_time: float = 0
    next_run_time: float = 0
    success_count: int = 0
    failure_count: int = 0
    last_result: str = ""


class TaskEntry(RecoverableUnit):
    """任务条目
    
    基于 RecoverableUnit 抽象的任务实现。
    支持：
    - 定时执行 execute 函数
    - interval（间隔）、cron（定时）、once（一次性）三种调度类型
    - 状态持久化与恢复
    """
    
    _instances: Dict[str, "TaskEntry"] = {}
    _instances_lock = threading.Lock()
    
    def __init__(
        self,
        metadata: TaskMetadata = None,
        state: TaskState = None,
    ):
        super().__init__(
            metadata=metadata or TaskMetadata(),
            state=state or TaskState(),
        )
        
        self._timer: Optional[threading.Timer] = None
        self._execution_count: int = 0
    
    def _get_func_name(self) -> str:
        return "execute"
    
    def _do_compile(self, code: str) -> Callable:
        env = self._build_execution_env()
        local_vars: Dict[str, Any] = {}
        exec(code, env, local_vars)
        
        func = local_vars.get(self._get_func_name())
        if not func or not callable(func):
            raise ValueError(f"函数 '{self._get_func_name()}' 未在代码中定义")
        
        return func
    
    def _do_start(self, func: Callable) -> dict:
        try:
            task_type = getattr(self._metadata, "task_type", "interval")
            
            if task_type == "once":
                self._schedule_once(func)
            elif task_type == "cron":
                self._schedule_cron(func)
            else:
                self._schedule_interval(func)
            
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _do_stop(self) -> dict:
        try:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _schedule_interval(self, func: Callable):
        """间隔调度"""
        interval = getattr(self._metadata, "interval_seconds", 60.0) or 60.0
        
        def run_and_reschedule():
            if self._stop_event.is_set():
                return
            
            self._execute_once(func)
            
            if not self._stop_event.is_set():
                self._timer = threading.Timer(interval, run_and_reschedule)
                self._timer.daemon = True
                self._timer.start()
        
        self._timer = threading.Timer(0.1, run_and_reschedule)
        self._timer.daemon = True
        self._timer.start()
    
    def _schedule_once(self, func: Callable):
        """一次性任务"""
        def run_once():
            if self._stop_event.is_set():
                return
            
            self._execute_once(func)
            
            self._state.status = "completed"
            self._was_running = False
            self.save()
        
        self._timer = threading.Timer(0.1, run_once)
        self._timer.daemon = True
        self._timer.start()
    
    def _schedule_cron(self, func: Callable):
        """Cron 调度（简化实现）"""
        interval = getattr(self._metadata, "interval_seconds", 60.0) or 60.0
        
        def run_and_reschedule():
            if self._stop_event.is_set():
                return
            
            self._execute_once(func)
            
            if not self._stop_event.is_set():
                self._timer = threading.Timer(interval, run_and_reschedule)
                self._timer.daemon = True
                self._timer.start()
        
        self._timer = threading.Timer(0.1, run_and_reschedule)
        self._timer.daemon = True
        self._timer.start()
    
    def _execute_once(self, func: Callable):
        """执行一次任务"""
        start_time = time.time()
        try:
            is_async = asyncio.iscoroutinefunction(func)
            
            if is_async:
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(func())
                finally:
                    loop.close()
            else:
                result = func()
            
            self._state.success_count += 1
            self._state.last_result = str(result)[:500] if result else "None"
            self._state.record_success()
            
            self._save_history(True, time.time() - start_time, str(result)[:500] if result else "")
            
        except Exception as e:
            self._state.failure_count += 1
            self._state.last_result = f"Error: {str(e)}"
            self._state.record_error(str(e))
            
            self._save_history(False, time.time() - start_time, str(e))
        
        self._state.last_run_time = time.time()
        self._execution_count += 1
        self.save()
    
    def _save_history(self, success: bool, duration: float, result: str):
        """保存执行历史"""
        try:
            db = NB(TASK_HISTORY_TABLE)
            history_key = f"{self.id}_{int(time.time() * 1000)}"
            db[history_key] = {
                "task_id": self.id,
                "task_name": self.name,
                "success": success,
                "duration": duration,
                "result": result[:500] if result else "",
                "timestamp": time.time(),
            }
        except Exception:
            pass
    
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
        interval_seconds: float = None,
        cron_expr: str = None,
        func_code: str = None,
        max_retries: int = None,
        timeout_seconds: float = None,
    ) -> dict:
        """更新配置"""
        if name is not None:
            self._metadata.name = name
        if description is not None:
            self._metadata.description = description
        if task_type is not None:
            self._metadata.task_type = task_type
        if interval_seconds is not None:
            self._metadata.interval_seconds = max(1.0, float(interval_seconds))
        if cron_expr is not None:
            self._metadata.cron_expr = cron_expr
        if max_retries is not None:
            self._metadata.max_retries = max(0, int(max_retries))
        if timeout_seconds is not None:
            self._metadata.timeout_seconds = max(1.0, float(timeout_seconds))
        
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
        return {
            "metadata": {
                "id": self._metadata.id,
                "name": self._metadata.name,
                "description": self._metadata.description,
                "tags": self._metadata.tags,
                "task_type": getattr(self._metadata, "task_type", "interval"),
                "interval_seconds": getattr(self._metadata, "interval_seconds", 60.0),
                "cron_expr": getattr(self._metadata, "cron_expr", ""),
                "max_retries": getattr(self._metadata, "max_retries", 3),
                "timeout_seconds": getattr(self._metadata, "timeout_seconds", 300.0),
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
        metadata = TaskMetadata(
            id=metadata_data.get("id", ""),
            name=metadata_data.get("name", "unnamed"),
            description=metadata_data.get("description", ""),
            tags=metadata_data.get("tags", []),
            task_type=metadata_data.get("task_type", "interval"),
            interval_seconds=metadata_data.get("interval_seconds", 60.0),
            cron_expr=metadata_data.get("cron_expr", ""),
            max_retries=metadata_data.get("max_retries", 3),
            timeout_seconds=metadata_data.get("timeout_seconds", 300.0),
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
        
        saved_status = state_data.get("status", UnitStatus.STOPPED.value)
        entry._was_running = (saved_status == UnitStatus.RUNNING.value)
        entry._state.status = UnitStatus.STOPPED.value
        
        return entry


class TaskManager:
    """任务管理器 V2
    
    继承统一管理器设计模式。
    """
    
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
        self._items: Dict[str, TaskEntry] = {}
        self._items_lock = threading.Lock()
        self._initialized = True
    
    def create(
        self,
        name: str,
        func_code: str,
        task_type: str = "interval",
        interval_seconds: float = 60.0,
        cron_expr: str = "",
        description: str = "",
        tags: List[str] = None,
    ) -> dict:
        import hashlib
        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]
        
        if "execute" not in func_code:
            return {"success": False, "error": "代码必须包含 execute 函数"}
        
        metadata = TaskMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            task_type=task_type,
            interval_seconds=interval_seconds,
            cron_expr=cron_expr,
        )
        
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
        
        self._log("INFO", "Task created", id=entry_id, name=name)
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}
    
    def get(self, entry_id: str) -> Optional[TaskEntry]:
        return self._items.get(entry_id)
    
    def get_by_name(self, name: str) -> Optional[TaskEntry]:
        for entry in self._items.values():
            if entry.name == name:
                return entry
        return None
    
    def list_all(self) -> List[TaskEntry]:
        return list(self._items.values())
    
    def list_all_dict(self) -> List[dict]:
        return [entry.to_dict() for entry in self._items.values()]
    
    def delete(self, entry_id: str) -> dict:
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
    
    def load_from_db(self) -> int:
        db = NB(TASK_TABLE)
        count = 0
        
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
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "reason": prep.get("reason"),
                        "error": prep.get("error"),
                    })
                    continue
                
                result = entry.start()
                
                if result.get("success"):
                    restored_count += 1
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": True,
                        "reason": prep.get("reason"),
                    })
                else:
                    failed_count += 1
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "error": result.get("error"),
                    })
                    
            except Exception as e:
                failed_count += 1
                results.append({
                    "entry_id": entry.id,
                    "entry_name": entry.name,
                    "success": False,
                    "error": str(e),
                })
        
        self._log(
            "INFO",
            "Restore running states finished",
            restored=restored_count,
            failed=failed_count,
        )
        
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
            info.append({
                "id": entry.id,
                "name": entry.name,
                "was_running": entry.was_running,
                "can_recover": prep.get("can_recover"),
                "reason": prep.get("reason"),
                "compile_error": entry.compile_error,
            })
        return info
    
    def get_stats(self) -> dict:
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
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[{ts}][TaskManager][{level}] {message} | {extra_str}")


_task_manager: Optional[TaskManager] = None
_task_manager_lock = threading.Lock()


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        with _task_manager_lock:
            if _task_manager is None:
                _task_manager = TaskManager()
    return _task_manager
