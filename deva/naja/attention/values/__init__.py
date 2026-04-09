"""
价值观系统

Query = 价值观

不同的价值观遇到同样的事件，会计算出不同的价值。

核心模块：
- types: 价值观类型、数据结构定义
- profile: 价值观配置管理
- config: 预定义价值观配置
- mapping: 价值观与策略映射
- system: 价值观系统单例
"""

from .types import (
    ValueType,
    ValueWeights,
    ValuePreferences,
    ValueProfile,
)

from .profile import (
    ValueProfileManager,
    get_default_profiles,
)

from .config import (
    VALUE_CONFIG,
    REGIME_COMPATIBILITY,
    get_value_config,
    get_compatible_values,
    is_value_compatible,
)

from .mapping import (
    VALUE_STRATEGY_MAPPING,
    STRATEGY_TO_VALUE_MAPPING,
    get_primary_strategy,
    get_secondary_strategies,
    get_strategy_principles,
    get_strategy_indicators,
    infer_value_type,
    get_all_strategies_for_value,
)

from .system import (
    ValueSystem,
    initialize_value_system,
)


__all__ = [
    "ValueType",
    "ValueWeights",
    "ValuePreferences",
    "ValueProfile",
    "ValueProfileManager",
    "get_default_profiles",
    "VALUE_CONFIG",
    "REGIME_COMPATIBILITY",
    "get_value_config",
    "get_compatible_values",
    "is_value_compatible",
    "VALUE_STRATEGY_MAPPING",
    "STRATEGY_TO_VALUE_MAPPING",
    "get_primary_strategy",
    "get_secondary_strategies",
    "get_strategy_principles",
    "get_strategy_indicators",
    "infer_value_type",
    "get_all_strategies_for_value",
    "ValueSystem",
    "initialize_value_system",
]