"""
UnifiedManasOutput - 统一末那识输出

整合 ManasEngine 和 AdaptiveManas 的输出结构
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum


class AttentionFocus(Enum):
    """注意力聚焦类型"""
    WATCH = "watch"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    REBALANCE = "rebalance"
    ACCUMULATE = "accumulate"


class HarmonyState(Enum):
    """和谐状态"""
    RESONANCE = "resonance"
    NEUTRAL = "neutral"
    RESISTANCE = "resistance"


class BiasState(Enum):
    """偏差状态"""
    NEUTRAL = "neutral"
    GREED = "greed"
    FEAR = "fear"


class ActionType(Enum):
    """行动类型"""
    HOLD = "hold"
    ACT_FULLY = "act_fully"
    ACT_CAREFULLY = "act_carefully"
    ACT_MINIMALLY = "act_minimally"


class PortfolioSignal(Enum):
    """持仓信号"""
    NONE = "none"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    REBALANCE = "rebalance"
    ACCUMULATE = "accumulate"


@dataclass
class UnifiedManasOutput:
    """统一末那识输出"""

    manas_score: float = 0.5
    timing_score: float = 0.5
    regime_score: float = 0.0
    confidence_score: float = 0.5
    risk_temperature: float = 1.0

    attention_focus: AttentionFocus = AttentionFocus.WATCH
    alpha: float = 1.0

    harmony_state: HarmonyState = HarmonyState.NEUTRAL
    harmony_strength: float = 0.5
    action_type: ActionType = ActionType.HOLD

    should_act: bool = False
    bias_state: BiasState = BiasState.NEUTRAL
    bias_correction: float = 1.0

    portfolio_signal: PortfolioSignal = PortfolioSignal.NONE
    portfolio_loss_pct: float = 0.0
    market_deterioration: bool = False

    sector_alloc: Dict[str, float] = field(default_factory=dict)
    enriched_positions: List[Dict] = field(default_factory=list)
    worst_sector: str = ""
    best_sector: str = ""

    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manas_score": self.manas_score,
            "timing_score": self.timing_score,
            "regime_score": self.regime_score,
            "confidence_score": self.confidence_score,
            "risk_temperature": self.risk_temperature,
            "attention_focus": self.attention_focus.value,
            "alpha": self.alpha,
            "harmony_state": self.harmony_state.value,
            "harmony_strength": self.harmony_strength,
            "action_type": self.action_type.value,
            "should_act": self.should_act,
            "bias_state": self.bias_state.value,
            "bias_correction": self.bias_correction,
            "portfolio_signal": self.portfolio_signal.value,
            "portfolio_loss_pct": self.portfolio_loss_pct,
            "market_deterioration": self.market_deterioration,
            "sector_alloc": self.sector_alloc,
            "enriched_positions": self.enriched_positions,
            "worst_sector": self.worst_sector,
            "best_sector": self.best_sector,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedManasOutput":
        return cls(
            manas_score=data.get("manas_score", 0.5),
            timing_score=data.get("timing_score", 0.5),
            regime_score=data.get("regime_score", 0.0),
            confidence_score=data.get("confidence_score", 0.5),
            risk_temperature=data.get("risk_temperature", 1.0),
            attention_focus=AttentionFocus(data.get("attention_focus", "watch")),
            alpha=data.get("alpha", 1.0),
            harmony_state=HarmonyState(data.get("harmony_state", "neutral")),
            harmony_strength=data.get("harmony_strength", 0.5),
            action_type=ActionType(data.get("action_type", "hold")),
            should_act=data.get("should_act", False),
            bias_state=BiasState(data.get("bias_state", "neutral")),
            bias_correction=data.get("bias_correction", 1.0),
            portfolio_signal=PortfolioSignal(data.get("portfolio_signal", "none")),
            portfolio_loss_pct=data.get("portfolio_loss_pct", 0.0),
            market_deterioration=data.get("market_deterioration", False),
            reason=data.get("reason", ""),
        )