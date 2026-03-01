"""Unified partial refresh helpers for admin panels."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Optional


def trigger_partial_refresh(
    ctx: dict,
    refresh_key: str,
    fallback_js: str = "location.reload()",
) -> bool:
    """Trigger a partial refresh callback from sync context."""
    callback = ctx.get(refresh_key)
    if callable(callback):
        try:
            result = callback()
            if inspect.isawaitable(result):
                run_async = ctx.get("run_async")
                if callable(run_async):
                    run_async(result)
                    return True
            else:
                return True
        except Exception:
            pass

    run_js = ctx.get("run_js")
    if callable(run_js):
        run_js(fallback_js)
        return False
    return False


async def await_partial_refresh(
    ctx: dict,
    refresh_key: str,
    fallback_js: str = "location.reload()",
) -> bool:
    """Await a partial refresh callback from async context."""
    callback = ctx.get(refresh_key)
    if callable(callback):
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
            return True
        except Exception:
            pass

    run_js = ctx.get("run_js")
    if callable(run_js):
        run_js(fallback_js)
        return False
    return False

