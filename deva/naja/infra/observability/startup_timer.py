"""启动性能监控工具

提供启动各阶段的计时能力，用于分析和优化启动性能。

使用方式：

    from deva.naja.infra.observability.startup_timer import StartupTimer

    StartupTimer.start("加载数据源")
    # ... 加载逻辑 ...
    StartupTimer.end("加载数据源")

    # 或使用装饰器
    @timed("我的函数")
    def my_function():
        pass

    # 生成报告
    print(StartupTimer.get_report())
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class TimerEntry:
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    children: List['TimerEntry'] = field(default_factory=list)
    error: Optional[str] = None


class StartupTimer:
    """启动性能计时器"""

    _instance: Optional['StartupTimer'] = None
    _entries: List[TimerEntry] = []
    _stack: List[TimerEntry] = []
    _enabled: bool = True
    _startup_start: float = 0.0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def enable(cls):
        cls._enabled = True

    @classmethod
    def disable(cls):
        cls._enabled = False

    @classmethod
    def reset(cls):
        """重置计时器"""
        cls._entries = []
        cls._stack = []
        cls._startup_start = time.time()
        logger.info("⏱️ StartupTimer 已重置")

    @classmethod
    def start(cls, name: str):
        """开始计时"""
        if not cls._enabled:
            return

        if not cls._startup_start:
            cls._startup_start = time.time()

        entry = TimerEntry(name=name, start_time=time.time())

        if cls._stack:
            cls._stack[-1].children.append(entry)
        else:
            cls._entries.append(entry)

        cls._stack.append(entry)

    @classmethod
    def end(cls, name: Optional[str] = None):
        """结束计时"""
        if not cls._enabled or not cls._stack:
            return

        entry = cls._stack.pop()
        entry.end_time = time.time()
        entry.duration_ms = (entry.end_time - entry.start_time) * 1000

        entry_name = name or entry.name
        if entry.duration_ms >= 100:
            logger.info(f"⏱️  {entry_name}: {entry.duration_ms:.2f}ms")
        else:
            logger.debug(f"⏱️  {entry_name}: {entry.duration_ms:.2f}ms")

    @classmethod
    def record_error(cls, name: str, error: str):
        """记录错误"""
        if not cls._entries:
            return

        def find_and_mark(entries: List[TimerEntry]):
            for entry in entries:
                if entry.name == name:
                    entry.error = error
                    return True
                if find_and_mark(entry.children):
                    return True
            return False

        find_and_mark(cls._entries)

    @classmethod
    @contextmanager
    def timer(cls, name: str):
        """上下文管理器计时"""
        cls.start(name)
        try:
            yield
        except Exception as e:
            cls.record_error(name, str(e))
            raise
        finally:
            cls.end(name)

    @classmethod
    def get_report(cls) -> str:
        """生成启动报告"""
        if not cls._entries:
            return "No startup timing data"

        total_time = time.time() - cls._startup_start if cls._startup_start else 0

        lines = ["\n" + "=" * 60, "🚀 启动性能报告", "=" * 60]
        lines.append(f"总启动时间: {total_time * 1000:.2f}ms")

        def _print_entry(entry: TimerEntry, indent: int = 0, siblings: int = 0):
            prefix = "  " * indent
            bar = "├─ " if indent > 0 and siblings > 0 else ("└─ " if indent > 0 else "")

            if entry.duration_ms is not None:
                pct = (entry.duration_ms / (total_time * 1000) * 100) if total_time > 0 else 0
                error_str = f" ⚠️ {entry.error}" if entry.error else ""
                lines.append(f"{prefix}{bar}{entry.name}: {entry.duration_ms:.2f}ms ({pct:.1f}%){error_str}")
            else:
                lines.append(f"{prefix}{bar}{entry.name}: (incomplete)")

            for i, child in enumerate(entry.children):
                _print_entry(child, indent + 1, len(entry.children) - 1)

        for i, entry in enumerate(cls._entries):
            _print_entry(entry, indent=0, siblings=len(cls._entries) - 1)

        lines.append("-" * 60)
        lines.append(f"总计时项: {len(cls._entries)}")
        lines.append("=" * 60 + "\n")

        return "\n".join(lines)

    @classmethod
    def get_summary(cls) -> Dict[str, float]:
        """获取启动摘要"""
        def sum_duration(entries: List[TimerEntry]) -> float:
            total = 0.0
            for entry in entries:
                if entry.duration_ms:
                    total += entry.duration_ms
                total += sum_duration(entry.children)
            return total

        total = sum_duration(cls._entries)
        return {
            "total_ms": total,
            "total_seconds": total / 1000,
            "item_count": len(cls._entries),
        }


def timed(name: Optional[str] = None):
    """装饰器：计时函数执行时间"""
    def decorator(func):
        timer_name = name or func.__name__

        def wrapper(*args, **kwargs):
            StartupTimer.start(timer_name)
            try:
                return func(*args, **kwargs)
            finally:
                StartupTimer.end(timer_name)

        return wrapper
    return decorator
