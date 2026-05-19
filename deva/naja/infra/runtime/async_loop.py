"""
Async Loop Manager - 共享 asyncio Event Loop 管理器

避免在每个线程中重复创建 event loop，提高性能。
"""

import asyncio
import threading
from typing import Optional


class AsyncLoopManager:
    """
    共享 asyncio Event Loop 管理器
    
    使用方式：
        from deva.naja.infra.runtime.async_loop import get_shared_loop, run_async_in_thread
        
        # 获取共享 loop
        loop = get_shared_loop()
        
        # 在线程中安全运行协程
        def my_thread():
            run_async_in_thread(my_coro())
    
    线程安全：使用双检查锁定模式
    """
    
    _instance: Optional['AsyncLoopManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._initialized = True
        
    def get_loop(self) -> asyncio.AbstractEventLoop:
        """获取共享 event loop，不存在则创建"""
        if self._loop is None or self._loop.is_closed():
            with self._loop_lock:
                if self._loop is None or self._loop.is_closed():
                    self._loop = asyncio.new_event_loop()
                    self._thread = threading.Thread(
                        target=self._run_loop_forever,
                        args=(self._loop,),
                        daemon=True,
                        name='async-loop-manager'
                    )
                    self._thread.start()
        return self._loop
    
    def _run_loop_forever(self, loop: asyncio.AbstractEventLoop):
        """在新线程中运行 event loop"""
        asyncio.set_event_loop(loop)
        loop.run_forever()
    
    def run_async_in_thread(self, coro):
        """
        在共享 loop 中安全运行协程
        
        Args:
            coro: 协程对象
            
        Returns:
            asyncio.Future: 可用于等待结果
        """
        loop = self.get_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop)
    
    def close(self):
        """关闭共享 loop"""
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop.close()
            self._loop = None


# 全局单例访问
_manager: Optional[AsyncLoopManager] = None


def get_async_loop_manager() -> AsyncLoopManager:
    """获取 AsyncLoopManager 单例"""
    global _manager
    if _manager is None:
        _manager = AsyncLoopManager()
    return _manager


def get_shared_loop() -> asyncio.AbstractEventLoop:
    """获取共享 event loop"""
    return get_async_loop_manager().get_loop()


def run_async_in_thread(coro):
    """在共享 loop 中运行协程"""
    return get_async_loop_manager().run_async_in_thread(coro)
