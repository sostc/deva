"""数据字典模块 V2 (Data Dictionary Module V2)

基于 RecoverableUnit 基类重构的数据字典实现。
统一状态保存恢复与执行函数恢复。

================================================================================
架构设计
================================================================================

【核心概念】
┌─────────────────────────────────────────────────────────────────────────────┐
│  DictionaryEntry (数据字典条目)                                              │
│  ├── 继承: RecoverableUnit                                                  │
│  ├── 调度: interval (间隔) / daily (每日定时)                                │
│  ├── 执行: fetch_data() 函数                                                │
│  └── 数据存储: payload_db                                                   │
│                                                                             │
│  DictionaryManager (数据字典管理器)                                          │
│  ├── 继承: BaseManager                                                      │
│  ├── 持久化: NB("dictionary_entries_v2")                                    │
│  └── 恢复: load_from_db() + restore_running_states()                        │
└─────────────────────────────────────────────────────────────────────────────┘

"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from deva import NB

from ..common.recoverable import (
    RecoverableUnit,
    UnitMetadata,
    UnitState,
    UnitStatus,
    recovery_manager,
)


DICT_ENTRY_TABLE = "dictionary_entries_v2"
DICT_PAYLOAD_TABLE = "dictionary_payloads_v2"


@dataclass
class DictionaryMetadata(UnitMetadata):
    """数据字典元数据"""
    dict_type: str = "custom"
    schedule_type: str = "interval"
    interval_seconds: int = 300
    daily_time: str = "03:00"
    retention: int = 1
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "dict_type": self.dict_type,
            "schedule_type": self.schedule_type,
            "interval_seconds": self.interval_seconds,
            "daily_time": self.daily_time,
            "retention": self.retention,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "DictionaryMetadata":
        if isinstance(data, cls):
            return data
        base = super().from_dict(data)
        return cls(
            id=base.id,
            name=base.name,
            description=base.description,
            tags=base.tags,
            created_at=base.created_at,
            updated_at=base.updated_at,
            dict_type=data.get("dict_type", "custom"),
            schedule_type=data.get("schedule_type", "interval"),
            interval_seconds=data.get("interval_seconds", 300),
            daily_time=data.get("daily_time", "03:00"),
            retention=data.get("retention", 1),
        )


@dataclass
class DictionaryState(UnitState):
    """数据字典状态"""
    last_update_ts: float = 0
    last_status: str = "never"
    data_size_bytes: int = 0
    payload_key: str = ""
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "last_update_ts": self.last_update_ts,
            "last_status": self.last_status,
            "data_size_bytes": self.data_size_bytes,
            "payload_key": self.payload_key,
        })
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "DictionaryState":
        if isinstance(data, cls):
            return data
        base = super().from_dict(data)
        return cls(
            status=base.status,
            start_time=base.start_time,
            last_activity_ts=base.last_activity_ts,
            error_count=base.error_count,
            last_error=base.last_error,
            last_error_ts=base.last_error_ts,
            run_count=base.run_count,
            last_update_ts=data.get("last_update_ts", 0),
            last_status=data.get("last_status", "never"),
            data_size_bytes=data.get("data_size_bytes", 0),
            payload_key=data.get("payload_key", ""),
        )


class DictionaryEntry(RecoverableUnit):
    """数据字典条目
    
    继承 RecoverableUnit，实现统一的状态保存恢复与执行函数恢复。
    
    特性:
    - 支持间隔调度 (interval) 和每日定时调度 (daily)
    - 执行 fetch_data() 函数获取数据
    - 数据存储到 payload_db
    - 系统启动后自动恢复运行状态
    """
    
    def __init__(
        self,
        metadata: DictionaryMetadata = None,
        state: DictionaryState = None,
        func_code: str = "",
    ):
        super().__init__(
            metadata=metadata or DictionaryMetadata(),
            state=state or DictionaryState(),
        )
        
        self._metadata: DictionaryMetadata = self._metadata
        self._state: DictionaryState = self._state
        
        self._func_code = func_code
        self._payload_db = NB(DICT_PAYLOAD_TABLE)
        
        if not self._state.payload_key:
            self._state.payload_key = f"{self.id}:latest"
    
    def _get_func_name(self) -> str:
        return "fetch_data"
    
    def _do_compile(self, code: str) -> Callable:
        env = self._build_execution_env()
        local_vars: Dict[str, Any] = {}
        
        exec(code, env, local_vars)
        
        func = local_vars.get(self._get_func_name())
        if not func or not callable(func):
            raise ValueError(f"函数 '{self._get_func_name()}' 未在代码中定义")
        
        func.__globals__.update(local_vars)
        
        return func
    
    def save(self) -> dict:
        try:
            db = NB(DICT_ENTRY_TABLE)
            self._metadata.touch()
            db[self.id] = self.to_dict()
            return {"success": True, "id": self.id}
        except Exception as e:
            self._log("ERROR", "Save failed", id=self.id, error=str(e))
            return {"success": False, "error": str(e)}
    
    def to_dict(self) -> dict:
        return {
            "metadata": self._metadata.to_dict(),
            "state": self._state.to_dict(),
            "func_code": self._func_code,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DictionaryEntry":
        metadata = DictionaryMetadata.from_dict(data.get("metadata", {}))
        state = DictionaryState.from_dict(data.get("state", {}))
        func_code = data.get("func_code", "")
        
        entry = cls(
            metadata=metadata,
            state=state,
            func_code=func_code,
        )
        
        saved_status = state.status
        entry._was_running = (saved_status == UnitStatus.RUNNING.value)
        entry._state.status = UnitStatus.STOPPED.value
        
        if func_code:
            entry.compile_code()
        
        return entry
    
    def _do_start(self, func: Callable) -> dict:
        self._thread = threading.Thread(
            target=self._worker_loop,
            args=[func],
            daemon=True,
            name=f"dict_{self.id}",
        )
        self._thread.start()
        return {"success": True}
    
    def _do_stop(self) -> dict:
        return {"success": True}
    
    def _worker_loop(self, func: Callable):
        while not self._stop_event.is_set():
            try:
                self._execute_once(func)
            except Exception as e:
                self._log("ERROR", "Execute failed", id=self.id, error=str(e))
                self._state.record_error(str(e))
                self.save()
            
            wait_seconds = self._calculate_wait_seconds()
            if self._stop_event.wait(timeout=wait_seconds):
                break
    
    def _execute_once(self, func: Callable):
        start_ts = time.time()
        
        self._state.last_status = "running"
        self.save()
        
        self._log("INFO", "Execute started", id=self.id, name=self.name)
        
        try:
            data = func()
            
            self._payload_db[self._state.payload_key] = {
                "ts": time.time(),
                "data": data,
                "entry_id": self.id,
                "entry_name": self.name,
            }
            
            self._state.last_update_ts = time.time()
            self._state.last_status = "success"
            self._state.last_error = ""
            self._state.record_success()
            self._state.data_size_bytes = self._estimate_size(data)
            self._metadata.touch()
            self.save()
            
            cost_ms = int((time.time() - start_ts) * 1000)
            self._log(
                "INFO",
                "Execute succeeded",
                id=self.id,
                name=self.name,
                cost_ms=cost_ms,
                size_bytes=self._state.data_size_bytes,
            )
            
        except Exception as e:
            self._state.last_status = "error"
            self._state.record_error(str(e))
            self.save()
            
            cost_ms = int((time.time() - start_ts) * 1000)
            self._log(
                "ERROR",
                "Execute failed",
                id=self.id,
                name=self.name,
                cost_ms=cost_ms,
                error=str(e),
            )
            raise
    
    def _calculate_wait_seconds(self) -> float:
        if self._metadata.schedule_type == "daily":
            return self._seconds_until_daily(self._metadata.daily_time)
        else:
            return float(max(5, self._metadata.interval_seconds))
    
    def _seconds_until_daily(self, hhmm: str) -> float:
        try:
            hour, minute = hhmm.split(":")
            hour_i = max(0, min(23, int(hour)))
            minute_i = max(0, min(59, int(minute)))
        except Exception:
            hour_i, minute_i = 3, 0
        
        now = datetime.now()
        target = now.replace(hour=hour_i, minute=minute_i, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        return max(1.0, (target - now).total_seconds())
    
    def _estimate_size(self, data: Any) -> int:
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                return int(data.memory_usage(index=True, deep=True).sum())
        except Exception:
            pass
        
        try:
            return len(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))
        except Exception:
            return len(str(data).encode("utf-8"))
    
    def get_payload(self) -> Any:
        payload = self._payload_db.get(self._state.payload_key)
        if isinstance(payload, dict):
            return payload.get("data")
        return None
    
    def get_payload_info(self) -> dict:
        payload = self._payload_db.get(self._state.payload_key)
        if isinstance(payload, dict):
            return {
                "ts": payload.get("ts"),
                "entry_id": payload.get("entry_id"),
                "entry_name": payload.get("entry_name"),
            }
        return {}
    
    def clear_payload(self) -> dict:
        try:
            if self._state.payload_key and self._state.payload_key in self._payload_db:
                del self._payload_db[self._state.payload_key]
            
            self._state.last_status = "cleared"
            self._state.last_update_ts = 0
            self._state.data_size_bytes = 0
            self.save()
            
            self._log("INFO", "Payload cleared", id=self.id, name=self.name)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def run_once(self) -> dict:
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
        schedule_type: str = None,
        interval_seconds: int = None,
        daily_time: str = None,
        func_code: str = None,
        enabled: bool = None,
    ) -> dict:
        if name is not None:
            self._metadata.name = name
        if description is not None:
            self._metadata.description = description
        if dict_type is not None:
            self._metadata.dict_type = dict_type
        if schedule_type is not None:
            self._metadata.schedule_type = schedule_type
        if interval_seconds is not None:
            self._metadata.interval_seconds = max(5, int(interval_seconds))
        if daily_time is not None:
            self._metadata.daily_time = daily_time
        if func_code is not None:
            if "def fetch_data" not in func_code:
                return {"success": False, "error": "代码必须包含 fetch_data 函数"}
            self._func_code = func_code
            self._compiled_func = None
            result = self.compile_code()
            if not result["success"]:
                return result
        
        self.save()
        
        if enabled is not None:
            if enabled:
                self.start()
            else:
                self.stop()
        
        return {"success": True}


class DictionaryManager:
    """数据字典管理器
    
    继承 BaseManager 的设计模式，提供统一的管理接口。
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
        if hasattr(self, '_initialized'):
            return
        
        self._items: Dict[str, DictionaryEntry] = {}
        self._items_lock = threading.Lock()
        self._initialized = True
        
        recovery_manager.register("dictionary", self)
    
    @classmethod
    def get_instance(cls) -> "DictionaryManager":
        return cls()
    
    def _new_id(self, name: str) -> str:
        return hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]
    
    def create(
        self,
        name: str,
        func_code: str,
        description: str = "",
        dict_type: str = "custom",
        schedule_type: str = "interval",
        interval_seconds: int = 300,
        daily_time: str = "03:00",
        enabled: bool = False,
    ) -> dict:
        if "def fetch_data" not in func_code:
            return {"success": False, "error": "代码必须包含 fetch_data 函数"}
        
        with self._items_lock:
            for entry in self._items.values():
                if entry.name == name:
                    return {"success": False, "error": f"数据字典名称已存在: {name}"}
            
            entry_id = self._new_id(name)
            metadata = DictionaryMetadata(
                id=entry_id,
                name=name,
                description=description,
                dict_type=dict_type,
                schedule_type=schedule_type,
                interval_seconds=max(5, int(interval_seconds)),
                daily_time=daily_time,
            )
            
            state = DictionaryState(
                payload_key=f"{entry_id}:latest",
            )
            
            entry = DictionaryEntry(
                metadata=metadata,
                state=state,
                func_code=func_code,
            )
            
            compile_result = entry.compile_code()
            if not compile_result["success"]:
                return {
                    "success": False,
                    "error": f"代码编译失败: {compile_result.get('error')}",
                }
            
            entry.save()
            self._items[entry_id] = entry
            
            self._log("INFO", "Dictionary created", id=entry_id, name=name)
        
        if enabled:
            entry.start()
        
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}
    
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
    
    def get_payload(self, entry_id: str) -> Any:
        entry = self.get(entry_id)
        if not entry:
            return None
        return entry.get_payload()
    
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
