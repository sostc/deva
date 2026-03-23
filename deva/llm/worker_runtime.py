"""Unified AI execution runtime with dedicated asyncio worker loop."""

from __future__ import annotations

import asyncio
import atexit
import threading
import warnings


_LOCK = threading.Lock()
_LOOP = None
_THREAD = None


def _ensure_loop():
    global _LOOP, _THREAD
    with _LOCK:
        if _LOOP is not None and _THREAD is not None and _THREAD.is_alive():
            return _LOOP
        loop = asyncio.new_event_loop()

        def _runner():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=_runner, name="deva-ai-worker-loop", daemon=True)
        thread.start()
        _LOOP = loop
        _THREAD = thread
        return loop


def submit_ai_coro(coro):
    loop = _ensure_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop)


async def run_ai_in_worker(coro, timeout: float = 60.0):
    """
    在工作线程中运行异步协程
    
    Args:
        coro: 要执行的协程
        timeout: 超时时间（秒），默认60秒
        
    Returns:
        协程的执行结果
        
    Raises:
        TimeoutError: 执行超时
        RuntimeError: 执行返回None或失败
    """
    try:
        future = submit_ai_coro(coro)
        result = await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)
        
        if result is None:
            raise RuntimeError("Worker thread returned None - possible crash or API error")
        
        return result
    except asyncio.TimeoutError:
        raise TimeoutError(f"LLM query timed out after {timeout} seconds")


def _is_in_async_context():
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def run_sync_in_worker(coro, timeout=None):
    if _is_in_async_context():
        warnings.warn(
            "run_sync_in_worker() called from async context. "
            "This will block the event loop. Use run_ai_in_worker() instead.",
            RuntimeWarning,
            stacklevel=2
        )
    future = submit_ai_coro(coro)
    return future.result(timeout=timeout)


def _shutdown():
    global _LOOP
    loop = _LOOP
    if loop is None:
        return
    if loop.is_running():
        loop.call_soon_threadsafe(loop.stop)


atexit.register(_shutdown)
