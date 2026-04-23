"""市场热点实时推送中心

设计思路：
1. 后端计算完成后，主动推送数据到前端
2. 使用 Deva Stream 作为消息总线
3. 前端页面通过 Stream.webview 接收并显示

架构：
    MarketHotspotSystem 计算完成
            ↓
    MarketHotspotPushCenter 收到通知
            ↓
    Stream.emit(data) 写入流
            ↓
    前端 Stream.webview 接收并显示
"""

from __future__ import annotations

import time
import threading
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

from deva.core import Stream


@dataclass
class HotspotPushData:
    """推送数据格式"""
    timestamp: float
    market: str  # "CN" or "US"
    global_hotspot: float
    activity: float
    hot_blocks: List[Dict[str, Any]]  # [{"block_id": "xxx", "name": "xxx", "weight": 0.5}]
    hot_stocks: List[Dict[str, Any]]   # [{"symbol": "xxx", "name": "xxx", "weight": 0.5}]
    block_changes: List[Dict[str, Any]]  # 板块变化
    stock_changes: List[Dict[str, Any]]   # 个股变化
    raw_snapshot: Optional[Dict[str, Any]] = None


class MarketHotspotPushCenter:
    """
    市场热点推送中心

    职责：
    1. 接收市场热点系统的计算结果
    2. 将结果写入 Stream，供前端订阅
    3. 管理推送会话（连接/断开）

    使用方式：
        # 后端：注册推送回调
        push_center = MarketHotspotPushCenter.get_instance()
        push_center.register_callback(on_hotspot_update)

        def on_hotspot_update(data: HotspotPushData):
            push_center.push(data)

        # 前端：订阅推送
        push_center = MarketHotspotPushCenter.get_instance()
        stream = push_center.get_stream()
        stream.webview("/market_hotspot_stream")
    """

    _instance: Optional[MarketHotspotPushCenter] = None
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
        self._stream.name = "market_hotspot_push"
        self._callbacks: List[Callable] = []
        self._last_push_time = 0.0
        self._push_interval = 1.0  # 最小推送间隔（秒）
        self._enabled = True
        self._initialized = True

        # 缓存最新数据
        self._latest_data: Optional[HotspotPushData] = None

    @classmethod
    def get_instance(cls) -> MarketHotspotPushCenter:
        """获取单例实例"""
        return cls()

    def get_stream(self) -> Stream:
        """获取推送 Stream，前端通过 webview 订阅"""
        return self._stream

    def register_callback(self, callback: Callable[[HotspotPushData], None]):
        """注册推送回调（供后端系统调用）"""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable):
        """取消注册推送回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def push(self, data: HotspotPushData):
        """
        推送数据到前端

        Args:
            data: HotspotPushData 实例
        """
        if not self._enabled:
            return

        # 限流：避免推送过于频繁
        now = time.time()
        if now - self._last_push_time < self._push_interval:
            # 更新缓存但不推送
            self._latest_data = data
            return

        self._last_push_time = now
        self._latest_data = data

        # 写入 Stream（前端会收到）
        self._stream.emit(data)

        # 调用其他回调
        for callback in self._callbacks:
            try:
                callback(data)
            except Exception as e:
                import traceback
                traceback.print_exc()

    def push_dict(self, data: Dict[str, Any]):
        """推送字典格式的数据（自动转换为 HotspotPushData）"""
        push_data = HotspotPushData(
            timestamp=data.get("timestamp", time.time()),
            market=data.get("market", "CN"),
            global_hotspot=data.get("global_hotspot", 0.0),
            activity=data.get("activity", 0.0),
            hot_blocks=data.get("hot_blocks", []),
            hot_stocks=data.get("hot_stocks", []),
            block_changes=data.get("block_changes", []),
            stock_changes=data.get("stock_changes", []),
            raw_snapshot=data.get("raw_snapshot"),
        )
        self.push(push_data)

    def get_latest_data(self) -> Optional[HotspotPushData]:
        """获取最新推送的数据"""
        return self._latest_data

    def set_enabled(self, enabled: bool):
        """启用/禁用推送"""
        self._enabled = enabled

    def set_push_interval(self, interval: float):
        """设置最小推送间隔（秒）"""
        self._push_interval = interval

    def get_push_count(self) -> int:
        """获取推送次数"""
        return len(self._stream)

    def clear(self):
        """清空 Stream"""
        self._stream = Stream()
        self._stream.name = "market_hotspot_push"
        self._latest_data = None


def get_push_center() -> MarketHotspotPushCenter:
    """便捷函数：获取推送中心实例"""
    return MarketHotspotPushCenter.get_instance()


def push_hotspot_data(data: Dict[str, Any]):
    """便捷函数：推送热点数据"""
    center = get_push_center()
    center.push_dict(data)


__all__ = [
    "HotspotPushData",
    "MarketHotspotPushCenter",
    "get_push_center",
    "push_hotspot_data",
]
