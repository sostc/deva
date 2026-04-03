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
    "get_awakened_alaya",
]

_awakened_alaya_instance = None


def get_awakened_alaya() -> "AwakenedAlaya":
    """获取觉醒阿赖耶识单例"""
    global _awakened_alaya_instance
    if _awakened_alaya_instance is None:
        _awakened_alaya_instance = AwakenedAlaya()
    return _awakened_alaya_instance
