"""Naja - 统一可恢复单元管理平台

基于 RecoverableUnit 抽象的统一管理平台。
"""

from .common.recoverable import (
    RecoverableUnit,
    UnitMetadata,
    UnitState,
    UnitStatus,
    RecoveryManager,
    recovery_manager,
)

from .tasks import (
    TaskEntry,
    TaskManager,
)

from .strategy import (
    StrategyEntry,
    StrategyManager,
    get_strategy_manager,
)

from .dictionary import (
    DictionaryEntry,
    DictionaryManager,
)

from .signal import (
    render_signal_page,
    set_auto_refresh,
    is_auto_refresh_enabled,
)

from .radar import (
    RadarEngine,
    get_radar_engine,
)

from .supervisor import (
    NajaSupervisor,
    get_naja_supervisor,
    stop_supervisor,
)

from .attention.manas_alaya_connector import ManasAlayaConnector

__version__ = "2.0.0"

__all__ = [
    # Base
    "RecoverableUnit",
    "UnitMetadata",
    "UnitState",
    "UnitStatus",
    "RecoveryManager",
    "recovery_manager",
    # Task
    "TaskEntry",
    "TaskManager",
    # Strategy
    "StrategyEntry",
    "StrategyManager",
    "get_strategy_manager",
    # Dictionary
    "DictionaryEntry",
    "DictionaryManager",
    # Signal
    "render_signal_page",
    "set_auto_refresh",
    "is_auto_refresh_enabled",
    # Radar
    "RadarEngine",
    "get_radar_engine",
    # Supervisor
    "NajaSupervisor",
    "get_naja_supervisor",
    "stop_supervisor",
    # Manas-Alaya Connector
    "ManasAlayaConnector",
]
