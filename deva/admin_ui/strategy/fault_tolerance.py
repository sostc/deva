"""容错与监控模块(Fault Tolerance & Monitoring)

提供异常隔离、实时诊断和UI告警功能。

================================================================================
架构设计
================================================================================

【异常隔离舱】
┌─────────────────────────────────────────────────────────────────────────────┐
│  SafeProcessor                                                              │
│  ├── try-except 封装                                                        │
│  ├── 异常捕获和分类                                                         │
│  ├── 错误数据包记录                                                         │
│  └── 异步发送到 ERROR_STREAM                                                │
└─────────────────────────────────────────────────────────────────────────────┘

【实时诊断】
┌─────────────────────────────────────────────────────────────────────────────┐
│  ErrorCollector                                                             │
│  ├── 收集所有策略的错误信息                                                  │
│  ├── 分类统计（按策略、按错误类型）                                          │
│  ├── 错误趋势分析                                                           │
│  └── 错误数据包存储                                                         │
└─────────────────────────────────────────────────────────────────────────────┘

【UI 告警】
┌─────────────────────────────────────────────────────────────────────────────┐
│  AlertManager                                                               │
│  ├── 实时置顶报错信息                                                       │
│  ├── 告警级别分类（INFO/WARNING/ERROR/CRITICAL）                            │
│  ├── 支持"一键反馈给 AI 修复"                                               │
│  └── 告警历史记录                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

【监控指标】
┌─────────────────────────────────────────────────────────────────────────────┐
│  MetricsCollector                                                           │
│  ├── 处理计数                                                               │
│  ├── 错误计数                                                               │
│  ├── 执行时间统计                                                           │
│  ├── 吞吐量计算                                                             │
│  └── 资源使用监控                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set
import functools
import hashlib

from deva import Stream, NS, NB, log, Dtalk
from .logging_context import get_logging_context, create_enhanced_log_record


class ErrorSeverity:
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ErrorRecord:
    id: str
    strategy_id: str
    strategy_name: str
    error_type: str
    error_message: str
    traceback: str
    data_preview: str
    severity: str
    ts: float
    resolved: bool = False
    resolved_at: Optional[float] = None
    ai_fix_suggestion: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "traceback": self.traceback,
            "data_preview": self.data_preview,
            "severity": self.severity,
            "ts": self.ts,
            "ts_readable": datetime.fromtimestamp(self.ts).isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
            "ai_fix_suggestion": self.ai_fix_suggestion,
        }


@dataclass
class AlertConfig:
    enable_dtalk: bool = True
    enable_log: bool = True
    dtalk_threshold: int = 3
    dtalk_window_seconds: int = 300
    max_alerts_per_hour: int = 100
    critical_immediate: bool = True
    
    def to_dict(self) -> dict:
        return {
            "enable_dtalk": self.enable_dtalk,
            "enable_log": self.enable_log,
            "dtalk_threshold": self.dtalk_threshold,
            "dtalk_window_seconds": self.dtalk_window_seconds,
            "max_alerts_per_hour": self.max_alerts_per_hour,
            "critical_immediate": self.critical_immediate,
        }


class SafeProcessor:
    """安全处理器封装
    
    提供异常隔离舱，封装 try-except，捕获代码执行异常。
    """
    
    def __init__(
        self,
        processor_func: Callable,
        strategy_id: str = "",
        strategy_name: str = "",
        error_stream: Stream = None,
        on_error: Callable = None,
    ):
        self.processor_func = processor_func
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.error_stream = error_stream
        self.on_error = on_error
        
        self._error_count = 0
        self._success_count = 0
        self._last_error = None
    
    def __call__(self, data: Any) -> Any:
        try:
            result = self.processor_func(data)
            self._success_count += 1
            return result
        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            
            error_record = self._create_error_record(e, data)
            
            if self.error_stream:
                self.error_stream.emit(error_record.to_dict())
            
            if self.on_error:
                try:
                    self.on_error(error_record)
                except Exception:
                    pass
            
            return None
    
    def _create_error_record(self, error: Exception, data: Any) -> ErrorRecord:
        """创建错误记录 - 包含策略和数据源上下文"""
        error_id = hashlib.md5(
            f"{self.strategy_id}_{time.time()}".encode()
        ).hexdigest()[:12]
        
        # 获取当前日志上下文以包含数据源信息
        context = get_logging_context()
        
        # 构建增强的错误消息
        error_message = str(error)
        context_parts = []
        
        if self.strategy_name:
            context_parts.append(f"策略[{self.strategy_name}]")
        if context.datasource_name:
            context_parts.append(f"数据源[{context.datasource_name}]")
        
        if context_parts:
            error_message = f"[{'|'.join(context_parts)}] {error_message}"
        
        return ErrorRecord(
            id=error_id,
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            error_type=type(error).__name__,
            error_message=error_message,
            traceback=traceback.format_exc(),
            data_preview=str(data)[:500] if data else "",
            severity=ErrorSeverity.ERROR,
            ts=time.time(),
        )
    
    def wrap(self) -> Callable:
        return self.__call__


def safe_process(
    strategy_id: str = "",
    strategy_name: str = "",
    error_stream: Stream = None,
):
    """装饰器：将函数包装为安全处理器"""
    def decorator(func: Callable) -> Callable:
        safe_proc = SafeProcessor(
            processor_func=func,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            error_stream=error_stream,
        )
        
        @functools.wraps(func)
        def wrapper(data: Any) -> Any:
            return safe_proc(data)
        
        wrapper._safe_processor = safe_proc
        return wrapper
    
    return decorator


class ErrorCollector:
    """错误收集器
    
    收集所有策略的错误信息，进行分类统计和趋势分析。
    """
    
    def __init__(self, max_errors: int = 1000):
        self._errors: List[ErrorRecord] = []
        self._max_errors = max_errors
        self._errors_lock = threading.Lock()
        
        self._by_strategy: Dict[str, List[ErrorRecord]] = defaultdict(list)
        self._by_type: Dict[str, List[ErrorRecord]] = defaultdict(list)
        self._by_severity: Dict[str, int] = defaultdict(int)
        
        self._error_stream: Optional[Stream] = None
    
    def set_error_stream(self, stream: Stream):
        self._error_stream = stream
        self._error_stream.sink(self._collect)
    
    def _collect(self, error_data: dict):
        record = ErrorRecord(
            id=error_data.get("id", ""),
            strategy_id=error_data.get("strategy_id", ""),
            strategy_name=error_data.get("strategy_name", ""),
            error_type=error_data.get("error_type", "Unknown"),
            error_message=error_data.get("error_message", error_data.get("error", "")),
            traceback=error_data.get("traceback", ""),
            data_preview=error_data.get("data_preview", ""),
            severity=error_data.get("severity", ErrorSeverity.ERROR),
            ts=error_data.get("ts", time.time()),
        )
        
        with self._errors_lock:
            self._errors.append(record)
            
            if len(self._errors) > self._max_errors:
                removed = self._errors.pop(0)
                if removed.strategy_id in self._by_strategy:
                    self._by_strategy[removed.strategy_id] = [
                        e for e in self._by_strategy[removed.strategy_id] if e.id != removed.id
                    ]
            
            self._by_strategy[record.strategy_id].append(record)
            self._by_type[record.error_type].append(record)
            self._by_severity[record.severity] += 1
    
    def add_error(self, record: ErrorRecord):
        with self._errors_lock:
            self._errors.append(record)
            
            if len(self._errors) > self._max_errors:
                self._errors.pop(0)
            
            self._by_strategy[record.strategy_id].append(record)
            self._by_type[record.error_type].append(record)
            self._by_severity[record.severity] += 1
    
    def get_errors(
        self,
        strategy_id: str = None,
        error_type: str = None,
        severity: str = None,
        limit: int = 50,
        unresolved_only: bool = False,
    ) -> List[dict]:
        with self._errors_lock:
            errors = list(self._errors)
        
        if strategy_id:
            errors = [e for e in errors if e.strategy_id == strategy_id]
        if error_type:
            errors = [e for e in errors if e.error_type == error_type]
        if severity:
            errors = [e for e in errors if e.severity == severity]
        if unresolved_only:
            errors = [e for e in errors if not e.resolved]
        
        errors = sorted(errors, key=lambda x: x.ts, reverse=True)
        return [e.to_dict() for e in errors[:limit]]
    
    def get_stats(self) -> dict:
        with self._errors_lock:
            total = len(self._errors)
            by_strategy = {
                sid: len(errors) for sid, errors in self._by_strategy.items()
            }
            by_type = {
                etype: len(errors) for etype, errors in self._by_type.items()
            }
            by_severity = dict(self._by_severity)
            unresolved = sum(1 for e in self._errors if not e.resolved)
        
        return {
            "total_errors": total,
            "unresolved": unresolved,
            "by_strategy": by_strategy,
            "by_type": by_type,
            "by_severity": by_severity,
        }
    
    def resolve_error(self, error_id: str) -> bool:
        with self._errors_lock:
            for error in self._errors:
                if error.id == error_id:
                    error.resolved = True
                    error.resolved_at = time.time()
                    return True
        return False
    
    def clear_resolved(self) -> int:
        with self._errors_lock:
            original_len = len(self._errors)
            self._errors = [e for e in self._errors if not e.resolved]
            cleared = original_len - len(self._errors)
            
            self._by_strategy.clear()
            self._by_type.clear()
            self._by_severity.clear()
            
            for e in self._errors:
                self._by_strategy[e.strategy_id].append(e)
                self._by_type[e.error_type].append(e)
                self._by_severity[e.severity] += 1
            
            return cleared
    
    def get_trend(self, hours: int = 24) -> dict:
        now = time.time()
        start_ts = now - hours * 3600
        
        with self._errors_lock:
            errors = [e for e in self._errors if e.ts >= start_ts]
        
        hourly_counts = defaultdict(int)
        for e in errors:
            hour = datetime.fromtimestamp(e.ts).strftime("%Y-%m-%d %H:00")
            hourly_counts[hour] += 1
        
        return {
            "hours": hours,
            "total_in_period": len(errors),
            "hourly_counts": dict(sorted(hourly_counts.items())),
        }


class AlertManager:
    """告警管理器
    
    提供实时告警和通知功能。
    """
    
    def __init__(self, config: AlertConfig = None):
        self.config = config or AlertConfig()
        self._alerts: List[dict] = []
        self._alerts_lock = threading.Lock()
        self._alert_counts: Dict[str, List[float]] = defaultdict(list)
        self._hourly_count = 0
        self._hourly_reset = time.time()
    
    def alert(
        self,
        strategy_id: str,
        strategy_name: str,
        message: str,
        severity: str = ErrorSeverity.ERROR,
        details: dict = None,
    ):
        now = time.time()
        
        if now - self._hourly_reset > 3600:
            self._hourly_count = 0
            self._hourly_reset = now
        
        if self._hourly_count >= self.config.max_alerts_per_hour:
            return
        
        self._hourly_count += 1
        
        alert_data = {
            "id": hashlib.md5(f"{strategy_id}_{now}".encode()).hexdigest()[:12],
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "message": message,
            "severity": severity,
            "details": details or {},
            "ts": now,
            "ts_readable": datetime.fromtimestamp(now).isoformat(),
        }
        
        with self._alerts_lock:
            self._alerts.append(alert_data)
            if len(self._alerts) > 500:
                self._alerts = self._alerts[-500:]
        
        if self.config.enable_log:
            self._log_alert(alert_data)
        
        if self.config.enable_dtalk:
            should_send = (
                self.config.critical_immediate and severity == ErrorSeverity.CRITICAL
            ) or self._check_dtalk_threshold(strategy_id)
            
            if should_send:
                self._send_dtalk(alert_data)
    
    def _check_dtalk_threshold(self, strategy_id: str) -> bool:
        now = time.time()
        window_start = now - self.config.dtalk_window_seconds
        
        self._alert_counts[strategy_id] = [
            ts for ts in self._alert_counts[strategy_id] if ts > window_start
        ]
        self._alert_counts[strategy_id].append(now)
        
        return len(self._alert_counts[strategy_id]) >= self.config.dtalk_threshold
    
    def _log_alert(self, alert: dict):
        """记录告警 - 使用增强的日志系统"""
        level_map = {
            ErrorSeverity.INFO: "INFO",
            ErrorSeverity.WARNING: "WARNING",
            ErrorSeverity.ERROR: "ERROR",
            ErrorSeverity.CRITICAL: "CRITICAL",
        }
        
        # 获取当前日志上下文
        context = get_logging_context()
        
        # 构建消息，包含策略和数据源信息
        message_parts = []
        if alert.get('strategy_name'):
            message_parts.append(f"策略[{alert['strategy_name']}]")
        if context.datasource_name:
            message_parts.append(f"数据源[{context.datasource_name}]")
        
        if message_parts:
            message = f"[{'|'.join(message_parts)}] {alert['message']}"
        else:
            message = alert['message']
        
        # 创建增强的日志记录
        extra_info = {
            "alert_id": alert.get("id"),
            "severity": alert["severity"],
            "alert_message": alert["message"],
        }
        
        # 添加策略信息
        if alert.get("strategy_id"):
            extra_info["strategy_id"] = alert["strategy_id"]
        if alert.get("strategy_name"):
            extra_info["strategy_name"] = alert["strategy_name"]
        
        # 添加详细信息
        if alert.get("details"):
            extra_info["details"] = alert["details"]
        
        record = create_enhanced_log_record(
            level_map.get(alert["severity"], "ERROR"),
            message,
            "deva.alert",
            **extra_info
        )
        
        try:
            record >> log
        except Exception:
            pass
    
    def _send_dtalk(self, alert: dict):
        """发送钉钉告警 - 包含策略和数据源上下文"""
        # 获取当前日志上下文
        context = get_logging_context()
        
        # 构建消息，包含策略和数据源信息
        message_parts = ["### 🚨 策略告警"]
        
        if alert.get('strategy_name'):
            message_parts.append(f"- **策略**: {alert['strategy_name']}")
        if context.datasource_name:
            message_parts.append(f"- **数据源**: {context.datasource_name}")
        if context.source_type:
            message_parts.append(f"- **类型**: {context.source_type}")
            
        message_parts.extend([
            f"- **级别**: {alert['severity'].upper()}",
            f"- **消息**: {alert['message']}",
            f"- **时间**: {alert['ts_readable']}"
        ])
        
        # 添加策略ID和数据源ID（如果有）
        if alert.get('strategy_id'):
            message_parts.append(f"- **策略ID**: {alert['strategy_id']}")
        if context.datasource_id:
            message_parts.append(f"- **数据源ID**: {context.datasource_id}")
        
        # 添加详细信息
        if alert.get('details'):
            details = alert['details']
            if isinstance(details, dict):
                if details.get('error_type'):
                    message_parts.append(f"- **错误类型**: {details['error_type']}")
                if details.get('error_message'):
                    message_parts.append(f"- **错误详情**: {details['error_message']}")
        
        message = "\n".join(message_parts)
        
        try:
            message >> Dtalk()
        except Exception:
            pass
    
    def get_alerts(
        self,
        severity: str = None,
        strategy_id: str = None,
        limit: int = 50,
    ) -> List[dict]:
        with self._alerts_lock:
            alerts = list(self._alerts)
        
        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]
        if strategy_id:
            alerts = [a for a in alerts if a["strategy_id"] == strategy_id]
        
        alerts = sorted(alerts, key=lambda x: x["ts"], reverse=True)
        return alerts[:limit]
    
    def clear_alerts(self):
        with self._alerts_lock:
            self._alerts.clear()


class MetricsCollector:
    """指标收集器
    
    收集策略执行的监控指标。
    """
    
    def __init__(self):
        self._metrics: Dict[str, dict] = defaultdict(lambda: {
            "processed_count": 0,
            "error_count": 0,
            "total_time_ms": 0,
            "min_time_ms": float("inf"),
            "max_time_ms": 0,
            "last_process_ts": 0,
        })
        self._metrics_lock = threading.Lock()
        
        self._history: List[dict] = []
        self._history_lock = threading.Lock()
        self._max_history = 10000
    
    def record(
        self,
        strategy_id: str,
        success: bool,
        execution_time_ms: float,
    ):
        with self._metrics_lock:
            metrics = self._metrics[strategy_id]
            metrics["processed_count"] += 1
            if not success:
                metrics["error_count"] += 1
            metrics["total_time_ms"] += execution_time_ms
            metrics["min_time_ms"] = min(metrics["min_time_ms"], execution_time_ms)
            metrics["max_time_ms"] = max(metrics["max_time_ms"], execution_time_ms)
            metrics["last_process_ts"] = time.time()
        
        with self._history_lock:
            self._history.append({
                "strategy_id": strategy_id,
                "success": success,
                "execution_time_ms": execution_time_ms,
                "ts": time.time(),
            })
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
    
    def get_metrics(self, strategy_id: str = None) -> dict:
        with self._metrics_lock:
            if strategy_id:
                metrics = dict(self._metrics.get(strategy_id, {}))
                if metrics:
                    count = metrics.get("processed_count", 0)
                    if count > 0:
                        metrics["avg_time_ms"] = metrics["total_time_ms"] / count
                        metrics["error_rate"] = metrics["error_count"] / count
                    else:
                        metrics["avg_time_ms"] = 0
                        metrics["error_rate"] = 0
                return metrics
            
            result = {}
            for sid, m in self._metrics.items():
                count = m.get("processed_count", 0)
                result[sid] = {
                    **m,
                    "avg_time_ms": m["total_time_ms"] / count if count > 0 else 0,
                    "error_rate": m["error_count"] / count if count > 0 else 0,
                }
            return result
    
    def get_throughput(self, strategy_id: str, window_seconds: int = 60) -> float:
        now = time.time()
        window_start = now - window_seconds
        
        with self._history_lock:
            count = sum(
                1 for h in self._history
                if h["strategy_id"] == strategy_id and h["ts"] >= window_start
            )
        
        return count / window_seconds if window_seconds > 0 else 0
    
    def get_summary(self) -> dict:
        with self._metrics_lock:
            total_processed = sum(m["processed_count"] for m in self._metrics.values())
            total_errors = sum(m["error_count"] for m in self._metrics.values())
            total_time = sum(m["total_time_ms"] for m in self._metrics.values())
        
        return {
            "total_strategies": len(self._metrics),
            "total_processed": total_processed,
            "total_errors": total_errors,
            "total_time_ms": total_time,
            "avg_time_ms": total_time / total_processed if total_processed > 0 else 0,
            "error_rate": total_errors / total_processed if total_processed > 0 else 0,
        }
    
    def reset(self, strategy_id: str = None):
        with self._metrics_lock:
            if strategy_id:
                self._metrics.pop(strategy_id, None)
            else:
                self._metrics.clear()


error_collector = ErrorCollector()
alert_manager = AlertManager()
metrics_collector = MetricsCollector()


def get_error_collector() -> ErrorCollector:
    return error_collector


def get_alert_manager() -> AlertManager:
    return alert_manager


def get_metrics_collector() -> MetricsCollector:
    return metrics_collector


def initialize_fault_tolerance():
    error_stream = NS("strategy_errors", description='策略错误流，用于收集策略执行过程中的错误信息')
    error_collector.set_error_stream(error_stream)
    
    error_stream.sink(lambda e: alert_manager.alert(
        strategy_id=e.get("strategy_id", ""),
        strategy_name=e.get("strategy_name", ""),
        message=e.get("error_message", e.get("error", "")),
        severity=e.get("severity", ErrorSeverity.ERROR),
        details={"error_type": e.get("error_type", "")},
    ))
    
    return {
        "error_stream": error_stream,
        "error_collector": error_collector,
        "alert_manager": alert_manager,
        "metrics_collector": metrics_collector,
    }
