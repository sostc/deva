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

from .datasource import (
    DataSourceEntry,
    DataSourceManager,
    get_datasource_manager,
)

from .tasks import (
    TaskEntry,
    TaskManager,
    get_task_manager,
)

from .strategy import (
    StrategyEntry,
    StrategyManager,
    get_strategy_manager,
)

from .dictionary import (
    DictionaryEntry,
    DictionaryManager,
    get_dictionary_manager,
)

__version__ = "2.0.0"

__all__ = [
    # Base
    "RecoverableUnit",
    "UnitMetadata",
    "UnitState",
    "UnitStatus",
    "RecoveryManager",
    "recovery_manager",
    # DataSource
    "DataSourceEntry",
    "DataSourceManager",
    "get_datasource_manager",
    # Task
    "TaskEntry",
    "TaskManager",
    "get_task_manager",
    # Strategy
    "StrategyEntry",
    "StrategyManager",
    "get_strategy_manager",
    # Dictionary
    "DictionaryEntry",
    "DictionaryManager",
    "get_dictionary_manager",
]
