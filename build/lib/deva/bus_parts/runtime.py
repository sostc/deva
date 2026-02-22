"""Runtime manager for the global deva bus."""

from __future__ import annotations

import os
import socket
import threading
import time
from typing import Any, Dict, Optional

from ..namespace import NB
from .backends import FileIpcBusBackend, LocalBusBackend, RedisBusBackend


class BusRuntime:
    def __init__(self, *, warn_stream, topic: str = "bus"):
        self.warn_stream = warn_stream
        self.topic = topic
        self.group = os.getenv("DEVA_BUS_GROUP", str(os.getpid()))
        self.mode = (os.getenv("DEVA_BUS_MODE", "redis") or "redis").strip().lower()
        self.backend = None
        self.stream = None

        self.meta: Dict[str, Any] = {
            "mode": self.mode,
            "topic": self.topic,
            "group": self.group,
            "connected": None,
            "error": None,
        }

        self.clients_table = NB("deva_bus_clients")
        self.client_ttl_seconds = 30
        self.heartbeat_interval_seconds = 5
        self.client_key = f"{socket.gethostname()}:{os.getpid()}"
        self.started_at = time.time()
        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    def _choose_backend(self):
        if self.mode == "local":
            self.backend = LocalBusBackend()
            self.meta.update({"mode": "local", "connected": True})
            return
        if self.mode in ("file", "file-ipc"):
            self.backend = FileIpcBusBackend()
            self.meta.update({"mode": "file-ipc", "connected": True})
            return
        self.backend = RedisBusBackend(group=self.group)

    def start(self):
        self._choose_backend()
        try:
            self.stream = self.backend.build_stream(self.topic)
            if self.stream is None:
                raise RuntimeError("bus backend returned empty stream")
            if not self.stream.is_cache:
                self.stream.start_cache(cache_max_len=200, cache_max_age_seconds=60 * 60 * 24)
            if self.meta.get("connected") is None:
                self.meta["connected"] = True
        except Exception as e:
            self.meta.update({
                "mode": "local-fallback",
                "connected": False,
                "error": str(e),
            })
            self.backend = LocalBusBackend()
            self.warn_stream.emit("bus backend 初始化失败，回退本地 stream: " + str(e))
            self.stream = self.backend.build_stream(self.topic)
            if not self.stream.is_cache:
                self.stream.start_cache(cache_max_len=200, cache_max_age_seconds=60 * 60 * 24)
        self._start_heartbeat()
        return self.stream

    def _heartbeat_payload(self):
        return {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "client_key": self.client_key,
            "topic": self.meta.get("topic"),
            "mode": self.meta.get("mode"),
            "group": self.meta.get("group"),
            "updated_at": time.time(),
            "started_at": self.started_at,
            "type": getattr(self.stream, "__class__", type("x", (), {})).__name__,
        }

    def _heartbeat_once(self):
        try:
            self.clients_table[self.client_key] = self._heartbeat_payload()
        except Exception:
            pass

    def _heartbeat_loop(self):
        while not self._stop_event.is_set():
            self._heartbeat_once()
            time.sleep(self.heartbeat_interval_seconds)

    def _start_heartbeat(self):
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="deva-bus-heartbeat")
        self._heartbeat_thread.start()

    def _remove_stale_bus_clients(self, ttl_seconds=None):
        ttl = ttl_seconds or self.client_ttl_seconds
        now = time.time()
        to_delete = []
        for key, value in list(self.clients_table.items()):
            if not isinstance(value, dict):
                to_delete.append(key)
                continue
            updated_at = value.get("updated_at", 0)
            if now - float(updated_at or 0) > ttl:
                to_delete.append(key)
        for key in to_delete:
            try:
                self.clients_table.delete(key)
            except Exception:
                try:
                    del self.clients_table[key]
                except Exception:
                    pass

    def get_clients(self, ttl_seconds=None):
        self._remove_stale_bus_clients(ttl_seconds=ttl_seconds)
        clients = []
        for _, value in list(self.clients_table.items()):
            if not isinstance(value, dict):
                continue
            if value.get("topic") != self.meta.get("topic"):
                continue
            clients.append(value)
        clients.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return clients

    def get_recent_messages(self, limit=10):
        if self.stream is None:
            return []
        try:
            messages = self.stream.recent(limit)
            if isinstance(messages, dict):
                return []
            return list(messages)[-limit:]
        except Exception:
            return []

    def send_message(self, message, *, sender="admin", extra=None):
        if self.stream is None:
            raise RuntimeError("bus not initialized")
        payload = {
            "sender": sender,
            "message": message,
            "ts": time.time(),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        return self.backend.publish(self.stream, payload)

    def get_status(self):
        status = dict(self.meta)
        if self.stream is None:
            status["connected"] = False
            status["error"] = status.get("error") or "bus not initialized"
            return status
        status["type"] = self.stream.__class__.__name__
        status["stopped"] = getattr(self.stream, "stopped", None)
        status["redis_ready"] = getattr(self.stream, "redis", None) is not None
        status["loop_running"] = getattr(getattr(self.stream, "loop", None), "asyncio_loop", None) is not None
        status["backend"] = (self.backend.describe() if self.backend else {"backend": "unknown"})
        if status.get("connected") is None:
            status["connected"] = True
        return status

    def stop(self):
        self._stop_event.set()
        try:
            self.clients_table.delete(self.client_key)
        except Exception:
            pass
        if self.backend is not None:
            self.backend.stop()
        if self.stream is not None:
            try:
                self.stream.stop()
            except Exception:
                pass
