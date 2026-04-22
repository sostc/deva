"""
WakeSyncManager - 系统唤醒同步管理器

核心功能：
1. 管理所有需要同步的组件（WakeSyncable）
2. 系统唤醒时自动检测需要同步的任务
3. 根据休眠时长判断同步范围（最多24小时）
4. 渐进式执行：按优先级排队，异步非阻塞执行
5. 持久化同步状态，支持去重

使用方式：
1. 各组件实现 WakeSyncable 协议
2. 在 WakeSyncManager 注册组件（可指定优先级）
3. 系统唤醒时调用 perform_wake_sync()

设计理念：
- 系统长时间休眠后，与外部世界重新同步
- 有限制地同步（不是全量拉取），保持与世界的状态一致
- 渐进式执行：按优先级排队，不影响系统整体性能
- 持久化同步结果，避免重复执行
"""

import json
import logging
import os
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Protocol, Tuple
from dataclasses import dataclass, asdict
from deva.naja.register import SR

log = logging.getLogger(__name__)

_STATE_FILE = os.path.expanduser("~/.naja/wake_sync_state.json")


class WakeSyncable(Protocol):
    """可同步的组件接口"""

    @property
    def name(self) -> str:
        """组件名称"""
        ...

    @property
    def description(self) -> str:
        """组件描述"""
        ...

    @property
    def priority(self) -> int:
        """优先级，数字越小优先级越高"""
        return 5

    def should_wake_sync(self, last_active: datetime) -> bool:
        """
        判断是否需要同步

        Args:
            last_active: 上次活跃时间

        Returns:
            True if 需要同步
        """
        ...

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """
        获取同步时间范围

        Args:
            last_active: 上次活跃时间
            max_hours: 最大同步小时数

        Returns:
            (start_time, end_time)
        """
        ...

    def execute_wake_sync(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """
        执行同步

        Args:
            start: 开始时间
            end: 结束时间

        Returns:
            {"success": bool, "message": str, "details": dict}
        """
        ...


@dataclass
class WakeSyncResult:
    """同步结果"""
    component_name: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    message: str
    details: Dict[str, Any]


class WakeSyncManager:
    """
    统一唤醒同步管理器

    管理所有需要同步的组件，系统唤醒时自动执行同步。

    特性：
    - 优先级执行：数字越小优先级越高
    - 渐进式执行：任务之间有延迟，避免系统负载过高
    - 异步非阻塞：后台线程执行，不阻塞主流程
    - 持久化：同步结果持久化到 ~/.naja/wake_sync_state.json
    - 去重：避免同一组件在短时间内重复执行
    """

    MAX_WAKE_SYNC_HOURS = 24
    DELAY_BETWEEN_TASKS = 2.0
    DEDUP_INTERVAL_SECONDS = 300  # 5分钟内不重复执行同一组件

    def __init__(self):
        self._components: Dict[str, WakeSyncable] = {}
        self._last_wake_sync_time: Optional[datetime] = None
        self._wake_sync_results: List[WakeSyncResult] = []
        self._sync_queue: List[WakeSyncable] = []
        self._sync_thread: Optional[threading.Thread] = None
        self._sync_lock = threading.Lock()
        self._last_sync_per_component: Dict[str, float] = {}  # name -> timestamp
        self._load_persisted_state()

    def _load_persisted_state(self):
        """从持久化文件加载上次同步状态"""
        try:
            if os.path.exists(_STATE_FILE):
                with open(_STATE_FILE, 'r') as f:
                    state = json.load(f)
                self._last_sync_per_component = state.get("last_sync_per_component", {})
                log.info(f"[WakeSync] 加载持久化状态: {len(self._last_sync_per_component)} 个组件记录")
        except Exception as e:
            log.warning(f"[WakeSync] 加载持久化状态失败: {e}")
            self._last_sync_per_component = {}

    def _persist_state(self):
        """持久化同步状态到文件"""
        try:
            os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
            state = {
                "last_sync_per_component": self._last_sync_per_component,
                "last_wake_sync_time": self._last_wake_sync_time.isoformat() if self._last_wake_sync_time else None,
            }
            with open(_STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            log.warning(f"[WakeSync] 持久化状态失败: {e}")

    def register(self, component: WakeSyncable):
        """
        注册同步组件

        Args:
            component: 实现 WakeSyncable 接口的组件
        """
        priority = getattr(component, 'priority', 5)
        self._components[component.name] = component
        log.info(f"[WakeSync] 已注册组件: {component.name} (优先级={priority}) - {component.description}")

    def unregister(self, name: str):
        """取消注册组件"""
        if name in self._components:
            del self._components[name]
            log.info(f"[WakeSync] 已取消注册组件: {name}")

    def get_registered_components(self) -> List[str]:
        """获取已注册的组件名称列表"""
        return list(self._components.keys())

    def is_component_synced_recently(self, name: str) -> bool:
        """检查组件是否在去重间隔内已执行过同步"""
        last_ts = self._last_sync_per_component.get(name, 0)
        if last_ts <= 0:
            return False
        return (time.time() - last_ts) < self.DEDUP_INTERVAL_SECONDS

    def perform_wake_sync(self, last_active: datetime) -> Dict[str, Any]:
        """
        执行唤醒同步

        系统唤醒时调用，检测所有注册组件是否需要同步。
        采用渐进式执行：将任务加入队列，由后台线程按优先级顺序执行。

        Args:
            last_active: 上次活跃时间

        Returns:
            同步结果汇总
        """
        if not last_active:
            log.info("[WakeSync] 无上次活跃时间，跳过同步")
            return {"success": True, "message": "无上次活跃时间", "components": []}

        now = datetime.now()
        sleep_duration = (now - last_active).total_seconds()
        sleep_hours = sleep_duration / 3600

        log.info(f"[WakeSync] 开始同步检查，上次活跃: {last_active}，休眠时长: {sleep_hours:.2f}小时")

        components_to_sync = []
        for name, component in self._components.items():
            try:
                if self.is_component_synced_recently(name):
                    log.info(f"[WakeSync] {name}: 去重跳过（5 分钟内已执行）")
                    continue
                if not component.should_wake_sync(last_active):
                    log.info(f"[WakeSync] {name}: 无需同步")
                    continue
                components_to_sync.append(component)
            except Exception as e:
                log.warning(f"[WakeSync] {name}: should_wake_sync 检查失败 - {e}")

        if not components_to_sync:
            log.info("[WakeSync] 没有组件需要同步")
            return {"success": True, "message": "无组件需要同步", "components": []}

        components_to_sync.sort(key=lambda c: getattr(c, 'priority', 5))

        log.info(f"[WakeSync] 需要同步 {len(components_to_sync)} 个组件，按优先级排序")

        for i, component in enumerate(components_to_sync):
            priority = getattr(component, 'priority', 5)
            log.info(f"[WakeSync]   {i+1}. {component.name} (优先级={priority})")

        self._sync_queue = components_to_sync
        self._last_wake_sync_time = now

        self._sync_thread = threading.Thread(
            target=self._progressive_sync_worker,
            args=(last_active,),
            daemon=True,
            name='wake-sync-worker'
        )
        self._sync_thread.start()

        return {
            "success": True,
            "message": f"已启动渐进式同步: {len(components_to_sync)} 个组件",
            "sleep_hours": round(sleep_hours, 2),
            "components": [
                {
                    "name": c.name,
                    "priority": getattr(c, 'priority', 5),
                }
                for c in components_to_sync
            ],
            "async": True
        }

    def _progressive_sync_worker(self, last_active: datetime):
        """后台渐进式同步工作线程"""
        results = []
        synced_count = 0

        for component in self._sync_queue:
            try:
                start_time = datetime.now()
                start_exec = time.time()

                start_range, end_range = component.get_wake_sync_range(
                    last_active, self.MAX_WAKE_SYNC_HOURS
                )
                duration = (end_range - start_range).total_seconds()

                log.info(f"[WakeSync] 执行 {component.name}: 范围 {start_range} ~ {end_range} ({duration/3600:.2f}小时)")

                result = component.execute_wake_sync(start_range, end_range)
                exec_duration = time.time() - start_exec

                wake_sync_result = WakeSyncResult(
                    component_name=component.name,
                    success=result.get("success", False),
                    start_time=start_time,
                    end_time=datetime.now(),
                    duration_seconds=exec_duration,
                    message=result.get("message", ""),
                    details=result
                )
                results.append(wake_sync_result)

                if result.get("success"):
                    synced_count += 1
                    self._last_sync_per_component[component.name] = time.time()
                    log.info(f"[WakeSync] {component.name}: 同步成功 ({exec_duration:.2f}秒)")
                else:
                    log.warning(f"[WakeSync] {component.name}: 同步失败 - {result.get('message', '未知错误')}")

            except Exception as e:
                log.error(f"[WakeSync] {component.name}: 同步异常 - {e}")
                import traceback
                traceback.print_exc()

            time.sleep(self.DELAY_BETWEEN_TASKS)

        self._wake_sync_results = results
        self._persist_state()

        summary = {
            "success": synced_count > 0,
            "message": f"渐进式同步完成: {synced_count}/{len(self._sync_queue)} 个组件成功",
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

        log.info(f"[WakeSync] {summary['message']}")


def _register_default_components():
    """注册默认的同步组件"""
    manager = _wake_sync_manager

    from deva.naja.state.system.wake_sync_handlers import (
        AIDailyReportWakeSync,
        NewsFetcherWakeSync,
        GlobalMarketScannerWakeSync,
        DailyReviewWakeSync,
        PortfolioPriceWakeSync,
    )

    manager.register(PortfolioPriceWakeSync())
    manager.register(NewsFetcherWakeSync())
    manager.register(GlobalMarketScannerWakeSync())
    manager.register(DailyReviewWakeSync())
    manager.register(AIDailyReportWakeSync())

    log.info("[WakeSync] 已注册默认同步组件")


_wake_sync_manager = WakeSyncManager()
