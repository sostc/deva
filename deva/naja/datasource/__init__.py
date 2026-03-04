"""DataSource V2 - 基于 RecoverableUnit 抽象"""

from __future__ import annotations

import asyncio
import os
import sys
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

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "last_data_ts": self.last_data_ts,
            "total_emitted": self.total_emitted,
            "pid": self.pid,
        })
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "DataSourceState":
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
            last_data_ts=data.get("last_data_ts", 0),
            total_emitted=data.get("total_emitted", 0),
            pid=data.get("pid", 0),
        )


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

            if source_type == "file":
                return self._start_file_source(func)

            if source_type == "directory":
                return self._start_directory_source(func)

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

    def _start_file_source(self, func: Callable) -> dict:
        """启动文件监控数据源"""
        config = getattr(self._metadata, "config", {}) or {}
        file_path = config.get("file_path")

        if not file_path:
            return {"success": False, "error": "缺少文件路径配置"}

        poll_interval = float(config.get("poll_interval", 0.1) or 0.1)
        delimiter = config.get("delimiter", "\n") or "\n"
        read_mode = config.get("read_mode", "tail")

        # 处理转义的分隔符
        if delimiter == "\\n":
            delimiter = "\n"
        elif delimiter == "\\t":
            delimiter = "\t"
        elif delimiter == "\\r":
            delimiter = "\r"
        elif delimiter == "\\r\\n":
            delimiter = "\r\n"

        def file_watch_loop():
            try:
                self._log("INFO", f"开始监控文件 {file_path}")

                import os

                if not os.path.exists(file_path):
                    self._log("ERROR", f"文件不存在: {file_path}")
                    self._state.record_error(f"文件不存在: {file_path}")
                    self._state.status = UnitStatus.ERROR.value
                    self.save()
                    return

                file_obj = open(file_path, 'r', encoding='utf-8', errors='replace')

                if read_mode == "tail":
                    file_obj.seek(0, 2)

                buffer = ""
                last_size = 0

                while not self._stop_event.is_set():
                    try:
                        current_size = os.path.getsize(file_path)

                        if read_mode == "full":
                            file_obj.seek(0)
                            content = file_obj.read()
                            if content:
                                data = func(content)
                                if data is not None:
                                    self._emit_data(data)
                                    self._state.last_data_ts = time.time()
                                    self._state.total_emitted += 1
                                    self._latest_data = data
                        else:
                            if current_size < last_size:
                                self._log("INFO", "文件被截断，重新从头开始")
                                file_obj.seek(0)
                                buffer = ""

                            last_size = current_size

                            new_content = file_obj.read()
                            if new_content:
                                buffer += new_content

                                if delimiter in buffer:
                                    parts = buffer.split(delimiter)
                                    buffer = parts.pop(-1)

                                    for part in parts:
                                        if part.strip():
                                            full_line = part + delimiter
                                            data = func(full_line)
                                            if data is not None:
                                                self._emit_data(data)
                                                self._state.last_data_ts = time.time()
                                                self._state.total_emitted += 1
                                                self._latest_data = data

                        if self._stop_event.wait(timeout=poll_interval):
                            break

                    except FileNotFoundError:
                        self._log("WARN", f"文件暂时不可用: {file_path}")
                        if self._stop_event.wait(timeout=1.0):
                            break
                    except Exception as e:
                        self._log("ERROR", "读取文件时出错", error=str(e))
                        if self._stop_event.wait(timeout=1.0):
                            break

                file_obj.close()
                self._log("INFO", "文件监控停止")

            except Exception as e:
                self._state.record_error(str(e))
                self._log("ERROR", "文件监控错误", error=str(e))
            finally:
                self._state.status = UnitStatus.STOPPED.value
                self.save()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=file_watch_loop,
            daemon=True,
            name=f"ds-file-{self.id[:8]}",
        )
        self._thread.start()

        self._state.pid = os.getpid()

        return {"success": True}

    def _start_directory_source(self, func: Callable) -> dict:
        """启动目录监控数据源"""
        config = getattr(self._metadata, "config", {}) or {}
        directory_path = config.get("directory_path")

        if not directory_path:
            return {"success": False, "error": "缺少目录路径配置"}

        poll_interval = float(config.get("poll_interval", 1.0) or 1.0)
        file_pattern = config.get("file_pattern", "*") or "*"
        recursive = config.get("recursive", False)
        watch_events = config.get("watch_events", ["created", "modified", "deleted"]) or [
            "created", "modified", "deleted"]

        def directory_watch_loop():
            try:
                import os
                from pathlib import Path

                self._log("INFO", f"开始监控目录 {directory_path}")

                if not os.path.exists(directory_path):
                    self._log("ERROR", f"目录不存在: {directory_path}")
                    self._state.record_error(f"目录不存在: {directory_path}")
                    self._state.status = UnitStatus.ERROR.value
                    self.save()
                    return

                if not os.path.isdir(directory_path):
                    self._log("ERROR", f"路径不是目录: {directory_path}")
                    self._state.record_error(f"路径不是目录: {directory_path}")
                    self._state.status = UnitStatus.ERROR.value
                    self.save()
                    return

                # 检查目录访问权限
                if not os.access(directory_path, os.R_OK):
                    error_msg = f"没有目录读取权限: {directory_path}"
                    if sys.platform == 'darwin':
                        error_msg += "。macOS 用户: 请在「系统偏好设置 > 安全性与隐私 > 隐私 > 完全磁盘访问权限」中添加运行 Web 服务的终端应用。"
                    self._log("ERROR", error_msg)
                    self._state.record_error(error_msg)
                    self._state.status = UnitStatus.ERROR.value
                    self.save()
                    return

                def get_files():
                    """获取目录中的文件列表"""
                    files = {}
                    base_path = Path(directory_path)
                    
                    if recursive:
                        pattern = f"**/{file_pattern}"
                    else:
                        pattern = file_pattern
                    
                    try:
                        for file_path in base_path.glob(pattern):
                            if file_path.is_file():
                                try:
                                    stat = file_path.stat()
                                    files[str(file_path)] = {
                                        "path": str(file_path),
                                        "name": file_path.name,
                                        "size": stat.st_size,
                                        "mtime": stat.st_mtime,
                                    }
                                except (PermissionError, OSError):
                                    pass
                    except PermissionError:
                        self._log("WARN", f"权限不足，无法扫描目录: {directory_path}")
                    
                    return files

                last_files = get_files()

                while not self._stop_event.is_set():
                    try:
                        current_files = get_files()

                        current_paths = set(current_files.keys())
                        last_paths = set(last_files.keys())

                        added = current_paths - last_paths
                        removed = last_paths - current_paths
                        common = current_paths & last_paths

                        events = []

                        if "created" in watch_events:
                            for path in added:
                                events.append({
                                    "event": "created",
                                    "path": path,
                                    "file_info": current_files[path],
                                })

                        if "deleted" in watch_events:
                            for path in removed:
                                events.append({
                                    "event": "deleted",
                                    "path": path,
                                    "file_info": last_files[path],
                                })

                        if "modified" in watch_events:
                            for path in common:
                                current_info = current_files[path]
                                last_info = last_files[path]

                                if (current_info["size"] != last_info["size"] or
                                        current_info["mtime"] != last_info["mtime"]):
                                    events.append({
                                        "event": "modified",
                                        "path": path,
                                        "file_info": current_files[path],
                                        "old_info": last_info,
                                    })

                        for event in events:
                            data = func(event)
                            if data is not None:
                                self._emit_data(data)
                                self._state.last_data_ts = time.time()
                                self._state.total_emitted += 1
                                self._latest_data = data

                        last_files = current_files

                        if events:
                            self.save()

                        if self._stop_event.wait(timeout=poll_interval):
                            break

                    except Exception as e:
                        self._log("ERROR", "扫描目录时出错", error=str(e))
                        if self._stop_event.wait(timeout=1.0):
                            break

                self._log("INFO", "目录监控停止")

            except Exception as e:
                self._state.record_error(str(e))
                self._log("ERROR", "目录监控错误", error=str(e))
            finally:
                self._state.status = UnitStatus.STOPPED.value
                self.save()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=directory_watch_loop,
            daemon=True,
            name=f"ds-dir-{self.id[:8]}",
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
                    if asyncio.iscoroutine(data):
                        if self._event_loop is None or self._event_loop.is_closed():
                            self._event_loop = asyncio.new_event_loop()
                        data = self._event_loop.run_until_complete(data)

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
        interval: float = None,
        description: str = "",
        tags: List[str] = None,
        source_type: str = "custom",
        config: dict = None,
    ) -> dict:
        from ..config import get_datasource_config

        import hashlib
        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

        # 使用配置默认值
        ds_config = get_datasource_config()
        if interval is None:
            interval = ds_config.get("default_interval", 5.0)

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
