"""
Integration - 系统集成
"""

from .attention_system import (
    AttentionSystem,
    AttentionSystemConfig,
    AttentionSystemIntegration,
    MarketSnapshot
)
from .integration import (
    IntelligenceAugmentedSystem,
    IntelligenceConfig,
    create_intelligence_system,
    create_system,
)
from .extended import (
    NajaAttentionIntegration,
    get_attention_integration,
    initialize_attention_system,
    get_attention_system,
    register_strategy_manager,
    get_strategy_manager,
    process_data_with_strategies,
    AttentionModeManager,
    get_mode_manager,
)

__all__ = [
    "AttentionSystem",
    "AttentionSystemConfig",
    "AttentionSystemIntegration",
    "MarketSnapshot",
    "IntelligenceAugmentedSystem",
    "IntelligenceConfig",
    "create_intelligence_system",
    "create_system",
    "NajaAttentionIntegration",
    "get_attention_integration",
    "initialize_attention_system",
    "get_attention_system",
    "register_strategy_manager",
    "get_strategy_manager",
    "process_data_with_strategies",
    "AttentionModeManager",
    "get_mode_manager",
]