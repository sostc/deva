"""Naja 流式日志模块

实现"一切皆流"的思路，将数据源运行日志和任务执行结果存储到流中，
而不是 DB 表。提供实时流式查看能力。

主要流：
- NS('naja_datasource_log'): 数据源运行日志
- NS('naja_task_log'): 任务执行日志
- NS('naja_strategy_log'): 策略执行日志
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from deva import NS


@dataclass
class LogEntry:
    """日志条目"""
    id: str = ""
    ts: float = 0
    level: str = "INFO"
    source_type: str = ""
    source_id: str = ""
    source_name: str = ""
    message: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.ts == 0:
            self.ts = time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts,
            "level": self.level,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "message": self.message,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LogEntry":
        return cls(
            id=data.get("id", ""),
            ts=data.get("ts", 0),
            level=data.get("level", "INFO"),
            source_type=data.get("source_type", ""),
            source_id=data.get("source_id", ""),
            source_name=data.get("source_name", ""),
            message=data.get("message", ""),
            extra=data.get("extra", {}),
        )


class NajaLogStream:
    """Naja 流式日志管理器"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.datasource_log = NS(
            'naja_datasource_log',
            cache_max_len=100,
            description='数据源运行日志流'
        )
        self.task_log = NS(
            'naja_task_log',
            cache_max_len=100,
            description='任务执行日志流'
        )
        self.strategy_log = NS(
            'naja_strategy_log',
            cache_max_len=100,
            description='策略执行日志流'
        )

        self._initialized = True

    def log_datasource(self, level: str, source_id: str, source_name: str, message: str, **extra):
        """记录数据源日志"""
        entry = LogEntry(
            ts=time.time(),
            level=level,
            source_type="datasource",
            source_id=source_id,
            source_name=source_name,
            message=message,
            extra=extra,
        )
        self.datasource_log << entry

    def log_task(self, level: str, source_id: str, source_name: str, message: str, **extra):
        """记录任务日志"""
        entry = LogEntry(
            ts=time.time(),
            level=level,
            source_type="task",
            source_id=source_id,
            source_name=source_name,
            message=message,
            extra=extra,
        )
        self.task_log << entry

    def log_strategy(self, level: str, source_id: str, source_name: str, message: str, **extra):
        """记录策略日志"""
        entry = LogEntry(
            ts=time.time(),
            level=level,
            source_type="strategy",
            source_id=source_id,
            source_name=source_name,
            message=message,
            extra=extra,
        )
        self.strategy_log << entry

    def get_datasource_logs(self, limit: int = 20) -> List[LogEntry]:
        """获取数据源日志"""
        logs = list(self.datasource_log.cache.values())
        return list(reversed(logs[-limit:]))

    def get_task_logs(self, limit: int = 20) -> List[LogEntry]:
        """获取任务日志"""
        logs = list(self.task_log.cache.values())
        return list(reversed(logs[-limit:]))

    def get_strategy_logs(self, limit: int = 20) -> List[LogEntry]:
        """获取策略日志"""
        logs = list(self.strategy_log.cache.values())
        return list(reversed(logs[-limit:]))


_log_stream: Optional[NajaLogStream] = None


def get_log_stream() -> NajaLogStream:
    """获取流式日志管理器单例"""
    global _log_stream
    if _log_stream is None:
        _log_stream = NajaLogStream()
    return _log_stream


def log_datasource(level: str, source_id: str, source_name: str, message: str, **extra):
    """便捷函数：记录数据源日志"""
    get_log_stream().log_datasource(level, source_id, source_name, message, **extra)


def log_task(level: str, source_id: str, source_name: str, message: str, **extra):
    """便捷函数：记录任务日志"""
    get_log_stream().log_task(level, source_id, source_name, message, **extra)


def log_strategy(level: str, source_id: str, source_name: str, message: str, **extra):
    """便捷函数：记录策略日志"""
    get_log_stream().log_strategy(level, source_id, source_name, message, **extra)


class LogStreamUI:
    """流式日志 UI 渲染器"""

    def __init__(self):
        self.log_stream = get_log_stream()

    def render(self):
        """渲染日志查看界面"""
        try:
            from pywebio.output import put_tabs, put_table, put_html, put_markdown, clear
            from pywebio import start_server
        except ImportError:
            print("LogStreamUI requires pywebio")
            return

        clear()
        put_markdown("### 📊 Naja 流式日志")

        ds_logs = self.log_stream.get_datasource_logs(limit=30)
        task_logs = self.log_stream.get_task_logs(limit=30)
        strategy_logs = self.log_stream.get_strategy_logs(limit=30)

        def render_log_table(logs, title):
            if not logs:
                return put_html(f"<p style='color:#999;'>暂无日志</p>")

            rows = [["时间", "级别", "名称", "消息"]]
            for log in logs:
                ts_str = datetime.fromtimestamp(log.ts).strftime("%H:%M:%S")
                level_color = {
                    "INFO": "#22c55e",
                    "WARN": "#eab308",
                    "ERROR": "#ef4444",
                }.get(log.level, "#6b7280")

                rows.append([
                    ts_str,
                    f"<span style='color:{level_color};font-weight:bold;'>{log.level}</span>",
                    f"<code>{log.source_name}</code>",
                    log.message,
                ])

            return put_table(rows)

        tabs = [
            {"title": "📡 数据源日志", "content": render_log_table(ds_logs, "数据源")},
            {"title": "📋 任务日志", "content": render_log_table(task_logs, "任务")},
            {"title": "📈 策略日志", "content": render_log_table(strategy_logs, "策略")},
        ]

        from pywebio.output import put_tabs as pywebio_put_tabs
        pywebio_put_tabs(tabs)


def log_stream_page():
    """Web 页面：流式日志查看"""
    ui = LogStreamUI()
    ui.render()
