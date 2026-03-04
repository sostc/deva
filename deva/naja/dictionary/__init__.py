"""Dictionary V2 - 基于 RecoverableUnit 抽象"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB

from ..common.recoverable import (
    RecoverableUnit,
    UnitMetadata,
    UnitState,
    UnitStatus,
)


DICT_ENTRY_TABLE = "naja_dictionary_entries"
DICT_PAYLOAD_TABLE = "naja_dictionary_payloads"


@dataclass
class DictionaryMetadata(UnitMetadata):
    """字典元数据"""
    dict_type: str = "dimension"
    schedule_type: str = "interval"
    interval_seconds: int = 300
    daily_time: str = "03:00"


@dataclass
class DictionaryState(UnitState):
    """字典状态"""
    last_status: str = ""
    last_update_ts: float = 0
    payload_key: str = ""
    data_size_bytes: int = 0
    
    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "last_status": self.last_status,
            "last_update_ts": self.last_update_ts,
            "payload_key": self.payload_key,
            "data_size_bytes": self.data_size_bytes,
        })
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
    
    def _do_start(self, func: Callable) -> dict:
        try:
            schedule_type = getattr(self._metadata, "schedule_type", "interval")
            
            if schedule_type == "daily":
                self._schedule_daily(func)
            else:
                self._schedule_interval(func)
            
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _do_stop(self) -> dict:
        if self._thread and hasattr(self._thread, 'cancel'):
            self._thread.cancel()
        return {"success": True}
    
    def _schedule_interval(self, func: Callable):
        """间隔调度"""
        interval = getattr(self._metadata, "interval_seconds", 300) or 300
        
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
    
    def _schedule_daily(self, func: Callable):
        """每日定时调度"""
        interval = getattr(self._metadata, "interval_seconds", 300) or 300
        
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
    
    def _execute_once(self, func: Callable):
        """执行一次"""
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
            
            self._save_payload(data)
            self._state.last_status = "success"
            self._state.last_update_ts = time.time()
            self._log("INFO", "fetch_data executed", id=self.id)
            
        except Exception as e:
            self._state.last_status = "error"
            self._state.record_error(str(e))
            self._log("ERROR", "fetch_data failed", id=self.id, error=str(e))
        
        self.save()
    
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
        metadata = DictionaryMetadata(
            id=metadata_data.get("id", ""),
            name=metadata_data.get("name", "unnamed"),
            description=metadata_data.get("description", ""),
            tags=metadata_data.get("tags", []),
            dict_type=metadata_data.get("dict_type", "dimension"),
            schedule_type=metadata_data.get("schedule_type", "interval"),
            interval_seconds=metadata_data.get("interval_seconds", 300),
            daily_time=metadata_data.get("daily_time", "03:00"),
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
    
    def create(
        self,
        name: str,
        func_code: str,
        schedule_type: str = "interval",
        interval_seconds: int = None,
        daily_time: str = None,
        description: str = "",
        tags: List[str] = None,
    ) -> dict:
        from ..config import get_dictionary_config
        
        import hashlib
        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]
        
        # 使用配置默认值
        dict_config = get_dictionary_config()
        if interval_seconds is None:
            interval_seconds = dict_config.get("default_interval", 300)
        if daily_time is None:
            daily_time = dict_config.get("default_daily_time", "03:00")
        
        if "fetch_data" not in func_code:
            return {"success": False, "error": "代码必须包含 fetch_data 函数"}
        
        metadata = DictionaryMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            schedule_type=schedule_type,
            interval_seconds=interval_seconds,
            daily_time=daily_time,
        )
        
        entry = DictionaryEntry(metadata=metadata)
        entry._func_code = func_code
        
        result = entry.compile_code()
        if not result["success"]:
            return {"success": False, "error": f"编译失败: {result['error']}"}
        
        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"字典名称已存在: {name}"}
            self._items[entry_id] = entry
        
        entry.save()
        
        self._log("INFO", "Dictionary created", id=entry_id, name=name)
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
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "reason": prep.get("reason"),
                    })
                    continue
                
                result = entry.start()
                
                if result.get("success"):
                    restored_count += 1
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": True,
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
            info.append({
                "id": entry.id,
                "name": entry.name,
                "was_running": entry.was_running,
                "can_recover": prep.get("can_recover"),
                "reason": prep.get("reason"),
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
