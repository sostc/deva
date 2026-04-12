"""Naja 统一性能监控模块

监控整个系统的性能表现，包括：
- 策略执行性能
- 任务执行性能
- 数据源处理性能
- 底层存储性能

提供统一的监控界面和告警机制。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union


class ComponentType(Enum):
    """组件类型"""
    STRATEGY = "strategy"
    TASK = "task"
    DATASOURCE = "datasource"
    STORAGE = "storage"
    WEB_REQUEST = "web_request"  # Web 请求
    LOCK_WAIT = "lock_wait"     # 锁等待
    THREAD_POOL = "thread_pool"  # 线程池
    DATASOURCE_ARRIVAL = "datasource_arrival"  # 数据源到达监控


class SeverityLevel(Enum):
    """严重程度级别"""
    NORMAL = "normal"      # 正常
    WARNING = "warning"    # 警告 (>100ms)
    CRITICAL = "critical"  # 严重 (>500ms)
    SEVERE = "severe"      # 极其严重 (>1000ms)


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    component_id: str
    component_name: str
    component_type: ComponentType
    
    # 执行时间统计 (毫秒)
    execution_times: deque = field(default_factory=lambda: deque(maxlen=100))
    
    # 调用统计
    call_count: int = 0
    error_count: int = 0
    last_call_time: Optional[float] = None
    last_error: str = ""
    last_error_time: Optional[float] = None
    
    # 性能指标
    slow_execution_count: int = 0
    
    # 抖动检测相关 (调用间隔监控)
    call_intervals_ms: deque = field(default_factory=lambda: deque(maxlen=100))
    expected_interval_ms: float = 0.0  # 期望的调用间隔
    
    @property
    def avg_call_interval_ms(self) -> float:
        """平均调用间隔"""
        if len(self.call_intervals_ms) < 2:
            return 0.0
        return sum(self.call_intervals_ms) / len(self.call_intervals_ms)
    
    @property
    def std_call_interval_ms(self) -> float:
        """调用间隔标准差"""
        if len(self.call_intervals_ms) < 2:
            return 0.0
        avg = self.avg_call_interval_ms
        variance = sum((i - avg) ** 2 for i in self.call_intervals_ms) / len(self.call_intervals_ms)
        return variance ** 0.5
    
    @property
    def jitter_ratio(self) -> float:
        """抖动率 = 标准差 / 平均值 (0.1 = 10%抖动)"""
        avg = self.avg_call_interval_ms
        if avg <= 0:
            return 0.0
        return self.std_call_interval_ms / avg
    
    @property
    def jitter_status(self) -> str:
        """抖动状态"""
        ratio = self.jitter_ratio
        if ratio < 0.15:
            return "stable"
        elif ratio < 0.30:
            return "minor_jitter"
        elif ratio < 0.50:
            return "moderate_jitter"
        else:
            return "severe_jitter"
    
    @property
    def calls_per_minute(self) -> float:
        """每分钟调用次数"""
        if not self.call_intervals_ms or len(self.call_intervals_ms) < 2:
            return 0.0
        total_ms = sum(self.call_intervals_ms)
        if total_ms <= 0:
            return 0.0
        return 60000.0 / total_ms * len(self.call_intervals_ms)
    
    @property
    def avg_execution_time(self) -> float:
        """平均执行时间"""
        if not self.execution_times:
            return 0.0
        return sum(self.execution_times) / len(self.execution_times)
    
    @property
    def max_execution_time(self) -> float:
        """最大执行时间"""
        if not self.execution_times:
            return 0.0
        return max(self.execution_times)
    
    @property
    def min_execution_time(self) -> float:
        """最小执行时间"""
        if not self.execution_times:
            return 0.0
        return min(self.execution_times)
    
    @property
    def p95_execution_time(self) -> float:
        """95百分位执行时间"""
        if not self.execution_times:
            return 0.0
        sorted_times = sorted(self.execution_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    @property
    def error_rate(self) -> float:
        """错误率"""
        if self.call_count == 0:
            return 0.0
        return self.error_count / self.call_count
    
    def get_severity(self, thresholds: Dict[str, float]) -> SeverityLevel:
        """根据阈值获取严重程度"""
        avg_time = self.avg_execution_time
        max_time = self.max_execution_time
        
        if max_time >= thresholds.get("severe", 1000):
            return SeverityLevel.SEVERE
        elif max_time >= thresholds.get("critical", 500):
            return SeverityLevel.CRITICAL
        elif avg_time >= thresholds.get("warning", 100):
            return SeverityLevel.WARNING
        return SeverityLevel.NORMAL
    
    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "component_name": self.component_name,
            "component_type": self.component_type.value,
            "avg_execution_time_ms": round(self.avg_execution_time, 2),
            "max_execution_time_ms": round(self.max_execution_time, 2),
            "min_execution_time_ms": round(self.min_execution_time, 2),
            "p95_execution_time_ms": round(self.p95_execution_time, 2),
            "call_count": self.call_count,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate * 100, 2),
            "slow_execution_count": self.slow_execution_count,
            "last_error": self.last_error,
            "last_error_time": datetime.fromtimestamp(self.last_error_time).isoformat() if self.last_error_time else None,
            "last_call_time": datetime.fromtimestamp(self.last_call_time).isoformat() if self.last_call_time else None,
            "jitter_stats": {
                "expected_interval_ms": self.expected_interval_ms,
                "avg_interval_ms": round(self.avg_call_interval_ms, 1),
                "std_interval_ms": round(self.std_call_interval_ms, 1),
                "jitter_ratio": round(self.jitter_ratio, 3),
                "jitter_status": self.jitter_status,
                "calls_per_minute": round(self.calls_per_minute, 1),
            } if self.expected_interval_ms > 0 else None,
        }


@dataclass
class PerformanceReport:
    """性能报告"""
    component_id: str
    component_name: str
    component_type: ComponentType
    severity: SeverityLevel
    avg_time_ms: float
    max_time_ms: float
    recommendation: str
    details: Dict[str, Any] = field(default_factory=dict)


class NajaPerformanceMonitor:
    """Naja 统一性能监控器

    单例模式，监控所有组件的性能表现。

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局性能监控：性能监控必须是全局的，才能准确反映整个系统的状态。
       如果存在多个实例，会导致指标分散，无法准确监控。

    2. 状态一致性：性能指标、告警状态等需要在全系统保持一致。

    3. 生命周期：监控器的生命周期与系统一致，随系统启动和关闭。

    4. 这是系统监控的设计选择，不是过度工程。
    ================================================================================
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        # 性能指标存储: (component_type, component_id) -> PerformanceMetrics
        self._metrics: Dict[tuple, PerformanceMetrics] = {}
        self._metrics_lock = threading.Lock()
        
        # 阈值配置
        self._thresholds = {
            "warning": 100,    # 100ms
            "critical": 500,   # 500ms
            "severe": 1000,    # 1000ms
        }
        
        # 监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._check_interval = 30  # 秒
        
        # 告警回调
        self._alert_callbacks: List[Callable[[List[PerformanceReport]], None]] = []
        
        # 历史报告
        self._reports_history: deque = deque(maxlen=100)
        
        self._initialized = True
        self._log("INFO", "统一性能监控器初始化完成")
    
    def configure(
        self,
        warning_threshold_ms: float = None,
        critical_threshold_ms: float = None,
        severe_threshold_ms: float = None,
        check_interval: int = None,
    ):
        """配置监控参数"""
        if warning_threshold_ms is not None:
            self._thresholds["warning"] = warning_threshold_ms
        if critical_threshold_ms is not None:
            self._thresholds["critical"] = critical_threshold_ms
        if severe_threshold_ms is not None:
            self._thresholds["severe"] = severe_threshold_ms
        if check_interval is not None:
            self._check_interval = check_interval
        
        self._log("INFO", "监控配置已更新", thresholds=self._thresholds)
    
    def register_alert_callback(self, callback: Callable[[List[PerformanceReport]], None]):
        """注册告警回调"""
        self._alert_callbacks.append(callback)
    
    def start_monitoring(self):
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        self._log("INFO", "性能监控已启动")
    
    def stop_monitoring(self):
        """停止监控"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self._log("INFO", "性能监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                reports = self.generate_performance_reports()
                slow_reports = [r for r in reports if r.severity != SeverityLevel.NORMAL]
                
                if slow_reports:
                    self._reports_history.append({
                        "timestamp": time.time(),
                        "reports": slow_reports,
                    })
                    
                    for callback in self._alert_callbacks:
                        try:
                            callback(slow_reports)
                        except Exception as e:
                            self._log("ERROR", "告警回调执行失败", error=str(e))
                
                time.sleep(self._check_interval)
            except Exception as e:
                self._log("ERROR", "监控循环错误", error=str(e))
                time.sleep(self._check_interval)
    
    def record_execution(
        self,
        component_id: str,
        component_name: str,
        component_type: ComponentType,
        execution_time_ms: float,
        success: bool = True,
        error: str = "",
        expected_interval_ms: float = 0.0,
    ):
        """记录组件执行性能
        
        Args:
            expected_interval_ms: 期望的调用间隔，用于抖动检测。如设为5000表示期望每5秒调用一次。
        """
        key = (component_type, component_id)
        
        with self._metrics_lock:
            if key not in self._metrics:
                self._metrics[key] = PerformanceMetrics(
                    component_id=component_id,
                    component_name=component_name,
                    component_type=component_type,
                )
            
            metrics = self._metrics[key]
            metrics.execution_times.append(execution_time_ms)
            metrics.call_count += 1
            
            if expected_interval_ms > 0 and metrics.last_call_time is not None:
                interval_ms = (time.time() - metrics.last_call_time) * 1000
                if interval_ms > 0:
                    metrics.call_intervals_ms.append(interval_ms)
                metrics.expected_interval_ms = expected_interval_ms
            
            metrics.last_call_time = time.time()
            
            if execution_time_ms > self._thresholds["warning"]:
                metrics.slow_execution_count += 1
            
            if not success:
                metrics.error_count += 1
                metrics.last_error = error
                metrics.last_error_time = time.time()
    
    def record_data_arrival(
        self,
        datasource_id: str,
        expected_interval_ms: float = 5000.0,
    ):
        """记录数据源数据到达，用于检测数据到达抖动
        
        Args:
            datasource_id: 数据源ID
            expected_interval_ms: 期望的数据到达间隔，默认5秒
        """
        component_type = ComponentType.DATASOURCE_ARRIVAL
        key = (component_type, datasource_id)
        
        with self._metrics_lock:
            if key not in self._metrics:
                self._metrics[key] = PerformanceMetrics(
                    component_id=datasource_id,
                    component_name=f"数据源到达监控({datasource_id})",
                    component_type=component_type,
                )
            
            metrics = self._metrics[key]
            
            if metrics.last_call_time is not None:
                interval_ms = (time.time() - metrics.last_call_time) * 1000
                if interval_ms > 0:
                    metrics.call_intervals_ms.append(interval_ms)
            
            metrics.call_count += 1
            metrics.last_call_time = time.time()
            metrics.expected_interval_ms = expected_interval_ms
    
    def generate_performance_reports(self) -> List[PerformanceReport]:
        """生成所有组件的性能报告"""
        reports = []
        
        with self._metrics_lock:
            for metrics in self._metrics.values():
                # 至少需要5次执行记录
                if len(metrics.execution_times) < 5:
                    continue
                
                severity = metrics.get_severity(self._thresholds)
                
                if severity != SeverityLevel.NORMAL:
                    recommendation = self._generate_recommendation(metrics, severity)
                    
                    reports.append(PerformanceReport(
                        component_id=metrics.component_id,
                        component_name=metrics.component_name,
                        component_type=metrics.component_type,
                        severity=severity,
                        avg_time_ms=metrics.avg_execution_time,
                        max_time_ms=metrics.max_execution_time,
                        recommendation=recommendation,
                        details=metrics.to_dict(),
                    ))
        
        # 抖动检测报告
        jitter_reports = self._generate_jitter_reports()
        reports.extend(jitter_reports)
        
        # 按严重程度排序
        severity_order = {
            SeverityLevel.SEVERE: 0,
            SeverityLevel.CRITICAL: 1,
            SeverityLevel.WARNING: 2,
            SeverityLevel.NORMAL: 3,
        }
        reports.sort(key=lambda r: severity_order.get(r.severity, 4))
        
        return reports
    
    def _generate_jitter_reports(self) -> List[PerformanceReport]:
        """生成抖动相关的报告"""
        reports = []
        
        with self._metrics_lock:
            for metrics in self._metrics.values():
                # 需要有抖动检测配置且有足够的间隔数据
                if metrics.expected_interval_ms <= 0:
                    continue
                if len(metrics.call_intervals_ms) < 5:
                    continue
                
                jitter_status = metrics.jitter_status
                if jitter_status in ("moderate_jitter", "severe_jitter"):
                    severity = (SeverityLevel.CRITICAL 
                               if jitter_status == "severe_jitter" 
                               else SeverityLevel.WARNING)
                    
                    deviation = abs(metrics.avg_call_interval_ms - metrics.expected_interval_ms)
                    deviation_pct = (deviation / metrics.expected_interval_ms * 100) if metrics.expected_interval_ms > 0 else 0
                    
                    recommendation = (
                        f"调用间隔抖动严重(jitter_ratio={metrics.jitter_ratio:.2f})，"
                        f"实际间隔波动 {metrics.std_call_interval_ms:.0f}ms，"
                        f"建议检查数据推送频率或添加防抖控制"
                    )
                    
                    reports.append(PerformanceReport(
                        component_id=f"{metrics.component_id}_jitter",
                        component_name=f"{metrics.component_name}[抖动检测]",
                        component_type=metrics.component_type,
                        severity=severity,
                        avg_time_ms=metrics.avg_call_interval_ms,
                        max_time_ms=max(metrics.call_intervals_ms) if metrics.call_intervals_ms else 0,
                        recommendation=recommendation,
                        details={
                            "expected_interval_ms": metrics.expected_interval_ms,
                            "avg_interval_ms": round(metrics.avg_call_interval_ms, 1),
                            "std_interval_ms": round(metrics.std_call_interval_ms, 1),
                            "jitter_ratio": round(metrics.jitter_ratio, 3),
                            "jitter_status": jitter_status,
                            "deviation_ms": round(deviation, 1),
                            "deviation_percentage": round(deviation_pct, 1),
                            "calls_per_minute": round(metrics.calls_per_minute, 1),
                        },
                    ))
        
        return reports
    
    def _generate_recommendation(self, metrics: PerformanceMetrics, severity: SeverityLevel) -> str:
        """生成优化建议"""
        recommendations = []
        
        if severity == SeverityLevel.SEVERE:
            recommendations.append("性能极其严重，建议立即停用并优化")
        elif severity == SeverityLevel.CRITICAL:
            recommendations.append("性能严重，建议尽快优化")
        elif severity == SeverityLevel.WARNING:
            recommendations.append("性能有瓶颈，建议关注优化")
        
        if metrics.error_rate > 0.1:
            recommendations.append(f"错误率较高 ({metrics.error_rate*100:.1f}%)，建议检查异常处理")
        
        if metrics.max_execution_time > metrics.avg_execution_time * 3:
            recommendations.append("执行时间波动大，可能存在偶发性问题")
        
        return "; ".join(recommendations) if recommendations else "运行正常"
    
    def get_metrics_by_type(self, component_type: ComponentType = None) -> Dict[str, dict]:
        """获取指定类型的性能指标"""
        with self._metrics_lock:
            result = {}
            for key, metrics in self._metrics.items():
                if component_type is None or metrics.component_type == component_type:
                    result[f"{metrics.component_type.value}:{metrics.component_id}"] = metrics.to_dict()
            return result
    
    def get_slow_components_summary(self) -> dict:
        """获取慢组件摘要"""
        reports = self.generate_performance_reports()
        
        by_type = {}
        for r in reports:
            type_name = r.component_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append({
                "id": r.component_id,
                "name": r.component_name,
                "severity": r.severity.value,
                "avg_time_ms": round(r.avg_time_ms, 2),
                "max_time_ms": round(r.max_time_ms, 2),
            })
        
        return {
            "total_slow": len(reports),
            "by_type": by_type,
            "severe_count": sum(1 for r in reports if r.severity == SeverityLevel.SEVERE),
            "critical_count": sum(1 for r in reports if r.severity == SeverityLevel.CRITICAL),
            "warning_count": sum(1 for r in reports if r.severity == SeverityLevel.WARNING),
        }
    
    def get_full_report(self) -> dict:
        """获取完整性能报告"""
        with self._metrics_lock:
            all_metrics = list(self._metrics.values())
        
        # 按类型分组
        by_type = {}
        for m in all_metrics:
            type_name = m.component_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(m.to_dict())
        
        # 慢组件报告
        slow_reports = self.generate_performance_reports()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "thresholds": self._thresholds,
            "summary": {
                "total_components": len(all_metrics),
                "slow_components": len(slow_reports),
                "by_type": {k: len(v) for k, v in by_type.items()},
            },
            "by_type": by_type,
            "slow_reports": [
                {
                    "component_id": r.component_id,
                    "component_name": r.component_name,
                    "component_type": r.component_type.value,
                    "severity": r.severity.value,
                    "avg_time_ms": r.avg_time_ms,
                    "max_time_ms": r.max_time_ms,
                    "recommendation": r.recommendation,
                }
                for r in slow_reports
            ],
        }
    
    def reset_metrics(self, component_type: ComponentType = None, component_id: str = None):
        """重置性能指标"""
        with self._metrics_lock:
            if component_id and component_type:
                key = (component_type, component_id)
                if key in self._metrics:
                    del self._metrics[key]
            elif component_type:
                keys_to_remove = [k for k in self._metrics.keys() if k[0] == component_type]
                for key in keys_to_remove:
                    del self._metrics[key]
            else:
                self._metrics.clear()
    
    def _log(self, level: str, message: str, **extra):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[{ts}][NajaPerformanceMonitor][{level}] {message} | {extra_str}")


# 全局实例
_performance_monitor: Optional[NajaPerformanceMonitor] = None
_performance_monitor_lock = threading.Lock()


def get_performance_monitor() -> NajaPerformanceMonitor:
    """获取性能监控器单例"""
    global _performance_monitor
    if _performance_monitor is None:
        with _performance_monitor_lock:
            if _performance_monitor is None:
                _performance_monitor = NajaPerformanceMonitor()
    return _performance_monitor


def start_performance_monitoring() -> NajaPerformanceMonitor:
    """启动性能监控"""
    monitor = get_performance_monitor()
    monitor.start_monitoring()
    return monitor


def stop_performance_monitoring():
    """停止性能监控"""
    monitor = get_performance_monitor()
    monitor.stop_monitoring()


def record_component_execution(
    component_id: str,
    component_name: str,
    component_type: Union[ComponentType, str],
    execution_time_ms: float,
    success: bool = True,
    error: str = "",
    expected_interval_ms: float = 0.0,
):
    """记录组件执行 (便捷函数)
    
    Args:
        expected_interval_ms: 期望的调用间隔，用于抖动检测。如设为5000表示期望每5秒调用一次。
    """
    monitor = get_performance_monitor()
    
    if isinstance(component_type, str):
        component_type = ComponentType(component_type)
    
    monitor.record_execution(
        component_id=component_id,
        component_name=component_name,
        component_type=component_type,
        execution_time_ms=execution_time_ms,
        success=success,
        error=error,
        expected_interval_ms=expected_interval_ms,
    )


def record_data_arrival(
    datasource_id: str,
    expected_interval_ms: float = 5000.0,
):
    """记录数据源数据到达，用于检测数据到达抖动
    
    Args:
        datasource_id: 数据源ID
        expected_interval_ms: 期望的数据到达间隔，默认5秒
    """
    monitor = get_performance_monitor()
    monitor.record_data_arrival(datasource_id, expected_interval_ms)


def record_web_request(
    request_path: str,
    execution_time_ms: float,
    success: bool = True,
    error: str = "",
):
    """记录 Web 请求性能
    
    Args:
        request_path: 请求路径，如 /naja/strategy
        execution_time_ms: 请求处理耗时（毫秒）
        success: 是否成功
        error: 错误信息（可选）
    """
    record_component_execution(
        component_id=request_path,
        component_name=request_path,
        component_type=ComponentType.WEB_REQUEST,
        execution_time_ms=execution_time_ms,
        success=success,
        error=error,
    )


def record_lock_wait(
    lock_name: str,
    wait_time_ms: float,
    operation: str = "",
):
    """记录锁等待性能
    
    Args:
        lock_name: 锁名称
        wait_time_ms: 等待时间（毫秒）
        operation: 当前操作描述
    """
    component_id = f"{lock_name}:{operation}" if operation else lock_name
    record_component_execution(
        component_id=component_id,
        component_name=f"{lock_name} 锁等待",
        component_type=ComponentType.LOCK_WAIT,
        execution_time_ms=wait_time_ms,
        success=wait_time_ms < 1000,  # 超过1秒认为有问题
        error=f"等待时间: {wait_time_ms:.1f}ms" if wait_time_ms >= 1000 else "",
    )


def record_thread_pool_metrics():
    """记录线程池性能指标
    
    从全局线程池获取统计数据并记录到性能监控中。
    建议定期调用（如每10秒）以监控线程池状态。
    """
    try:
        from deva.naja.infra.runtime.thread_pool import get_thread_pool
        
        pool = get_thread_pool()
        stats = pool.get_stats()
        
        pending = stats.get("pending_tasks", 0)
        max_workers = stats.get("max_workers", 8)
        
        pending_per_worker = pending / max_workers if max_workers > 0 else 0
        
        record_component_execution(
            component_id="global_thread_pool",
            component_name="全局线程池",
            component_type=ComponentType.THREAD_POOL,
            execution_time_ms=pending_per_worker * 10,
            success=pending < max_workers * 10,
            error=f"待处理: {pending}, 线程: {max_workers}" if pending >= max_workers * 10 else "",
        )
        
        return stats
    except Exception as e:
        return {"error": str(e)}


def get_thread_pool_status() -> Dict[str, Any]:
    """获取线程池状态（便捷函数）
    
    Returns:
        包含线程池统计和健康状态的字典
    """
    try:
        from deva.naja.infra.runtime.thread_pool import get_thread_pool
        
        pool = get_thread_pool()
        stats = pool.get_stats()
        
        pending = stats.get("pending_tasks", 0)
        max_workers = stats.get("max_workers", 8)
        
        health_status = "healthy"
        if pending > max_workers * 10:
            health_status = "overloaded"
        elif pending > max_workers * 5:
            health_status = "busy"
        elif pending > max_workers * 2:
            health_status = "moderate"
        
        return {
            "status": health_status,
            "stats": stats,
            "recommendation": _get_thread_pool_recommendation(stats),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _get_thread_pool_recommendation(stats: Dict[str, Any]) -> str:
    """根据线程池统计生成优化建议"""
    pending = stats.get("pending_tasks", 0)
    max_workers = stats.get("max_workers", 8)
    rejected = stats.get("total_rejected", 0)
    
    if rejected > 0:
        return f"建议增加线程数，当前拒绝任务数: {rejected}"
    
    if pending > max_workers * 15:
        return f"严重过载！建议立即增加线程数（当前 {max_workers}）到 {max_workers * 2} 或更多"
    
    if pending > max_workers * 10:
        return f"过载警告，建议增加线程数（当前 {max_workers}）"
    
    if pending < max_workers and max_workers > 4:
        return f"负载较低，可考虑减少线程数（当前 {max_workers}）以节省资源"
    
    return "运行正常"


def adjust_thread_pool(max_workers: int = None, max_queue_size: int = None) -> Dict[str, Any]:
    """动态调整线程池参数
    
    Args:
        max_workers: 最大工作线程数（1-32）
        max_queue_size: 最大队列大小（10-10000）
    
    Returns:
        调整后的状态
    """
    try:
        from deva.naja.infra.runtime.thread_pool import get_thread_pool
        
        pool = get_thread_pool()
        
        if max_workers is not None:
            pool.max_workers = max_workers
        
        if max_queue_size is not None:
            pool.max_queue_size = max_queue_size
        
        return {
            "success": True,
            "new_config": {
                "max_workers": pool.max_workers,
                "max_queue_size": pool.max_queue_size,
            },
            "status": get_thread_pool_status(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
