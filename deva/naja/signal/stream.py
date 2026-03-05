"""信号流模块

提供固定缓存长度的信号流实现，支持持久化存储
"""

from collections import deque
from datetime import datetime
from typing import List, Optional, Any

from deva import Stream, NB
from deva.naja.strategy.result_store import StrategyResult


class SignalStream(Stream):
    """固定缓存长度的信号流
    
    用于存储策略产出的结果，支持固定缓存长度和持久化存储
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, max_cache_size: int = 100, persist_name: str = "naja_signals", **kwargs):
        """初始化信号流
        
        Args:
            max_cache_size: 最大缓存长度
            persist_name: 持久化存储名称
            **kwargs: 其他参数
        """
        if not hasattr(self, "_initialized") or not self._initialized:
            super().__init__(**kwargs)
            
            # 固定长度缓存
            self.max_cache_size = max_cache_size
            self.cache = deque(maxlen=max_cache_size)
            
            # 持久化存储
            self.persist_name = persist_name
            self.db = NB(persist_name, key_mode='time')
            
            # 加载持久化数据
            self._load_from_persistence()
            
            self._initialized = True
    
    def _load_from_persistence(self):
        """从持久化存储加载数据"""
        try:
            # 获取所有键并按时间排序
            keys = list(self.db.keys())
            keys.sort(reverse=True)  # 时间倒序
            
            # 加载最近的 max_cache_size 条数据
            for key in keys[:self.max_cache_size]:
                data = self.db.get(key)
                if isinstance(data, dict):
                    # 转换为 StrategyResult 对象
                    result = StrategyResult(
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
                        metadata=data.get("metadata", {})
                    )
                    # 从左侧添加，保持时间倒序
                    self.cache.appendleft(result)
        except Exception as e:
            print(f"加载持久化数据失败: {e}")
    
    def update(self, result: StrategyResult, who=None):
        """更新流数据
        
        Args:
            result: 策略执行结果
            who: 上游流
        """
        # 添加到缓存
        self.cache.appendleft(result)
        
        # 立即持久化存储
        try:
            # 使用时间戳作为键
            key = f"{result.strategy_id}:{result.id}"
            self.db.upsert(key, result.to_dict())
        except Exception as e:
            print(f"持久化存储失败: {e}")
        
        # 发送到下游
        return self._emit(result)
    
    def get_recent(self, limit: int = 20) -> List[StrategyResult]:
        """获取最近的信号
        
        Args:
            limit: 返回数量限制
            
        Returns:
            最近的策略执行结果列表
        """
        return list(self.cache)[:limit]
    
    def clear(self):
        """清空缓存和持久化存储"""
        self.cache.clear()
        try:
            self.db.clear()
        except Exception as e:
            print(f"清空持久化存储失败: {e}")


def get_signal_stream() -> SignalStream:
    """获取信号流实例
    
    Returns:
        SignalStream 实例
    """
    return SignalStream()
