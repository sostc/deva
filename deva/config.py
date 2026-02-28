"""统一配置管理模块

所有配置统一存储在 NB 命名空间中，底层使用 SQLite 持久化。
支持环境变量覆盖，敏感信息保护。

配置命名空间：
- deva_config: 主配置表
  - auth: 认证配置
  - llm_{model_type}: 大模型配置
  - database: 数据库配置
  - dtalk: 钉钉配置
  - mail: 邮件配置
  - tushare: Tushare配置
  - bus: 总线配置

使用示例：
    from deva import config
    
    # 获取配置
    api_key = config.get('llm.deepseek.api_key')
    
    # 设置配置
    config.set('llm.deepseek.api_key', 'your-api-key')
    
    # 批量设置
    config.update('llm.deepseek', {
        'api_key': 'xxx',
        'base_url': 'https://api.deepseek.com/v1',
        'model': 'deepseek-chat'
    })
"""

from __future__ import annotations

import os
import secrets
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SENSITIVE_KEYWORDS = ('key', 'token', 'secret', 'password', 'passwd', 'credential', 'api_key')

DEFAULT_LLM_CONFIGS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "sambanova": {
        "base_url": "https://api.sambanova.ai/v1",
        "model": "Meta-Llama-3.1-70B-Instruct",
    },
}

DEFAULT_CONFIG_SCHEMA = {
    "auth": {
        "username": {"type": "string", "default": "", "sensitive": False, "description": "管理员用户名"},
        "password": {"type": "string", "default": "", "sensitive": True, "description": "管理员密码"},
        "secret": {"type": "string", "default": None, "sensitive": True, "description": "Token签名密钥"},
    },
    "database": {
        "sqlite_path": {"type": "string", "default": "~/.deva/nb.sqlite", "sensitive": False, "description": "SQLite数据库路径"},
        "redis_host": {"type": "string", "default": "localhost", "sensitive": False, "description": "Redis主机地址"},
        "redis_port": {"type": "int", "default": 6379, "sensitive": False, "description": "Redis端口"},
        "redis_db": {"type": "int", "default": 0, "sensitive": False, "description": "Redis数据库编号"},
        "redis_password": {"type": "string", "default": None, "sensitive": True, "description": "Redis密码"},
    },
    "bus": {
        "mode": {"type": "string", "default": "redis", "sensitive": False, "description": "总线模式(redis/local/file)"},
        "topic": {"type": "string", "default": "bus", "sensitive": False, "description": "总线主题"},
        "group": {"type": "string", "default": None, "sensitive": False, "description": "总线组名"},
    },
    "dtalk": {
        "webhook": {"type": "string", "default": None, "sensitive": True, "description": "钉钉机器人Webhook"},
        "secret": {"type": "string", "default": None, "sensitive": True, "description": "钉钉机器人签名密钥"},
    },
    "mail": {
        "hostname": {"type": "string", "default": None, "sensitive": False, "description": "SMTP服务器地址"},
        "username": {"type": "string", "default": None, "sensitive": False, "description": "发件人邮箱"},
        "password": {"type": "string", "default": None, "sensitive": True, "description": "邮箱密码"},
        "port": {"type": "int", "default": 465, "sensitive": False, "description": "SMTP端口"},
        "use_tls": {"type": "bool", "default": True, "sensitive": False, "description": "是否使用TLS"},
    },
    "tushare": {
        "token": {"type": "string", "default": None, "sensitive": True, "description": "Tushare API Token"},
    },
    "log": {
        "level": {"type": "string", "default": "INFO", "sensitive": False, "description": "日志级别"},
        "cache_max_len": {"type": "int", "default": 200, "sensitive": False, "description": "日志缓存最大长度"},
    },
}

OLD_NAMESPACE_MAPPING = {
    "admin": "auth",
    "deepseek": "llm_deepseek",
    "kimi": "llm_kimi",
    "sambanova": "llm_sambanova",
    "dtalk_deva": "dtalk",
    "mail": "mail",
    "tushare": "tushare",
}

CONFIG_NAMESPACE = "deva_config"
MIGRATION_FLAG = "__migration_done__"


def _is_sensitive(key: str) -> bool:
    """检查键名是否为敏感信息"""
    key_lower = key.lower()
    return any(kw in key_lower for kw in SENSITIVE_KEYWORDS)


def _mask_value(key: str, value: Any) -> str:
    """遮蔽敏感信息的值"""
    if value is None:
        return "None"
    if not _is_sensitive(key):
        return str(value)
    str_val = str(value)
    if len(str_val) <= 4:
        return "****"
    return str_val[:2] + "****" + str_val[-2:]


class ConfigManager:
    """统一配置管理器
    
    所有配置存储在 NB 命名空间中，支持：
    - SQLite 持久化存储
    - 环境变量覆盖
    - 运行时动态修改
    - 敏感信息保护
    - 自动迁移旧配置
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._nb = None
        self._env_prefix = "DEVA_"
        self._migrated = False
    
    @property
    def nb(self):
        """延迟加载 NB 命名空间"""
        if self._nb is None:
            from .core.namespace import NB
            self._nb = NB(CONFIG_NAMESPACE)
            if not self._migrated:
                self._migrate_old_config()
        return self._nb
    
    def _migrate_old_config(self):
        """迁移旧配置到新的命名空间"""
        if self._migrated:
            return
        
        if MIGRATION_FLAG in self._nb:
            self._migrated = True
            return
        
        try:
            from .core.namespace import NB
            
            migrated = False
            for old_ns, new_key in OLD_NAMESPACE_MAPPING.items():
                try:
                    old_table = NB(old_ns)
                    if not old_table:
                        continue
                    
                    for key, value in old_table.items():
                        self._nb[f"{new_key}.{key}"] = value
                        migrated = True
                    
                    old_table.clear()
                    logger.info(f"已迁移并清理旧配置: {old_ns}")
                except Exception:
                    continue
            
            self._nb[MIGRATION_FLAG] = True
            
            if migrated:
                logger.info("配置迁移完成，所有配置已合并到 deva_config")
        except Exception as e:
            logger.debug(f"配置迁移跳过: {e}")
        
        self._migrated = True
    
    def _get_env_key(self, path: str) -> str:
        """将配置路径转换为环境变量名"""
        return self._env_prefix + path.upper().replace('.', '_')
    
    def _get_env_value(self, path: str) -> Optional[str]:
        """从环境变量获取配置值"""
        env_key = self._get_env_key(path)
        return os.getenv(env_key)
    
    def _parse_path(self, path: str) -> str:
        """解析配置路径为存储键"""
        parts = [p for p in path.split('.') if p]
        
        if not parts:
            return ""
        
        if parts[0] == 'llm' and len(parts) >= 2:
            model_type = parts[1]
            if len(parts) == 2:
                return f"llm_{model_type}"
            return f"llm_{model_type}.{'.'.join(parts[2:])}"
        
        return '.'.join(parts)
    
    def get(self, path: str, default: Any = None) -> Any:
        """获取配置值
        
        优先级：环境变量 > NB存储 > 默认值
        
        Args:
            path: 配置路径，如 'llm.deepseek.api_key'
            default: 默认值
            
        Returns:
            配置值
        """
        env_value = self._get_env_value(path)
        if env_value is not None:
            return env_value
        
        storage_key = self._parse_path(path)
        if not storage_key:
            return default
        
        value = self.nb.get(storage_key)
        if value is not None:
            return value
        
        parts = path.split('.')
        if parts:
            category = parts[0]
            if category in DEFAULT_CONFIG_SCHEMA:
                key = '.'.join(parts[1:]) if len(parts) > 1 else None
                if key and key in DEFAULT_CONFIG_SCHEMA[category]:
                    return DEFAULT_CONFIG_SCHEMA[category][key].get("default", default)
        
        return default
    
    def set(self, path: str, value: Any) -> None:
        """设置配置值
        
        Args:
            path: 配置路径，如 'llm.deepseek.api_key'
            value: 配置值
        """
        storage_key = self._parse_path(path)
        if storage_key:
            self.nb[storage_key] = value
    
    def update(self, path: str, values: Dict[str, Any]) -> None:
        """批量更新配置
        
        Args:
            path: 配置路径前缀，如 'llm.deepseek'
            values: 配置字典
        """
        for key, value in values.items():
            full_path = f"{path}.{key}"
            self.set(full_path, value)
    
    def delete(self, path: str) -> None:
        """删除配置
        
        Args:
            path: 配置路径
        """
        storage_key = self._parse_path(path)
        if storage_key and storage_key in self.nb:
            del self.nb[storage_key]
    
    def get_all(self, mask_sensitive: bool = True) -> Dict[str, Any]:
        """获取所有配置
        
        Args:
            mask_sensitive: 是否遮蔽敏感信息
            
        Returns:
            配置字典
        """
        result = {}
        
        for storage_key, value in self.nb.items():
            parts = storage_key.split('.')
            
            if storage_key.startswith('llm_'):
                model_type = parts[0][4:]
                if 'llm' not in result:
                    result['llm'] = {}
                if model_type not in result['llm']:
                    result['llm'][model_type] = {}
                
                key = '.'.join(parts[1:]) if len(parts) > 1 else 'value'
                if mask_sensitive:
                    result['llm'][model_type][key] = _mask_value(key, value)
                else:
                    result['llm'][model_type][key] = value
            else:
                category = parts[0]
                if category not in result:
                    result[category] = {}
                
                key = '.'.join(parts[1:]) if len(parts) > 1 else 'value'
                if mask_sensitive:
                    result[category][key] = _mask_value(key, value)
                else:
                    result[category][key] = value
        
        for category, schema in DEFAULT_CONFIG_SCHEMA.items():
            if category not in result:
                result[category] = {}
            for key, meta in schema.items():
                if key not in result[category]:
                    result[category][key] = meta.get("default")
        
        return result
    
    def get_llm_config(self, model_type: str = "deepseek") -> Dict[str, Any]:
        """获取LLM模型配置
        
        Args:
            model_type: 模型类型
            
        Returns:
            模型配置字典
        """
        defaults = DEFAULT_LLM_CONFIGS.get(model_type, {})
        config = dict(defaults)
        
        prefix = f"llm_{model_type}."
        for storage_key, value in self.nb.items():
            if storage_key.startswith(prefix):
                key = storage_key[len(prefix):]
                config[key] = value
            elif storage_key == f"llm_{model_type}":
                if isinstance(value, dict):
                    config.update(value)
        
        return config
    
    def is_llm_ready(self, model_type: str = "deepseek") -> bool:
        """检查LLM模型是否配置完成"""
        config = self.get_llm_config(model_type)
        required = ("api_key", "base_url", "model")
        
        for key in required:
            value = config.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                return False
        return True
    
    def get_missing_llm_config(self, model_type: str = "deepseek") -> List[str]:
        """获取缺失的LLM配置项"""
        config = self.get_llm_config(model_type)
        required = ("api_key", "base_url", "model")
        
        missing = []
        for key in required:
            value = config.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(key)
        return missing
    
    def get_auth_config(self) -> Dict[str, Any]:
        """获取认证配置"""
        return {
            "username": self.get("auth.username", ""),
            "password": self.get("auth.password", ""),
            "secret": self.get("auth.secret"),
        }
    
    def get_database_config(self) -> Dict[str, Any]:
        """获取数据库配置"""
        return {
            "sqlite_path": self.get("database.sqlite_path", "~/.deva/nb.sqlite"),
            "redis_host": self.get("database.redis_host", "localhost"),
            "redis_port": int(self.get("database.redis_port", 6379)),
            "redis_db": int(self.get("database.redis_db", 0)),
            "redis_password": self.get("database.redis_password"),
        }
    
    def get_bus_config(self) -> Dict[str, Any]:
        """获取总线配置"""
        return {
            "mode": self.get("bus.mode", "redis"),
            "topic": self.get("bus.topic", "bus"),
            "group": self.get("bus.group") or str(os.getpid()),
        }
    
    def ensure_auth_secret(self) -> str:
        """确保认证密钥存在，不存在则自动生成"""
        secret = self.get("auth.secret")
        if not secret:
            secret = secrets.token_hex(32)
            self.set("auth.secret", secret)
            logger.info("自动生成认证密钥")
        return secret
    
    def cleanup_old_namespaces(self):
        """清理旧的配置命名空间"""
        from .core.namespace import NB
        
        cleaned = 0
        for old_ns in OLD_NAMESPACE_MAPPING.keys():
            try:
                old_table = NB(old_ns)
                if old_table:
                    old_table.clear()
                    cleaned += 1
                    logger.info(f"已清理旧配置命名空间: {old_ns}")
            except Exception as e:
                logger.warning(f"清理命名空间 {old_ns} 失败: {e}")
        
        if cleaned:
            logger.info(f"已清理 {cleaned} 个旧配置命名空间")


config = ConfigManager()


def get_config() -> ConfigManager:
    """获取配置管理器实例"""
    return config


__all__ = [
    "config",
    "get_config",
    "ConfigManager",
    "DEFAULT_LLM_CONFIGS",
    "DEFAULT_CONFIG_SCHEMA",
    "SENSITIVE_KEYWORDS",
    "CONFIG_NAMESPACE",
]
