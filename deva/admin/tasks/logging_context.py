"""临时的日志上下文模块，替代已删除的 strategy.logging_context"""

from deva import log


def task_log(level: str, message: str, **extra):
    """记录任务日志"""
    payload = {"level": level.upper(), "source": "deva.admin.task", "message": str(message)}
    if extra:
        payload.update(extra)
    try:
        payload >> log
    except Exception:
        print(f"[{level.upper()}][deva.admin.task] {message}")


def log_task_event(level: str, message: str, task=None, **extra):
    """记录任务事件"""
    payload = {
        "level": level.upper(),
        "source": "deva.admin.task",
        "message": str(message)
    }
    if task:
        payload["task_id"] = getattr(task, "id", "unknown")
        payload["task_name"] = getattr(task, "name", "unknown")
    if extra:
        payload.update(extra)
    try:
        payload >> log
    except Exception:
        print(f"[{level.upper()}][deva.admin.task] {message}")
