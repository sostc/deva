"""策略管理模块"""

from ..common.base import (
    BaseMetadata,
    BaseState,
    BaseStats,
    BaseManager,
    BaseStatus,
    StatusMixin,
    CallbackMixin,
)
from .utils import (
    format_pct,
    format_duration,
    df_to_html,
    prepare_df,
    calc_block_ranking,
    get_top_stocks_in_block,
    build_block_change_html,
    build_limit_up_down_html,
    build_block_ranking_html,
    TABLE_STYLE,
)
from .strategy_unit import (
    StrategyUnit,
    StrategyStatus,
    OutputType,
    DataSchema,
    SchemaDefinition,
    StrategyMetadata,
    ExecutionState,
    create_strategy_unit,
)
from .strategy_manager import (
    StrategyManager,
    get_manager,
    ManagerStats,
    ErrorRecord,
)

from .fault_tolerance import (
    get_error_collector,
    get_alert_manager,
    get_metrics_collector,
    initialize_fault_tolerance,
)
from .strategy_panel import render_strategy_admin_panel
from .stock_strategies import (
    StockStrategyUnit,
    BlockChangeStrategy,
    BlockRankingStrategy,
    LimitUpDownStrategy,
    CustomStockFilterStrategy,
    create_stock_strategy,
    list_available_strategies,
    initialize_default_stock_strategies,
    STRATEGY_REGISTRY,
)
from .strategy_logic_db import (
    StrategyLogicDB,
    StrategyInstanceDB,
    StrategyLogicMeta,
    StrategyInstanceState,
    initialize_strategy_logic_db,
    get_logic_db,
    get_instance_db,
)
from .result_store import (
    StrategyResult,
    ResultStore,
    get_result_store,
)
from .runtime import (
    initialize_strategy_monitor_streams,
    save_all_strategy_states,
    restore_strategy_states,
    setup_graceful_shutdown,
    register_shutdown_handler,
    execute_shutdown_handlers,
    get_strategy_config,
    set_strategy_config,
    log_strategy_event,
)
from .logging_context import (
    LoggingContext,
    LoggingContextManager,
    logging_context_manager,
    get_logging_context,
    with_strategy_logging,
    with_datasource_logging,
    create_enhanced_log_record,
    strategy_log,
    datasource_log,
    log_strategy_event,
    log_datasource_event,
)

__all__ = [
    # Base classes
    'BaseMetadata',
    'BaseState',
    'BaseStats',
    'BaseManager',
    'BaseStatus',
    'StatusMixin',
    'CallbackMixin',
    # Utils
    'format_pct',
    'format_duration',
    'df_to_html',
    'prepare_df',
    'calc_block_ranking',
    'get_top_stocks_in_block',
    'build_block_change_html',
    'build_limit_up_down_html',
    'build_block_ranking_html',
    'TABLE_STYLE',
    # Strategy Unit
    'StrategyUnit',
    'StrategyStatus',
    'OutputType',
    'DataSchema',
    'SchemaDefinition',
    'StrategyMetadata',
    'ExecutionState',
    'create_strategy_unit',
    # Strategy Manager
    'StrategyManager',
    'get_manager',
    'ManagerStats',
    'ErrorRecord',

    # Fault Tolerance
    'get_error_collector',
    'get_alert_manager',
    'get_metrics_collector',
    'initialize_fault_tolerance',
    # Strategy Panel
    'render_strategy_admin_panel',
    # Stock Strategies
    'StockStrategyUnit',
    'BlockChangeStrategy',
    'BlockRankingStrategy',
    'LimitUpDownStrategy',
    'CustomStockFilterStrategy',
    'create_stock_strategy',
    'list_available_strategies',
    'initialize_default_stock_strategies',
    'STRATEGY_REGISTRY',
    # Strategy Logic DB
    'StrategyLogicDB',
    'StrategyInstanceDB',
    'StrategyLogicMeta',
    'StrategyInstanceState',
    'initialize_strategy_logic_db',
    'get_logic_db',
    'get_instance_db',
    # Result Store
    'StrategyResult',
    'ResultStore',
    'get_result_store',
    # Runtime
    'initialize_strategy_monitor_streams',
    'save_all_strategy_states',
    'restore_strategy_states',
    'setup_graceful_shutdown',
    'get_strategy_config',
    'set_strategy_config',
    'log_strategy_event',
    'DEFAULT_STRATEGIES_CONFIG',
    # Logging Context
    'LoggingContext',
    'LoggingContextManager',
    'logging_context_manager',
    'get_logging_context',
    'with_strategy_logging',
    'with_datasource_logging',
    'strategy_log',
    'datasource_log',
    'log_datasource_event',
]
