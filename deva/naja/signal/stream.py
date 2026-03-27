"""信号流模块

提供注意力感知的信号流实现：
1. 固定缓存长度的信号流
2. 根据 QueryState 动态计算信号优先级
3. 分级路由：高优先级、中优先级、低优先级
4. 接入 deva/naja 统一 exit 流程持久化
"""

import threading
import time
from datetime import datetime, timedelta
from typing import List, Optional, Callable

from deva import NB, Stream, log, when
from deva.naja.strategy.result_store import StrategyResult


class SignalStream(Stream):
    """注意力感知的信号流。

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局信号总线：SignalStream 是策略执行结果的全局信号总线，所有策略的
       执行结果都发送到同一个信号流。如果存在多个实例，会导致信号丢失或重复。

    2. 优先级语义：信号的优先级（high/medium/low）是全局语义，需要所有地方
       看到同一个优先级划分。

    3. 状态一致性：信号历史缓存、持久化状态等需要在全系统保持一致。

    4. 资源管理：数据库连接（NB）是系统资源，应该全局唯一。

    5. 这是流式计算系统的设计选择，不是过度工程。
    ================================================================================
    """

    _instance = None
    _shutdown_hook_registered = False
    _CACHE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365 * 10

    HIGH_PRIORITY_THRESHOLD = 0.7
    LOW_PRIORITY_THRESHOLD = 0.3

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

        self._query_state = None
        self._query_state_lock = threading.Lock()

        self._high_priority_stream: Optional[Stream] = None
        self._medium_priority_stream: Optional[Stream] = None
        self._low_priority_stream: Optional[Stream] = None

        loaded_count = self._load_from_persistence()
        self._register_shutdown_hook()
        self._initialized = True
        print(f"📊 初始化信号流: 加载历史信号({loaded_count})")

    @classmethod
    def _register_shutdown_hook(cls):
        if cls._shutdown_hook_registered:
            return
        when('exit', source=log).then(_close_signal_stream_on_shutdown)
        cls._shutdown_hook_registered = True

    def set_query_state(self, query_state):
        """设置 QueryState 用于优先级计算"""
        with self._query_state_lock:
            self._query_state = query_state

    def get_query_state(self):
        """获取当前的 QueryState"""
        with self._query_state_lock:
            return self._query_state

    def _compute_priority(self, result: StrategyResult) -> float:
        """计算信号优先级"""
        if isinstance(result, StrategyResult):
            return result.compute_priority(self._query_state)
        return 0.5

    def _get_priority_level(self, result: StrategyResult) -> str:
        """根据优先级分类信号"""
        priority = self._compute_priority(result)
        if priority >= self.HIGH_PRIORITY_THRESHOLD:
            return "high"
        elif priority >= self.LOW_PRIORITY_THRESHOLD:
            return "medium"
        else:
            return "low"

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
            priority=data.get("priority", 0.5),
            attention_score=data.get("attention_score", 0.0),
            matches_attention_focus=data.get("matches_attention_focus", False),
            matches_held_symbol=data.get("matches_held_symbol", False),
            tags=data.get("tags", []),
        )

    def _cache_key_from_result(self, result: StrategyResult) -> datetime:
        ts = result.ts if result.ts and result.ts > 0 else datetime.now().timestamp()
        cache_key = datetime.fromtimestamp(ts)
        while cache_key in self.cache:
            cache_key += timedelta(microseconds=1)
        return cache_key

    def _load_from_persistence(self) -> int:
        """从持久化存储加载固定长度历史数据。"""
        count = 0
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
                count = len(items)
        except Exception as e:
            print(f"加载持久化数据失败: {e}")
        return count

    def update(self, result: StrategyResult, who=None):
        """更新流数据，添加注意力感知路由。"""
        with self._persist_lock:
            if not isinstance(result, StrategyResult):
                result = StrategyResult(
                    id="",
                    strategy_id="",
                    strategy_name="",
                    ts=result.ts if hasattr(result, 'ts') else time.time(),
                    success=True,
                    output_full=result
                )

            priority = self._compute_priority(result)
            result.priority = priority

            cache_key = self._cache_key_from_result(result)
            self.cache[cache_key] = result

            return self._emit(result)

    def get_recent(self, limit: int = 20, priority_level: str = None) -> List[StrategyResult]:
        """获取最近的信号，按时间倒序返回。

        Args:
            limit: 返回数量限制
            priority_level: 可选过滤 'high', 'medium', 'low'
        """
        with self._persist_lock:
            cached = list(self.cache.values())

            if priority_level:
                cached = [r for r in cached if self._get_priority_level(r) == priority_level]

            return list(reversed(cached[-limit:]))

    def get_high_priority_stream(self) -> Stream:
        """获取高优先级信号流（priority >= 0.7）"""
        if self._high_priority_stream is None:
            self._high_priority_stream = self.filter(
                lambda r: isinstance(r, StrategyResult) and r.priority >= self.HIGH_PRIORITY_THRESHOLD
            )
        return self._high_priority_stream

    def get_medium_priority_stream(self) -> Stream:
        """获取中优先级信号流（0.3 <= priority < 0.7）"""
        if self._medium_priority_stream is None:
            self._medium_priority_stream = self.filter(
                lambda r: isinstance(r, StrategyResult) and self.LOW_PRIORITY_THRESHOLD <= r.priority < self.HIGH_PRIORITY_THRESHOLD
            )
        return self._medium_priority_stream

    def get_low_priority_stream(self) -> Stream:
        """获取低优先级信号流（priority < 0.3）"""
        if self._low_priority_stream is None:
            self._low_priority_stream = self.filter(
                lambda r: isinstance(r, StrategyResult) and r.priority < self.LOW_PRIORITY_THRESHOLD
            )
        return self._low_priority_stream

    def get_stream_by_priority(self, priority: str) -> Stream:
        """根据优先级名称获取对应的流

        Args:
            priority: 'high', 'medium', 'low'
        """
        if priority == "high":
            return self.get_high_priority_stream()
        elif priority == "medium":
            return self.get_medium_priority_stream()
        elif priority == "low":
            return self.get_low_priority_stream()
        return self

    def persist(self):
        """将当前固定长度缓存整体持久化到数据库。"""
        with self._persist_lock:
            if self._closed:
                return
            try:
                recent_results = list(reversed(self.get_recent(limit=self.max_cache_size)))
                recent_signals = []
                for result in recent_results:
                    d = {
                        "id": result.id,
                        "strategy_id": result.strategy_id,
                        "strategy_name": result.strategy_name,
                        "ts": result.ts,
                        "success": result.success,
                        "input_preview": result.input_preview,
                        "output_preview": result.output_preview,
                        "output_full": result.output_full,
                        "process_time_ms": result.process_time_ms,
                        "error": result.error,
                        "metadata": result.metadata,
                        "priority": result.priority,
                        "attention_score": result.attention_score,
                        "matches_attention_focus": result.matches_attention_focus,
                        "matches_held_symbol": result.matches_held_symbol,
                        "tags": result.tags,
                    }
                    recent_signals.append(d)
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
