"""
Alaya Module - 阿赖耶识层

提供光明藏（SeedIlluminator）和觉醒阿赖耶识能力

类：
- SeedIlluminator: 种子发光引擎
- IlluminatedPattern: 被照亮的模式
- PatternType: 模式类型
- AwakenedAlaya: 觉醒阿赖耶识
- EpiphanyEngine: 顿悟引擎
"""

from .seed_illuminator import (
    SeedIlluminator,
    IlluminatedPattern,
    PatternType,
    PatternTemplate,
)

from .awakened_alaya import (
    AwakenedAlaya,
    AwakeningLevel,
    PatternArchive,
    AwakeningSignal,
    CrossMarketMemory,
    PatternArchiveManager,
    AwakeningEngine,
)

from .epiphany_engine import (
    EpiphanyEngine,
    Epiphany,
    PortfolioEpiphany,
    CrossMarketPattern,
    MarketType,
    PatternEpiphany,
    FullRecall,
)
from deva.naja.register import SR

__all__ = [
    "SeedIlluminator",
    "IlluminatedPattern",
    "PatternType",
    "PatternTemplate",
    "AwakenedAlaya",
    "AwakeningLevel",
    "PatternArchive",
    "AwakeningSignal",
    "CrossMarketMemory",
    "PatternArchiveManager",
    "AwakeningEngine",
    "EpiphanyEngine",
    "Epiphany",
    "PortfolioEpiphany",
    "CrossMarketPattern",
    "MarketType",
    "PatternEpiphany",
    "FullRecall",
]
