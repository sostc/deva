"""
信号流实时推送中心

设计思路：
1. 订阅 SignalStream 的信号结果
2. 将结果写入 SSE 流，供前端订阅
3. 支持按优先级筛选

架构：
    StrategyResult 写入 SignalStream
            ↓
    SignalPushCenter 订阅 stream
            ↓
    Stream.emit(data) 写入流
            ↓
    前端 SSE 接收并显示
"""

from __future__ import annotations

import time
import threading
from typing import Any, Callable, Dict, List, Optional
from dataclasses import asdict, dataclass, is_dataclass

from deva.core import Stream


@dataclass
class SignalPushData:
    """信号推送数据格式"""
    timestamp: float
    signals: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SignalPushCenter:
    """
    信号流推送中心

    职责：
    1. 订阅 SignalStream 的信号
    2. 将结果写入 SSE，供前端订阅
    3. 支持按优先级筛选
    """

    _instance: Optional[SignalPushCenter] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._stream = Stream()
        self._stream.name = "signal_push"
        self._callbacks: List[Callable] = []
        self._last_push_time = 0.0
        self._push_interval = 1.0
        self._enabled = True
        self._initialized = True

        self._latest_signals: List[Dict[str, Any]] = []
        self._priority_filter: Optional[str] = None

        import logging
        self._log = logging.getLogger(__name__)
        self._log.info("[SignalPushCenter] 初始化完成")

    @classmethod
    def get_instance(cls) -> SignalPushCenter:
        return cls()

    def get_stream(self) -> Stream:
        return self._stream

    def register_callback(self, callback: Callable):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def push_signal(self, result: Any):
        if not self._enabled:
            return

        try:
            if hasattr(result, 'to_dict'):
                signal_dict = result.to_dict()
            elif is_dataclass(result):
                signal_dict = asdict(result)
            elif isinstance(result, dict):
                signal_dict = result
            else:
                signal_dict = {'raw': str(result)}

            priority_level = self._get_priority_level(signal_dict.get('priority', 0.5))
            if self._priority_filter and priority_level != self._priority_filter:
                return

            now = time.time()
            if now - self._last_push_time < self._push_interval:
                return

            self._last_push_time = now

            self._latest_signals.insert(0, signal_dict)
            if len(self._latest_signals) > 30:
                self._latest_signals = self._latest_signals[:30]

            payload = {
                'timestamp': now,
                'signals': self._latest_signals
            }

            self._stream.emit(payload)

            for callback in self._callbacks:
                try:
                    callback(payload)
                except Exception as e:
                    self._log.error(f"[SignalPushCenter] callback 失败: {e}")

        except Exception as e:
            self._log.error(f"[SignalPushCenter] push_signal 失败: {e}")

    def _get_priority_level(self, priority: float) -> str:
        if priority >= 0.7:
            return 'high'
        elif priority >= 0.4:
            return 'medium'
        else:
            return 'low'

    def set_priority_filter(self, level: Optional[str]):
        self._priority_filter = level

    def get_priority_filter(self) -> Optional[str]:
        return self._priority_filter

    def get_latest_signals(self) -> List[Dict[str, Any]]:
        return self._latest_signals

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def set_push_interval(self, interval: float):
        self._push_interval = max(0.5, interval)

    def clear(self):
        self._latest_signals = []
        self._stream = Stream()
        self._stream.name = "signal_push"


def get_signal_push_center() -> SignalPushCenter:
    return SignalPushCenter.get_instance()


def push_signal_result(result: Any):
    center = get_signal_push_center()
    center.push_signal(result)


__all__ = [
    "SignalPushData",
    "SignalPushCenter",
    "get_signal_push_center",
    "push_signal_result",
]
