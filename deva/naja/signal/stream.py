"""信号流模块

提供固定缓存长度的信号流实现，使用 Stream 自带 cache，并接入 deva/naja 统一 exit 流程持久化。
"""

import threading
from datetime import datetime, timedelta
from typing import List

from deva import NB, Stream, log, when
from deva.naja.strategy.result_store import StrategyResult


class SignalStream(Stream):
    """固定缓存长度的信号流。"""

    _instance = None
    _shutdown_hook_registered = False
    _CACHE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365 * 10

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_cache_size: int = 100, persist_name: str = "naja_signals", **kwargs):
        """初始化信号流。

        Args:
            max_cache_size: 最大缓存长度
            persist_name: 持久化存储名称
            **kwargs: 其他参数
        """
        if getattr(self, "_initialized", False):
            return

        super().__init__(
            cache_max_len=max_cache_size,
            cache_max_age_seconds=self._CACHE_MAX_AGE_SECONDS,
            **kwargs,
        )

        self.max_cache_size = max_cache_size
        self.persist_name = persist_name
        self.db = NB(persist_name)
        self._persist_lock = threading.RLock()
        self._closed = False

        self._load_from_persistence()
        self._register_shutdown_hook()
        self._initialized = True

    @classmethod
    def _register_shutdown_hook(cls):
        if cls._shutdown_hook_registered:
            return
        when('exit', source=log).then(_close_signal_stream_on_shutdown)
        cls._shutdown_hook_registered = True

    @staticmethod
    def _deserialize_result(data: dict) -> StrategyResult:
        return StrategyResult(
            id=data.get("id", ""),
            strategy_id=data.get("strategy_id", ""),
            strategy_name=data.get("strategy_name", ""),
            ts=data.get("ts", 0),
            success=data.get("success", False),
            input_preview=data.get("input_preview", ""),
            output_preview=data.get("output_preview", ""),
            output_full=data.get("output_full"),
            process_time_ms=data.get("process_time_ms", 0),
            error=data.get("error", ""),
            metadata=data.get("metadata", {}),
        )

    def _cache_key_from_result(self, result: StrategyResult) -> datetime:
        cache_key = datetime.fromtimestamp(result.ts or datetime.now().timestamp())
        while cache_key in self.cache:
            cache_key += timedelta(microseconds=1)
        return cache_key

    def _load_from_persistence(self):
        """从持久化存储加载固定长度历史数据。"""
        try:
            recent_signals = self.db.get("recentSignal")
            if isinstance(recent_signals, list):
                items = []
                for data in recent_signals:
                    if isinstance(data, dict):
                        items.append(self._deserialize_result(data))

                items.sort(key=lambda item: (item.ts, item.id))

                for result in items[-self.max_cache_size:]:
                    self.cache[self._cache_key_from_result(result)] = result
        except Exception as e:
            print(f"加载持久化数据失败: {e}")

    def update(self, result: StrategyResult, who=None):
        """更新流数据，仅写入 Stream cache，不做实时落库。"""
        with self._persist_lock:
            return self._emit(result)

    def get_recent(self, limit: int = 20) -> List[StrategyResult]:
        """获取最近的信号，按时间倒序返回。"""
        with self._persist_lock:
            cached = list(self.cache.values())
            return list(reversed(cached[-limit:]))

    def persist(self):
        """将当前固定长度缓存整体持久化到数据库。"""
        with self._persist_lock:
            if self._closed:
                return
            try:
                recent_results = list(reversed(self.get_recent(limit=self.max_cache_size)))
                recent_signals = [result.to_dict() for result in recent_results]
                self.db.upsert("recentSignal", recent_signals)
            except Exception as e:
                print(f"持久化信号流失败: {e}")

    def close(self, persist: bool = True):
        """关闭信号流，避免退出阶段重复写库。"""
        with self._persist_lock:
            if self._closed:
                return
            if persist:
                self.persist()
            self._closed = True

    def clear(self):
        """清空缓存和持久化存储。"""
        with self._persist_lock:
            self.clear_cache()
            try:
                if "recentSignal" in self.db:
                    del self.db["recentSignal"]
            except Exception as e:
                print(f"清空持久化存储失败: {e}")


def get_signal_stream() -> SignalStream:
    """获取信号流实例。"""
    return SignalStream()


def _close_signal_stream_on_shutdown():
    stream = SignalStream._instance
    if stream is None:
        return
    stream.close()