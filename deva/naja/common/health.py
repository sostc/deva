"""HealthCheck - 组件健康检查"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from deva.naja.register import SR


logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthReport:
    """健康报告"""
    status: HealthStatus
    component: str
    timestamp: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY

    @property
    def is_degraded(self) -> bool:
        return self.status == HealthStatus.DEGRADED

    @property
    def is_unhealthy(self) -> bool:
        return self.status == HealthStatus.UNHEALTHY

    def __str__(self) -> str:
        icon = {
            HealthStatus.HEALTHY: "✓",
            HealthStatus.DEGRADED: "⚠",
            HealthStatus.UNHEALTHY: "✗",
            HealthStatus.UNKNOWN: "?",
        }.get(self.status, "?")

        return f"{icon} [{self.component}] {self.status.value}: {self.message}"


class ComponentHealthCheck:
    """
    单个组件的健康检查

    用法:
        check = ComponentHealthCheck("my_component")

        check.add_check("data_source", lambda: is_ds_running())
        check.add_check("memory", lambda: get_memory_usage() < 0.9)

        report = check.run()
        print(report)
    """

    def __init__(
        self,
        component_name: str,
        checks: Optional[Dict[str, Callable[[], bool]]] = None,
    ):
        self.component = component_name
        self._checks: Dict[str, Callable[[], bool]] = checks or {}
        self._last_report: Optional[HealthReport] = None

    def add_check(self, name: str, check_func: Callable[[], bool]):
        """添加检查项"""
        self._checks[name] = check_func

    def remove_check(self, name: str) -> bool:
        """移除检查项"""
        if name in self._checks:
            del self._checks[name]
            return True
        return False

    def run(self) -> HealthReport:
        """运行健康检查"""
        if not self._checks:
            return HealthReport(
                status=HealthStatus.UNKNOWN,
                component=self.component,
                timestamp=time.time(),
                message="没有配置检查项",
            )

        results = {}
        issues = []

        for name, check_func in self._checks.items():
            try:
                result = check_func()
                results[name] = {
                    'passed': bool(result),
                    'error': None,
                }
                if not result:
                    issues.append(f"{name} failed")
            except Exception as e:
                results[name] = {
                    'passed': False,
                    'error': str(e),
                }
                issues.append(f"{name} error: {e}")

        passed_count = sum(1 for r in results.values() if r['passed'])
        total_count = len(results)

        if passed_count == total_count:
            status = HealthStatus.HEALTHY
            message = f"All {total_count} checks passed"
        elif passed_count > 0:
            status = HealthStatus.DEGRADED
            message = f"{passed_count}/{total_count} checks passed"
        else:
            status = HealthStatus.UNHEALTHY
            message = f"All {total_count} checks failed"

        self._last_report = HealthReport(
            status=status,
            component=self.component,
            timestamp=time.time(),
            message=message,
            details={'checks': results},
            issues=issues,
        )

        return self._last_report

    @property
    def last_report(self) -> Optional[HealthReport]:
        """上次健康报告"""
        return self._last_report


class HealthCheckManager:
    """
    健康检查管理器 - 统一管理所有组件的健康检查

    用法:
        manager = HealthCheckManager()

        manager.register("orchestrator", orchestrator_check)
        manager.register("datasource", datasource_check)
        manager.register("attention", attention_check)

        # 全面检查
        reports = manager.check_all()

        # 检查特定组件
        report = manager.check("orchestrator")
    """

    def __init__(self):
        self._components: Dict[str, ComponentHealthCheck] = {}

    def register(
        self,
        component: str,
        checks: Optional[Dict[str, Callable[[], bool]]] = None,
    ) -> ComponentHealthCheck:
        """注册组件"""
        check = ComponentHealthCheck(component, checks)
        self._components[component] = check
        return check

    def unregister(self, component: str) -> bool:
        """注销组件"""
        if component in self._components:
            del self._components[component]
            return True
        return False

    def get_check(self, component: str) -> Optional[ComponentHealthCheck]:
        """获取组件检查器"""
        return self._components.get(component)

    def check(self, component: str) -> Optional[HealthReport]:
        """检查单个组件"""
        check = self._components.get(component)
        if check is None:
            return None
        return check.run()

    def check_all(self) -> Dict[str, HealthReport]:
        """检查所有组件"""
        reports = {}
        for name, check in self._components.items():
            try:
                reports[name] = check.run()
            except Exception as e:
                logger.exception(f"Health check for {name} failed: {e}")
                reports[name] = HealthReport(
                    status=HealthStatus.UNKNOWN,
                    component=name,
                    timestamp=time.time(),
                    message=f"Health check error: {e}",
                )
        return reports

    def get_overall_status(self) -> HealthReport:
        """获取总体状态"""
        reports = self.check_all()

        if not reports:
            return HealthReport(
                status=HealthStatus.UNKNOWN,
                component="system",
                timestamp=time.time(),
                message="No components registered",
            )

        healthy = sum(1 for r in reports.values() if r.is_healthy)
        degraded = sum(1 for r in reports.values() if r.is_degraded)
        unhealthy = sum(1 for r in reports.values() if r.is_unhealthy)

        all_issues = []
        for r in reports.values():
            all_issues.extend(r.issues)

        if unhealthy > 0:
            status = HealthStatus.UNHEALTHY
            message = f"{unhealthy} unhealthy, {degraded} degraded, {healthy} healthy"
        elif degraded > 0:
            status = HealthStatus.DEGRADED
            message = f"{degraded} degraded, {healthy} healthy"
        elif healthy == len(reports):
            status = HealthStatus.HEALTHY
            message = f"All {healthy} components healthy"
        else:
            status = HealthStatus.UNKNOWN
            message = f"{healthy}/{len(reports)} components healthy"

        return HealthReport(
            status=status,
            component="system",
            timestamp=time.time(),
            message=message,
            details={
                'healthy': healthy,
                'degraded': degraded,
                'unhealthy': unhealthy,
                'total': len(reports),
            },
            issues=all_issues,
        )

    def __repr__(self) -> str:
        return f"HealthCheckManager(components={len(self._components)})"


_health_check_manager: Optional[HealthCheckManager] = None


def get_health_check_manager() -> HealthCheckManager:
    """获取全局健康检查管理器"""
    global _health_check_manager
    if _health_check_manager is None:
        _health_check_manager = HealthCheckManager()
    return _health_check_manager


def create_attention_health_checks() -> Dict[str, Callable[[], bool]]:
    """创建注意力系统健康检查项"""
    from deva.naja.market_hotspot.integration import get_market_hotspot_integration

    def check_attention_system():
        integration = get_market_hotspot_integration()
        return integration is not None and integration.hotspot_system is not None

    def check_datasource():
        from deva.naja.datasource import get_datasource_manager
        mgr = get_datasource_manager()
        running = sum(1 for e in mgr.list_all() if e.is_running)
        return running > 0

    def check_dictionary():
        mgr = SR('dictionary_manager')
        entry = mgr.get_by_name("通达信概念板块")
        if entry is None:
            return False
        payload = entry.get_payload()
        return payload is not None and not payload.empty

    return {
        "attention_system": check_attention_system,
        "datasource": check_datasource,
        "dictionary": check_dictionary,
    }


__all__ = [
    'HealthStatus',
    'HealthReport',
    'ComponentHealthCheck',
    'HealthCheckManager',
    'get_health_check_manager',
    'create_attention_health_checks',
]
