"""Naja 配置管理模块

提供数据源、策略、任务、字典四个类别的配置管理。
支持两种存储方式：
1. 文件存储（配置 + func_code）- 方便版本控制和代码审查
2. NB 存储（运行时数据）- 性能更好

配置存储在 NB('naja_config') 命名空间中。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from deva import NB

NAJA_CONFIG_TABLE = "naja_config"

DEFAULT_CONFIG = {
    "datasource": {
        "default_interval": 5,
        "max_retries": 3,
        "retry_delay": 1.0,
        "timeout": 30,
        "enabled_types": ["timer", "file", "directory", "custom", "replay"],
        "enabled_timer_execution_modes": ["timer", "scheduler", "event_trigger"],
    },
    "strategy": {
        "single_history_count": 30,
        "total_history_count": 500,
        "default_window_size": 5,
        "default_window_interval": "10s",
        "persist_mode": "summary",
    },
    "attention": {
        "enabled": True,
        "global_history_window": 20,
        "max_sectors": 5000,
        "sector_decay_half_life": 300.0,
        "max_symbols": 5000,
        "low_interval": 60.0,
        "medium_interval": 10.0,
        "high_interval": 1.0,
        "river_history_window": 20,
        "pytorch_max_concurrent": 10,
        "pytorch_batch_size": 32,
        "enable_monitoring": True,
        "report_interval": 60.0,
        "debug_mode": False,
        "log_level": "INFO",
    },
    "noise_filter": {
        "enabled": True,
        "min_amount": 100000,
        "min_volume": 10000,
        "min_price": 0.1,
        "max_price": 5000.0,
        "max_price_change_pct": 20.0,
        "normal_time_interval": 5.0,
        "max_time_gap": 300.0,
        "time_gap_adjustment": True,
        "flat_threshold": 0.5,
        "flat_consecutive_frames": 10,
        "wash_trading_volume_ratio": 3.0,
        "wash_trading_price_change_max": 0.5,
        "abnormal_volatility_threshold": 10.0,
        "filter_b_shares": True,
        "filter_st": False,
        "blacklist": [],
        "whitelist": [],
    },
    "sector_noise": {
        "enabled": True,
        "auto_blacklist_enabled": True,
        "min_attention_threshold": 0.01,
        "blacklist_patterns": [
            '通达信', '系统', 'ST', 'B股', '基金', '指数', '期权', '期货',
            '上证', '深证', '沪深', '大盘', '权重', '综合', '行业', '地域',
            '概念', '风格', '上证所', '深交所', '_sys', '_index', '884',
            '物业管理', '含B股', '地方版', '预预', '昨日', '近日',
        ],
    },
    "task": {
        "default_interval": 60,
        "max_concurrent": 10,
        "retry_count": 3,
        "retry_delay": 5,
    },
    "dictionary": {
        "default_interval": 300,
        "default_daily_time": "03:00",
        "max_cache_size": 10000,
    },
    "memory": {
        "auto_save_enabled": True,
        "auto_save_interval": 300,
        "auto_load_on_start": True,
        "attention_filter_enabled": True,
        "attention_gate_base": 0.35,
        "target_rate_per_min": 30,
        "rate_window_seconds": 300,
        "max_batch_keep": 80,
        "narrative_enabled": True,
    },
    "insight": {
        "auto_save_enabled": True,
        "auto_save_interval": 300,
        "auto_load_on_start": True,
        "llm_reflect_interval": 3600,
        "llm_reflect_window": 7200,
        "short_memory_size": 1000,
        "mid_memory_size": 5000,
        "long_memory_size": 30,
        "signal_buffer_size": 1000,
        "mid_memory_threshold": 0.6,
    },
    "radar": {
        "event_retention_days": 7,
        "cleanup_interval_seconds": 600,
        "macro_only": True,
        "auto_start_news_fetcher": True,
        "news_fetch_interval": 60,
        "news_attention_threshold": 0.6,
        "news_force_trading": False,
        "auto_start_global_scanner": True,
        "global_scanner_interval": 60,
        "global_scanner_volatility_threshold": 2.0,
        "global_scanner_single_threshold": 3.0,
    },
    "llm": {
        "model_type": "deepseek",
        "min_interval_seconds": 300,
        "auto_adjust_enabled": True,
        "auto_adjust_interval_seconds": 900,
        "auto_adjust_window_seconds": 600,
        "auto_adjust_min_events": 3,
        "auto_adjust_dry_run": False,
        "allowed_actions": ["update_params", "reset", "start", "stop", "restart"],
        "max_actions_per_run": 5,
        "strategy_allowlist": [],
        "strategy_denylist": [],
        "min_results_count_for_adjust": 20,
        "max_success_rate_to_adjust": 1.0,
        "allowed_param_keys": [],
        "blocked_param_keys": ["class_path", "code", "func_code", "strategy_code"],
        "reflection_enabled": True,
        "reflection_interval_seconds": 1800,
        "reflection_min_signals": 3,
        "reflection_max_signals": 50,
    },
    "auth": {
        "username": "",
        "password": "",
        "secret": "",
        "dev_mode": False,
    },
    "performance": {
        "lock_monitoring_enabled": False,
        "lock_monitoring_threshold_ms": 100,
        "web_request_monitoring_enabled": True,
        "storage_monitoring_enabled": False,
        "monitored_modules": ["strategy", "datasource", "task", "storage"],
    },
}


def get_config(category: str = None, key: str = None, default: Any = None) -> Any:
    """获取配置值"""
    db = NB(NAJA_CONFIG_TABLE)

    if category is None:
        return dict(db.items())

    category_config = db.get(category, {})

    if key is None:
        return {**DEFAULT_CONFIG.get(category, {}), **category_config}

    return category_config.get(key, DEFAULT_CONFIG.get(category, {}).get(key, default))


def set_config(category: str, key: str, value: Any) -> bool:
    """设置配置值"""
    try:
        db = NB(NAJA_CONFIG_TABLE)
        category_config = db.get(category, {})
        category_config[key] = value
        db[category] = category_config
        return True
    except Exception as e:
        print(f"设置配置失败: {e}")
        return False


def set_category_config(category: str, config: Dict[str, Any]) -> bool:
    """设置整个类别的配置"""
    try:
        db = NB(NAJA_CONFIG_TABLE)
        db[category] = config
        return True
    except Exception as e:
        print(f"设置配置失败: {e}")
        return False


def get_datasource_config() -> Dict[str, Any]:
    """获取数据源配置"""
    return get_config("datasource")


def get_enabled_datasource_types() -> list:
    """获取启用的数据源类型列表"""
    config = get_config("datasource")
    return config.get("enabled_types", ["timer", "custom", "replay"])


def get_enabled_timer_execution_modes() -> list:
    """获取定时器数据源启用的调度方式列表"""
    config = get_config("datasource")
    return config.get("enabled_timer_execution_modes", ["timer", "scheduler", "event_trigger"])


def get_strategy_config() -> Dict[str, Any]:
    """获取策略配置"""
    return get_config("strategy")


def get_strategy_persist_mode() -> str:
    """获取策略结果持久化模式。"""
    mode = get_config("strategy", "persist_mode", "summary")
    mode = str(mode or "summary").strip().lower()
    if mode in {"summary", "errors_only", "none"}:
        return mode
    return "summary"


def get_task_config() -> Dict[str, Any]:
    """获取任务配置"""
    return get_config("task")


def get_dictionary_config() -> Dict[str, Any]:
    """获取字典配置"""
    return get_config("dictionary")


def get_memory_config() -> Dict[str, Any]:
    """获取记忆配置"""
    return get_config("memory")


def get_insight_config() -> Dict[str, Any]:
    """获取洞察配置"""
    return get_config("insight")


def get_radar_config() -> Dict[str, Any]:
    """获取雷达配置"""
    return get_config("radar")


def get_llm_config() -> Dict[str, Any]:
    """获取 LLM 调节配置"""
    return get_config("llm")


def get_strategy_single_history_count() -> int:
    """获取单条策略的历史保留条数"""
    return get_config("strategy", "single_history_count", 30)


def get_strategy_total_history_count() -> int:
    """获取总历史数据保留条数"""
    return get_config("strategy", "total_history_count", 500)


def reset_to_default(category: str = None) -> bool:
    """重置配置为默认值"""
    try:
        db = NB(NAJA_CONFIG_TABLE)
        if category:
            db[category] = DEFAULT_CONFIG.get(category, {})
        else:
            for cat, config in DEFAULT_CONFIG.items():
                db[cat] = config
        return True
    except Exception as e:
        print(f"重置配置失败: {e}")
        return False


def get_auth_config() -> Dict[str, Any]:
    """获取认证配置"""
    return get_config("auth")


def get_performance_config() -> Dict[str, Any]:
    """获取性能监控配置"""
    return get_config("performance")


def get_attention_config() -> Dict[str, Any]:
    """获取注意力系统配置"""
    return get_config("attention")


def get_noise_filter_config() -> Dict[str, Any]:
    """获取噪音过滤配置"""
    return get_config("noise_filter")


def get_sector_noise_config() -> Dict[str, Any]:
    """获取板块噪音配置"""
    return get_config("sector_noise")


def ensure_auth_secret() -> str:
    """确保认证密钥存在，不存在则生成"""
    import secrets
    secret = get_config("auth", "secret", "")
    if not secret:
        secret = secrets.token_hex(32)
        set_config("auth", "secret", secret)
    return secret


from .file_config import (
    get_file_config_manager,
    get_dict_file_config_manager,
    get_task_file_config_manager,
    get_strategy_file_config_manager,
    get_datasource_file_config_manager,
    ConfigFileItem,
    BaseConfigMetadata,
    TaskConfigMetadata,
    StrategyConfigMetadata,
    DatasourceConfigMetadata,
    TASK_CONFIG_DIR,
    STRATEGY_CONFIG_DIR,
    DATASOURCE_CONFIG_DIR,
)

from .migration import (
    migrate_tasks_to_file,
    migrate_strategies_to_file,
    migrate_datasources_to_file,
    migrate_all_to_file,
    get_migration_status,
    create_example_files as create_migration_examples,
)

from .ui import (
    ConfigSchema,
    ConfigEditorField,
    build_editor_form,
    parse_editor_form,
    render_config_editor,
    render_config_list,
)


__all__ = [
    'NAJA_CONFIG_TABLE',
    'DEFAULT_CONFIG',
    'get_config',
    'set_config',
    'set_category_config',
    'get_datasource_config',
    'get_enabled_datasource_types',
    'get_enabled_timer_execution_modes',
    'get_strategy_config',
    'get_strategy_persist_mode',
    'get_task_config',
    'get_dictionary_config',
    'get_memory_config',
    'get_insight_config',
    'get_radar_config',
    'get_llm_config',
    'get_strategy_single_history_count',
    'get_strategy_total_history_count',
    'reset_to_default',
    'get_auth_config',
    'get_performance_config',
    'get_attention_config',
    'get_noise_filter_config',
    'get_sector_noise_config',
    'ensure_auth_secret',
    'get_file_config_manager',
    'get_dict_file_config_manager',
    'get_task_file_config_manager',
    'get_strategy_file_config_manager',
    'get_datasource_file_config_manager',
    'ConfigFileItem',
    'BaseConfigMetadata',
    'TaskConfigMetadata',
    'StrategyConfigMetadata',
    'DatasourceConfigMetadata',
    'TASK_CONFIG_DIR',
    'STRATEGY_CONFIG_DIR',
    'DATASOURCE_CONFIG_DIR',
    'migrate_tasks_to_file',
    'migrate_strategies_to_file',
    'migrate_datasources_to_file',
    'migrate_all_to_file',
    'get_migration_status',
    'create_migration_examples',
    'ConfigSchema',
    'ConfigEditorField',
    'build_editor_form',
    'parse_editor_form',
    'render_config_editor',
    'render_config_list',
]
