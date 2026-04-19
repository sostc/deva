from __future__ import annotations

import threading
from typing import Dict, Generic, List, Optional, TypeVar


TEntry = TypeVar("TEntry")


class SingletonLazyManager:
    """Shared singleton + lazy-init skeleton for manager-style components."""

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

    def _ensure_initialized(self):
        if getattr(self, "_initialized", False):
            return
        with self._init_lock:
            if getattr(self, "_initialized", False):
                return
            self._initialize_manager_state()
            self._initialized = True

    def _initialize_manager_state(self):
        raise NotImplementedError


class CatalogManagerMixin(Generic[TEntry]):
    _items: Dict[str, TEntry]
    _items_lock: threading.Lock

    def get(self, entry_id: str) -> Optional[TEntry]:
        self._ensure_initialized()
        return self._items.get(entry_id)

    def get_by_name(self, name: str) -> Optional[TEntry]:
        self._ensure_initialized()
        for entry in self._items.values():
            if getattr(entry, "name", None) == name:
                return entry
        return None

    def list_all(self) -> List[TEntry]:
        self._ensure_initialized()
        return list(self._items.values())

    def list_all_dict(self) -> List[dict]:
        self._ensure_initialized()
        return [entry.to_dict() for entry in self._items.values()]

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

    def _log(self, level: str, message: str, **extra):
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[{type(self).__name__}][{level}] {message} | {extra_str}")
