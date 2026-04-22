"""WakeOrchestrator — 系统唤醒补作业统一编排器

职责：
1. 系统启动或心跳检测"断片"时统一触发
2. 协调组件恢复（RecoveryLifecycleMixin）与数据补齐（WakeSyncManager）
3. 基于休眠时长决定补作业策略

归属层：application（运行时装配与生命周期）

调用链：
  AppContainer._perform_wake_sync()
    -> WakeOrchestrator.wake()
       -> (1) RecoveryLifecycleMixin.restore_all_states()  组件内部状态恢复
       -> (2) WakeSyncManager.perform_wake_sync()           外部数据补齐
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, TYPE_CHECKING

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from deva.naja.state.system.system_state import SystemStateManager


class WakeOrchestrator:
    """唤醒补作业编排器

    统一协调系统唤醒时的恢复流程：
    - 休眠 < 1 小时：跳过所有补作业
    - 休眠 1-2 小时：仅做组件状态恢复 + 核心数据同步（持仓价格、新闻）
    - 休眠 2 小时以上：全量补作业（含复盘、AI 日报等）
    """

    SKIP_THRESHOLD_HOURS = 1.0
    LIGHT_SYNC_THRESHOLD_HOURS = 2.0

    def __init__(self, state_manager: "SystemStateManager"):
        self._state_manager = state_manager

    def wake(self) -> Dict[str, Any]:
        """执行唤醒补作业流程

        这是系统启动时的统一入口，内部按顺序协调各层恢复逻辑。
        """
        state_summary = self._state_manager.get_state_summary()
        sleep_hours = state_summary.get("sleep_duration_hours", 0)

        log.info(f"[WakeOrchestrator] 唤醒开始，休眠时长: {sleep_hours:.2f} 小时")

        if sleep_hours < self.SKIP_THRESHOLD_HOURS:
            log.info(f"[WakeOrchestrator] 休眠不足 {self.SKIP_THRESHOLD_HOURS} 小时，跳过补作业")
            return {
                "success": True,
                "action": "skipped",
                "reason": f"休眠时长 {sleep_hours:.2f}h < {self.SKIP_THRESHOLD_HOURS}h 阈值",
            }

        results = {
            "success": True,
            "sleep_hours": round(sleep_hours, 2),
            "recovery": None,
            "wake_sync": None,
        }

        last_active = self._state_manager.get_last_active_time()
        if last_active:
            results["recovery"] = self._recover_components()
            results["wake_sync"] = self._sync_external_data(last_active, sleep_hours)
        else:
            log.info("[WakeOrchestrator] 无上次活跃时间记录，仅做组件恢复")
            results["recovery"] = self._recover_components()

        return results

    def _recover_components(self) -> Dict[str, Any]:
        """恢复组件内部运行状态（策略/数据源/任务的启停状态）

        归属：infra 层 RecoveryManager 的职责，此处仅做协调调用。
        """
        from deva.naja.infra.runtime.recoverable import recovery_manager

        try:
            result = recovery_manager.restore_all(
                order=["datasource", "strategy", "task"]
            )
            log.info(f"[WakeOrchestrator] 组件状态恢复完成")
            return result
        except Exception as e:
            log.error(f"[WakeOrchestrator] 组件状态恢复失败: {e}")
            return {"success": False, "error": str(e)}

    def _sync_external_data(self, last_active: datetime, sleep_hours: float) -> Dict[str, Any]:
        """补齐外部数据（新闻/行情/复盘等）

        根据休眠时长决定同步范围：
        - sleep_hours < 2: 仅同步核心数据（持仓价格 + 新闻）
        - sleep_hours >= 2: 全量同步
        """
        from deva.naja.state.system.wake_sync_manager import _wake_sync_manager

        try:
            if sleep_hours < self.LIGHT_SYNC_THRESHOLD_HOURS:
                log.info("[WakeOrchestrator] 轻量同步模式（仅持仓价格 + 新闻）")
                return self._light_sync(last_active)
            else:
                log.info("[WakeOrchestrator] 全量同步模式")
                return _wake_sync_manager.perform_wake_sync(last_active)
        except Exception as e:
            log.error(f"[WakeOrchestrator] 外部数据同步失败: {e}")
            return {"success": False, "error": str(e)}

    def _light_sync(self, last_active: datetime) -> Dict[str, Any]:
        """轻量同步：仅执行优先级最高的核心组件

        避免短时间休眠后执行不必要的复盘/AI 报告等重操作。
        """
        from deva.naja.state.system.wake_sync_manager import _wake_sync_manager

        core_names = ["Portfolio_Price", "News_Fetcher"]

        results = []
        synced_count = 0
        for name in core_names:
            component = _wake_sync_manager._components.get(name)
            if not component:
                continue
            try:
                if not component.should_wake_sync(last_active):
                    log.info(f"[WakeOrchestrator] 轻量跳过 {name}")
                    continue
                start_range, end_range = component.get_wake_sync_range(last_active)
                result = component.execute_wake_sync(start_range, end_range)
                if result.get("success"):
                    synced_count += 1
                results.append({"name": name, **result})
            except Exception as e:
                log.warning(f"[WakeOrchestrator] 轻量同步 {name} 失败: {e}")
                results.append({"name": name, "success": False, "error": str(e)})

        return {
            "success": synced_count > 0,
            "mode": "light",
            "components": results,
        }


_wake_orchestrator: Optional[WakeOrchestrator] = None


def get_wake_orchestrator() -> WakeOrchestrator:
    """获取唤醒编排器单例"""
    global _wake_orchestrator
    if _wake_orchestrator is None:
        from deva.naja.register import SR
        state_mgr = SR('system_state_manager')
        _wake_orchestrator = WakeOrchestrator(state_mgr)
    return _wake_orchestrator
