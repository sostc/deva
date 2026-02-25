"""统一错误处理模块(Unified Error Handling Module)

为策略和数据源提供统一的错误收集、处理和上报机制。

================================================================================
功能特性
================================================================================

1. **错误收集**: 统一的错误记录和分类
2. **错误上报**: 支持多种上报方式（日志、UI、外部系统）
3. **错误分析**: 错误统计和趋势分析
4. **错误恢复**: 自动重试和降级处理
5. **错误展示**: 统一的错误展示界面
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Type

from deva import log


class ErrorLevel(str, Enum):
    """错误级别"""
    LOW = "low"      # 轻微错误，不影响功能
    MEDIUM = "medium"  # 中等错误，部分功能受影响
    HIGH = "high"    # 严重错误，核心功能受影响
    CRITICAL = "critical"  # 致命错误，系统不可用


class ErrorCategory(str, Enum):
    """错误分类"""
    CODE_EXECUTION = "code_execution"  # 代码执行错误
    DATA_VALIDATION = "data_validation"  # 数据验证错误
    NETWORK = "network"  # 网络错误
    SYSTEM = "system"  # 系统错误
    CONFIGURATION = "configuration"  # 配置错误
    DEPENDENCY = "dependency"  # 依赖错误
    UNKNOWN = "unknown"  # 未知错误


@dataclass
class ErrorRecord:
    """错误记录"""
    # 基本信息
    error_id: str
    timestamp: float
    level: ErrorLevel
    category: ErrorCategory
    
    # 错误详情
    message: str
    exception_type: str
    traceback: str
    
    # 上下文信息
    unit_id: str  # 策略ID或数据源ID
    unit_name: str
    unit_type: str  # "strategy" 或 "datasource"
    
    # 数据上下文
    data_preview: str = ""  # 数据预览（限制长度）
    data_type: str = ""  # 数据类型
    data_size: int = 0  # 数据大小
    
    # 系统上下文
    memory_usage: int = 0  # 内存使用（字节）
    thread_id: str = ""  # 线程ID
    process_id: int = 0  # 进程ID
    
    # 恢复信息
    retry_count: int = 0  # 重试次数
    recovered: bool = False  # 是否已恢复
    recovery_time: float = 0  # 恢复时间
    
    # 元数据
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data["timestamp_readable"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)
        )
        if self.recovery_time > 0:
            data["recovery_time_readable"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(self.recovery_time)
            )
        return data


class ErrorCollector:
    """错误收集器
    
    统一收集和管理策略、数据源等模块的错误信息
    """
    
    def __init__(self, max_errors: int = 1000):
        """
        Args:
            max_errors: 最大错误记录数，超过则清理旧记录
        """
        self._errors: List[ErrorRecord] = []
        self._max_errors = max_errors
        self._error_callbacks: List[Callable[[ErrorRecord], None]] = []
        
    def add_error(
        self,
        error: Exception,
        unit_id: str,
        unit_name: str,
        unit_type: str,
        level: ErrorLevel = ErrorLevel.MEDIUM,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        context: str = None,
        data: Any = None,
        tags: List[str] = None
    ) -> ErrorRecord:
        """添加错误记录
        
        Args:
            error: 异常对象
            unit_id: 单元ID
            unit_name: 单元名称
            unit_type: 单元类型 ("strategy" 或 "datasource")
            level: 错误级别
            category: 错误分类
            context: 错误上下文
            data: 相关数据
            tags: 标签
            
        Returns:
            错误记录
        """
        import threading
        import os
        import psutil
        
        # 构建错误消息
        message = str(error)
        if context:
            message = f"{context}: {message}"
        
        # 获取数据预览
        data_preview = ""
        data_type = ""
        data_size = 0
        
        if data is not None:
            try:
                data_preview = self._format_data_preview(data, max_length=200)
                data_type = type(data).__name__
                data_size = self._get_data_size(data)
            except Exception as e:
                log.warning(f"格式化数据预览失败: {e}")
        
        # 创建错误记录
        record = ErrorRecord(
            error_id=self._generate_error_id(),
            timestamp=time.time(),
            level=level,
            category=category,
            message=message,
            exception_type=type(error).__name__,
            traceback=traceback.format_exc(),
            unit_id=unit_id,
            unit_name=unit_name,
            unit_type=unit_type,
            data_preview=data_preview,
            data_type=data_type,
            data_size=data_size,
            memory_usage=self._get_memory_usage(),
            thread_id=str(threading.current_thread().ident),
            process_id=os.getpid(),
            tags=tags or [],
        )
        
        # 添加到列表
        self._errors.append(record)
        
        # 清理旧记录
        if len(self._errors) > self._max_errors:
            self._errors = self._errors[-self._max_errors:]
        
        # 记录日志
        self._log_error(record)
        
        # 触发回调
        self._trigger_callbacks(record)
        
        return record
    
    def record_recovery(self, error_id: str):
        """记录错误恢复
        
        Args:
            error_id: 错误ID
        """
        for error in self._errors:
            if error.error_id == error_id:
                error.recovered = True
                error.recovery_time = time.time()
                log.info(f"错误已恢复: {error_id}")
                break
    
    def get_errors(
        self,
        unit_id: str = None,
        unit_type: str = None,
        level: ErrorLevel = None,
        category: ErrorCategory = None,
        limit: int = 100,
        include_recovered: bool = False
    ) -> List[ErrorRecord]:
        """获取错误记录
        
        Args:
            unit_id: 单元ID过滤
            unit_type: 单元类型过滤
            level: 错误级别过滤
            category: 错误分类过滤
            limit: 返回记录数限制
            include_recovered: 是否包含已恢复的错误
            
        Returns:
            错误记录列表
        """
        filtered_errors = []
        
        for error in reversed(self._errors):  # 最新的在前
            if len(filtered_errors) >= limit:
                break
                
            # 过滤条件
            if unit_id and error.unit_id != unit_id:
                continue
            if unit_type and error.unit_type != unit_type:
                continue
            if level and error.level != level:
                continue
            if category and error.category != category:
                continue
            if not include_recovered and error.recovered:
                continue
                
            filtered_errors.append(error)
        
        return filtered_errors
    
    def get_error_stats(self, unit_id: str = None, unit_type: str = None) -> Dict[str, Any]:
        """获取错误统计
        
        Args:
            unit_id: 单元ID过滤
            unit_type: 单元类型过滤
            
        Returns:
            统计信息
        """
        filtered_errors = [
            error for error in self._errors
            if (not unit_id or error.unit_id == unit_id) and
               (not unit_type or error.unit_type == unit_type)
        ]
        
        if not filtered_errors:
            return {
                "total_count": 0,
                "error_rate": 0,
                "level_counts": {},
                "category_counts": {},
                "unit_counts": {},
                "recovery_rate": 0,
            }
        
        # 基本统计
        total_count = len(filtered_errors)
        recovered_count = sum(1 for error in filtered_errors if error.recovered)
        
        # 级别统计
        level_counts = {}
        for level in ErrorLevel:
            count = sum(1 for error in filtered_errors if error.level == level)
            if count > 0:
                level_counts[level.value] = count
        
        # 分类统计
        category_counts = {}
        for category in ErrorCategory:
            count = sum(1 for error in filtered_errors if error.category == category)
            if count > 0:
                category_counts[category.value] = count
        
        # 单元统计
        unit_counts = {}
        for error in filtered_errors:
            key = f"{error.unit_type}:{error.unit_name}"
            unit_counts[key] = unit_counts.get(key, 0) + 1
        
        # 时间窗口统计（最近1小时）
        recent_time = time.time() - 3600
        recent_count = sum(1 for error in filtered_errors if error.timestamp > recent_time)
        error_rate = recent_count / 3600  # 错误/秒
        
        return {
            "total_count": total_count,
            "error_rate": error_rate,
            "level_counts": level_counts,
            "category_counts": category_counts,
            "unit_counts": unit_counts,
            "recovery_rate": recovered_count / total_count if total_count > 0 else 0,
            "recent_1h_count": recent_count,
        }
    
    def add_callback(self, callback: Callable[[ErrorRecord], None]):
        """添加错误回调
        
        Args:
            callback: 回调函数，接收ErrorRecord参数
        """
        self._error_callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[ErrorRecord], None]):
        """移除错误回调"""
        if callback in self._error_callbacks:
            self._error_callbacks.remove(callback)
    
    def _generate_error_id(self) -> str:
        """生成错误ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _format_data_preview(self, data: Any, max_length: int = 200) -> str:
        """格式化数据预览"""
        try:
            import json
            import pandas as pd
            
            preview = ""
            
            if isinstance(data, pd.DataFrame):
                if len(data) == 0:
                    preview = "空DataFrame"
                else:
                    # 显示前3行
                    preview = str(data.head(3))
            elif isinstance(data, pd.Series):
                if len(data) == 0:
                    preview = "空Series"
                else:
                    preview = str(data.head(10))
            elif isinstance(data, (list, tuple)):
                if len(data) == 0:
                    preview = f"空{data.__class__.__name__}"
                else:
                    preview = str(data[:5])  # 前5个元素
            elif isinstance(data, dict):
                if len(data) == 0:
                    preview = "空字典"
                else:
                    # 显示前3个键值对
                    preview = str(dict(list(data.items())[:3]))
            else:
                preview = str(data)
            
            # 限制长度
            if len(preview) > max_length:
                preview = preview[:max_length-3] + "..."
            
            return preview
            
        except Exception as e:
            return f"数据预览生成失败: {e}"
    
    def _get_data_size(self, data: Any) -> int:
        """获取数据大小"""
        try:
            import sys
            return sys.getsizeof(data)
        except Exception:
            return 0
    
    def _get_memory_usage(self) -> int:
        """获取当前内存使用"""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss
        except Exception:
            return 0
    
    def _log_error(self, error: ErrorRecord):
        """记录错误日志"""
        # 根据级别选择日志级别
        if error.level == ErrorLevel.CRITICAL:
            log.critical(f"[{error.unit_type}:{error.unit_name}] {error.message}")
        elif error.level == ErrorLevel.HIGH:
            log.error(f"[{error.unit_type}:{error.unit_name}] {error.message}")
        elif error.level == ErrorLevel.MEDIUM:
            log.warning(f"[{error.unit_type}:{error.unit_name}] {error.message}")
        else:
            log.info(f"[{error.unit_type}:{error.unit_name}] {error.message}")
    
    def _trigger_callbacks(self, error: ErrorRecord):
        """触发错误回调"""
        for callback in self._error_callbacks:
            try:
                callback(error)
            except Exception as e:
                log.error(f"错误回调执行失败: {e}")


class ErrorHandler:
    """错误处理器
    
    为可执行单元提供错误处理上下文
    """
    
    def __init__(self, unit: Any, collector: ErrorCollector = None):
        """
        Args:
            unit: 可执行单元
            collector: 错误收集器，如果为None则使用全局收集器
        """
        self.unit = unit
        self.collector = collector or get_global_error_collector()
    
    def handle_error(
        self,
        error: Exception,
        level: ErrorLevel = ErrorLevel.MEDIUM,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        context: str = None,
        data: Any = None,
        tags: List[str] = None
    ) -> ErrorRecord:
        """处理错误
        
        Args:
            error: 异常对象
            level: 错误级别
            category: 错误分类
            context: 错误上下文
            data: 相关数据
            tags: 标签
            
        Returns:
            错误记录
        """
        return self.collector.add_error(
            error=error,
            unit_id=self.unit.id,
            unit_name=self.unit.name,
            unit_type=getattr(self.unit, 'unit_type', 'unknown'),
            level=level,
            category=category,
            context=context,
            data=data,
            tags=tags
        )
    
    def handle_code_error(
        self,
        error: Exception,
        context: str = None,
        data: Any = None
    ) -> ErrorRecord:
        """处理代码执行错误"""
        return self.handle_error(
            error=error,
            level=ErrorLevel.HIGH,
            category=ErrorCategory.CODE_EXECUTION,
            context=context,
            data=data,
            tags=["code_execution"]
        )
    
    def handle_data_error(
        self,
        error: Exception,
        data: Any = None
    ) -> ErrorRecord:
        """处理数据错误"""
        return self.handle_error(
            error=error,
            level=ErrorLevel.MEDIUM,
            category=ErrorCategory.DATA_VALIDATION,
            context="数据验证失败",
            data=data,
            tags=["data_validation"]
        )
    
    def handle_network_error(
        self,
        error: Exception
    ) -> ErrorRecord:
        """处理网络错误"""
        return self.handle_error(
            error=error,
            level=ErrorLevel.MEDIUM,
            category=ErrorCategory.NETWORK,
            context="网络请求失败",
            tags=["network"]
        )
    
    def record_recovery(self):
        """记录当前单元的错误恢复"""
        # 找到最近的未恢复错误并标记为已恢复
        recent_errors = self.collector.get_errors(
            unit_id=self.unit.id,
            include_recovered=False,
            limit=1
        )
        
        if recent_errors:
            self.collector.record_recovery(recent_errors[0].error_id)


# 全局错误收集器实例
_global_error_collector: Optional[ErrorCollector] = None


def get_global_error_collector() -> ErrorCollector:
    """获取全局错误收集器"""
    global _global_error_collector
    if _global_error_collector is None:
        _global_error_collector = ErrorCollector()
    return _global_error_collector


def set_global_error_collector(collector: ErrorCollector):
    """设置全局错误收集器"""
    global _global_error_collector
    _global_error_collector = collector