"""
价值观类型定义

Query = 价值观

不同的价值观遇到同样的事件，会计算出不同的价值。

价值观分类：

【糊涂的跟随者 - 投机】
  只跟着价格跑，不关心世界发生了什么
  - 趋势追踪、动量策略、流动性猎人、情绪周期

【清醒的创造者 - 投资】
  思考世界怎么改变，投资推动进步的赛道
  - 成长投资、价值投资、事件驱动

"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import time


class InvestmentDirection(Enum):
    """投资方向 - 区分'糊涂跟随'和'清醒创造'"""
    SPECULATIVE = "speculative"
    CREATIVE = "creative"

    @property
    def display_name(self) -> str:
        names = {
            "speculative": "🛠️ 节奏调整",
            "creative": "🚀 赛道投资",
        }
        return names.get(self.value, self.value)

    @property
    def emoji(self) -> str:
        emojis = {
            "speculative": "🛠️",
            "creative": "🚀",
        }
        return emojis.get(self.value, "")

    @property
    def description(self) -> str:
        descs = {
            "speculative": "🛠️ 节奏调整（辅助）：服务于赛道投资，利用市场波动降低成本，高抛低吸",
            "creative": "🚀 赛道投资（核心）：投资推动世界进步的赛道，发现问题，解决问题，推动世界发展",
        }
        return descs.get(self.value, "")


class ValueType(Enum):
    """价值观类型枚举"""
    TREND = "trend"
    CONTRARIAN = "contrarian"
    VALUE = "value"
    MOMENTUM = "momentum"
    LIQUIDITY = "liquidity"
    BALANCED = "balanced"
    GROWTH = "growth"
    EVENT_DRIVEN = "event_driven"
    MARKET_MAKING = "market_making"
    SENTIMENT_CYCLE = "sentiment_cycle"
    LIQUIDITY_RESCUE = "liquidity_rescue"

    @classmethod
    def from_string(cls, s: str) -> "ValueType":
        """从字符串转换"""
        s = s.lower().strip()
        for t in cls:
            if t.value == s:
                return t
        return cls.BALANCED

    @property
    def display_name(self) -> str:
        """显示名称"""
        names = {
            "trend": "趋势追踪",
            "contrarian": "逆向投资",
            "value": "价值投资",
            "momentum": "动量策略",
            "liquidity": "流动性猎人",
            "balanced": "均衡配置",
            "growth": "成长投资",
            "event_driven": "事件驱动",
            "market_making": "高频做市",
            "sentiment_cycle": "情绪周期",
            "liquidity_rescue": "流动性救援者",
        }
        return names.get(self.value, self.value)

    @property
    def description(self) -> str:
        descs = {
            "trend": "🛠️ 趋势追踪，服务于仓位调整，低买高卖。不是追涨杀跌，是顺势而为。",
            "contrarian": "🚀 逆向投资，发现均值回归机会。别人恐惧时贪婪，等待价值回归。",
            "value": "🚀 价值投资，发现被低估的资产。安全边际是第一原则，等待市场纠错。",
            "momentum": "🛠️ 动量策略，捕捉短期动量变化。强者恒强，优化持仓成本。",
            "liquidity": "🛠️ 流动性猎人，观察资金流向。服务于仓位调整，寻找机会。",
            "balanced": "🚀 均衡配置，分散风险。核心仓位+辅助调整。",
            "growth": "🚀 成长投资，核心赛道。投资推动世界进步的赛道，长期持有，不因为短期波动而动摇。",
            "event_driven": "🛠️ 事件驱动，观察重大事件影响。财报、并购、政策都是机会。",
            "market_making": "🩹 做市商服务，偶尔提供流动性。获取价差收益。",
            "sentiment_cycle": "🛠️ 情绪周期，利用市场情绪波动。恐惧与贪婪，服务于降低成本。",
            "liquidity_rescue": "🩹 流动性救援，偶尔发现市场危机。雪中送炭，不是趁火打劫，是解决问题。",
        }
        return descs.get(self.value, "")

    @property
    def investment_direction(self) -> InvestmentDirection:
        """投资方向"""
        speculative_types = {"trend", "momentum", "liquidity", "sentiment_cycle", "market_making"}
        if self.value in speculative_types:
            return InvestmentDirection.SPECULATIVE
        return InvestmentDirection.CREATIVE


@dataclass
class ValueWeights:
    """价值观权重配置 - 决定'关注什么'"""

    price_sensitivity: float = 0.5
    volume_sensitivity: float = 0.5
    sentiment_weight: float = 0.3
    liquidity_weight: float = 0.4
    fundamentals_weight: float = 0.3

    def to_dict(self) -> Dict[str, float]:
        return {
            "price_sensitivity": self.price_sensitivity,
            "volume_sensitivity": self.volume_sensitivity,
            "sentiment_weight": self.sentiment_weight,
            "liquidity_weight": self.liquidity_weight,
            "fundamentals_weight": self.fundamentals_weight,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> "ValueWeights":
        return cls(
            price_sensitivity=d.get("price_sensitivity", 0.5),
            volume_sensitivity=d.get("volume_sensitivity", 0.5),
            sentiment_weight=d.get("sentiment_weight", 0.3),
            liquidity_weight=d.get("liquidity_weight", 0.4),
            fundamentals_weight=d.get("fundamentals_weight", 0.3),
        )


@dataclass
class ValuePreferences:
    """价值观偏好 - 决定'怎么想'"""

    risk_preference: float = 0.5
    time_horizon: float = 0.5
    concentration: float = 0.5

    @property
    def risk_level(self) -> str:
        if self.risk_preference < 0.3:
            return "保守"
        elif self.risk_preference < 0.6:
            return "中性"
        else:
            return "激进"

    @property
    def time_label(self) -> str:
        if self.time_horizon < 0.3:
            return "短期"
        elif self.time_horizon < 0.7:
            return "中期"
        else:
            return "长期"

    @property
    def concentration_label(self) -> str:
        if self.concentration < 0.3:
            return "分散"
        elif self.concentration < 0.6:
            return "均衡"
        else:
            return "集中"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_preference": self.risk_preference,
            "time_horizon": self.time_horizon,
            "concentration": self.concentration,
            "risk_level": self.risk_level,
            "time_label": self.time_label,
            "concentration_label": self.concentration_label,
        }


@dataclass
class ValueProfile:
    """价值观配置"""
    name: str
    value_type: ValueType
    description: str = ""
    weights: ValueWeights = field(default_factory=ValueWeights)
    preferences: ValuePreferences = field(default_factory=ValuePreferences)
    enabled: bool = True
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_modified: float = field(default_factory=time.time)
    applicable_regimes: List[str] = field(default_factory=lambda: ["trend_up", "neutral", "trend_down"])
    principles: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    implemented: bool = True
    pending_strategies: List[str] = field(default_factory=list)
    investment_direction: InvestmentDirection = field(default=None)

    def __post_init__(self):
        if self.investment_direction is None:
            self.investment_direction = self.value_type.investment_direction

    @property
    def direction(self) -> InvestmentDirection:
        """获取投资方向"""
        return self.investment_direction or self.value_type.investment_direction

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value_type": self.value_type.value,
            "value_type_display": self.value_type.display_name,
            "description": self.description or self.value_type.description,
            "weights": self.weights.to_dict(),
            "preferences": self.preferences.to_dict(),
            "enabled": self.enabled,
            "weight": self.weight,
            "created_at": self.created_at,
            "last_modified": self.last_modified,
            "applicable_regimes": self.applicable_regimes,
            "principles": self.principles,
            "metadata": self.metadata,
            "implemented": self.implemented,
            "pending_strategies": self.pending_strategies,
            "investment_direction": self.direction.value,
            "direction_display": self.direction.display_name,
            "direction_emoji": self.direction.emoji,
        }

    def update_weights(self, weights: ValueWeights):
        """更新权重"""
        self.weights = weights
        self.last_modified = time.time()

    def update_preferences(self, preferences: ValuePreferences):
        """更新偏好"""
        self.preferences = preferences
        self.last_modified = time.time()


__all__ = [
    "ValueType",
    "ValueWeights",
    "ValuePreferences",
    "ValueProfile",
]