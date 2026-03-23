"""ManagerHealthMixin - 为 Manager 类提供健康检查功能"""

import time
import logging
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ManagerHealthReport:
    """Manager 健康报告"""
    component: str
    healthy: bool
    timestamp: float
    item_count: int
    running_count: int
    error_count: int
    issues: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "✓" if self.healthy else "✗"
        return f"{status} [{self.component}] items={self.item_count}, running={self.running_count}, errors={self.error_count}"


class ManagerHealthMixin:
    """
    Manager 健康检查混入类

    为 Manager 类提供标准化的健康检查功能

    用法:
        class DataSourceManager(ManagerHealthMixin):
            def __init__(self):
                self._init_health_mixin("DataSourceManager")
                ...

            def health_check(self) -> ManagerHealthReport:
                return self._do_health_check()
    """

    def _init_health_mixin(
        self,
        component_name: str,
        get_items_func: Optional[Callable] = None,
        is_running_func: Optional[Callable] = None,
    ):
        """初始化健康检查混入"""
        self._health_component = component_name
        self._health_get_items = get_items_func
        self._health_is_running = is_running_func
        self._health_last_report: Optional[ManagerHealthReport] = None

    def _do_health_check(self) -> ManagerHealthReport:
        """执行健康检查"""
        try:
            items = []
            if self._health_get_items:
                items = self._health_get_items()
            elif hasattr(self, 'list_all'):
                items = self.list_all()
            elif hasattr(self, '_items'):
                items = list(self._items.values())

            item_count = len(items)
            running_count = 0
            error_count = 0
            issues = []

            for item in items:
                try:
                    if self._health_is_running:
                        if self._health_is_running(item):
                            running_count += 1
                    elif hasattr(item, 'is_running'):
                        if item.is_running:
                            running_count += 1
                except Exception:
                    error_count += 1
                    issues.append(f"{getattr(item, 'name', 'unknown')}: is_running check failed")

            healthy = error_count == 0

            report = ManagerHealthReport(
                component=self._health_component,
                healthy=healthy,
                timestamp=time.time(),
                item_count=item_count,
                running_count=running_count,
                error_count=error_count,
                issues=issues,
                details={
                    'total_items': item_count,
                    'running_items': running_count,
                    'error_items': error_count,
                }
            )

            self._health_last_report = report
            return report

        except Exception as e:
            logger.exception(f"[{self._health_component}] Health check failed: {e}")
            report = ManagerHealthReport(
                component=self._health_component,
                healthy=False,
                timestamp=time.time(),
                item_count=0,
                running_count=0,
                error_count=1,
                issues=[f"Health check exception: {str(e)}"]
            )
            self._health_last_report = report
            return report

    def get_last_health_report(self) -> Optional[ManagerHealthReport]:
        """获取上次健康报告"""
        return self._health_last_report


def create_manager_health_check(name: str) -> Callable:
    """
    创建 Manager 健康检查函数

    用法:
        def my_health_check():
            return create_manager_health_check("MyManager")()

        health_check_manager.register("my_manager", {"health_check": my_health_check})
    """
    def health_check_func() -> ManagerHealthReport:
        from deva.naja.common.health import HealthStatus, HealthReport

        try:
            mgr = None
            if name == "DataSource":
                from deva.naja.datasource import get_datasource_manager
                mgr = get_datasource_manager()
            elif name == "Strategy":
                from deva.naja.strategy import get_strategy_manager
                mgr = get_strategy_manager()
            elif name == "Task":
                from deva.naja.tasks import get_task_manager
                mgr = get_task_manager()
            elif name == "Dictionary":
                from deva.naja.dictionary import get_dictionary_manager
                mgr = get_dictionary_manager()

            if mgr is None:
                return ManagerHealthReport(
                    component=name,
                    healthy=False,
                    timestamp=time.time(),
                    item_count=0,
                    running_count=0,
                    error_count=1,
                    issues=[f"Manager not found: {name}"]
                )

            items = mgr.list_all() if hasattr(mgr, 'list_all') else []
            running = sum(1 for i in items if hasattr(i, 'is_running') and i.is_running)

            return ManagerHealthReport(
                component=name,
                healthy=True,
                timestamp=time.time(),
                item_count=len(items),
                running_count=running,
                error_count=0,
            )

        except Exception as e:
            logger.exception(f"Health check for {name} failed: {e}")
            return ManagerHealthReport(
                component=name,
                healthy=False,
                timestamp=time.time(),
                item_count=0,
                running_count=0,
                error_count=1,
                issues=[str(e)]
            )

    return health_check_func


__all__ = [
    'ManagerHealthMixin',
    'ManagerHealthReport',
    'create_manager_health_check',
]
