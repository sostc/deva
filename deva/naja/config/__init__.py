"""Naja 配置管理模块

提供数据源、策略、任务、字典四个类别的配置管理。
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
        # 策略结果持久化模式:
        # - "summary": 持久化精简摘要（默认）
        # - "errors_only": 仅持久化失败结果
        # - "none": 不持久化结果（仅内存与流）
        "persist_mode": "summary",
    },
    "attention": {
        "enabled": True,
        "global_history_window": 20,
        "max_sectors": 100,
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
        "min_amount": 100000,          # 降低到10万，避免过度过滤
        "min_volume": 10000,           # 降低到1万股
        "min_price": 0.1,              # 降低到0.1元
        "max_price": 5000.0,           # 提高到5000元
        "max_price_change_pct": 20.0,
        # 时间跨度相关配置
        "normal_time_interval": 5.0,           # 正常时间间隔（秒）
        "max_time_gap": 300.0,                 # 最大允许时间间隔（5分钟）
        "time_gap_adjustment": True,           # 是否根据时间跨度调整阈值
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
    },
    "radar": {
        "event_retention_days": 7,
        "cleanup_interval_seconds": 600,
    },
    "llm": {
        "model_type": "kimi",
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
    """获取配置值
    
    Args:
        category: 配置类别 (datasource/strategy/task/dictionary)
        key: 配置键名
        default: 默认值
    
    Returns:
        配置值
    """
    db = NB(NAJA_CONFIG_TABLE)
    
    if category is None:
        return dict(db.items())
    
    category_config = db.get(category, {})
    
    if key is None:
        return {**DEFAULT_CONFIG.get(category, {}), **category_config}
    
    return category_config.get(key, DEFAULT_CONFIG.get(category, {}).get(key, default))


def set_config(category: str, key: str, value: Any) -> bool:
    """设置配置值
    
    Args:
        category: 配置类别
        key: 配置键名
        value: 配置值
    
    Returns:
        是否成功
    """
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
    """设置整个类别的配置
    
    Args:
        category: 配置类别
        config: 配置字典
    
    Returns:
        是否成功
    """
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
    """获取策略结果持久化模式。

    返回值:
        "summary"     - 持久化精简摘要（默认）
        "errors_only" - 仅持久化失败结果
        "none"        - 不持久化结果
    """
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
    """重置配置为默认值
    
    Args:
        category: 配置类别，为 None 则重置所有
    
    Returns:
        是否成功
    """
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


def ensure_auth_secret() -> str:
    """确保认证密钥存在，不存在则生成
    
    Returns:
        认证密钥
    """
    import secrets
    secret = get_config("auth", "secret", "")
    if not secret:
        secret = secrets.token_hex(32)
        set_config("auth", "secret", secret)
    return secret
