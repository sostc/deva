"""
BackfillManager - 统一补执行管理器

核心功能：
1. 管理所有需要补执行的组件（Backfillable）
2. 系统启动时自动检测需要补执行的任务
3. 根据休眠时长判断补执行范围（最多24小时）
4. 批量执行补执行任务

使用方式：
1. 各组件实现 Backfillable 协议
2. 在 BackfillManager 注册组件
3. 系统启动时调用 perform_backfill()
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Protocol, Tuple
from dataclasses import dataclass

log = logging.getLogger(__name__)


class Backfillable(Protocol):
    """可补执行的组件接口"""

    @property
    def name(self) -> str:
        """组件名称"""
        ...

    @property
    def description(self) -> str:
        """组件描述"""
        ...

    def should_backfill(self, last_active: datetime) -> bool:
        """
        判断是否需要补执行

        Args:
            last_active: 上次活跃时间

        Returns:
            True if 需要补执行
        """
        ...

    def get_backfill_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """
        获取补执行时间范围

        Args:
            last_active: 上次活跃时间
            max_hours: 最大补执行小时数

        Returns:
            (start_time, end_time)
        """
        ...

    def execute_backfill(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """
        执行补执行

        Args:
            start: 开始时间
            end: 结束时间

        Returns:
            {"success": bool, "message": str, "details": dict}
        """
        ...


@dataclass
class BackfillResult:
    """补执行结果"""
    component_name: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    message: str
    details: Dict[str, Any]


class BackfillManager:
    """
    统一补执行管理器

    管理所有需要补执行的组件，系统启动时自动执行补执行。
    """

    MAX_BACKFILL_HOURS = 24

    def __init__(self):
        self._components: Dict[str, Backfillable] = {}
        self._last_backfill_time: Optional[datetime] = None
        self._backfill_results: List[BackfillResult] = []

    def register(self, component: Backfillable):
        """
        注册补执行组件

        Args:
            component: 实现 Backfillable 接口的组件
        """
        self._components[component.name] = component
        log.info(f"[Backfill] 已注册组件: {component.name} - {component.description}")

    def unregister(self, name: str):
        """取消注册组件"""
        if name in self._components:
            del self._components[name]
            log.info(f"[Backfill] 已取消注册组件: {name}")

    def get_registered_components(self) -> List[str]:
        """获取已注册的组件名称列表"""
        return list(self._components.keys())

    def perform_backfill(self, last_active: datetime) -> Dict[str, Any]:
        """
        执行补执行

        系统启动时调用，检测所有注册组件是否需要补执行。

        Args:
            last_active: 上次活跃时间

        Returns:
            补执行结果汇总
        """
        if not last_active:
            log.info("[Backfill] 无上次活跃时间，跳过补执行")
            return {"success": True, "message": "无上次活跃时间", "components": []}

        now = datetime.now()
        sleep_duration = (now - last_active).total_seconds()
        sleep_hours = sleep_duration / 3600

        log.info(f"[Backfill] 开始补执行检查，上次活跃: {last_active}，休眠时长: {sleep_hours:.2f}小时")

        results = []
        backfilled_count = 0

        for name, component in self._components.items():
            try:
                if not component.should_backfill(last_active):
                    log.info(f"[Backfill] {name}: 无需补执行")
                    continue

                start_time, end_time = component.get_backfill_range(last_active, self.MAX_BACKFILL_HOURS)
                duration = (end_time - start_time).total_seconds()

                log.info(f"[Backfill] {name}: 补执行 {start_time} ~ {end_time} ({duration/3600:.2f}小时)")

                import time
                start_exec = time.time()
                result = component.execute_backfill(start_time, end_time)
                exec_duration = time.time() - start_exec

                backfill_result = BackfillResult(
                    component_name=name,
                    success=result.get("success", False),
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=exec_duration,
                    message=result.get("message", ""),
                    details=result
                )
                results.append(backfill_result)

                if result.get("success"):
                    backfilled_count += 1
                    log.info(f"[Backfill] {name}: 补执行成功 ({exec_duration:.2f}秒)")
                else:
                    log.warning(f"[Backfill] {name}: 补执行失败 - {result.get('message', '未知错误')}")

            except Exception as e:
                log.error(f"[Backfill] {name}: 补执行异常 - {e}")
                import traceback
                traceback.print_exc()

        self._last_backfill_time = now
        self._backfill_results = results

        summary = {
            "success": backfilled_count > 0,
            "message": f"补执行完成: {backfilled_count}/{len(self._components)} 个组件成功",
            "sleep_hours": round(sleep_hours, 2),
            "components": [
                {
                    "name": r.component_name,
                    "success": r.success,
                    "duration_seconds": round(r.duration_seconds, 2),
                    "message": r.message,
                }
                for r in results
            ]
        }

        log.info(f"[Backfill] 补执行汇总: {summary['message']}")
        return summary


_backfill_manager: Optional[BackfillManager] = None


def get_backfill_manager() -> BackfillManager:
    global _backfill_manager
    if _backfill_manager is None:
        _backfill_manager = BackfillManager()
        _register_default_components()
    return _backfill_manager


def _register_default_components():
    """注册默认的补执行组件"""
    manager = _backfill_manager

    from deva.naja.system_state.backfillers import (
        AIDailyReportBackfiller,
        NewsFetcherBackfiller,
        GlobalMarketScannerBackfiller,
        MarketReplayBackfiller,
    )

    manager.register(AIDailyReportBackfiller())
    manager.register(NewsFetcherBackfiller())
    manager.register(GlobalMarketScannerBackfiller())
    manager.register(MarketReplayBackfiller())

    log.info("[Backfill] 已注册默认补执行组件")