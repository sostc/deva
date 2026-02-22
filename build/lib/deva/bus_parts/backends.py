"""Bus backend implementations.

This module provides pluggable backends for the global ``deva.bus`` runtime.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Optional

from ..namespace import NS, NT


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


class BaseBusBackend:
    name = "base"

    def build_stream(self, topic: str):
        raise NotImplementedError

    def publish(self, stream, payload: Any):
        return stream.emit(payload)

    def stop(self):
        return None

    def describe(self):
        return {"backend": self.name}


class LocalBusBackend(BaseBusBackend):
    name = "local"

    def build_stream(self, topic: str):
        return NS(topic)


class RedisBusBackend(BaseBusBackend):
    name = "redis"

    def __init__(self, group: str):
        self.group = group

    def build_stream(self, topic: str):
        return NT(
            topic,
            group=self.group,
            address=os.getenv("DEVA_REDIS_HOST", "localhost"),
            db=_env_int("DEVA_REDIS_DB", 0),
            password=os.getenv("DEVA_REDIS_PASSWORD"),
        )

    def describe(self):
        return {"backend": self.name, "group": self.group}


class FileIpcBusBackend(BaseBusBackend):
    name = "file-ipc"

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path
        self._stream = None
        self._stop = threading.Event()
        self._thread = None
        self._offset = 0

    def _resolve_file_path(self, topic: str) -> str:
        if self.file_path:
            return self.file_path
        default = f"/tmp/deva_bus_{topic}.log"
        return os.getenv("DEVA_BUS_FILE", default)

    def _tail_loop(self):
        while not self._stop.is_set():
            try:
                if not os.path.exists(self.file_path):
                    time.sleep(0.2)
                    continue
                with open(self.file_path, "r", encoding="utf-8") as f:
                    f.seek(self._offset)
                    lines = f.readlines()
                    self._offset = f.tell()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except Exception:
                        payload = {"sender": "file-ipc", "message": line, "ts": time.time()}
                    self._stream.emit(payload)
            except Exception:
                # Keep tail loop resilient.
                pass
            time.sleep(0.2)

    def build_stream(self, topic: str):
        self.file_path = self._resolve_file_path(topic)
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            open(self.file_path, "a", encoding="utf-8").close()

        self._stream = NS(topic)
        replay = os.getenv("DEVA_BUS_FILE_REPLAY", "0").strip() == "1"
        self._offset = 0 if replay else os.path.getsize(self.file_path)

        self._thread = threading.Thread(target=self._tail_loop, daemon=True, name="deva-bus-file-tail")
        self._thread.start()
        return self._stream

    def publish(self, stream, payload: Any):
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            f.flush()
        return payload

    def stop(self):
        self._stop.set()

    def describe(self):
        return {"backend": self.name, "file_path": self.file_path}
