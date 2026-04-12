"""State Module - 统一状态管理

合并了原 system_state/ 和 runtime_state/ 两个模块，并包含业务快照：
- state.system: 系统唤醒同步（SystemStateManager, WakeSyncManager）
- state.runtime: 运行时状态持久化（RuntimeStateManager, adapters）
- state.snapshot: 业务数据快照（热点/市场/决策）
"""

from .system.system_state import SystemStateManager
from .system.wake_sync_manager import WakeSyncManager, WakeSyncable
from .runtime.manager import (
    RuntimeStateManager,
    StatefulComponent,
    ComponentStateInfo,
    StateStatus,
    get_runtime_state_manager,
    register_stateful_component,
    load_all_state,
    save_all_state,
)
from .snapshot import (
    SnapshotManager,
    HotspotSnapshotRecord,
    MarketStateSnapshot,
    BanditDecisionContext,
    get_snapshot_manager,
    record_hotspot_snapshot,
    record_market_state_snapshot,
    record_bandit_decision,
)

__all__ = [
    # system
    "SystemStateManager",
    "WakeSyncManager",
    "WakeSyncable",
    # runtime
    "RuntimeStateManager",
    "StatefulComponent",
    "ComponentStateInfo",
    "StateStatus",
    "get_runtime_state_manager",
    "register_stateful_component",
    "load_all_state",
    "save_all_state",
    # snapshot
    "SnapshotManager",
    "HotspotSnapshotRecord",
    "MarketStateSnapshot",
    "BanditDecisionContext",
    "get_snapshot_manager",
    "record_hotspot_snapshot",
    "record_market_state_snapshot",
    "record_bandit_decision",
]
