#!/usr/bin/env python
"""总线模块,提供全局事件流和日志功能

本模块提供了一个全局事件总线系统,用于在不同组件间传递消息和事件。
主要包含以下功能:

1. log流: 用于全局日志记录
2. warn流: 用于警告信息
3. debug流: 用于调试信息
4. bus: 通用事件总线

主要组件:
--------
log : NS
    全局日志流,缓存最近消息
warn : NS 
    警告信息流,输出到logging
debug : NS
    调试信息流
bus : NT
    通用事件总线,用于组件间通信

示例:
-----
# 基本日志
'hello' >> log  # 输出日志

# 警告信息
'warning!' >> warn  # 输出警告

# 调试信息
'debug info' >> debug  # 输出调试信息

# 事件总线
def handler(msg):
    print('收到消息:', msg)
    
bus.sink(handler)  # 注册处理器
'event' >> bus  # 发送事件

# 函数调试
@debug  # 装饰器方式
def foo():
    pass

f = range+sum  # 函数组合
ff = f^debug  # 添加调试
'123' >> ff  # 执行时输出调试信息
"""

"""公共总线流."""
import json
import logging
import socket
import threading
import time
import inspect
from typing import Any, Dict, Optional

import atexit
import os

from .namespace import NS, NT
from .core import (
    normalize_record as _adapter_normalize_record,
    format_line as _adapter_format_line,
    should_emit_level as _adapter_should_emit_level,
    setup_deva_logging,
)


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


class BusRuntime:
    def __init__(self, *, warn_stream, topic: str = "bus"):
        from .namespace import NB
        self.warn_stream = warn_stream
        self.topic = topic
        self.group = os.getenv("DEVA_BUS_GROUP", str(os.getpid()))
        self.mode = (os.getenv("DEVA_BUS_MODE", "redis") or "redis").strip().lower()
        self.backend = None
        self.stream = None
        self.meta: Dict[str, Any] = {"mode": self.mode, "topic": self.topic, "group": self.group, "connected": None, "error": None}
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
            self.meta.update({"mode": "local-fallback", "connected": False, "error": str(e)})
            self.backend = LocalBusBackend()
            self.warn_stream.emit("bus backend 初始化失败，回退本地 stream: " + str(e))
            self.stream = self.backend.build_stream(self.topic)
            if not self.stream.is_cache:
                self.stream.start_cache(cache_max_len=200, cache_max_age_seconds=60 * 60 * 24)
        self._start_heartbeat()
        return self.stream

    def _heartbeat_payload(self):
        return {"pid": os.getpid(), "host": socket.gethostname(), "client_key": self.client_key, "topic": self.meta.get("topic"), "mode": self.meta.get("mode"), "group": self.meta.get("group"), "updated_at": time.time(), "started_at": self.started_at, "type": getattr(self.stream, "__class__", type("x", (), {})).__name__}

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
        payload = {"sender": sender, "message": message, "ts": time.time()}
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

__all__ = [
    'log', 'warn', 'debug', 'bus',
    'get_bus_runtime_status', 'get_bus_clients', 'get_bus_recent_messages', 'send_bus_message',
    'configure_log_behavior',
]

warn = NS('warn')
debug = NS('debug')
setup_deva_logging()


_DEFAULT_LOGGER = logging.getLogger("deva.log")
_LOG_SINK_INSTALLED = False
_INTERNAL_SENDER_FILES = {
    "bus.py",
    "core.py",
    "pipe.py",
    "sources.py",
    "namespace.py",
    "when.py",
    "ops.py",
}


def _normalize_log_record(x):
    return _adapter_normalize_record(x, default_level="INFO", default_source="deva")


def _format_log_line(record):
    return _adapter_format_line(record)


def _should_emit_level(level_name):
    return _adapter_should_emit_level(level_name)


def _emit_to_python_logger(record):
    level_name = str(record.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    _DEFAULT_LOGGER.log(level, record.get("message", ""), extra={"deva_extra": record.get("extra", {})})


def _default_log_sink(x):
    record = _normalize_log_record(x)
    if not _should_emit_level(record.get("level")):
        return
    print(_format_log_line(record))
    if os.getenv("DEVA_LOG_FORWARD_TO_LOGGING", "0").strip() == "1":
        _emit_to_python_logger(record)


def _emit_with_defaults(x, *, level="INFO", source="deva"):
    record = _normalize_log_record(x)
    if not record.get("level"):
        record["level"] = level
    if str(record.get("level", "")).upper() == "INFO" and level != "INFO":
        record["level"] = level
    if not record.get("source") or record.get("source") == "deva":
        record["source"] = source
    return record


def _warn_sink(x):
    record = _emit_with_defaults(x, level="WARNING", source="deva.warn")
    log.emit(record)


def _debug_sink(x):
    record = _emit_with_defaults(x, level="DEBUG", source="deva.debug")
    log.emit(record)


def configure_log_behavior():
    """配置 deva 默认日志行为（结构化、可转发到 logging）。"""
    global _LOG_SINK_INSTALLED
    if _LOG_SINK_INSTALLED:
        return
    log.sink(_default_log_sink)
    warn.sink(_warn_sink)
    debug.sink(_debug_sink)
    _LOG_SINK_INSTALLED = True


def _default_bus_sender():
    env_sender = (os.getenv("DEVA_BUS_SENDER") or "").strip()
    if env_sender:
        return env_sender
    return f"{socket.gethostname()}:{os.getpid()}"


def _infer_sender_from_stack():
    """Infer caller as function/method name for bus auto-sender."""
    try:
        stack = inspect.stack()
        for frame in stack[2:]:
            filename = frame.filename
            base = os.path.basename(filename)
            if base in _INTERNAL_SENDER_FILES:
                continue
            if "site-packages" in filename and "deva" not in filename:
                continue
            fn = frame.function
            locals_ = frame.frame.f_locals
            self_obj = locals_.get("self")
            if self_obj is not None:
                return f"{self_obj.__class__.__name__}.{fn}"
            cls_obj = locals_.get("cls")
            if cls_obj is not None and hasattr(cls_obj, "__name__"):
                return f"{cls_obj.__name__}.{fn}"
            return fn
    except Exception:
        pass
    return _default_bus_sender()


def _normalize_bus_payload(payload):
    if isinstance(payload, dict):
        out = dict(payload)
        if not out.get("sender"):
            out["sender"] = _infer_sender_from_stack()
        if not out.get("ts"):
            out["ts"] = time.time()
        return out
    return payload


log = NS(
    'log',
    cache_max_len=int(os.getenv("DEVA_LOG_CACHE_MAX_LEN", "200")),
    cache_max_age_seconds=60 * 60 * 24,
)
configure_log_behavior()

_BUS_RUNTIME = BusRuntime(
    warn_stream=warn,
    topic=os.getenv("DEVA_BUS_TOPIC", "bus"),
)
bus = _BUS_RUNTIME.start()
_BUS_ORIGINAL_EMIT = bus.emit


def _bus_emit_with_auto_sender(payload):
    return _BUS_ORIGINAL_EMIT(_normalize_bus_payload(payload))


bus.emit = _bus_emit_with_auto_sender


def get_bus_clients(ttl_seconds=30):
    return _BUS_RUNTIME.get_clients(ttl_seconds=ttl_seconds)


def get_bus_recent_messages(limit=10):
    return _BUS_RUNTIME.get_recent_messages(limit=limit)


def send_bus_message(message, sender="admin", extra=None):
    payload = {"sender": sender, "message": message, "ts": time.time()}
    if isinstance(extra, dict):
        payload.update(extra)
    return bus.emit(payload)


def get_bus_runtime_status():
    return _BUS_RUNTIME.get_status()


@atexit.register
def exit():
    """进程退出时发信号到log.

    Examples:
    ----------
    when('exit',source=log).then(lambda :print('bye bye'))
    """
    #
    try:
        _BUS_RUNTIME.stop()
    except Exception as e:
        e >> log

# debug.map(str).unique() >> Dtalk()
# debug.sink(lambda x: console.log(x, log_locals=True))
