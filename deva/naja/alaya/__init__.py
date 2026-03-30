"""
Alaya Module - 阿赖耶识层

提供光明藏（SeedIlluminator）能力

类：
- SeedIlluminator: 种子发光引擎
- IlluminatedPattern: 被照亮的模式
- PatternType: 模式类型
"""

from .seed_illuminator import (
    SeedIlluminator,
    IlluminatedPattern,
    PatternType,
    PatternTemplate,
)

__all__ = [
    "SeedIlluminator",
    "IlluminatedPattern",
    "PatternType",
    "PatternTemplate",
]
