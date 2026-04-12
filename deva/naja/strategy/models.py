"""Strategy 数据模型 - StrategyMetadata / StrategyState / 常量"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..common.recoverable import UnitMetadata, UnitState


STRATEGY_TABLE = "naja_strategies"
STRATEGY_RESULTS_TABLE = "naja_strategy_results"
STRATEGY_EXPERIMENT_TABLE = "naja_strategy_experiment"
STRATEGY_EXPERIMENT_ACTIVE_KEY = "active_session"


@dataclass
class StrategyMetadata(UnitMetadata):
    """策略元数据"""
    bound_datasource_id: str = ""
    bound_datasource_ids: List[str] = field(default_factory=list)  # 多数据源支持
    compute_mode: str = "record"
    window_size: int = 5
    window_type: str = "sliding"
    window_interval: str = "10s"
    window_return_partial: bool = False
    dictionary_profile_ids: List[str] = field(default_factory=list)
    max_history_count: int = 100
    diagram_info: Dict[str, Any] = field(default_factory=dict)
    category: str = "默认"  # 策略类别
    strategy_type: str = "legacy"  # legacy/river/plugin
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    strategy_config: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    handler_type: str = "unknown"  # radar/memory/bandit/llm/unknown - 策略处理器类型

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "bound_datasource_id": self.bound_datasource_id,
                "bound_datasource_ids": self.bound_datasource_ids,
                "compute_mode": self.compute_mode,
                "window_size": self.window_size,
                "window_type": self.window_type,
                "window_interval": self.window_interval,
                "window_return_partial": self.window_return_partial,
                "dictionary_profile_ids": self.dictionary_profile_ids,
                "max_history_count": self.max_history_count,
                "diagram_info": self.diagram_info,
                "category": self.category,
                "strategy_type": self.strategy_type,
                "strategy_params": self.strategy_params,
                "strategy_config": self.strategy_config,
                "version": self.version,
                "handler_type": self.handler_type,
            }
        )
        return data


@dataclass
class StrategyState(UnitState):
    """策略状态"""
    processed_count: int = 0
    last_process_ts: float = 0
    output_count: int = 0
