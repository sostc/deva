"""
Discovery - 主动发现模块

发现市场中的投资机会，包括盲区检测、叙事发现等。

核心能力:
- 外部热点 vs 我们持仓的差异分析
- 叙事驱动的题材发现
- 信念强度验证
"""

from .blind_spot_investigator import (
    BlindSpotInvestigator,
    InvestigationResult,
    BatchInvestigationResult,
    get_blind_spot_investigator,
    CAUSAL_KNOWLEDGE,
)
from .narrative_block_linker import (
    NarrativeBlockLinker,
    get_linked_blocks,
    get_linked_markets,
    get_market_config,
    get_narrative_block_linker,
)
from .conviction_validator import (
    ConvictionValidator,
    ValidationResult,
    get_conviction_validator,
)

__all__ = [
    # BlindSpotInvestigator
    "BlindSpotInvestigator",
    "InvestigationResult",
    "BatchInvestigationResult",
    "get_blind_spot_investigator",
    "CAUSAL_KNOWLEDGE",
    # NarrativeBlockLinker
    "NarrativeBlockLinker",
    "get_linked_blocks",
    "get_linked_markets",
    "get_market_config",
    "get_narrative_block_linker",
    # ConvictionValidator
    "ConvictionValidator",
    "ValidationResult",
    "get_conviction_validator",
]