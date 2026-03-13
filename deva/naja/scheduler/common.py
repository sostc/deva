"""调度共享模块 - 统一的调度逻辑和工具函数

提供数据源、任务、字典等模块共享的调度配置、工具函数和管理器。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from deva import scheduler as deva_scheduler, timer as deva_timer


@dataclass
class SchedulerConfig:
    """统一的调度配置
    
    用于数据源、任务、字典等模块的调度配置。
    """
    execution_mode: str = "timer"
    scheduler_trigger: str = "interval"
    cron_expr: str = ""
    run_at: str = ""
    event_source: str = "log"
    event_condition: str = ""
    event_condition_type: str = "contains"
    interval_seconds: float = 60.0
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        """验证调度配置
        
        Returns:
            (是否有效, 错误信息)
        """
        if self.execution_mode == "scheduler":
            if self.scheduler_trigger == "cron" and not self.cron_expr:
                return False, "scheduler=cron 时 cron_expr 不能为空"
            if self.scheduler_trigger == "date" and not self.run_at:
                return False, "scheduler=date 时 run_at 不能为空"
        
        if self.execution_mode == "event_trigger":
            if self.event_condition_type == "python_expr" and not self.event_condition:
                return False, "event_condition_type=python_expr 时 event_condition 不能为空"
        
        return True, None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "execution_mode": self.execution_mode,
            "scheduler_trigger": self.scheduler_trigger,
            "cron_expr": self.cron_expr,
            "run_at": self.run_at,
            "event_source": self.event_source,
            "event_condition": self.event_condition,
            "event_condition_type": self.event_condition_type,
            "interval_seconds": self.interval_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SchedulerConfig":
        """从字典创建"""
        return cls(
            execution_mode=data.get("execution_mode", "timer"),
            scheduler_trigger=data.get("scheduler_trigger", "interval"),
            cron_expr=data.get("cron_expr", ""),
            run_at=data.get("run_at", ""),
            event_source=data.get("event_source", "log"),
            event_condition=data.get("event_condition", ""),
            event_condition_type=data.get("event_condition_type", "contains"),
            interval_seconds=float(data.get("interval_seconds", 60.0)),
        )


class SchedulerManager:
    """统一的调度器管理器（单例）
    
    管理共享的调度器实例，提供统一的作业添加/移除接口。
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._scheduler = None
                    cls._instance._timer_handles: Dict[str, Any] = {}
                    cls._event_sinks: Dict[str, Any] = {}
        return cls._instance
    
    def get_scheduler(self):
        """获取共享的调度器实例"""
        if self._scheduler is None:
            with self._lock:
                if self._scheduler is None:
                    self._scheduler = deva_scheduler(start=True)
        return self._scheduler
    
    def add_scheduler_job(self, name: str, func: Callable, trigger: str, **kwargs) -> dict:
        """添加调度作业
        
        Args:
            name: 作业名称
            func: 执行函数
            trigger: 触发器类型 (interval/cron/date)
            **kwargs: 触发器参数
            
        Returns:
            {"success": True} 或 {"success": False, "error": str}
        """
        try:
            scheduler = self.get_scheduler()
            
            # 先移除已存在的作业
            try:
                scheduler.remove_job(name)
            except Exception:
                pass
            
            scheduler.add_job(
                func=func,
                name=name,
                trigger=trigger,
                **kwargs
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def remove_scheduler_job(self, name: str):
        """移除调度作业"""
        try:
            scheduler = self.get_scheduler()
            scheduler.remove_job(name)
        except Exception:
            pass
    
    def start_timer(self, name: str, interval: float, func: Callable) -> dict:
        """启动定时器
        
        Args:
            name: 定时器名称
            interval: 间隔秒数
            func: 执行函数
            
        Returns:
            {"success": True} 或 {"success": False, "error": str}
        """
        try:
            # 先停止已存在的定时器
            self.stop_timer(name)
            
            timer_handle = deva_timer(
                interval=max(0.1, float(interval)),
                start=False,
                func=func,
            )
            timer_handle.start()
            self._timer_handles[name] = timer_handle
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def stop_timer(self, name: str):
        """停止定时器"""
        timer_handle = self._timer_handles.pop(name, None)
        if timer_handle is not None:
            try:
                timer_handle.stop()
            except Exception:
                pass
    
    def register_event_sink(self, name: str, event_sink: Any):
        """注册事件接收器"""
        # 先销毁已存在的
        self.unregister_event_sink(name)
        self._event_sinks[name] = event_sink
    
    def unregister_event_sink(self, name: str):
        """注销事件接收器"""
        event_sink = self._event_sinks.pop(name, None)
        if event_sink is not None:
            try:
                event_sink.destroy()
            except Exception:
                pass
    
    def clear_all(self, name_prefix: str = ""):
        """清除所有调度资源
        
        Args:
            name_prefix: 只清除名称以此前缀开头的资源
        """
        # 清除定时器
        for name in list(self._timer_handles.keys()):
            if not name_prefix or name.startswith(name_prefix):
                self.stop_timer(name)
        
        # 清除调度作业
        if self._scheduler is not None:
            for job in self._scheduler.get_jobs():
                if not name_prefix or job.name.startswith(name_prefix):
                    try:
                        self._scheduler.remove_job(job.name)
                    except Exception:
                        pass
        
        # 清除事件接收器
        for name in list(self._event_sinks.keys()):
            if not name_prefix or name.startswith(name_prefix):
                self.unregister_event_sink(name)


def parse_cron_expr(expr: str) -> Dict[str, str]:
    """解析 cron 表达式为字典格式
    
    Args:
        expr: cron 表达式字符串 (5段或6段)
        
    Returns:
        包含 cron 各部分的字典
        
    Raises:
        ValueError: 当表达式格式不正确时
    """
    parts = [p for p in str(expr or "").strip().split() if p]
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
        return {
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }
    if len(parts) == 6:
        second, minute, hour, day, month, day_of_week = parts
        return {
            "second": second,
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }
    raise ValueError("cron 表达式必须是 5 或 6 段")


def humanize_cron(expr: str) -> str:
    """将 cron 表达式转换为人类可读的描述
    
    Args:
        expr: cron 表达式
        
    Returns:
        人类可读的描述
    """
    cron = str(expr or "").strip()
    if not cron:
        return "按计划执行"
    
    parts = cron.split()
    if len(parts) != 5:
        return f"按计划执行（规则: {cron}）"
    
    minute, hour, day, month, weekday = parts
    
    # 每 N 分钟
    if minute.startswith("*/") and hour == "*" and day == "*" and month == "*" and weekday == "*":
        n = minute[2:]
        if n.isdigit():
            return f"每 {n} 分钟执行一次"
    
    # 每小时
    if hour == "*" and day == "*" and month == "*" and weekday == "*":
        if minute.isdigit():
            return f"每小时第 {int(minute):02d} 分执行"
    
    # 每天
    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and weekday == "*":
        return f"每天 {int(hour):02d}:{int(minute):02d} 执行"
    
    # 每周
    weekday_map = {
        "mon": "周一", "tue": "周二", "wed": "周三",
        "thu": "周四", "fri": "周五", "sat": "周六", "sun": "周日"
    }
    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and weekday.lower() in weekday_map:
        return f"每{weekday_map[weekday.lower()]} {int(hour):02d}:{int(minute):02d} 执行"
    
    # 每月
    if minute.isdigit() and hour.isdigit() and day.isdigit() and month == "*" and weekday == "*":
        return f"每月 {int(day)} 日 {int(hour):02d}:{int(minute):02d} 执行"
    
    return f"按计划执行（规则: {cron}）"


def normalize_execution_mode(
    execution_mode: Optional[str],
    task_type: Optional[str] = None
) -> str:
    """标准化执行模式
    
    Args:
        execution_mode: 执行模式字符串
        task_type: 任务类型（用于兼容旧版本）
        
    Returns:
        标准化的执行模式 (timer/scheduler/event_trigger)
    """
    raw = (execution_mode or task_type or "timer").strip().lower()
    mapping = {
        "interval": "timer",
        "once": "scheduler",
        "schedule": "scheduler",
        "cron": "scheduler",
        "timer": "timer",
        "scheduler": "scheduler",
        "eventtrigger": "event_trigger",
        "event_trigger": "event_trigger",
        "event": "event_trigger",
    }
    return mapping.get(raw, "timer")


def parse_hhmm(value: str) -> Optional[Tuple[int, int]]:
    """解析 HH:MM 格式的时间
    
    Args:
        value: 时间字符串
        
    Returns:
        (小时, 分钟) 元组，解析失败返回 None
    """
    raw = str(value or "").strip().replace("：", ":")
    parts = raw.split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except Exception:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour, minute


def preview_next_runs(cron_expr: str, count: int = 5) -> List[str]:
    """预览 cron 表达式的未来执行时间
    
    Args:
        cron_expr: cron 表达式
        count: 预览次数
        
    Returns:
        未来执行时间字符串列表
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
        import pytz
    except Exception:
        return []
    
    try:
        trigger = CronTrigger.from_crontab(
            str(cron_expr or "").strip(),
            timezone=pytz.timezone("Asia/Shanghai")
        )
        out = []
        now = datetime.now(pytz.timezone("Asia/Shanghai"))
        prev = None
        current = now
        for _ in range(max(1, count)):
            nxt = trigger.get_next_fire_time(prev, current)
            if not nxt:
                break
            out.append(nxt.strftime("%Y-%m-%d %H:%M:%S"))
            prev = nxt
            current = nxt
        return out
    except Exception:
        return []


def daily_time_to_cron(daily_time: str) -> str:
    """将每日时间转换为 cron 表达式
    
    Args:
        daily_time: 时间字符串 (HH:MM)
        
    Returns:
        cron 表达式
        
    Raises:
        ValueError: 当时间格式无效时
    """
    raw = str(daily_time or "03:00").strip().replace("：", ":")
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError("daily_time 格式应为 HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("daily_time 无效")
    return f"{minute} {hour} * * *"


def build_event_condition_checker(
    condition_type: str,
    condition: str
) -> Callable[[Any], bool]:
    """构建事件条件检查器
    
    Args:
        condition_type: 条件类型 (contains/python_expr)
        condition: 条件表达式
        
    Returns:
        条件检查函数
    """
    cond_type = str(condition_type or "contains").strip().lower()
    cond = str(condition or "")
    
    if cond_type == "contains":
        if not cond:
            return lambda x: True
        return lambda x: cond in str(x)
    
    if cond_type == "python_expr":
        if not cond:
            raise ValueError("event_condition_type=python_expr 时 event_condition 不能为空")
        compiled_expr = compile(cond, "<event_condition>", "eval")
        
        def _checker(x: Any) -> bool:
            return bool(eval(compiled_expr, {"__builtins__": __builtins__}, {"x": x}))
        
        return _checker
    
    raise ValueError(f"不支持的事件条件类型: {cond_type}")
