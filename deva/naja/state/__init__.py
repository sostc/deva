"""State Module - 统一状态管理

合并了原 system_state/ 和 runtime_state/ 两个模块，并包含业务快照：
- state.system: 系统唤醒同步（SystemStateManager, WakeSyncManager）
- state.snapshot: 业务数据快照（热点/市场/决策）
"""

from .system.system_state import SystemStateManager
from .system.wake_sync_manager import WakeSyncManager, WakeSyncable
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
