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


async def run_ai_in_worker(coro):
    future = submit_ai_coro(coro)
    return await asyncio.wrap_future(future)


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
