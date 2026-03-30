"""
AdaptiveManas - 顺应型末那识

不是"要不要动"，而是"天要我动"

核心思想：
- 顺应天道，而非强迫天道
- 时机到了，自然行动
- 时机未到，绝不妄动

能力：
1. TianShiResponse: 天时响应 - 感受天时，顺势而为
2. RegimeHarmony: 环境和谐 - 与环境合一，不强求
3. WuWeiAction: 无为而治 - 不妄动，不执着

使用方式：
    manas = AdaptiveManas()
    decision = manas.compute_顺应(current_state)
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

log = logging.getLogger(__name__)


class HarmonyState(Enum):
    """和谐状态"""
    RESONANCE = "resonance"
    NEUTRAL = "neutral"
    RESISTANCE = "resistance"


@dataclass
class WuWeiDecision:
    """无为决策"""
    should_act: bool
    harmony_state: HarmonyState
    harmony_strength: float
    tian_shi_score: float
    di_shi_score: float
    ren_shi_score: float
    confidence: float
    reason: str
    action_type: str = "hold"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_act": self.should_act,
            "harmony_state": self.harmony_state.value,
            "harmony_strength": self.harmony_strength,
            "tian_shi_score": self.tian_shi_score,
            "di_shi_score": self.di_shi_score,
            "ren_shi_score": self.ren_shi_score,
            "confidence": self.confidence,
            "reason": self.reason,
            "action_type": self.action_type,
        }


class TianShiResponse:
    """
    天时响应

    感受天时的变化，顺应时机
    """

    def __init__(self):
        self._market_open_history: deque = deque(maxlen=20)
        self._volatility_history: deque = deque(maxlen=20)
        self._trend_history: deque = deque(maxlen=20)

    def evaluate(self, market_state: Dict[str, Any]) -> float:
        """
        评估天时得分 [0, 1]

        Returns:
            天时适合程度
        """
        tian_shi = 0.5

        if market_state.get("is_market_open", False):
            tian_shi += 0.2
        else:
            tian_shi -= 0.2

        volatility = market_state.get("volatility", 1.0)
        if 0.5 <= volatility <= 1.5:
            tian_shi += 0.1

        trend = market_state.get("trend_strength", 0.0)
        if abs(trend) > 0.3:
            tian_shi += trend * 0.2

        time_of_day = market_state.get("time_of_day", 0)
        if 9.5 <= time_of_day <= 10.5:
            tian_shi += 0.1
        elif 14.0 <= time_of_day <= 15.0:
            tian_shi += 0.15

        return max(0.0, min(1.0, tian_shi))


class RegimeHarmony:
    """
    环境和谐

    与市场环境合一，不强求
    """

    def __init__(self):
        self._regime_history: deque = deque(maxlen=30)
        self._current_regime = "unknown"

    def evaluate(
        self,
        current_regime: str,
        regime_stability: float,
        market_breadth: float
    ) -> tuple[float, HarmonyState]:
        """
        评估与环境的和谐程度

        Returns:
            (harmony_score, harmony_state)
        """
        self._regime_history.append({
            "regime": current_regime,
            "timestamp": time.time()
        })

        if len(self._regime_history) >= 5:
            recent_regimes = [h["regime"] for h in list(self._regime_history)[-5:]]
            stability = len(set(recent_regimes)) / 5.0
        else:
            stability = 1.0

        harmony = regime_stability * 0.5 + stability * 0.3 + abs(market_breadth) * 0.2

        if harmony > 0.7:
            state = HarmonyState.RESONANCE
        elif harmony < 0.4:
            state = HarmonyState.RESISTANCE
        else:
            state = HarmonyState.NEUTRAL

        return harmony, state


class RenShiResponse:
    """
    人时响应

    感知自身的状态，不强求
    """

    def __init__(self):
        self._recent_decisions: deque = deque(maxlen=20)
        self._recent_outcomes: deque = deque(maxlen=20)

    def evaluate(
        self,
        confidence: float,
        risk_appetite: float,
        recent_success_rate: float
    ) -> float:
        """
        评估"人时"得分 [0, 1]

        考虑自身状态：
        - 信心程度
        - 风险偏好
        - 近期成功率
        """
        base = confidence

        confidence_boost = (confidence - 0.5) * 0.2
        risk_factor = (risk_appetite - 0.5) * 0.1
        success_factor = (recent_success_rate - 0.5) * 0.3

        ren_shi = base + confidence_boost + risk_factor + success_factor

        if len(self._recent_decisions) > 0:
            recent_aggression = sum(1 for d in list(self._recent_decisions)[-5:]
                                   if d.get("action", "hold") != "hold")
            if recent_aggression >= 4:
                ren_shi *= 0.8

        return max(0.0, min(1.0, ren_shi))

    def record_decision(self, decision: Dict[str, Any]):
        """记录决策"""
        self._recent_decisions.append(decision)

    def record_outcome(self, outcome: Dict[str, Any]):
        """记录结果"""
        self._recent_outcomes.append(outcome)


class AdaptiveManas:
    """
    顺应型末那识

    不是强迫自己行动，而是感受天时、地势、人和
    当一切就绪，自然而然地行动
    当时机不对，安静地等待
    """

    def __init__(self):
        self.tian_shi = TianShiResponse()
        self.regime = RegimeHarmony()
        self.ren_shi = RenShiResponse()

        self._decision_history: List[WuWeiDecision] = []
        self._last_decision_time = 0.0
        self._min_decision_interval = 30.0

    def compute_decision(
        self,
        market_state: Dict[str, Any],
        confidence: float = 0.5,
        risk_appetite: float = 0.5,
        portfolio: Optional[Dict[str, Any]] = None
    ) -> WuWeiDecision:
        """
        决策计算

        Args:
            market_state: 市场状态
            confidence: 策略信心
            risk_appetite: 风险偏好
            portfolio: 持仓信息
                - held_symbols: 持仓股票列表
                - position_count: 持仓数量
                - total_return: 总收益率
                - profit_loss: 总盈亏
                - cash_ratio: 现金比例
                - concentration: 集中度
                - position_details: 持仓明细 [{symbol, weight, return_pct, ...}]
                - sector_allocations: 板块配置 {sector: weight}

        Returns:
            WuWeiDecision
        """
        current_time = time.time()
        if current_time - self._last_decision_time < self._min_decision_interval:
            if self._decision_history:
                return self._decision_history[-1]

        tian_score = self.tian_shi.evaluate(market_state)
        di_score, harmony_state = self.regime.evaluate(
            market_state.get("regime", "unknown"),
            market_state.get("regime_stability", 0.5),
            market_state.get("market_breadth", 0.0)
        )

        portfolio_factor = self._evaluate_portfolio_factor(portfolio)

        ren_score = self.ren_shi.evaluate(
            confidence,
            risk_appetite,
            self._get_recent_success_rate(),
            portfolio_factor
        )

        harmony_strength = (tian_score * 0.4 + di_score * 0.35 + ren_score * 0.25)

        should_act = harmony_strength > 0.6
        if harmony_state == HarmonyState.RESISTANCE:
            should_act = False
        elif harmony_state == HarmonyState.RESONANCE:
            should_act = harmony_strength > 0.4

        action_type = "hold"
        if should_act:
            if harmony_state == HarmonyState.RESONANCE and tian_score > 0.7:
                action_type = "act_fully"
            elif harmony_state == HarmonyState.NEUTRAL:
                action_type = "act_carefully"
            else:
                action_type = "act_minimally"

        reason = self._generate_reason(tian_score, di_score, ren_score, harmony_state, portfolio)

        decision = WuWeiDecision(
            should_act=should_act,
            harmony_state=harmony_state,
            harmony_strength=harmony_strength,
            tian_shi_score=tian_score,
            di_shi_score=di_score,
            ren_shi_score=ren_score,
            confidence=harmony_strength,
            reason=reason,
            action_type=action_type
        )

        self._decision_history.append(decision)
        if len(self._decision_history) > 100:
            self._decision_history.pop(0)

        self._last_decision_time = current_time

        return decision

    def _evaluate_portfolio_factor(self, portfolio: Optional[Dict[str, Any]]) -> float:
        """评估持仓状态对我执的影响"""
        if not portfolio:
            return 0.5

        factor = 0.5

        cash_ratio = portfolio.get("cash_ratio", 0.5)
        if cash_ratio < 0.2:
            factor += 0.1
        elif cash_ratio > 0.5:
            factor -= 0.15

        total_return = portfolio.get("total_return", 0)
        if total_return < -0.1:
            factor -= 0.15
        elif total_return > 0.1:
            factor += 0.1

        concentration = portfolio.get("concentration", 0)
        if concentration > 0.5:
            factor -= 0.1

        position_count = portfolio.get("position_count", 0)
        if position_count == 0:
            factor += 0.2

        return max(0.0, min(1.0, factor))

    def _get_recent_success_rate(self) -> float:
        """获取近期成功率"""
        if not self._decision_history:
            return 0.5

        recent = list(self._decision_history)[-10:]
        if not recent:
            return 0.5

        success = sum(1 for d in recent if d.should_act)
        return success / len(recent)

    def _generate_reason(
        self,
        tian: float,
        di: float,
        ren: float,
        harmony: HarmonyState,
        portfolio: Optional[Dict[str, Any]] = None
    ) -> str:
        """生成决策原因"""
        reasons = []

        if tian > 0.7:
            reasons.append("天时有利")
        elif tian < 0.4:
            reasons.append("天时不利")

        if harmony == HarmonyState.RESONANCE:
            reasons.append("与势共振")
        elif harmony == HarmonyState.RESISTANCE:
            reasons.append("与势相抗")

        if di > 0.7:
            reasons.append("地势有利")
        elif di < 0.4:
            reasons.append("地势不利")

        if ren > 0.7:
            reasons.append("人和")
        elif ren < 0.4:
            reasons.append("人和不足")

        return " | ".join(reasons) if reasons else "中性"

    def compute_traditional(self, manas_score: float) -> WuWeiDecision:
        """
        计算传统 manas 风格决策（兼容）

        Args:
            manas_score: manas 分数 [0, 1]

        Returns:
            WuWeiDecision
        """
        return self.compute_顺应({
            "is_market_open": True,
            "volatility": 1.0,
            "trend_strength": (manas_score - 0.5) * 2,
            "time_of_day": 10.0,
            "regime": "trend",
            "regime_stability": 0.5,
            "market_breadth": (manas_score - 0.5) * 0.5
        }, confidence=manas_score)

    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "decision_count": len(self._decision_history),
            "last_decision": self._decision_history[-1].to_dict() if self._decision_history else None,
            "recent_success_rate": self._get_recent_success_rate(),
        }
