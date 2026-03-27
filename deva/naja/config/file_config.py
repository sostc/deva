"""File-based Configuration System - 文件配置管理系统

设计原则：
1. 配置（metadata + parameters + func_code）存文件，方便版本控制和代码审查
2. NB 只存运行时数据（payload, state）
3. 启动时从文件加载到 NB
4. 支持向后兼容：NB 中的旧数据可以迁移到文件

目录结构：
config/
  dictionaries/        # 字典配置
    _examples/         # 示例配置
    tongdaxin_blocks.yaml
  tasks/              # 任务配置
    _examples/
    my_task.yaml
  strategies/         # 策略配置
    _examples/
    my_strategy.yaml
  datasources/        # 数据源配置
    _examples/
    my_datasource.yaml
"""

import os
import json
import yaml
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict, field
import threading

BASE_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def get_config_dir(config_type: str) -> Path:
    """获取指定类型的配置目录"""
    base = BASE_CONFIG_DIR / config_type
    base.mkdir(parents=True, exist_ok=True)
    (base / "_examples").mkdir(parents=True, exist_ok=True)
    return base


DICT_CONFIG_DIR = get_config_dir("dictionaries")
TASK_CONFIG_DIR = get_config_dir("tasks")
STRATEGY_CONFIG_DIR = get_config_dir("strategies")
DATASOURCE_CONFIG_DIR = get_config_dir("datasources")


def ensure_config_dirs():
    """确保所有配置目录存在"""
    for config_type in ["dictionaries", "tasks", "strategies", "datasources"]:
        get_config_dir(config_type)


def get_config_path(name: str, config_type: str) -> Path:
    """获取配置文件路径"""
    ensure_config_dirs()
    return BASE_CONFIG_DIR / config_type / f"{name}.yaml"


def load_raw_config(name: str, config_type: str) -> Optional[Dict[str, Any]]:
    """从文件加载原始配置（不解析为类）"""
    path = get_config_path(name, config_type)
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix == '.json':
                return json.load(f)
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[FileConfig] Load {path} failed: {e}")
        return None


def save_raw_config(name: str, config_type: str, data: Dict[str, Any]) -> bool:
    """保存配置到文件"""
    path = get_config_path(name, config_type)
    try:
        ensure_config_dirs()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            if path.suffix == '.json':
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return True
    except Exception as e:
        print(f"[FileConfig] Save {path} failed: {e}")
        return False


def delete_raw_config(name: str, config_type: str) -> bool:
    """删除配置文件"""
    path = get_config_path(name, config_type)
    if path.exists():
        try:
            path.unlink()
            return True
        except Exception as e:
            print(f"[FileConfig] Delete {path} failed: {e}")
    return False


def list_config_names(config_type: str) -> List[str]:
    """列出所有配置文件名称（不含 _examples）"""
    ensure_config_dirs()
    base = BASE_CONFIG_DIR / config_type
    if not base.exists():
        return []

    configs = []
    for p in base.glob("*.yaml"):
        if p.stem.startswith('_'):
            continue
        configs.append(p.stem)
    for p in base.glob("*.json"):
        if p.stem.startswith('_'):
            continue
        configs.append(p.stem)
    return sorted(configs)


def config_exists(name: str, config_type: str) -> bool:
    """检查配置是否存在"""
    path = get_config_path(name, config_type)
    return path.exists()


@dataclass
class BaseConfigMetadata:
    """基础配置元数据"""
    id: str = ""
    name: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    category: str = ""
    created_at: float = 0
    updated_at: float = 0
    enabled: bool = True
    source: str = "file"  # "file" or "nb"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "BaseConfigMetadata":
        if not data:
            return cls()
        return cls(
            id=data.get('id', ''),
            name=data.get('name', ''),
            description=data.get('description', ''),
            tags=data.get('tags', []),
            category=data.get('category', ''),
            created_at=data.get('created_at', 0),
            updated_at=data.get('updated_at', 0),
            enabled=data.get('enabled', True),
            source=data.get('source', 'file'),
        )


@dataclass
class TaskConfigMetadata(BaseConfigMetadata):
    """任务配置元数据"""
    task_type: str = "timer"
    execution_mode: str = "timer"
    interval_seconds: float = 60.0
    scheduler_trigger: str = "interval"
    cron_expr: str = ""
    run_at: str = ""
    event_source: str = "log"
    event_condition: str = ""
    event_condition_type: str = "contains"
    func_code_file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "TaskConfigMetadata":
        if not data:
            return cls()
        base = BaseConfigMetadata.from_dict(data)
        return cls(
            id=base.id,
            name=base.name,
            description=base.description,
            tags=base.tags,
            category=base.category,
            created_at=base.created_at,
            updated_at=base.updated_at,
            enabled=base.enabled,
            source=base.source,
            task_type=data.get('task_type', 'timer'),
            execution_mode=data.get('execution_mode', 'timer'),
            interval_seconds=data.get('interval_seconds', 60.0),
            scheduler_trigger=data.get('scheduler_trigger', 'interval'),
            cron_expr=data.get('cron_expr', ''),
            run_at=data.get('run_at', ''),
            event_source=data.get('event_source', 'log'),
            event_condition=data.get('event_condition', ''),
            event_condition_type=data.get('event_condition_type', 'contains'),
            func_code_file=data.get('func_code_file', ''),
        )


@dataclass
class StrategyConfigMetadata(BaseConfigMetadata):
    """策略配置元数据"""
    bound_datasource_id: str = ""
    bound_datasource_ids: List[str] = field(default_factory=list)
    compute_mode: str = "record"
    window_size: int = 5
    window_type: str = "sliding"
    window_interval: str = "10s"
    window_return_partial: bool = False
    dictionary_profile_ids: List[str] = field(default_factory=list)
    max_history_count: int = 100
    strategy_type: str = "legacy"
    handler_type: str = "unknown"
    version: int = 1
    func_code_file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "StrategyConfigMetadata":
        if not data:
            return cls()
        base = BaseConfigMetadata.from_dict(data)
        return cls(
            id=base.id,
            name=base.name,
            description=base.description,
            tags=base.tags,
            category=base.category,
            created_at=base.created_at,
            updated_at=base.updated_at,
            enabled=base.enabled,
            source=base.source,
            bound_datasource_id=data.get('bound_datasource_id', ''),
            bound_datasource_ids=data.get('bound_datasource_ids', []),
            compute_mode=data.get('compute_mode', 'record'),
            window_size=data.get('window_size', 5),
            window_type=data.get('window_type', 'sliding'),
            window_interval=data.get('window_interval', '10s'),
            window_return_partial=data.get('window_return_partial', False),
            dictionary_profile_ids=data.get('dictionary_profile_ids', []),
            max_history_count=data.get('max_history_count', 100),
            strategy_type=data.get('strategy_type', 'legacy'),
            handler_type=data.get('handler_type', 'unknown'),
            version=data.get('version', 1),
            func_code_file=data.get('func_code_file', ''),
        )


@dataclass
class DatasourceConfigMetadata(BaseConfigMetadata):
    """数据源配置元数据"""
    source_type: str = "timer"
    interval_seconds: float = 5.0
    enabled_types: List[str] = field(default_factory=list)
    func_code_file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "DatasourceConfigMetadata":
        if not data:
            return cls()
        base = BaseConfigMetadata.from_dict(data)
        return cls(
            id=base.id,
            name=base.name,
            description=base.description,
            tags=base.tags,
            category=base.category,
            created_at=base.created_at,
            updated_at=base.updated_at,
            enabled=base.enabled,
            source=base.source,
            source_type=data.get('source_type', 'timer'),
            interval_seconds=data.get('interval_seconds', 5.0),
            enabled_types=data.get('enabled_types', []),
            func_code_file=data.get('func_code_file', ''),
        )


@dataclass
class ConfigFileItem:
    """统一的配置文件项

    包含：
    - metadata: 基础元数据
    - parameters: 控制参数（灵活的 dict）
    - config: 类型特定配置
    - func_code: 执行代码
    """
    name: str
    config_type: str  # "dictionary", "task", "strategy", "datasource"
    metadata: BaseConfigMetadata = field(default_factory=BaseConfigMetadata)
    parameters: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    func_code: str = ""
    func_code_file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'metadata': self.metadata.to_dict() if isinstance(self.metadata, BaseConfigMetadata) else self.metadata,
            'parameters': self.parameters,
            'config': self.config,
            'func_code': self.func_code,
            'func_code_file': self.func_code_file,
        }

    @classmethod
    def from_dict(cls, name: str, config_type: str, data: Dict[str, Any]) -> "ConfigFileItem":
        """从字典创建"""
        metadata_dict = data.get('metadata', {})
        metadata_cls = cls._get_metadata_class(config_type)
        metadata = metadata_cls.from_dict(metadata_dict)

        return cls(
            name=name,
            config_type=config_type,
            metadata=metadata,
            parameters=data.get('parameters', {}),
            config=data.get('config', {}),
            func_code=data.get('func_code', ''),
            func_code_file=metadata_dict.get('func_code_file', ''),
        )

    @staticmethod
    def _get_metadata_class(config_type: str):
        """获取对应类型的元数据类"""
        mapping = {
            'dictionary': BaseConfigMetadata,
            'task': TaskConfigMetadata,
            'strategy': StrategyConfigMetadata,
            'datasource': DatasourceConfigMetadata,
            'dictionaries': BaseConfigMetadata,
            'tasks': TaskConfigMetadata,
            'strategies': StrategyConfigMetadata,
            'datasources': DatasourceConfigMetadata,
        }
        return mapping.get(config_type, BaseConfigMetadata)


class FileConfigManager:
    """文件配置管理器基类

    提供从文件加载/保存配置的功能。
    """

    CONFIG_TYPE: str = ""  # "dictionary", "task", "strategy", "datasource"
    METADATA_CLASS = BaseConfigMetadata

    def __init__(self):
        ensure_config_dirs()
        self._items: Dict[str, ConfigFileItem] = {}
        self._lock = threading.Lock()
        self._load_all()

    def _get_file_path(self, name: str) -> Path:
        return get_config_path(name, self.CONFIG_TYPE)

    def _load_all(self):
        """加载所有配置文件"""
        with self._lock:
            self._items.clear()
            for name in list_config_names(self.CONFIG_TYPE):
                item = self._load_item(name)
                if item:
                    self._items[name] = item

    def _load_item(self, name: str) -> Optional[ConfigFileItem]:
        """加载单个配置项"""
        data = load_raw_config(name, self.CONFIG_TYPE)
        if not data:
            return None

        item = ConfigFileItem.from_dict(name, self.CONFIG_TYPE, data)

        if item.func_code_file:
            item.func_code = self._load_func_code_file(item.func_code_file)

        if not item.func_code:
            item.func_code = data.get('func_code', '') or data.get('fetch_code', '')

        return item

    def _load_func_code_file(self, filepath: str) -> str:
        """加载外部 func_code 文件"""
        if not filepath:
            return ''
        path = Path(filepath)
        if not path.is_absolute():
            path = BASE_CONFIG_DIR / filepath
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
        return ''

    def _save_func_code_file(self, filepath: str, func_code: str) -> bool:
        """保存 func_code 到外部文件"""
        if not filepath:
            return False
        path = Path(filepath)
        if not path.is_absolute():
            path = BASE_CONFIG_DIR / filepath
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(func_code)
            return True
        except Exception as e:
            print(f"[FileConfig] Save func_code file failed: {e}")
            return False

    def get(self, name: str) -> Optional[ConfigFileItem]:
        """获取配置项"""
        return self._items.get(name)

    def get_metadata(self, name: str) -> Optional[BaseConfigMetadata]:
        """获取配置元数据"""
        item = self._items.get(name)
        return item.metadata if item else None

    def get_parameters(self, name: str) -> Dict[str, Any]:
        """获取控制参数"""
        item = self._items.get(name)
        return item.parameters if item else {}

    def get_config(self, name: str) -> Dict[str, Any]:
        """获取类型特定配置"""
        item = self._items.get(name)
        return item.config if item else {}

    def get_func_code(self, name: str) -> str:
        """获取执行代码"""
        item = self._items.get(name)
        return item.func_code if item else ''

    def list_all(self) -> List[ConfigFileItem]:
        """列出所有配置项"""
        return list(self._items.values())

    def list_names(self) -> List[str]:
        """列出所有配置名称"""
        return list(self._items.keys())

    def save(self, item: ConfigFileItem) -> bool:
        """保存配置项到文件"""
        import time

        item.metadata.updated_at = time.time()
        if not item.metadata.created_at:
            item.metadata.created_at = time.time()

        if item.func_code_file:
            self._save_func_code_file(item.func_code_file, item.func_code)

        data = item.to_dict()
        if not item.func_code_file:
            del data['func_code_file']

        success = save_raw_config(item.name, self.CONFIG_TYPE, data)

        if success:
            with self._lock:
                self._items[item.name] = item

        return success

    def create(self, name: str, metadata: BaseConfigMetadata = None,
               parameters: Dict[str, Any] = None,
               config: Dict[str, Any] = None,
               func_code: str = "") -> Optional[ConfigFileItem]:
        """创建新的配置项"""
        if not metadata:
            metadata = self.METADATA_CLASS()

        item = ConfigFileItem(
            name=name,
            config_type=self.CONFIG_TYPE,
            metadata=metadata,
            parameters=parameters or {},
            config=config or {},
            func_code=func_code,
        )

        if self.save(item):
            return item
        return None

    def delete(self, name: str) -> bool:
        """删除配置"""
        with self._lock:
            if name in self._items:
                del self._items[name]
        return delete_raw_config(name, self.CONFIG_TYPE)

    def exists(self, name: str) -> bool:
        """检查配置是否存在"""
        return name in self._items

    def reload(self, name: str = None):
        """重新加载配置"""
        if name:
            item = self._load_item(name)
            with self._lock:
                if item:
                    self._items[name] = item
                elif name in self._items:
                    del self._items[name]
        else:
            self._load_all()


class DictionaryFileConfigManager(FileConfigManager):
    """字典文件配置管理器"""
    CONFIG_TYPE = "dictionaries"
    METADATA_CLASS = BaseConfigMetadata


class TaskFileConfigManager(FileConfigManager):
    """任务文件配置管理器"""
    CONFIG_TYPE = "tasks"
    METADATA_CLASS = TaskConfigMetadata


class StrategyFileConfigManager(FileConfigManager):
    """策略文件配置管理器"""
    CONFIG_TYPE = "strategies"
    METADATA_CLASS = StrategyConfigMetadata


class DatasourceFileConfigManager(FileConfigManager):
    """数据源文件配置管理器"""
    CONFIG_TYPE = "datasources"
    METADATA_CLASS = DatasourceConfigMetadata


_managers: Dict[str, FileConfigManager] = {}
_managers_lock = threading.Lock()


def get_file_config_manager(config_type: str) -> FileConfigManager:
    """获取指定类型的文件配置管理器（单例）"""
    type_mapping = {
        "dictionary": "dictionaries",
        "task": "tasks",
        "strategy": "strategies",
        "datasource": "datasources",
    }

    normalized_type = type_mapping.get(config_type, config_type)

    with _managers_lock:
        if normalized_type not in _managers:
            if normalized_type == "dictionaries":
                _managers[normalized_type] = DictionaryFileConfigManager()
            elif normalized_type == "tasks":
                _managers[normalized_type] = TaskFileConfigManager()
            elif normalized_type == "strategies":
                _managers[normalized_type] = StrategyFileConfigManager()
            elif normalized_type == "datasources":
                _managers[normalized_type] = DatasourceFileConfigManager()
            else:
                raise ValueError(f"Unknown config type: {config_type}")
        return _managers[normalized_type]


def get_dict_file_config_manager() -> DictionaryFileConfigManager:
    return get_file_config_manager("dictionary")


def get_task_file_config_manager() -> TaskFileConfigManager:
    return get_file_config_manager("task")


def get_strategy_file_config_manager() -> StrategyFileConfigManager:
    return get_file_config_manager("strategy")


def get_datasource_file_config_manager() -> DatasourceFileConfigManager:
    return get_file_config_manager("datasource")


def create_example_configs():
    """创建示例配置文件"""
    ensure_config_dirs()

    tongdaxin_example = {
        'metadata': {
            'id': 'tongdaxin_blocks_example',
            'name': '通达信概念板块',
            'description': '通达信概念板块数据，从 infoharbor_block.dat 文件读取',
            'tags': ['板块', '概念', '通达信'],
            'category': '股票数据',
            'enabled': True,
        },
        'parameters': {
            'refresh_interval': 86400,
            'max_block_count': 100,
        },
        'config': {
            'dict_type': 'stock_basic_block',
            'source_mode': 'task',
            'execution_mode': 'scheduler',
            'scheduler_trigger': 'cron',
            'cron_expr': '0 3 * * *',
            'refresh_enabled': True,
        },
        'func_code': '''import pandas as pd
from pathlib import Path
from deva.naja.dictionary.tongdaxin_blocks import get_dataframe

def fetch_data():
    """获取通达信概念板块数据

    返回展开格式的 DataFrame，每行一个股票-板块组合
    """
    blocks_file = Path(__file__).parent.parent.parent / "dictionary" / "infoharbor_block.dat"
    return get_dataframe(filepath=str(blocks_file))
'''
    }

    path = DICT_CONFIG_DIR / "_examples" / "tongdaxin_blocks.yaml"
    try:
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(tongdaxin_example, f, allow_unicode=True, default_flow_style=False)
        print(f"[FileConfig] Created example: {path}")
    except Exception as e:
        print(f"[FileConfig] Create example failed: {e}")


def migrate_nb_to_file(config_type: str, nb_table: str, entry_to_item_func) -> Dict[str, Any]:
    """通用的 NB 到文件的迁移函数

    Args:
        config_type: 配置类型
        nb_table: NB 表名
        entry_to_item_func: 将 NB 条目转换为 ConfigFileItem 的函数

    Returns:
        迁移结果统计
    """
    from deva import NB

    db = NB(nb_table)
    mgr = get_file_config_manager(config_type)

    success_count = 0
    skip_count = 0
    error_count = 0
    errors = []

    for entry_id, data in list(db.items()):
        if not isinstance(data, dict):
            skip_count += 1
            continue

        try:
            item = entry_to_item_func(entry_id, data)
            if not item:
                skip_count += 1
                continue

            if mgr.exists(item.name):
                existing = mgr.get(item.name)
                if existing and existing.metadata.updated_at >= item.metadata.updated_at:
                    skip_count += 1
                    continue

            if mgr.save(item):
                success_count += 1
            else:
                error_count += 1
                errors.append(f"{entry_id}: save failed")
        except Exception as e:
            error_count += 1
            errors.append(f"{entry_id}: {str(e)}")

    return {
        'success': success_count,
        'skip': skip_count,
        'error': error_count,
        'errors': errors[:10],
    }


__all__ = [
    'BASE_CONFIG_DIR',
    'DICT_CONFIG_DIR',
    'TASK_CONFIG_DIR',
    'STRATEGY_CONFIG_DIR',
    'DATASOURCE_CONFIG_DIR',
    'ensure_config_dirs',
    'get_config_path',
    'load_raw_config',
    'save_raw_config',
    'delete_raw_config',
    'list_config_names',
    'config_exists',
    'BaseConfigMetadata',
    'TaskConfigMetadata',
    'StrategyConfigMetadata',
    'DatasourceConfigMetadata',
    'ConfigFileItem',
    'FileConfigManager',
    'DictionaryFileConfigManager',
    'TaskFileConfigManager',
    'StrategyFileConfigManager',
    'DatasourceFileConfigManager',
    'get_file_config_manager',
    'get_dict_file_config_manager',
    'get_task_file_config_manager',
    'get_strategy_file_config_manager',
    'get_datasource_file_config_manager',
    'create_example_configs',
    'migrate_nb_to_file',
]
