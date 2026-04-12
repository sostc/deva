"""DataSource 防抖器"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional


class DataSourceDebouncer:
    """数据源防抖器

    用于减少数据到达时的抖动，合并短时间内的多次数据推送。
    工作原理：收到数据后等待 debounce_ms，如果在这期间有新的数据到来，
    则用新数据替代旧数据（只保留最新），等 debounce_ms 期间没有新数据后才处理。
    """

    def __init__(self, debounce_ms: int = 500):
        self._debounce_ms = debounce_ms / 1000.0
        self._pending_data = None
        self._pending_is_batch = False
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._emit_callback: Optional[Callable] = None
        self._total_emitted = 0
        self._total_received = 0

    def set_emit_callback(self, callback: Callable):
        """设置实际发送数据的回调函数"""
        self._emit_callback = callback

    def receive(self, data: Any, is_batch: bool = False):
        """接收数据，触发防抖逻辑"""
        with self._lock:
            self._total_received += 1
            self._pending_data = data
            self._pending_is_batch = is_batch

            if self._timer:
                self._timer.cancel()

            self._timer = threading.Timer(self._debounce_ms, self._flush)
            self._timer.start()

    def _flush(self):
        """实际发送数据（防抖合并后）"""
        with self._lock:
            if self._pending_data is None:
                return

            data = self._pending_data
            is_batch = self._pending_is_batch
            self._pending_data = None
            self._pending_is_batch = False

        if self._emit_callback:
            self._emit_callback(data, is_batch)
            self._total_emitted += 1

    def get_stats(self) -> dict:
        """获取防抖统计"""
        with self._lock:
            return {
                "total_received": self._total_received,
                "total_emitted": self._total_emitted,
                "debounce_ratio": round(self._total_emitted / max(self._total_received, 1), 3),
                "debounce_ms": int(self._debounce_ms * 1000),
                "pending": self._pending_data is not None,
            }

    def reset_stats(self):
        """重置统计"""
        with self._lock:
            self._total_emitted = 0
            self._total_received = 0

