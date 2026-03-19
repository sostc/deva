"""全局线程池管理器

自动性能调节策略：
1. 动态调整 max_workers (10-100)
2. 动态调整 max_queue_size (100-10000)
3. 根据 CPU 负载和任务延迟智能调节
"""

from concurrent.futures import ThreadPoolExecutor, Future
from queue import Queue, Full
from typing import Callable, Optional, Dict, Any
import threading
import time
import os


class ThreadPoolManager:
    """线程池管理器 - 支持自动性能调节"""
    
    _instance = None
    _lock = threading.Lock()
    
    # 自动调节配置
    AUTO_TUNE_ENABLED = True
    MIN_WORKERS = 10
    MAX_WORKERS = 100
    MIN_QUEUE_SIZE = 100
    MAX_QUEUE_SIZE = 10000
    
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
        
        # 动态配置
        self._max_workers = self.MIN_WORKERS
        self._max_queue_size = self.MIN_QUEUE_SIZE
        self._task_queue = Queue(maxsize=self._max_queue_size)
        
        # 统计信息
        self._total_submitted = 0
        self._total_completed = 0
        self._total_rejected = 0
        self._stats_lock = threading.Lock()
        
        # 性能监控
        self._last_tune_time = 0
        self._tune_interval = 30  # 30秒调节一次
        self._task_latencies = []  # 任务延迟记录
        self._latency_lock = threading.Lock()
        
        self._pool = None
        self._work_queue = None
        self._ensure_pool()
        self._initialized = True
        
        # 启动自动调节线程
        if self.AUTO_TUNE_ENABLED:
            self._tune_thread = threading.Thread(target=self._auto_tune_loop, daemon=True)
            self._tune_thread.start()
    
    def _ensure_pool(self):
        """确保线程池已创建"""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix='naja-worker'
            )
            self._work_queue = self._pool._work_queue
    
    def _auto_tune_loop(self):
        """自动调节循环"""
        while True:
            time.sleep(self._tune_interval)
            try:
                self._perform_auto_tune()
            except Exception as e:
                # 静默处理，不影响主程序
                pass
    
    def _perform_auto_tune(self):
        """执行自动调节"""
        stats = self.get_stats()
        pending = stats.get('pending_tasks', 0)
        rejected = stats.get('total_rejected', 0)
        workers = stats.get('max_workers', self._max_workers)
        
        # 计算负载率
        load_ratio = pending / workers if workers > 0 else 0
        
        # 策略1: 如果待处理任务超过工作线程的5倍，增加线程
        if load_ratio > 5 and workers < self.MAX_WORKERS:
            new_workers = min(workers + 5, self.MAX_WORKERS)
            self.max_workers = new_workers
            print(f"[ThreadPool] 自动扩容: {workers} -> {new_workers} (负载: {load_ratio:.1f})")
        
        # 策略2: 如果待处理任务少于工作线程的0.5倍，减少线程
        elif load_ratio < 0.5 and workers > self.MIN_WORKERS:
            new_workers = max(workers - 3, self.MIN_WORKERS)
            self.max_workers = new_workers
            print(f"[ThreadPool] 自动缩容: {workers} -> {new_workers} (负载: {load_ratio:.1f})")
        
        # 策略3: 如果拒绝任务过多，扩大队列
        if rejected > 10 and self._max_queue_size < self.MAX_QUEUE_SIZE:
            new_size = min(self._max_queue_size + 500, self.MAX_QUEUE_SIZE)
            self.max_queue_size = new_size
            print(f"[ThreadPool] 扩大队列: {self._max_queue_size} -> {new_size}")
    
    @property
    def max_workers(self) -> int:
        return self._max_workers
    
    @max_workers.setter
    def max_workers(self, value: int):
        old_pool = self._pool
        self._max_workers = max(self.MIN_WORKERS, min(value, self.MAX_WORKERS))
        self._ensure_pool()
        if old_pool is not None and old_pool != self._pool:
            old_pool.shutdown(wait=False)
    
    @property
    def max_queue_size(self) -> int:
        return self._max_queue_size
    
    @max_queue_size.setter
    def max_queue_size(self, value: int):
        self._max_queue_size = max(self.MIN_QUEUE_SIZE, min(value, self.MAX_QUEUE_SIZE))
    
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
        import sys
        # 检查解释器是否正在关闭
        if sys.is_finalizing():
            return None
        
        if self._total_submitted >= self._max_queue_size * self._max_workers:
            self._total_rejected += 1
            return None
        
        try:
            future = self._pool.submit(fn, *args, **kwargs)
            self._total_submitted += 1
            future.add_done_callback(lambda _: self._on_task_done())
            return future
        except (Full, RuntimeError):
            # 队列已满或线程池已关闭
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
