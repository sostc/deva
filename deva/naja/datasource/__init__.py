"""DataSource V2 - 基于 RecoverableUnit 抽象"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB
from deva.core.namespace import NS

from ..common.recoverable import (
    RecoverableUnit,
    UnitMetadata,
    UnitState,
    UnitStatus,
)


DS_TABLE = "naja_datasources"
DS_LATEST_DATA_TABLE = "naja_ds_latest_data"


@dataclass
class DataSourceMetadata(UnitMetadata):
    """数据源元数据"""
    source_type: str = "custom"
    config: Dict[str, Any] = field(default_factory=dict)
    interval: float = 5.0


@dataclass
class DataSourceState(UnitState):
    """数据源状态"""
    last_data_ts: float = 0
    total_emitted: int = 0
    pid: int = 0


class DataSourceEntry(RecoverableUnit):
    """数据源条目"""
    
    def __init__(
        self,
        metadata: DataSourceMetadata = None,
        state: DataSourceState = None,
    ):
        super().__init__(
            metadata=metadata or DataSourceMetadata(),
            state=state or DataSourceState(),
        )
        
        self._stream: Optional[Any] = None
        self._latest_data: Any = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
    
    def _get_func_name(self) -> str:
        return "fetch_data"
    
    def start(self) -> dict:
        """启动数据源，replay 类型不需要编译代码"""
        source_type = getattr(self._metadata, "source_type", "custom") or "custom"
        
        if source_type == "replay":
            import threading
            import time
            
            with self._execution_lock:
                if self.is_running:
                    return {"success": True, "message": "Already running"}
                
                try:
                    self._state.status = UnitStatus.INITIALIZING.value
                    self._stop_event.clear()
                    
                    start_result = self._start_replay_source()
                    if not start_result["success"]:
                        self._state.status = UnitStatus.ERROR.value
                        self._state.record_error(start_result.get("error", "Unknown error"))
                        self.save()
                        return start_result
                    
                    self._state.status = UnitStatus.RUNNING.value
                    self._state.start_time = time.time()
                    self._was_running = True
                    self.save()
                    
                    self._log("INFO", "Unit started", id=self.id, name=self.name)
                    return {"success": True, "status": self._state.status}
                    
                except Exception as e:
                    self._state.status = UnitStatus.ERROR.value
                    self._state.record_error(str(e))
                    self.save()
                    self._log("ERROR", "Start failed", id=self.id, error=str(e))
                    return {"success": False, "error": str(e)}
        
        return super().start()
    
    def _do_compile(self, code: str) -> Callable:
        env = self._build_execution_env()
        exec(code, env)
        
        func = env.get(self._get_func_name())
        if not func or not callable(func):
            raise ValueError(f"函数 '{self._get_func_name()}' 未在代码中定义")
        
        return func
    
    def _do_start(self, func: Callable) -> dict:
        try:
            source_type = getattr(self._metadata, "source_type", "custom") or "custom"
            
            if source_type == "replay":
                return self._start_replay_source()
            
            self._event_loop = asyncio.new_event_loop()
            
            self._thread = threading.Thread(
                target=self._worker_loop,
                args=[func],
                daemon=True,
                name=f"ds-{self.id[:8]}",
            )
            self._thread.start()
            
            self._state.pid = os.getpid()
            
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _start_replay_source(self) -> dict:
        """启动回放数据源"""
        config = getattr(self._metadata, "config", {}) or {}
        table_name = config.get("table_name")
        
        if not table_name:
            return {"success": False, "error": "缺少回放表名配置"}
        
        start_time = config.get("start_time")
        end_time = config.get("end_time")
        interval = float(config.get("interval", 1.0) or 1.0)
        
        def replay_loop():
            try:
                self._log("INFO", f"开始回放表 {table_name}")
                
                db_stream = NB(table_name, key_mode='time')
                
                if start_time is None and end_time is None:
                    keys = list(db_stream.keys())
                else:
                    keys = list(db_stream[start_time:end_time])
                
                self._log("INFO", f"找到 {len(keys)} 条数据")
                
                for key in keys:
                    if self._stop_event.is_set():
                        self._log("INFO", "回放被手动停止")
                        break
                    
                    try:
                        data = db_stream.get(key)
                        if data is not None:
                            self._emit_data(data)
                            self._state.last_data_ts = time.time()
                            self._state.total_emitted += 1
                            self._latest_data = data
                        
                        if interval > 0:
                            if self._stop_event.wait(timeout=interval):
                                self._log("INFO", "回放被手动停止")
                                break
                    except Exception as e:
                        self._log("ERROR", f"处理数据 {key} 时出错", error=str(e))
                        
            except Exception as e:
                self._state.record_error(str(e))
                self._log("ERROR", "回放错误", error=str(e))
            finally:
                self._log("INFO", "回放完成，自动停止数据源")
                self._stop_event.set()
                self._state.status = UnitStatus.STOPPED.value
                self.save()
        
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=replay_loop,
            daemon=True,
            name=f"ds-replay-{self.id[:8]}",
        )
        self._thread.start()
        
        self._state.pid = os.getpid()
        
        return {"success": True}
    
    def _do_stop(self) -> dict:
        try:
            if self._event_loop and not self._event_loop.is_closed():
                self._event_loop.call_soon_threadsafe(self._event_loop.stop)
            
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _worker_loop(self, func: Callable):
        """工作线程循环"""
        is_async = asyncio.iscoroutinefunction(func)
        
        while not self._stop_event.is_set():
            try:
                if is_async:
                    if self._event_loop is None or self._event_loop.is_closed():
                        self._event_loop = asyncio.new_event_loop()
                    data = self._event_loop.run_until_complete(func())
                else:
                    data = func()
                
                if data is not None:
                    self._emit_data(data)
                    self._state.last_data_ts = time.time()
                    self._state.total_emitted += 1
                    self._latest_data = data
                    
            except Exception as e:
                self._state.record_error(str(e))
                self._log("ERROR", "fetch_data failed", error=str(e))
            
            interval = getattr(self._metadata, "interval", 5.0) or 5.0
            self._stop_event.wait(interval)
        
        if self._event_loop and not self._event_loop.is_closed():
            self._event_loop.close()
    
    def _emit_data(self, data: Any):
        """发送数据到流"""
        try:
            if self._stream is None:
                self._stream = NS(
                    self.name,
                    cache_max_len=10,
                    cache_max_age_seconds=3600,
                    description=f"DataSource {self.name} output",
                )
            
            if hasattr(self._stream, "emit"):
                self._stream.emit(data)
                
        except Exception as e:
            self._log("ERROR", "emit data failed", error=str(e))
    
    def get_stream(self) -> Optional[Any]:
        """获取输出流，确保流存在"""
        if self._stream is None:
            self._stream = NS(
                self.name,
                cache_max_len=10,
                cache_max_age_seconds=3600,
                description=f"DataSource {self.name} output",
            )
        return self._stream
    
    def get_latest_data(self) -> Any:
        return self._latest_data
    
    def update_config(
        self,
        name: str = None,
        interval: float = None,
        func_code: str = None,
        source_type: str = None,
        config: dict = None,
        description: str = None,
    ) -> dict:
        if name is not None:
            self._metadata.name = name
        if interval is not None:
            self._metadata.interval = max(0.1, float(interval))
        if source_type is not None:
            self._metadata.source_type = source_type
        if config is not None:
            self._metadata.config = config
        if description is not None:
            self._metadata.description = description
        
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
            db = NB(DS_TABLE)
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
                "source_type": getattr(self._metadata, "source_type", "custom"),
                "config": getattr(self._metadata, "config", {}),
                "interval": getattr(self._metadata, "interval", 5.0),
                "created_at": self._metadata.created_at,
                "updated_at": self._metadata.updated_at,
            },
            "state": self._state.to_dict(),
            "func_code": self._func_code,
            "was_running": self._was_running,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DataSourceEntry":
        metadata_data = data.get("metadata", {})
        metadata = DataSourceMetadata(
            id=metadata_data.get("id", ""),
            name=metadata_data.get("name", "unnamed"),
            description=metadata_data.get("description", ""),
            tags=metadata_data.get("tags", []),
            source_type=metadata_data.get("source_type", "custom"),
            config=metadata_data.get("config", {}),
            interval=metadata_data.get("interval", 5.0),
            created_at=metadata_data.get("created_at", time.time()),
            updated_at=metadata_data.get("updated_at", time.time()),
        )
        
        state_data = data.get("state", {})
        state = DataSourceState.from_dict(state_data)
        
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


class DataSourceManager:
    """数据源管理器"""
    
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
        self._items: Dict[str, DataSourceEntry] = {}
        self._items_lock = threading.Lock()
        self._initialized = True
    
    def create(
        self,
        name: str,
        func_code: str = "",
        interval: float = 5.0,
        description: str = "",
        tags: List[str] = None,
        source_type: str = "custom",
        config: dict = None,
    ) -> dict:
        import hashlib
        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]
        
        if source_type == "custom" and func_code and "fetch_data" not in func_code:
            return {"success": False, "error": "代码必须包含 fetch_data 函数"}
        
        if source_type == "replay":
            if not config or not config.get("table_name"):
                return {"success": False, "error": "回放数据源必须指定表名"}
        
        metadata = DataSourceMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            interval=interval,
            source_type=source_type,
            config=config or {},
        )
        
        entry = DataSourceEntry(metadata=metadata)
        entry._func_code = func_code
        
        if func_code:
            result = entry.compile_code()
            if not result["success"]:
                return {"success": False, "error": f"编译失败: {result['error']}"}
        
        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"数据源名称已存在: {name}"}
            self._items[entry_id] = entry
        
        entry.save()
        
        self._log("INFO", "DataSource created", id=entry_id, name=name, source_type=source_type)
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}
    
    def get(self, entry_id: str) -> Optional[DataSourceEntry]:
        return self._items.get(entry_id)
    
    def get_by_name(self, name: str) -> Optional[DataSourceEntry]:
        for entry in self._items.values():
            if entry.name == name:
                return entry
        return None
    
    def list_all(self) -> List[DataSourceEntry]:
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
        
        db = NB(DS_TABLE)
        if entry_id in db:
            del db[entry_id]
        
        self._log("INFO", "DataSource deleted", id=entry_id, name=entry.name)
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
    
    def load_from_db(self) -> int:
        db = NB(DS_TABLE)
        count = 0
        
        with self._items_lock:
            self._items.clear()
            
            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue
                
                try:
                    entry = DataSourceEntry.from_dict(data)
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
        error = sum(1 for e in entries if e._state.error_count > 0)
        
        return {
            "total": len(entries),
            "running": running,
            "stopped": len(entries) - running,
            "error": error,
        }
    
    def start_all(self) -> dict:
        success = 0
        failed = 0
        skipped = 0
        
        for entry in self.list_all():
            if entry.is_running:
                skipped += 1
                continue
            
            result = entry.start()
            if result.get("success"):
                success += 1
            else:
                failed += 1
        
        return {"success": success, "failed": failed, "skipped": skipped}
    
    def stop_all(self) -> dict:
        success = 0
        failed = 0
        skipped = 0
        
        for entry in self.list_all():
            if not entry.is_running:
                skipped += 1
                continue
            
            result = entry.stop()
            if result.get("success"):
                success += 1
            else:
                failed += 1
        
        return {"success": success, "failed": failed, "skipped": skipped}
    
    def _log(self, level: str, message: str, **extra):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[{ts}][DataSourceManager][{level}] {message} | {extra_str}")


_ds_manager: Optional[DataSourceManager] = None
_ds_manager_lock = threading.Lock()


def get_datasource_manager() -> DataSourceManager:
    global _ds_manager
    if _ds_manager is None:
        with _ds_manager_lock:
            if _ds_manager is None:
                _ds_manager = DataSourceManager()
    return _ds_manager
