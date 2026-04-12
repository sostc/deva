"""DataSource - 基于 RecoverableUnit 抽象

拆分结构：
  models.py    — DataSourceMetadata, DataSourceState, 常量
  debouncer.py — DataSourceDebouncer (防抖器)
  entry.py     — DataSourceEntry (RecoverableUnit 子类)
  manager.py   — DataSourceManager (单例管理器) + get_datasource_manager()
"""

from .models import (
    DataSourceMetadata,
    DataSourceState,
    DS_TABLE,
    DS_LATEST_DATA_TABLE,
)
from .debouncer import DataSourceDebouncer
from .entry import DataSourceEntry
from .manager import DataSourceManager, get_datasource_manager

__all__ = [
    "DataSourceMetadata",
    "DataSourceState",
    "DataSourceEntry",
    "DataSourceDebouncer",
    "DataSourceManager",
    "get_datasource_manager",
    "DS_TABLE",
    "DS_LATEST_DATA_TABLE",
]
