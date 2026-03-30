"""
Senses Module - 五识层

提供预感知和实时尝受能力

类：
- ProphetSense: 天眼通预感知引擎
- MomentumPrecipice: 动量悬崖预判
- SentimentTransitionSense: 情绪转换预判
- FlowTasteSense: 资金流向味道
- VolatilitySurfaceSense: 波动率曲面感知
- RealtimeTaste: 实时舌识尝受
"""

from .prophetic_sensing import (
    ProphetSense,
    ProphetSignal,
    PresageType,
    MomentumPrecipice,
    SentimentTransitionSense,
    FlowTasteSense,
    VolatilitySurfaceSense,
)

from .realtime_taste import (
    RealtimeTaste,
    TasteSignal,
)

__all__ = [
    "ProphetSense",
    "ProphetSignal",
    "PresageType",
    "MomentumPrecipice",
    "SentimentTransitionSense",
    "FlowTasteSense",
    "VolatilitySurfaceSense",
    "RealtimeTaste",
    "TasteSignal",
]
