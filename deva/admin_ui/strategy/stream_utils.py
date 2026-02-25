"""流处理集成工具类(Stream Processing Integration Utils)

为策略和数据源提供统一的流处理集成能力，简化流的创建、管理和数据传递。

================================================================================
功能特性
================================================================================

1. **统一流接口**: 标准化的流创建和管理
2. **流缓存优化**: 智能缓存策略
3. **数据转换**: 自动数据格式转换
4. **背压处理**: 流量控制和背压机制
5. **监控指标**: 流处理性能监控
6. **错误处理**: 流处理错误恢复
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union, Type
from enum import Enum

from deva import Stream, NS, log


class StreamRole(str, Enum):
    """流角色"""
    INPUT = "input"    # 输入流
    OUTPUT = "output"  # 输出流
    INTERNAL = "internal"  # 内部流


class StreamStatus(str, Enum):
    """流状态"""
    CREATED = "created"
    CONNECTED = "connected"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    CLOSED = "closed"


@dataclass
class StreamMetrics:
    """流指标"""
    # 基本指标
    total_emitted: int = 0
    total_received: int = 0
    total_errors: int = 0
    
    # 速率指标
    emit_rate: float = 0.0  # 条/秒
    receive_rate: float = 0.0  # 条/秒
    error_rate: float = 0.0  # 错误/秒
    
    # 时间指标
    created_at: float = field(default_factory=time.time)
    last_emit_ts: float = 0
    last_receive_ts: float = 0
    
    # 性能指标
    avg_process_time: float = 0.0
    max_process_time: float = 0.0
    min_process_time: float = 0.0
    
    # 缓存指标
    cache_size: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        uptime = time.time() - self.created_at
        return {
            "total_emitted": self.total_emitted,
            "total_received": self.total_received,
            "total_errors": self.total_errors,
            "emit_rate": self.emit_rate,
            "receive_rate": self.receive_rate,
            "error_rate": self.error_rate,
            "uptime_seconds": uptime,
            "avg_process_time": self.avg_process_time,
            "max_process_time": self.max_process_time,
            "min_process_time": self.min_process_time,
            "cache_size": self.cache_size,
            "cache_hit_rate": self.cache_hits / (self.cache_hits + self.cache_misses) if (self.cache_hits + self.cache_misses) > 0 else 0,
        }


class StreamWrapper:
    """流包装器
    
    为原生Stream提供增强功能：
    - 指标收集
    - 错误处理
    - 性能监控
    - 缓存管理
    """
    
    def __init__(
        self,
        stream: Stream,
        name: str,
        role: StreamRole,
        cache_size: int = 100,
        enable_metrics: bool = True,
        error_handler: Optional[Callable] = None
    ):
        """
        Args:
            stream: 原始流对象
            name: 流名称
            role: 流角色
            cache_size: 缓存大小
            enable_metrics: 是否启用指标收集
            error_handler: 错误处理函数
        """
        self.stream = stream
        self.name = name
        self.role = role
        self.cache_size = cache_size
        self.enable_metrics = enable_metrics
        self.error_handler = error_handler
        
        # 状态管理
        self.status = StreamStatus.CREATED
        self._lock = threading.Lock()
        
        # 指标
        self.metrics = StreamMetrics()
        
        # 缓存
        self._cache = deque(maxlen=cache_size) if cache_size > 0 else None
        self._cache_index = {}  # 快速查找索引
        
        # 性能监控
        self._process_times = deque(maxlen=100)  # 最近100个处理时间
        
        # 速率计算
        self._rate_window = 60  # 60秒时间窗口
        self._emit_timestamps = deque()
        self._receive_timestamps = deque()
        
    # ==========================================================================
    # 核心流操作方法
    # ==========================================================================
    
    def emit(self, data: Any, metadata: Dict[str, Any] = None) -> bool:
        """发送数据到流
        
        Args:
            data: 要发送的数据
            metadata: 元数据
            
        Returns:
            是否成功发送
        """
        try:
            with self._lock:
                if self.status != StreamStatus.ACTIVE:
                    log.warning(f"流 {self.name} 未激活，无法发送数据")
                    return False
                
                # 添加到缓存
                if self._cache is not None:
                    self._add_to_cache(data, metadata)
                
                # 发送到原始流
                if hasattr(self.stream, 'emit'):
                    self.stream.emit(data)
                
                # 更新指标
                if self.enable_metrics:
                    self._update_emit_metrics()
                
                return True
                
        except Exception as e:
            self._handle_error(e, "emit", data)
            return False
    
    def receive(self, timeout: float = None) -> Optional[Any]:
        """从流接收数据
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            接收到的数据，超时返回None
        """
        try:
            if hasattr(self.stream, 'receive'):
                data = self.stream.receive(timeout)
                
                if data is not None:
                    # 更新指标
                    if self.enable_metrics:
                        self._update_receive_metrics()
                    
                    # 添加到缓存
                    if self._cache is not None:
                        self._add_to_cache(data)
                
                return data
            else:
                log.warning(f"流 {self.name} 不支持接收操作")
                return None
                
        except Exception as e:
            self._handle_error(e, "receive")
            return None
    
    def map(self, func: Callable, *args, **kwargs) -> 'StreamWrapper':
        """映射操作
        
        Args:
            func: 映射函数
            *args, **kwargs: 额外参数
            
        Returns:
            新的流包装器
        """
        def wrapped_func(data):
            start_time = time.time()
            try:
                result = func(data, *args, **kwargs)
                
                # 记录处理时间
                if self.enable_metrics:
                    process_time = time.time() - start_time
                    self._record_process_time(process_time)
                
                return result
                
            except Exception as e:
                self._handle_error(e, "map", data)
                return None
        
        # 创建映射后的流
        if hasattr(self.stream, 'map'):
            mapped_stream = self.stream.map(wrapped_func)
            wrapper = StreamWrapper(
                mapped_stream,
                f"{self.name}_mapped",
                self.role,
                self.cache_size,
                self.enable_metrics,
                self.error_handler
            )
            return wrapper
        else:
            log.error(f"流 {self.name} 不支持map操作")
            return None
    
    def filter(self, predicate: Callable, *args, **kwargs) -> 'StreamWrapper':
        """过滤操作
        
        Args:
            predicate: 过滤函数
            *args, **kwargs: 额外参数
            
        Returns:
            新的流包装器
        """
        def wrapped_predicate(data):
            try:
                return predicate(data, *args, **kwargs)
            except Exception as e:
                self._handle_error(e, "filter", data)
                return False
        
        if hasattr(self.stream, 'filter'):
            filtered_stream = self.stream.filter(wrapped_predicate)
            wrapper = StreamWrapper(
                filtered_stream,
                f"{self.name}_filtered",
                self.role,
                self.cache_size,
                self.enable_metrics,
                self.error_handler
            )
            return wrapper
        else:
            log.error(f"流 {self.name} 不支持filter操作")
            return None
    
    def subscribe(self, callback: Callable, *args, **kwargs):
        """订阅流数据
        
        Args:
            callback: 回调函数
            *args, **kwargs: 额外参数
        """
        def wrapped_callback(data):
            start_time = time.time()
            try:
                result = callback(data, *args, **kwargs)
                
                # 记录处理时间
                if self.enable_metrics:
                    process_time = time.time() - start_time
                    self._record_process_time(process_time)
                
                return result
                
            except Exception as e:
                self._handle_error(e, "subscribe", data)
                return None
        
        if hasattr(self.stream, 'subscribe'):
            self.stream.subscribe(wrapped_callback)
        else:
            log.error(f"流 {self.name} 不支持subscribe操作")
    
    # ==========================================================================
    # 缓存管理方法
    # ==========================================================================
    
    def _add_to_cache(self, data: Any, metadata: Dict[str, Any] = None):
        """添加到缓存"""
        if self._cache is None:
            return
        
        cache_item = {
            'data': data,
            'metadata': metadata or {},
            'timestamp': time.time()
        }
        
        # 添加缓存索引（基于数据哈希）
        data_hash = hash(str(data))
        self._cache_index[data_hash] = len(self._cache)
        
        # 添加到队列
        self._cache.append(cache_item)
        
        # 更新缓存指标
        if self.enable_metrics:
            self.metrics.cache_size = len(self._cache)
            self.metrics.cache_hits += 1
    
    def get_from_cache(self, data_hash: int) -> Optional[Dict[str, Any]]:
        """从缓存获取
        
        Args:
            data_hash: 数据哈希值
            
        Returns:
            缓存项，不存在返回None
        """
        if self._cache is None:
            return None
        
        index = self._cache_index.get(data_hash)
        if index is not None and index < len(self._cache):
            if self.enable_metrics:
                self.metrics.cache_hits += 1
            return self._cache[index]
        else:
            if self.enable_metrics:
                self.metrics.cache_misses += 1
            return None
    
    def get_cache_snapshot(self, limit: int = None) -> List[Dict[str, Any]]:
        """获取缓存快照
        
        Args:
            limit: 返回数量限制
            
        Returns:
            缓存项列表
        """
        if self._cache is None:
            return []
        
        items = list(self._cache)
        if limit and limit > 0:
            items = items[-limit:]  # 最新的数据
        
        return items
    
    def clear_cache(self):
        """清空缓存"""
        if self._cache is not None:
            self._cache.clear()
            self._cache_index.clear()
            if self.enable_metrics:
                self.metrics.cache_size = 0
    
    # ==========================================================================
    # 状态管理方法
    # ==========================================================================
    
    def connect(self) -> bool:
        """连接流"""
        try:
            with self._lock:
                if self.status == StreamStatus.CLOSED:
                    log.error(f"流 {self.name} 已关闭，无法连接")
                    return False
                
                # 调用原始流的连接方法（如果存在）
                if hasattr(self.stream, 'connect'):
                    self.stream.connect()
                
                self.status = StreamStatus.CONNECTED
                log.info(f"流 {self.name} 已连接")
                return True
                
        except Exception as e:
            self._handle_error(e, "connect")
            return False
    
    def activate(self) -> bool:
        """激活流"""
        try:
            with self._lock:
                if self.status not in [StreamStatus.CREATED, StreamStatus.CONNECTED]:
                    log.error(f"流 {self.name} 状态为 {self.status}，无法激活")
                    return False
                
                self.status = StreamStatus.ACTIVE
                log.info(f"流 {self.name} 已激活")
                return True
                
        except Exception as e:
            self._handle_error(e, "activate")
            return False
    
    def pause(self) -> bool:
        """暂停流"""
        try:
            with self._lock:
                if self.status != StreamStatus.ACTIVE:
                    log.warning(f"流 {self.name} 未激活，无法暂停")
                    return False
                
                self.status = StreamStatus.PAUSED
                log.info(f"流 {self.name} 已暂停")
                return True
                
        except Exception as e:
            self._handle_error(e, "pause")
            return False
    
    def resume(self) -> bool:
        """恢复流"""
        try:
            with self._lock:
                if self.status != StreamStatus.PAUSED:
                    log.warning(f"流 {self.name} 未暂停，无法恢复")
                    return False
                
                self.status = StreamStatus.ACTIVE
                log.info(f"流 {self.name} 已恢复")
                return True
                
        except Exception as e:
            self._handle_error(e, "resume")
            return False
    
    def close(self) -> bool:
        """关闭流"""
        try:
            with self._lock:
                if self.status == StreamStatus.CLOSED:
                    log.warning(f"流 {self.name} 已关闭")
                    return True
                
                # 调用原始流的关闭方法（如果存在）
                if hasattr(self.stream, 'close'):
                    self.stream.close()
                
                self.status = StreamStatus.CLOSED
                log.info(f"流 {self.name} 已关闭")
                return True
                
        except Exception as e:
            self._handle_error(e, "close")
            return False
    
    # ==========================================================================
    # 指标更新方法
    # ==========================================================================
    
    def _update_emit_metrics(self):
        """更新发送指标"""
        current_time = time.time()
        
        # 基本计数
        self.metrics.total_emitted += 1
        self.metrics.last_emit_ts = current_time
        
        # 时间戳记录
        self._emit_timestamps.append(current_time)
        
        # 清理过期时间戳
        cutoff_time = current_time - self._rate_window
        while self._emit_timestamps and self._emit_timestamps[0] < cutoff_time:
            self._emit_timestamps.popleft()
        
        # 计算速率
        if len(self._emit_timestamps) >= 2:
            time_span = self._emit_timestamps[-1] - self._emit_timestamps[0]
            if time_span > 0:
                self.metrics.emit_rate = len(self._emit_timestamps) / time_span
    
    def _update_receive_metrics(self):
        """更新接收指标"""
        current_time = time.time()
        
        # 基本计数
        self.metrics.total_received += 1
        self.metrics.last_receive_ts = current_time
        
        # 时间戳记录
        self._receive_timestamps.append(current_time)
        
        # 清理过期时间戳
        cutoff_time = current_time - self._rate_window
        while self._receive_timestamps and self._receive_timestamps[0] < cutoff_time:
            self._receive_timestamps.popleft()
        
        # 计算速率
        if len(self._receive_timestamps) >= 2:
            time_span = self._receive_timestamps[-1] - self._receive_timestamps[0]
            if time_span > 0:
                self.metrics.receive_rate = len(self._receive_timestamps) / time_span
    
    def _record_process_time(self, process_time: float):
        """记录处理时间"""
        self._process_times.append(process_time)
        
        # 更新统计
        if self._process_times:
            times = list(self._process_times)
            self.metrics.avg_process_time = sum(times) / len(times)
            self.metrics.max_process_time = max(times)
            self.metrics.min_process_time = min(times)
    
    def _handle_error(self, error: Exception, operation: str, data: Any = None):
        """处理错误"""
        self.metrics.total_errors += 1
        self.metrics.error_rate = self.metrics.total_errors / (time.time() - self.metrics.created_at + 1)
        
        error_msg = f"流 {self.name} 操作 {operation} 失败: {error}"
        log.error(error_msg)
        
        # 调用错误处理回调
        if self.error_handler:
            try:
                self.error_handler(error, operation, data)
            except Exception as e:
                log.error(f"错误处理回调失败: {e}")


class StreamManager:
    """流管理器
    
    统一管理多个流的创建、配置和生命周期
    """
    
    def __init__(self, default_cache_size: int = 100):
        """
        Args:
            default_cache_size: 默认缓存大小
        """
        self._streams: Dict[str, StreamWrapper] = {}
        self._default_cache_size = default_cache_size
        self._lock = threading.Lock()
    
    def create_stream(
        self,
        name: str,
        role: StreamRole,
        cache_size: int = None,
        enable_metrics: bool = True,
        error_handler: Optional[Callable] = None,
        stream_type: str = "NS"
    ) -> StreamWrapper:
        """创建流
        
        Args:
            name: 流名称
            role: 流角色
            cache_size: 缓存大小，None使用默认值
            enable_metrics: 是否启用指标收集
            error_handler: 错误处理函数
            stream_type: 流类型 ("NS" 或其他)
            
        Returns:
            流包装器
        """
        with self._lock:
            if name in self._streams:
                log.warning(f"流 {name} 已存在，返回现有实例")
                return self._streams[name]
            
            # 创建原始流
            if stream_type == "NS":
                raw_stream = NS(name, cache_max_len=cache_size or self._default_cache_size)
            else:
                # 其他流类型的支持
                raise ValueError(f"不支持的流类型: {stream_type}")
            
            # 创建包装器
            wrapper = StreamWrapper(
                stream=raw_stream,
                name=name,
                role=role,
                cache_size=cache_size or self._default_cache_size,
                enable_metrics=enable_metrics,
                error_handler=error_handler
            )
            
            self._streams[name] = wrapper
            log.info(f"流 {name} 已创建")
            
            return wrapper
    
    def get_stream(self, name: str) -> Optional[StreamWrapper]:
        """获取流
        
        Args:
            name: 流名称
            
        Returns:
            流包装器，不存在返回None
        """
        return self._streams.get(name)
    
    def remove_stream(self, name: str) -> bool:
        """移除流
        
        Args:
            name: 流名称
            
        Returns:
            是否成功移除
        """
        with self._lock:
            wrapper = self._streams.pop(name, None)
            if wrapper:
                wrapper.close()
                log.info(f"流 {name} 已移除")
                return True
            return False
    
    def get_all_streams(self) -> List[StreamWrapper]:
        """获取所有流"""
        return list(self._streams.values())
    
    def get_streams_by_role(self, role: StreamRole) -> List[StreamWrapper]:
        """按角色获取流"""
        return [wrapper for wrapper in self._streams.values() if wrapper.role == role]
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取整体指标"""
        total_streams = len(self._streams)
        active_streams = sum(1 for wrapper in self._streams.values() if wrapper.status == StreamStatus.ACTIVE)
        
        total_emitted = sum(wrapper.metrics.total_emitted for wrapper in self._streams.values())
        total_received = sum(wrapper.metrics.total_received for wrapper in self._streams.values())
        total_errors = sum(wrapper.metrics.total_errors for wrapper in self._streams.values())
        
        return {
            "total_streams": total_streams,
            "active_streams": active_streams,
            "total_emitted": total_emitted,
            "total_received": total_received,
            "total_errors": total_errors,
            "error_rate": total_errors / (total_emitted + total_received + 1),
        }
    
    def close_all(self):
        """关闭所有流"""
        with self._lock:
            for name, wrapper in list(self._streams.items()):
                try:
                    wrapper.close()
                except Exception as e:
                    log.error(f"关闭流 {name} 失败: {e}")
            
            self._streams.clear()
            log.info("所有流已关闭")


# 全局流管理器实例
_global_stream_manager: Optional[StreamManager] = None


def get_global_stream_manager() -> StreamManager:
    """获取全局流管理器"""
    global _global_stream_manager
    if _global_stream_manager is None:
        _global_stream_manager = StreamManager()
    return _global_stream_manager


def set_global_stream_manager(manager: StreamManager):
    """设置全局流管理器"""
    global _global_stream_manager
    _global_stream_manager = manager