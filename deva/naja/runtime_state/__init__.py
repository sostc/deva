"""运行时状态管理模块

提供统一的运行时状态持久化管理。
"""

from deva.naja.runtime_state.manager import (
    RuntimeStateManager,
    StatefulComponent,
    ComponentStateInfo,
    StateStatus,
    get_runtime_state_manager,
    register_stateful_component,
    load_all_state,
    save_all_state,
)
from deva.naja.runtime_state.adapters import (
    DataSourceManagerAdapter,
    TaskManagerAdapter,
    StrategyManagerAdapter,
    AttentionCenterAdapter,
    BanditRunnerAdapter,
    RadarEngineAdapter,
    SignalTunerAdapter,
    register_all_adapters,
)

__all__ = [
    "RuntimeStateManager",
    "StatefulComponent",
    "ComponentStateInfo",
    "StateStatus",
    "get_runtime_state_manager",
    "register_stateful_component",
    "load_all_state",
    "save_all_state",
    "DataSourceManagerAdapter",
    "TaskManagerAdapter",
    "StrategyManagerAdapter",
    "AttentionCenterAdapter",
    "BanditRunnerAdapter",
    "RadarEngineAdapter",
    "register_all_adapters",
]