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

from .signal import (
    render_signal_page,
    set_auto_refresh,
    is_auto_refresh_enabled,
)

from .tables import (
    get_table_list,
    get_table_info,
    create_table,
    delete_table,
)

from .config import (
    get_config,
    set_config,
    get_datasource_config,
    get_strategy_config,
    get_task_config,
    get_dictionary_config,
    get_strategy_single_history_count,
    get_strategy_total_history_count,
    get_enabled_datasource_types,
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
    # Signal
    "render_signal_page",
    "set_auto_refresh",
    "is_auto_refresh_enabled",
    # Tables
    "get_table_list",
    "get_table_info",
    "create_table",
    "delete_table",
    # Config
    "get_config",
    "set_config",
    "get_datasource_config",
    "get_strategy_config",
    "get_task_config",
    "get_dictionary_config",
    "get_strategy_single_history_count",
    "get_strategy_total_history_count",
]
