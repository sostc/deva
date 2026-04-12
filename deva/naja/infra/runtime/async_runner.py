"""统一的异步执行器 - 解决事件循环嵌套问题"""

import asyncio
import concurrent.futures
from typing import Any, Callable, Optional
from functools import wraps
import threading


class AsyncRunner:
    """
    统一的异步执行器

    在任何上下文中安全运行协程函数：
    - 如果当前线程有事件循环，使用线程池执行
    - 如果当前线程没有事件循环，可以创建新的
    """

    _shared_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
    _executor_lock = threading.Lock()

    @classmethod
    def get_executor(cls) -> concurrent.futures.ThreadPoolExecutor:
        """获取共享线程池"""
        if cls._shared_executor is None or cls._shared_executor._shutdown:
            with cls._executor_lock:
                if cls._shared_executor is None or cls._shared_executor._shutdown:
                    cls._shared_executor = concurrent.futures.ThreadPoolExecutor(
                        max_workers=4,
                        thread_name_prefix="async_runner_"
                    )
        return cls._shared_executor

    @classmethod
    def run(cls, coro_func: Callable, *args, timeout: float = 30.0, **kwargs) -> Any:
        """
        运行协程函数

        Args:
            coro_func: 协程函数
            *args: 位置参数
            timeout: 超时时间（秒）
            **kwargs: 关键字参数

        Returns:
            协程函数的返回值

        Raises:
            TimeoutError: 执行超时
            Exception: 协程函数执行失败
        """
        try:
            loop = asyncio.get_running_loop()
            return cls._run_in_executor(loop, coro_func, *args, **kwargs)
        except RuntimeError:
            return cls._run_in_new_loop(coro_func, *args, **kwargs)

    @classmethod
    def _run_in_executor(cls, loop: asyncio.AbstractEventLoop, coro_func: Callable, *args, **kwargs) -> Any:
        """在已有事件循环的线程中执行"""
        executor = cls.get_executor()
        future = executor.submit(asyncio.run, coro_func(*args, **kwargs))
        return cls._wait_for_future(future, timeout=30)

    @classmethod
    def _run_in_new_loop(cls, coro_func: Callable, *args, **kwargs) -> Any:
        """在没有事件循环的线程中执行"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro_func(*args, **kwargs))
        finally:
            loop.close()

    @classmethod
    def _wait_for_future(cls, future: concurrent.futures.Future, timeout: float) -> Any:
        """等待 Future 并处理超时"""
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError(f"异步执行超时 ({timeout}秒)")

    @classmethod
    def shutdown(cls, wait: bool = True):
        """关闭线程池"""
        if cls._shared_executor is not None:
            cls._shared_executor.shutdown(wait=wait)
            cls._shared_executor = None


def async_safe(coro_func: Callable) -> Callable:
    """
    装饰器：使协程函数在调用时自动选择正确的执行方式

    用法:
        @async_safe
        async def my_async_func():
            ...

        # 在任何上下文中调用
        result = my_async_func()
    """
    @wraps(coro_func)
    def wrapper(*args, **kwargs):
        return AsyncRunner.run(coro_func, *args, **kwargs)
    return wrapper


class AsyncContext:
    """
    异步上下文管理器，用于需要共享事件循环的场景

    用法:
        with AsyncContext() as loop:
            # 在这个上下文中可以安全地创建任务
            task = loop.create_task(some_coro())
    """

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> asyncio.AbstractEventLoop:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        def run_loop():
            self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        return self._loop

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=5)
            self._loop.close()
            self._loop = None

    def create_task(self, coro):
        """在线程安全的方式创建任务"""
        if self._loop is None:
            raise RuntimeError("AsyncContext not entered")
        return self._loop.create_task(coro)


__all__ = ['AsyncRunner', 'async_safe', 'AsyncContext']
