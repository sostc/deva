"""Dictionary 辅助函数"""

from __future__ import annotations

from typing import Optional

from ..scheduler import normalize_execution_mode
from deva.naja.register import SR


def _normalize_source_mode(source_mode: Optional[str], has_upload: bool, has_code: bool) -> str:
    raw = str(source_mode or "").strip().lower()
    if raw in {"upload", "task", "upload_and_task"}:
        return raw
    if has_upload and has_code:
        return "upload_and_task"
    if has_upload:
        return "upload"
    return "task"


def _task_type_from_refresh_config(execution_mode: str, scheduler_trigger: str) -> str:
    """从刷新配置推断任务类型（用于向后兼容）"""
    mode = normalize_execution_mode(execution_mode)
    trig = str(scheduler_trigger or "interval").strip().lower()
    if mode == "scheduler" and trig == "date":
        return "once"
    if mode == "event_trigger":
        return "event_trigger"
    if mode == "scheduler":
        return "schedule"
    return "interval"


def _build_refresh_task_code(entry_id: str, fetch_code: str) -> str:
    return f'''{fetch_code}

def _resolve_awaitable(value):
    import asyncio
    import inspect
    import threading

    if not inspect.isawaitable(value):
        return value

    try:
        running_loop = asyncio.get_running_loop()
        loop_running = running_loop.is_running()
    except RuntimeError:
        loop_running = False

    if not loop_running:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(value)
        finally:
            loop.close()

    box = {{"value": None, "error": None}}

    def _runner():
        loop = asyncio.new_event_loop()
        try:
            box["value"] = loop.run_until_complete(value)
        except Exception as e:
            box["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if box["error"] is not None:
        raise box["error"]
    return box["value"]

def execute(event=None):

    mgr = SR('dictionary_manager')
    entry = mgr.get("{entry_id}")
    if entry is None:
        return "dictionary_not_found"

    try:
        data = fetch_data()
        data = _resolve_awaitable(data)
        entry.apply_fresh_data(data)
        return "ok"
    except Exception as e:
        entry.mark_refresh_error(str(e))
        raise
'''


