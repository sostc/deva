"""全局线程池管理器"""

from concurrent.futures import ThreadPoolExecutor, Future
from queue import Queue, Full
from typing import Callable, Optional, Dict, Any
import threading
import time


class ThreadPoolManager:
    """线程池管理器"""
    
    _instance = None
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
        
        self._max_workers = 20
        self._max_queue_size = 1000
        self._task_queue = Queue(maxsize=self._max_queue_size)
        self._total_submitted = 0
        self._total_completed = 0
        self._total_rejected = 0
        self._stats_lock = threading.Lock()
        self._pool = None
        self._work_queue = None
        self._ensure_pool()
        self._initialized = True
    
    def _ensure_pool(self):
        """确保线程池已创建"""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix='naja-worker'
            )
            self._work_queue = self._pool._work_queue
    
    @property
    def max_workers(self) -> int:
        return self._max_workers
    
    @max_workers.setter
    def max_workers(self, value: int):
        old_pool = self._pool
        self._max_workers = max(1, min(value, 100))
        self._ensure_pool()
        if old_pool is not None and old_pool != self._pool:
            old_pool.shutdown(wait=False)
    
    @property
    def max_queue_size(self) -> int:
        return self._max_queue_size
    
    @max_queue_size.setter
    def max_queue_size(self, value: int):
        self._max_queue_size = max(10, min(value, 10000))
    
    def get_stats(self) -> Dict[str, Any]:
        """获取线程池统计信息"""
        with self._stats_lock:
            stats = {
                'max_workers': self._max_workers,
                'queue_size': self._task_queue.qsize(),
                'max_queue_size': self._max_queue_size,
                'total_submitted': self._total_submitted,
                'total_completed': self._total_completed,
                'total_rejected': self._total_rejected,
                'pending_tasks': self._total_submitted - self._total_completed - self._total_rejected,
                'active_threads': self._pool._work_queue.qsize() if self._pool else 0
            }
            return stats
    
    def is_overloaded(self) -> bool:
        """检查是否过载"""
        if not self._pool:
            return False
        queue_ratio = self._work_queue.qsize() / self._max_workers
        return queue_ratio > 10
    
    def get_status_summary(self) -> str:
        """获取状态摘要"""
        stats = self.get_stats()
        return (
            f"线程池: {stats['active_threads']}/{stats['max_workers']} "
            f"活跃, 队列: {stats['pending_tasks']} 待处理, 已完成: {stats['total_completed']}"
        )
    
    def submit(self, fn: Callable, *args, **kwargs) -> Optional[Future]:
        """提交任务到线程池"""
        if self._total_submitted >= self._max_queue_size * self._max_workers:
            self._total_rejected += 1
            return None
        
        try:
            future = self._pool.submit(fn, *args, **kwargs)
            self._total_submitted += 1
            future.add_done_callback(lambda _: self._on_task_done())
            return future
        except Full:
            self._total_rejected += 1
            return None
    
    def _on_task_done(self):
        """任务完成回调"""
        with self._stats_lock:
            self._total_completed += 1
    
    def shutdown(self, wait: bool = True):
        """关闭线程池"""
        if self._pool:
            self._pool.shutdown(wait=wait)
            self._pool = None


_thread_pool: Optional[ThreadPoolManager] = None


def get_thread_pool() -> ThreadPoolManager:
    """获取全局线程池管理器单例"""
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolManager()
    return _thread_pool


def get_pool_stats() -> Dict[str, Any]:
    """获取线程池统计信息的快捷函数"""
    return get_thread_pool().get_stats()
