"""
雷达新闻实时推送中心

设计思路：
1. 接收 TextFocusedEvent（source=radar_news）
2. 将结果写入 Stream，供前端 SSE 订阅
3. 支持按 importance_score 筛选

架构：
    TextFocusedEvent (source=radar_news)
            ↓
    RadarNewsPushCenter 收到通知
            ↓
    Stream.emit(data) 写入流
            ↓
    前端 SSE 接收并显示
"""

from __future__ import annotations

import time
import threading
from typing import Any, Callable, Dict, List, Optional
from dataclasses import asdict, dataclass

from deva.core import Stream


@dataclass
class NewsPushData:
    """新闻推送数据格式"""
    timestamp: float
    news: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RadarNewsPushCenter:
    """
    雷达新闻推送中心

    职责：
    1. 接收 radar_news 源的 TextFocusedEvent
    2. 将结果写入 Stream，供前端 SSE 订阅
    3. 支持按 importance_score 筛选

    使用方式：
        # 后端：注册事件回调（由 event_registrar 调用）
        push_center = RadarNewsPushCenter.get_instance()
        push_center.register_callback(on_news_event)

        def on_news_event(event):
            push_center.push_news(event)

        # 前端：订阅推送
        push_center = RadarNewsPushCenter.get_instance()
        stream = push_center.get_stream()
        stream.webview("/radar_news_stream")
    """

    _instance: Optional[RadarNewsPushCenter] = None
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
        self._stream.name = "radar_news_push"
        self._callbacks: List[Callable] = []
        self._last_push_time = 0.0
        self._push_interval = 2.0
        self._enabled = True
        self._initialized = True

        self._latest_news: List[Dict[str, Any]] = []
        self._min_importance_filter = 0.0

        import logging
        self._log = logging.getLogger(__name__)
        self._log.info("[RadarNewsPushCenter] 初始化完成")

    @classmethod
    def get_instance(cls) -> RadarNewsPushCenter:
        return cls()

    def get_stream(self) -> Stream:
        return self._stream

    def register_callback(self, callback: Callable):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def push_news(self, event_or_dict: Any):
        if not self._enabled:
            return

        try:
            if hasattr(event_or_dict, 'to_dict'):
                news_dict = event_or_dict.to_dict()
            else:
                news_dict = event_or_dict

            importance = news_dict.get('importance_score', 0.0)
            if importance < self._min_importance_filter:
                return

            now = time.time()
            if now - self._last_push_time < self._push_interval:
                return

            self._last_push_time = now

            self._latest_news.insert(0, news_dict)
            if len(self._latest_news) > 50:
                self._latest_news = self._latest_news[:50]

            payload = {
                'timestamp': now,
                'news': self._latest_news
            }

            self._stream.emit(payload)

            for callback in self._callbacks:
                try:
                    callback(payload)
                except Exception as e:
                    self._log.error(f"[RadarNewsPushCenter] callback 失败: {e}")

        except Exception as e:
            self._log.error(f"[RadarNewsPushCenter] push_news 失败: {e}")

    def set_filter(self, min_importance: float):
        self._min_importance_filter = max(0.0, min(1.0, min_importance))

    def get_filter(self) -> float:
        return self._min_importance_filter

    def get_latest_news(self) -> List[Dict[str, Any]]:
        return self._latest_news

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def set_push_interval(self, interval: float):
        self._push_interval = max(0.5, interval)

    def clear(self):
        self._latest_news = []
        self._stream = Stream()
        self._stream.name = "radar_news_push"

    def get_push_count(self) -> int:
        return len(self._stream)


def get_news_push_center() -> RadarNewsPushCenter:
    return RadarNewsPushCenter.get_instance()


def push_radar_news(event: Any):
    center = get_news_push_center()
    center.push_news(event)


__all__ = [
    "NewsPushData",
    "RadarNewsPushCenter",
    "get_news_push_center",
    "push_radar_news",
]
