"""
评级跃迁告警：单例 + Stream，只在等级变化时推送

仿 radar/push_center 的形态，但只接收日更/周报产生的跃迁事件；
不订阅行情、不做轮询。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from deva.core import Stream

log = logging.getLogger(__name__)


class GeoRiskAlertCenter:
    _instance: Optional["GeoRiskAlertCenter"] = None
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
        self._stream.name = "geo_risk_alerts"
        self._callbacks: List[Callable] = []
        self._latest: List[Dict[str, Any]] = []
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "GeoRiskAlertCenter":
        return cls()

    def get_stream(self) -> Stream:
        return self._stream

    def register_callback(self, callback: Callable):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def get_latest(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(self._latest[:limit])

    def publish(self, transition: Dict[str, Any]) -> bool:
        """接收一条跃迁事件；from == to 的无效事件直接丢弃。"""
        if not isinstance(transition, dict):
            return False
        before = transition.get("from")
        after = transition.get("to")
        if not before or not after or before == after:
            return False

        event = {
            **transition,
            "timestamp": time.time(),
        }
        self._latest.insert(0, event)
        self._latest = self._latest[:50]

        payload = {"timestamp": event["timestamp"], "alerts": self._latest}
        try:
            self._stream.emit(payload)
        except Exception as exc:  # noqa: BLE001
            log.error("[GeoRiskAlert] Stream 推送失败: %s", exc)

        for callback in list(self._callbacks):
            try:
                callback(payload)
            except Exception as exc:  # noqa: BLE001
                log.error("[GeoRiskAlert] callback 失败: %s", exc)
        return True


def get_alert_center() -> GeoRiskAlertCenter:
    return GeoRiskAlertCenter.get_instance()
