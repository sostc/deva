"""策略和数据源日志上下文管理模块

提供增强的日志记录功能，自动携带策略和数据源上下文信息。
"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field


@dataclass
class LoggingContext:
    """日志上下文信息"""
    strategy_id: Optional[str] = None
    strategy_name: Optional[str] = None
    datasource_id: Optional[str] = None
    datasource_name: Optional[str] = None
    source_type: Optional[str] = None
    extra_context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {}
        if self.strategy_id:
            result["strategy_id"] = self.strategy_id
        if self.strategy_name:
            result["strategy_name"] = self.strategy_name
        if self.datasource_id:
            result["datasource_id"] = self.datasource_id
        if self.datasource_name:
            result["datasource_name"] = self.datasource_name
        if self.source_type:
            result["source_type"] = self.source_type
        
        result.update(self.extra_context)
        return result
    
    def format_source(self, base_source: str) -> str:
        """格式化日志来源"""
        parts = [base_source]
        
        if self.strategy_name:
            parts.append(f"strategy.{self.strategy_name}")
        elif self.datasource_name:
            parts.append(f"datasource.{self.datasource_name}")
            
        return ".".join(parts)


class LoggingContextManager:
    """日志上下文管理器
    
    使用线程本地存储来管理当前线程的日志上下文。
    """
    
    def __init__(self):
        self._local = threading.local()
    
    def get_context(self) -> LoggingContext:
        """获取当前线程的日志上下文"""
        if not hasattr(self._local, 'context'):
            self._local.context = LoggingContext()
        return self._local.context
    
    def set_context(self, context: LoggingContext):
        """设置当前线程的日志上下文"""
        self._local.context = context
    
    def clear_context(self):
        """清除当前线程的日志上下文"""
        if hasattr(self._local, 'context'):
            delattr(self._local, 'context')
    
    def update_context(self, **kwargs):
        """更新当前线程的日志上下文"""
        context = self.get_context()
        for key, value in kwargs.items():
            if hasattr(context, key):
                setattr(context, key, value)
            else:
                context.extra_context[key] = value
    
    @contextlib.contextmanager
    def strategy_context(self, strategy_id: str, strategy_name: str, **extra):
        """策略上下文管理器"""
        old_context = self.get_context()
        new_context = LoggingContext(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            extra_context=extra
        )
        self.set_context(new_context)
        
        try:
            yield new_context
        finally:
            self.set_context(old_context)
    
    @contextlib.contextmanager
    def datasource_context(self, datasource_id: str, datasource_name: str, source_type: str = None, **extra):
        """数据源上下文管理器"""
        old_context = self.get_context()
        new_context = LoggingContext(
            datasource_id=datasource_id,
            datasource_name=datasource_name,
            source_type=source_type,
            extra_context=extra
        )
        self.set_context(new_context)
        
        try:
            yield new_context
        finally:
            self.set_context(old_context)
    
    @contextlib.contextmanager
    def combined_context(self, strategy_id: str = None, strategy_name: str = None,
                        datasource_id: str = None, datasource_name: str = None,
                        source_type: str = None, **extra):
        """组合上下文管理器"""
        old_context = self.get_context()
        new_context = LoggingContext(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            datasource_id=datasource_id,
            datasource_name=datasource_name,
            source_type=source_type,
            extra_context=extra
        )
        self.set_context(new_context)
        
        try:
            yield new_context
        finally:
            self.set_context(old_context)


# 全局日志上下文管理器实例
logging_context_manager = LoggingContextManager()


def get_logging_context() -> LoggingContext:
    """获取当前日志上下文"""
    return logging_context_manager.get_context()


def with_strategy_logging(strategy_id: str, strategy_name: str, **extra):
    """策略日志上下文装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with logging_context_manager.strategy_context(strategy_id, strategy_name, **extra):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def with_datasource_logging(datasource_id: str, datasource_name: str, source_type: str = None, **extra):
    """数据源日志上下文装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with logging_context_manager.datasource_context(datasource_id, datasource_name, source_type, **extra):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def create_enhanced_log_record(level: str, message: str, source: str = None, **extra) -> Dict[str, Any]:
    """创建增强的日志记录
    
    自动包含当前日志上下文信息。
    """
    context = get_logging_context()
    
    # 构建基础日志记录
    record = {
        "level": level.upper(),
        "message": message,
        "source": context.format_source(source or "deva.strategy"),
        "ts": None,  # 将在格式化时设置
    }
    
    # 添加上下文信息
    context_dict = context.to_dict()
    if context_dict:
        record["extra"] = {**context_dict, **extra}
    elif extra:
        record["extra"] = extra
    
    return record


def strategy_log(level: str, message: str, strategy_id: str = None, strategy_name: str = None, **extra):
    """策略日志记录函数
    
    如果提供了strategy_id和strategy_name，将临时设置上下文。
    """
    if strategy_id or strategy_name:
        with logging_context_manager.strategy_context(strategy_id or "", strategy_name or "", **extra):
            record = create_enhanced_log_record(level, message, "deva.strategy")
    else:
        record = create_enhanced_log_record(level, message, "deva.strategy", **extra)
    
    try:
        from deva import log
        record >> log
    except Exception:
        # 如果deva日志系统不可用，使用标准logging
        logging.getLogger(record["source"]).log(
            getattr(logging, record["level"], logging.INFO),
            record["message"]
        )


def datasource_log(level: str, message: str, datasource_id: str = None, datasource_name: str = None, source_type: str = None, **extra):
    """数据源日志记录函数
    
    如果提供了datasource_id和datasource_name，将临时设置上下文。
    """
    if datasource_id or datasource_name:
        with logging_context_manager.datasource_context(datasource_id or "", datasource_name or "", source_type, **extra):
            record = create_enhanced_log_record(level, message, "deva.datasource")
    else:
        record = create_enhanced_log_record(level, message, "deva.datasource", **extra)
    
    try:
        from deva import log
        record >> log
    except Exception:
        # 如果deva日志系统不可用，使用标准logging
        logging.getLogger(record["source"]).log(
            getattr(logging, record["level"], logging.INFO),
            record["message"]
        )


def log_strategy_event(level: str, message: str, strategy_unit=None, **extra):
    """记录策略事件的便捷函数
    
    支持从StrategyUnit对象自动提取上下文信息。
    """
    if strategy_unit:
        strategy_log(
            level, message,
            strategy_id=strategy_unit.id,
            strategy_name=strategy_unit.name,
            **extra
        )
    else:
        strategy_log(level, message, **extra)


def log_datasource_event(level: str, message: str, datasource=None, **extra):
    """记录数据源事件的便捷函数
    
    支持从DataSource对象自动提取上下文信息。
    """
    if datasource:
        datasource_log(
            level, message,
            datasource_id=datasource.id,
            datasource_name=datasource.name,
            source_type=datasource.metadata.source_type.value if hasattr(datasource.metadata, 'source_type') else None,
            **extra
        )
    else:
        datasource_log(level, message, **extra)


def task_log(level: str, message: str, task_id: str = None, task_name: str = None, task_type: str = None, **extra):
    """任务日志记录函数
    
    如果提供了task_id和task_name，将临时设置上下文。
    """
    if task_id or task_name:
        with logging_context_manager.combined_context(
            strategy_id=None, strategy_name=None,
            datasource_id=None, datasource_name=None,
            source_type=task_type or "task", **extra
        ):
            record = create_enhanced_log_record(level, message, "deva.task", task_id=task_id, task_name=task_name, task_type=task_type, **extra)
    else:
        record = create_enhanced_log_record(level, message, "deva.task", task_id=task_id, task_name=task_name, task_type=task_type, **extra)
    
    try:
        from deva import log
        record >> log
    except Exception:
        # 如果deva日志系统不可用，使用标准logging
        logging.getLogger(record["source"]).log(
            getattr(logging, record["level"], logging.INFO),
            record["message"]
        )


def log_task_event(level: str, message: str, task_unit=None, **extra):
    """记录任务事件的便捷函数
    
    支持从TaskUnit对象自动提取上下文信息。
    """
    if task_unit:
        task_log(
            level, message,
            task_id=task_unit.id,
            task_name=task_unit.name,
            task_type=task_unit.metadata.task_type.value if hasattr(task_unit.metadata, 'task_type') else None,
            **extra
        )
    else:
        task_log(level, message, **extra)