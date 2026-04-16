"""
Naja 配置模块

包含：
- SoulConfigLoader: 灵魂配置加载器
- SoulGenerator: 灵魂生成器
- SoulManager: 多灵魂管理器
- 其他配置功能
"""

import os
import json
import logging
import hashlib
import getpass
from typing import Dict, Any

log = logging.getLogger(__name__)

_AUTH_CONFIG_PATH = os.path.expanduser("~/.naja/auth.json")


def _hash_password(password: str) -> str:
    """对密码进行哈希处理"""
    return hashlib.sha256(password.encode()).hexdigest()


def _load_auth_config_file() -> Dict[str, Any]:
    """从文件加载认证配置"""
    try:
        if os.path.exists(_AUTH_CONFIG_PATH):
            with open(_AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"加载认证配置失败: {e}")
    return {}


def _save_auth_config_file(auth_config: Dict[str, Any]):
    """保存认证配置到文件"""
    try:
        os.makedirs(os.path.dirname(_AUTH_CONFIG_PATH), exist_ok=True)
        with open(_AUTH_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(auth_config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"保存认证配置失败: {e}")
        raise


class RadarConfig:
    """雷达配置"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config = {
            "event_retention_days": 7,
            "cleanup_interval_seconds": 600,
            "macro_only": True,
            "auto_start_news_fetcher": True,
            "auto_start_global_scanner": True,
            "global_scanner_interval": 60,
            "global_scanner_volatility_threshold": 2.0,
            "global_scanner_single_threshold": 3.0,
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        self._config[key] = value

    def update(self, config: Dict[str, Any]):
        self._config.update(config)


_radar_config_instance = RadarConfig()


def get_radar_config() -> RadarConfig:
    """获取雷达配置单例"""
    return _radar_config_instance


class NajaConfig:
    """Naja通用配置"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config = {}
        self._load_default_config()

    def _load_default_config(self):
        self._config = {
            "auth_secret": os.environ.get("NAJA_AUTH_SECRET", ""),
            "enabled_timer_execution_modes": ["timer", "scheduler", "event_trigger"],
            "enabled_datasource_types": ["timer", "file", "directory", "replay", "custom"],
            "strategy_debug": False,
            "strategy_total_history_count": 1000,
            "strategy_persist_mode": "json",
            "memory_config": {},
            "llm_config": {},
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        self._config[key] = value

    def update(self, config: Dict[str, Any]):
        self._config.update(config)


_naja_config_instance = NajaConfig()


def get_config(key: str = None, default: Any = None) -> Any:
    """通用配置获取"""
    if key is None:
        return _naja_config_instance
    return _naja_config_instance.get(key, default)


def set_config(key: str, value: Any):
    """通用配置设置，支持嵌套key（如 "auth.username"）"""
    if "." in key:
        parts = key.split(".", 1)
        parent_key, child_key = parts
        parent = _naja_config_instance.get(parent_key, {})
        if not isinstance(parent, dict):
            parent = {}
        parent[child_key] = value
        _naja_config_instance.set(parent_key, parent)
    else:
        _naja_config_instance.set(key, value)


def update_config(config: Dict[str, Any]):
    """批量更新配置"""
    _naja_config_instance.update(config)


def get_auth_config() -> Dict[str, Any]:
    """获取认证配置（从文件加载）"""
    file_config = _load_auth_config_file()
    return {
        "secret": _naja_config_instance.get("auth_secret", ""),
        "username": file_config.get("username", ""),
        "password": file_config.get("password_hash", ""),
        "dev_mode": file_config.get("dev_mode", False),
    }


def set_auth_config(username: str = None, password: str = None, dev_mode: bool = None):
    """保存认证配置到文件

    Args:
        username: 用户名
        password: 明文密码（会自动哈希存储）
        dev_mode: 开发模式标志
    """
    file_config = _load_auth_config_file()

    if username is not None:
        file_config["username"] = username
    if password is not None:
        file_config["password_hash"] = _hash_password(password)
    if dev_mode is not None:
        file_config["dev_mode"] = dev_mode

    _save_auth_config_file(file_config)


def verify_auth(username: str, password: str) -> bool:
    """验证用户名和密码

    Args:
        username: 用户名
        password: 明文密码

    Returns:
        验证是否通过
    """
    file_config = _load_auth_config_file()

    if not file_config.get("username") or not file_config.get("password_hash"):
        return False

    if username != file_config.get("username"):
        return False

    return _hash_password(password) == file_config.get("password_hash")


def ensure_auth_secret() -> str:
    """确保认证密钥存在"""
    return _naja_config_instance.get("auth_secret", "")


def get_datasource_config() -> Dict[str, Any]:
    """获取数据源配置"""
    return _naja_config_instance.get("datasource_config", {})


def get_enabled_timer_execution_modes() -> list:
    """获取启用的定时执行模式"""
    return _naja_config_instance.get("enabled_timer_execution_modes", ["timer", "scheduler", "event_trigger"])


def get_enabled_datasource_types() -> list:
    """获取启用的数据源类型"""
    return _naja_config_instance.get("enabled_datasource_types", ["timer", "file", "directory", "replay", "custom"])


def get_strategy_debug() -> bool:
    """获取策略调试模式"""
    return _naja_config_instance.get("strategy_debug", False)


def get_strategy_total_history_count() -> int:
    """获取策略历史记录总数"""
    return _naja_config_instance.get("strategy_total_history_count", 1000)


def get_strategy_single_history_count() -> int:
    """获取单条策略历史记录数"""
    return _naja_config_instance.get("strategy_single_history_count", 100)


def get_strategy_persist_mode() -> str:
    """获取策略持久化模式"""
    return _naja_config_instance.get("strategy_persist_mode", "json")


def get_strategy_config() -> Dict[str, Any]:
    """获取策略配置"""
    return {
        "debug": get_strategy_debug(),
        "total_history_count": get_strategy_total_history_count(),
        "persist_mode": get_strategy_persist_mode(),
    }


def get_task_config() -> Dict[str, Any]:
    """获取任务配置"""
    return _naja_config_instance.get("task_config", {})


def get_dictionary_config() -> Dict[str, Any]:
    """获取词典配置"""
    return _naja_config_instance.get("dictionary_config", {})


def get_memory_config() -> Dict[str, Any]:
    """获取内存配置"""
    return _naja_config_instance.get("memory_config", {})


def get_llm_config() -> Dict[str, Any]:
    """获取LLM配置"""
    return _naja_config_instance.get("llm_config", {})


def set_category_config(category: str, config: Dict[str, Any]):
    """设置分类配置"""
    _naja_config_instance.set(f"{category}_config", config)


def get_noise_filter_config() -> Dict[str, Any]:
    """获取噪音过滤配置"""
    return _naja_config_instance.get("noise_filter_config", {
        "enabled": True,
        "min_amount": 1000000,
        "min_volume": 100000,
        "min_price": 1.0,
        "max_price": 1000.0,
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
    })


def get_block_noise_config() -> Dict[str, Any]:
    """获取题材噪音配置"""
    return _naja_config_instance.get("block_noise_config", {
        "enabled": True,
        "auto_blacklist_enabled": True,
        "min_attention_threshold": 0.01,
        "blacklist_patterns": [],
    })


def reset_to_default(category: str):
    """恢复默认配置"""
    defaults = {
        "datasource": {"default_interval": 5, "max_retries": 3, "timeout": 30},
        "noise_filter": {"enabled": True, "min_amount": 1000000},
        "block_noise": {"enabled": True, "auto_blacklist_enabled": True},
    }
    if category in defaults:
        set_category_config(category, defaults[category])


DEFAULT_CONFIG = {
    "datasource": {
        "default_interval": 5,
        "max_retries": 3,
        "retry_delay": 1.0,
        "timeout": 30,
        "enabled_types": ["timer", "custom", "replay"],
        "enabled_timer_execution_modes": ["timer", "scheduler", "event_trigger"],
    },
    "noise_filter": get_noise_filter_config(),
    "block_noise": get_block_noise_config(),
}


def load_config() -> NajaConfig:
    """加载配置"""
    return _naja_config_instance


try:
    from .soul_config_loader import SoulConfigLoader, get_config_loader
    from .soul_generator import SoulGenerator, get_generator
    from .soul_manager import SoulManager, get_soul_manager

    SOUL_AVAILABLE = True
except ImportError as e:
    log.warning(f"灵魂配置模块加载失败: {e}")
    SoulConfigLoader = None
    SoulGenerator = None
    SoulManager = None
    get_config_loader = None
    get_generator = None
    get_soul_manager = None
    SOUL_AVAILABLE = False

__all__ = [
    "get_radar_config",
    "get_config",
    "set_config",
    "update_config",
    "get_auth_config",
    "set_auth_config",
    "verify_auth",
    "ensure_auth_secret",
    "get_datasource_config",
    "get_enabled_timer_execution_modes",
    "get_enabled_datasource_types",
    "get_strategy_debug",
    "get_strategy_total_history_count",
    "get_strategy_persist_mode",
    "get_strategy_config",
    "get_task_config",
    "get_dictionary_config",
    "get_memory_config",
    "get_llm_config",
    "set_category_config",
    "get_noise_filter_config",
    "get_block_noise_config",
    "reset_to_default",
    "DEFAULT_CONFIG",
    "load_config",
    "RadarConfig",
    "NajaConfig",
    "SoulConfigLoader",
    "SoulGenerator",
    "SoulManager",
    "get_config_loader",
    "get_generator",
    "get_soul_manager",
    "SOUL_AVAILABLE",
]

# 启动模式配置（从顶级 startup_modes.py 迁入）
try:
    from .startup_modes import (
        StartupMode, NewsRadarMode, StartupConfig,
        MODE_COMBINATIONS,
        get_mode_description, get_news_radar_description,
        create_normal_config, create_lab_config, create_cognition_debug_config,
    )
except ImportError:
    pass
