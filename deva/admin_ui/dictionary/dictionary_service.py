"""Data Dictionary service for enrichment base datasets."""

from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from deva import NB


DICT_ENTRY_TABLE = "data_dictionary_entries"
DICT_PAYLOAD_TABLE = "data_dictionary_payloads"


@dataclass
class DictEntry:
    id: str
    name: str
    dict_type: str = "stock_basic_block"
    description: str = ""
    schedule_type: str = "interval"  # interval | daily
    interval_seconds: int = 300
    daily_time: str = "03:00"
    enabled: bool = False
    code: str = ""
    payload_table: str = DICT_PAYLOAD_TABLE
    payload_key: str = ""
    retention: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_update_ts: float = 0.0
    last_status: str = "never"
    last_error: str = ""
    run_count: int = 0
    data_size_bytes: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class DictionaryManager:
    """Manage dictionary entries and scheduled refresh tasks."""

    def __init__(self):
        self._items: Dict[str, DictEntry] = {}
        self._lock = threading.Lock()
        self._threads: Dict[str, threading.Thread] = {}
        self._stops: Dict[str, threading.Event] = {}
        self._run_threads: Dict[str, threading.Thread] = {}
        self._running: set[str] = set()

    def _log(self, level: str, message: str, **extra):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = " ".join([f"{k}={v}" for k, v in extra.items()])
        if details:
            print(f"[{ts}][DICT][{level}] {message} | {details}")
        else:
            print(f"[{ts}][DICT][{level}] {message}")

    def _entry_db(self):
        return NB(DICT_ENTRY_TABLE)

    def _payload_db(self):
        return NB(DICT_PAYLOAD_TABLE)

    def _save(self, entry: DictEntry):
        entry.updated_at = time.time()
        self._entry_db()[entry.id] = entry.to_dict()

    def _from_dict(self, data: dict) -> DictEntry:
        entry = DictEntry(id=data.get("id", ""), name=data.get("name", ""))
        for k, v in data.items():
            if hasattr(entry, k):
                setattr(entry, k, v)
        return entry

    def load_from_db(self) -> int:
        db = self._entry_db()
        count = 0
        with self._lock:
            self._items.clear()
            for _, raw in list(db.items()):
                if not isinstance(raw, dict):
                    continue
                entry = self._from_dict(raw)
                if not entry.id:
                    continue
                self._items[entry.id] = entry
                count += 1
        for entry in self.list_entries():
            if entry.enabled:
                self.start(entry.id)
        self._log("INFO", "load_from_db finished", count=count)
        return count

    def list_entries(self):
        with self._lock:
            return list(self._items.values())

    def get_entry(self, entry_id: str) -> Optional[DictEntry]:
        with self._lock:
            return self._items.get(entry_id)

    def get_entry_by_name(self, name: str) -> Optional[DictEntry]:
        with self._lock:
            for e in self._items.values():
                if e.name == name:
                    return e
        return None

    def _new_id(self, name: str) -> str:
        import hashlib
        return hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

    def upsert(
        self,
        *,
        entry_id: Optional[str],
        name: str,
        dict_type: str,
        description: str,
        schedule_type: str,
        interval_seconds: int,
        daily_time: str,
        enabled: bool,
        code: str,
        retention: int,
    ) -> DictEntry:
        with self._lock:
            if entry_id and entry_id in self._items:
                entry = self._items[entry_id]
            else:
                if any(e.name == name for e in self._items.values()):
                    raise ValueError(f"数据字典名称已存在: {name}")
                entry = DictEntry(id=self._new_id(name), name=name)
                self._items[entry.id] = entry

            if "def fetch_data" not in code:
                raise ValueError("代码必须包含 fetch_data 函数")

            entry.name = name
            entry.dict_type = dict_type
            entry.description = description
            entry.schedule_type = schedule_type if schedule_type in ("interval", "daily") else "interval"
            entry.interval_seconds = max(5, int(interval_seconds or 300))
            entry.daily_time = daily_time or "03:00"
            entry.enabled = bool(enabled)
            entry.code = code
            entry.retention = max(1, int(retention or 1))
            entry.payload_key = entry.payload_key or f"{entry.id}:latest"
            self._save(entry)
            self._log(
                "INFO",
                "dictionary entry upserted",
                entry_id=entry.id,
                name=entry.name,
                schedule_type=entry.schedule_type,
                interval_seconds=entry.interval_seconds,
                daily_time=entry.daily_time,
                enabled=entry.enabled,
            )

        if entry.enabled:
            self.start(entry.id)
        else:
            self.stop(entry.id)
        return entry

    def delete(self, entry_id: str) -> bool:
        self.stop(entry_id)
        with self._lock:
            entry = self._items.pop(entry_id, None)
            if not entry:
                return False
            db = self._entry_db()
            if entry_id in db:
                del db[entry_id]
            self._log("WARNING", "dictionary entry deleted", entry_id=entry_id, name=entry.name)
        return True

    def _compile_fetch(self, code: str) -> Callable[[], Any]:
        import pandas as pd
        import numpy as np

        env = {
            "__builtins__": __builtins__,
            "pd": pd,
            "pandas": pd,
            "np": np,
            "numpy": np,
            "time": time,
            "datetime": datetime,
            "json": json,
        }
        local_vars: Dict[str, Any] = {}
        exec(code, env, local_vars)
        fn = local_vars.get("fetch_data")
        if not callable(fn):
            raise ValueError("fetch_data not found")
        return fn

    def _estimate_size_bytes(self, data: Any) -> int:
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

    def _execute_once(self, entry_id: str) -> dict:
        entry = self.get_entry(entry_id)
        if not entry:
            return {"success": False, "error": "entry not found"}

        start_ts = time.time()
        with self._lock:
            if entry_id in self._running:
                return {"success": False, "error": "entry is already running"}
            self._running.add(entry_id)
            entry.last_status = "running"
            entry.last_error = ""
            self._save(entry)
            self._log("INFO", "dictionary refresh started", entry_id=entry.id, name=entry.name)

        try:
            fn = self._compile_fetch(entry.code)
            data = fn()
            payload_db = self._payload_db()
            payload_db[entry.payload_key] = {
                "ts": time.time(),
                "data": data,
            }

            entry.last_update_ts = time.time()
            entry.last_status = "success"
            entry.last_error = ""
            entry.run_count += 1
            entry.data_size_bytes = self._estimate_size_bytes(data)
            self._save(entry)
            self._log(
                "INFO",
                "dictionary refresh succeeded",
                entry_id=entry.id,
                name=entry.name,
                size_bytes=entry.data_size_bytes,
                cost_ms=int((time.time() - start_ts) * 1000),
                run_count=entry.run_count,
            )
            return {"success": True, "entry_id": entry.id, "size": entry.data_size_bytes}
        except Exception as e:
            entry.last_status = "error"
            entry.last_error = str(e)
            self._save(entry)
            self._log(
                "ERROR",
                "dictionary refresh failed",
                entry_id=entry.id,
                name=entry.name,
                cost_ms=int((time.time() - start_ts) * 1000),
                error=str(e),
            )
            return {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        finally:
            with self._lock:
                self._running.discard(entry_id)

    def run_once(self, entry_id: str) -> dict:
        return self._execute_once(entry_id)

    def run_once_async(self, entry_id: str) -> dict:
        entry = self.get_entry(entry_id)
        if not entry:
            return {"success": False, "error": "entry not found"}

        with self._lock:
            thread = self._run_threads.get(entry_id)
            if thread and thread.is_alive():
                return {"success": False, "error": "entry async task already running"}
            if entry_id in self._running:
                return {"success": False, "error": "entry is already running"}

            t = threading.Thread(
                target=self._execute_once,
                args=(entry_id,),
                daemon=True,
                name=f"dict_run_once_{entry_id}",
            )
            self._run_threads[entry_id] = t
            t.start()
            self._log("INFO", "dictionary refresh queued", entry_id=entry_id)
            return {"success": True, "queued": True, "entry_id": entry_id}

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

    def _worker(self, entry_id: str):
        while True:
            stop = self._stops.get(entry_id)
            if stop is None or stop.is_set():
                return

            entry = self.get_entry(entry_id)
            if not entry:
                return

            self._execute_once(entry_id)

            entry = self.get_entry(entry_id)
            if not entry:
                return
            if entry.schedule_type == "daily":
                wait_s = self._seconds_until_daily(entry.daily_time)
            else:
                wait_s = float(max(5, int(entry.interval_seconds or 300)))

            if stop.wait(timeout=wait_s):
                return

    def start(self, entry_id: str) -> bool:
        entry = self.get_entry(entry_id)
        if not entry:
            return False

        with self._lock:
            entry.enabled = True
            self._save(entry)

            if entry_id in self._threads and self._threads[entry_id].is_alive():
                return True

            stop_event = threading.Event()
            thread = threading.Thread(target=self._worker, args=(entry_id,), daemon=True, name=f"dict_{entry_id}")
            self._stops[entry_id] = stop_event
            self._threads[entry_id] = thread
            thread.start()
            self._log("INFO", "dictionary scheduler started", entry_id=entry.id, name=entry.name)
            return True

    def stop(self, entry_id: str) -> bool:
        entry = self.get_entry(entry_id)
        with self._lock:
            if entry:
                entry.enabled = False
                self._save(entry)

            stop_event = self._stops.get(entry_id)
            if stop_event:
                stop_event.set()
            if entry:
                self._log("WARNING", "dictionary scheduler stopped", entry_id=entry.id, name=entry.name)
            return True

    def get_latest_payload(self, entry: DictEntry) -> Any:
        payload = self._payload_db().get(entry.payload_key)
        if isinstance(payload, dict):
            return payload.get("data")
        return None

    def clear_payload(self, entry_id: str) -> dict:
        entry = self.get_entry(entry_id)
        if not entry:
            return {"success": False, "error": "entry not found"}

        try:
            payload_db = self._payload_db()
            removed = 0

            # 删除当前主键
            if entry.payload_key and entry.payload_key in payload_db:
                del payload_db[entry.payload_key]
                removed += 1

            # 删除历史键（兼容未来扩展：<entry_id>:*）
            prefix = f"{entry.id}:"
            for k in list(payload_db.keys()):
                if isinstance(k, str) and k.startswith(prefix):
                    del payload_db[k]
                    removed += 1

            entry.last_status = "cleared"
            entry.last_error = ""
            entry.last_update_ts = 0.0
            entry.data_size_bytes = 0
            self._save(entry)
            self._log("WARNING", "dictionary payload cleared", entry_id=entry.id, name=entry.name, removed=removed)

            return {"success": True, "removed": removed}
        except Exception as e:
            entry.last_status = "error"
            entry.last_error = str(e)
            self._save(entry)
            self._log("ERROR", "dictionary payload clear failed", entry_id=entry.id, name=entry.name, error=str(e))
            return {"success": False, "error": str(e)}

    def get_stats(self) -> dict:
        entries = self.list_entries()
        running = sum(1 for e in entries if e.enabled)
        healthy = sum(1 for e in entries if e.last_status == "success")
        error = sum(1 for e in entries if e.last_status == "error")
        return {
            "total": len(entries),
            "running": running,
            "healthy": healthy,
            "error": error,
        }


_DICT_MANAGER = DictionaryManager()
_DICT_MANAGER_LOADED = False
_DICT_MANAGER_LOAD_LOCK = threading.Lock()


def get_dictionary_manager() -> DictionaryManager:
    global _DICT_MANAGER_LOADED
    if not _DICT_MANAGER_LOADED:
        with _DICT_MANAGER_LOAD_LOCK:
            if not _DICT_MANAGER_LOADED:
                try:
                    _DICT_MANAGER.load_from_db()
                finally:
                    _DICT_MANAGER_LOADED = True
    return _DICT_MANAGER
