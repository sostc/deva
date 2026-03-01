"""DataSource V2 - 基于 RecoverableUnit 抽象

统一状态保存恢复与执行函数恢复的数据源实现。
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
import traceback
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


DS_TABLE = "data_sources_v2"
DS_LATEST_DATA_TABLE = "ds_v2_latest_data"
DS_CODE_VERSION_TABLE = "ds_v2_code_versions"


@dataclass
class DataSourceMetadata(UnitMetadata):
    """数据源元数据"""
    source_type: str = "custom"
    config: Dict[str, Any] = field(default_factory=dict)
    interval: float = 5.0
    description: str = ""


@dataclass
class DataSourceState(UnitState):
    """数据源状态"""
    last_data_ts: float = 0
    total_emitted: int = 0
    emit_rate: float = 0.0
    pid: int = 0


class DataSourceEntry(RecoverableUnit):
    """数据源条目
    
    基于 RecoverableUnit 抽象的数据源实现。
    支持：
    - 定时执行 fetch_data 函数
    - 数据流输出
    - 状态持久化与恢复
    """
    
    _instances: Dict[str, "DataSourceEntry"] = {}
    _instances_lock = threading.Lock()
    
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
        """获取输出流"""
        return self._stream
    
    def get_latest_data(self) -> Any:
        """获取最新数据"""
        return self._latest_data
    
    def get_recent_data(self, count: int = 1) -> List[Any]:
        """获取最近的数据"""
        if self._stream is None:
            return []
        
        try:
            cache = getattr(self._stream, "_cache", [])
            return cache[-count:] if cache else []
        except Exception:
            return []
    
    def update_config(
        self,
        name: str = None,
        description: str = None,
        interval: float = None,
        func_code: str = None,
        config: dict = None,
    ) -> dict:
        """更新配置"""
        if name is not None:
            self._metadata.name = name
        if description is not None:
            self._metadata.description = description
        if interval is not None:
            self._metadata.interval = max(0.1, float(interval))
        if config is not None:
            self._metadata.config = config
        
        if func_code is not None:
            if self._get_func_name() not in func_code:
                return {"success": False, "error": f"代码必须包含 {self._get_func_name()} 函数"}
            
            old_code = self._func_code
            self._func_code = func_code
            self._compiled_func = None
            
            result = self.compile_code()
            if not result["success"]:
                self._func_code = old_code
                return result
            
            self._save_code_version(func_code, old_code)
        
        self.save()
        return {"success": True}
    
    def _save_code_version(self, new_code: str, old_code: str):
        """保存代码版本"""
        try:
            db = NB(DS_CODE_VERSION_TABLE)
            version_key = f"{self.id}_{int(time.time() * 1000)}"
            db[version_key] = {
                "id": self.id,
                "name": self.name,
                "new_code": new_code,
                "old_code": old_code,
                "timestamp": time.time(),
            }
        except Exception:
            pass
    
    def save(self) -> dict:
        try:
            db = NB(DS_TABLE)
            db[self.id] = self.to_dict()
            self._save_latest_data()
            return {"success": True, "id": self.id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _save_latest_data(self):
        """保存最新数据"""
        if self._latest_data is not None:
            try:
                db = NB(DS_LATEST_DATA_TABLE)
                db[f"{self.id}_latest"] = {
                    "id": self.id,
                    "name": self.name,
                    "data": self._latest_data,
                    "timestamp": time.time(),
                }
            except Exception:
                pass
    
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
        
        saved_status = state_data.get("status", UnitStatus.STOPPED.value)
        entry._was_running = (saved_status == UnitStatus.RUNNING.value)
        entry._state.status = UnitStatus.STOPPED.value
        
        return entry


class DataSourceManager:
    """数据源管理器 V2
    
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
        self._items: Dict[str, DataSourceEntry] = {}
        self._items_lock = threading.Lock()
        self._initialized = True
    
    def create(
        self,
        name: str,
        func_code: str,
        interval: float = 5.0,
        description: str = "",
        config: dict = None,
        tags: List[str] = None,
    ) -> dict:
        import hashlib
        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]
        
        if "fetch_data" not in func_code:
            return {"success": False, "error": "代码必须包含 fetch_data 函数"}
        
        metadata = DataSourceMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            interval=interval,
            config=config or {},
        )
        
        entry = DataSourceEntry(metadata=metadata)
        entry._func_code = func_code
        
        result = entry.compile_code()
        if not result["success"]:
            return {"success": False, "error": f"编译失败: {result['error']}"}
        
        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"数据源名称已存在: {name}"}
            self._items[entry_id] = entry
        
        entry.save()
        
        self._log("INFO", "DataSource created", id=entry_id, name=name)
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
        
        return {
            "total": len(entries),
            "running": running,
            "stopped": len(entries) - running,
        }
    
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
