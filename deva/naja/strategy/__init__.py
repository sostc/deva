"""Strategy - 基于 RecoverableUnit 抽象

拆分结构：
  models.py  — StrategyMetadata, StrategyState, 常量
  entry.py   — StrategyEntry (RecoverableUnit 子类)
  manager.py — StrategyManager (单例管理器) + get_strategy_manager()
"""

from .models import (
    StrategyMetadata,
    StrategyState,
    STRATEGY_TABLE,
    STRATEGY_RESULTS_TABLE,
    STRATEGY_EXPERIMENT_TABLE,
    STRATEGY_EXPERIMENT_ACTIVE_KEY,
)
from .entry import StrategyEntry
from .manager import StrategyManager, get_strategy_manager

__all__ = [
    "StrategyMetadata",
    "StrategyState",
    "StrategyEntry",
    "StrategyManager",
    "get_strategy_manager",
    "STRATEGY_TABLE",
    "STRATEGY_RESULTS_TABLE",
    "STRATEGY_EXPERIMENT_TABLE",
    "STRATEGY_EXPERIMENT_ACTIVE_KEY",
]
