"""策略管理模块"""

from .base import (
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
    Lineage,
    UpstreamSource,
    DownstreamSink,
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
from .replay_lab import ReplayLab, get_lab
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
from .datasource import (
    DataSource,
    DataSourceStatus,
    DataSourceType,
    DataSourceMetadata,
    DataSourceState,
    DataSourceStats,
    DataSourceManager,
    get_ds_manager,
    create_timer_source,
    create_stream_source,
)
from .ai_strategy_generator import (
    analyze_data_schema,
    generate_strategy_code,
    validate_strategy_code,
    test_strategy_code,
    generate_strategy_documentation,
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
    setup_strategy_streams,
    save_all_strategy_states,
    restore_strategy_states,
    setup_graceful_shutdown,
    register_shutdown_handler,
    execute_shutdown_handlers,
    start_history_replay,
    stop_history_replay,
    is_replay_running,
    get_strategy_config,
    set_strategy_config,
    log_strategy_event,
    DEFAULT_STRATEGIES_CONFIG,
)
