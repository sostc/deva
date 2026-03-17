"""临时的错误处理模块，替代已删除的 strategy.error_handler"""

from dataclasses import dataclass
from typing import List, Dict, Any
import time


class ErrorLevel:
    """错误级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory:
    """错误类别"""
    EXECUTION = "execution"
    COMPILATION = "compilation"
    NETWORK = "network"
    DATABASE = "database"
    OTHER = "other"


@dataclass
class ErrorRecord:
    """错误记录"""
    level: str
    category: str
    message: str
    timestamp: float = time.time()
    details: Dict[str, Any] = None


class ErrorHandler:
    """错误处理器"""
    
    def __init__(self, unit=None):
        self._errors: List[ErrorRecord] = []
        self._unit = unit
    
    def record_error(self, level: str, category: str, message: str, **details):
        """记录错误"""
        error = ErrorRecord(
            level=level,
            category=category,
            message=message,
            details=details
        )
        self._errors.append(error)
    
    def get_errors(self, limit: int = 100) -> List[ErrorRecord]:
        """获取错误记录"""
        return self._errors[-limit:]
    
    def clear_errors(self):
        """清除错误记录"""
        self._errors.clear()


class GlobalErrorCollector:
    """全局错误收集器"""
    
    def __init__(self):
        self._handlers: Dict[str, ErrorHandler] = {}
    
    def get_handler(self, name: str) -> ErrorHandler:
        """获取错误处理器"""
        if name not in self._handlers:
            self._handlers[name] = ErrorHandler()
        return self._handlers[name]
    
    def record_error(self, name: str, level: str, category: str, message: str, **details):
        """记录错误"""
        handler = self.get_handler(name)
        handler.record_error(level, category, message, **details)
    
    def get_errors(self, name: str, limit: int = 100) -> List[ErrorRecord]:
        """获取错误记录"""
        handler = self.get_handler(name)
        return handler.get_errors(limit)
    
    def clear_errors(self, name: str):
        """清除错误记录"""
        handler = self.get_handler(name)
        handler.clear_errors()


_global_error_collector = GlobalErrorCollector()


def get_global_error_collector() -> GlobalErrorCollector:
    """获取全局错误收集器"""
    return _global_error_collector
