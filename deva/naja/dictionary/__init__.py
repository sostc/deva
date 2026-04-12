"""Dictionary - 基于 RecoverableUnit 抽象

拆分结构：
  models.py   — DictionaryMetadata, DictionaryState, 常量
  helpers.py  — 内部辅助函数
  entry.py    — DictionaryEntry (RecoverableUnit 子类)
  manager.py  — DictionaryManager (单例管理器)
  utils.py    — 工具函数 (create_tongdaxin_blocks_dict, enrich_stock_with_blocks)
"""

from .models import (
    DictionaryMetadata,
    DictionaryState,
    DICT_ENTRY_TABLE,
    DICT_PAYLOAD_TABLE,
)
from .entry import DictionaryEntry
from .manager import DictionaryManager
from .utils import create_tongdaxin_blocks_dict, enrich_stock_with_blocks

# tongdaxin_blocks 子模块的便捷导出
from .tongdaxin_blocks import (
    get_stock_blocks,
    get_block_info,
    get_block_stocks,
    get_all_blocks,
    get_blocks_by_keyword,
    get_stock_block_mapping,
    get_dataframe,
)

__all__ = [
    "DictionaryMetadata",
    "DictionaryState",
    "DictionaryEntry",
    "DictionaryManager",
    "DICT_ENTRY_TABLE",
    "DICT_PAYLOAD_TABLE",
    "create_tongdaxin_blocks_dict",
    "enrich_stock_with_blocks",
    "get_stock_blocks",
    "get_block_info",
    "get_block_stocks",
    "get_all_blocks",
    "get_blocks_by_keyword",
    "get_stock_block_mapping",
    "get_dataframe",
]
