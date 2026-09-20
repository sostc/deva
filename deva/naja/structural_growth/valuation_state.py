"""估值状态机 S0-S4

五个状态：
- S0 普通周期状态（起点）：市场按历史周期利润和低估值倍数定价
- S1 需求加速（观察）：订单和需求指标持续改善，但供给和价格仍不确定
- S2 瓶颈形成（验证）：交付周期、产能、认证或资源约束开始影响产业链
- S3 利润兑现（关键阶段）：毛利率、经营利润率和自由现金流改善
- S4 估值重估候选（重点研究）：评估持续时间、竞争扩产和股价是否已反映预期

设计原则：
- 转换阈值集中在 TransitionRules（单一真源），禁止在调用点写备用分支
- 状态可前进也可回退（不是单向流水线）
- 转换决策依据三 Agent 链的输出（验证结果 + 估值分析），而非单一因子
- 每次转换记录历史，可回溯
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .industry_state import IndustryState, FactorTrend
from .agents.discovery_agent import HypothesisType
from .agents.verification_agent import VerificationResult, VerificationVerdict
from .agents.valuation_agent import ValuationAnalysis


class ValuationPhase(Enum):
    """估值状态 S0-S4"""
    S0_CYCLICAL = "S0"          # 普通周期状态
    S1_DEMAND_ACCEL = "S1"      # 需求加速
    S2_BOTTLENECK = "S2"        # 瓶颈形成
    S3_PROFIT_MATERIALIZE = "S3"  # 利润兑现
    S4_REVALUATION_CANDIDATE = "S4"  # 估值重估候选

    @property
    def display_name(self) -> str:
        names = {
            "S0": "普通周期",
            "S1": "需求加速",
            "S2": "瓶颈形成",
            "S3": "利润兑现",
            "S4": "重估候选",
        }
        return names[self.value]

    @property
    def is_early_stage(self) -> bool:
        """是否处于早期阶段（S0/S1）"""
        return self in (ValuationPhase.S0_CYCLICAL, ValuationPhase.S1_DEMAND_ACCEL)

    @property
    def is_key_stage(self) -> bool:
        """是否处于关键阶段（S3）"""
        return self == ValuationPhase.S3_PROFIT_MATERIALIZE


@dataclass
class TransitionRules:
    """状态转换规则（单一真源）

    所有阈值集中在此处，业务代码只能通过 evaluate() 使用，
    禁止在其他地方硬编码同义阈值。
    """
    # S0 → S1: 需求加速阈值（百分点）
    demand_accel_pp: float = 5.0
    # S1 → S2: 供给瓶颈是否被验证（CONFIRMED 或 PARTIALLY_SUPPORTED）
    require_bottleneck_verified: bool = True
    # S2 → S3: 需要同时验证的假设数（利润率扩张 + 现金流拐点）
    require_profit_and_cashflow: bool = True
    # S3 → S4: 利润跃迁假设被确认 + 预期差阈值（百分点）
    require_profit_transition_confirmed: bool = True
    expectation_gap_pp: float = 3.0
    # 回退：需求减速阈值（百分点）
    demand_decel_pp: float = -2.0


@dataclass
class StateTransition:
    """单次状态转换记录"""
    from_state: Optional[ValuationPhase]
    to_state: ValuationPhase
    timestamp: float
    reason: str
    triggered_by: List[str] = field(default_factory=list)  # 触发的假设/信号

    def to_dict(self) -> Dict:
        return {
            "from_state": self.from_state.value if self.from_state else None,
            "to_state": self.to_state.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "triggered_by": list(self.triggered_by),
        }


class ValuationStateMachine:
    """估值状态机

    输入：产业状态 + 验证结果 + 估值分析
    输出：当前估值状态 + 转换历史
    """

    def __init__(self, rules: Optional[TransitionRules] = None):
        self.rules = rules or TransitionRules()
        self._current: ValuationPhase = ValuationPhase.S0_CYCLICAL
        self._history: List[StateTransition] = []

    # ---- 属性 ----
    @property
    def current(self) -> ValuationPhase:
        return self._current

    @property
    def history(self) -> List[StateTransition]:
        return list(self._history)

    # ---- 主入口 ----
    def evaluate(self, state: IndustryState, verifications: List[VerificationResult],
                 valuation: ValuationAnalysis) -> ValuationPhase:
        """根据三 Agent 输出评估当前状态，必要时执行转换"""
        state.recompute_signals()
        new_state = self._determine_state(state, verifications, valuation)
        if new_state != self._current:
            transition = self._build_transition(self._current, new_state, state, verifications, valuation)
            self._history.append(transition)
            self._current = new_state
        return self._current

    # ---- 状态判定 ----
    def _determine_state(self, state: IndustryState, verifications: List[VerificationResult],
                         valuation: ValuationAnalysis) -> ValuationPhase:
        rules = self.rules
        verified = {r.hypothesis_type: r for r in verifications if not r.is_veto}
        vetoed = {r.hypothesis_type: r for r in verifications if r.is_veto}

        demand_accel = state.signals.demand_growth_acceleration or 0.0

        # S4: 利润跃迁确认 + 正预期差
        if self._check_s4(verified, valuation, rules):
            return ValuationPhase.S4_REVALUATION_CANDIDATE

        # S3: 利润兑现（利润率扩张 + 现金流拐点均验证通过）
        if self._check_s3(verified, rules):
            return ValuationPhase.S3_PROFIT_MATERIALIZE

        # S2: 瓶颈形成（供给瓶颈验证通过）
        if self._check_s2(verified, rules):
            return ValuationPhase.S2_BOTTLENECK

        # S1: 需求加速
        if demand_accel > rules.demand_accel_pp and state.demand.trend() == FactorTrend.ACCELERATING:
            return ValuationPhase.S1_DEMAND_ACCEL

        # S0: 普通周期
        return ValuationPhase.S0_CYCLICAL

    def _check_s4(self, verified: Dict, valuation: ValuationAnalysis, rules: TransitionRules) -> bool:
        pt = verified.get("profit_transition")
        if pt is None:
            return False
        if rules.require_profit_transition_confirmed and pt.verdict != VerificationVerdict.CONFIRMED:
            return False
        return valuation.expectation_gap > rules.expectation_gap_pp

    def _check_s3(self, verified: Dict, rules: TransitionRules) -> bool:
        if not rules.require_profit_and_cashflow:
            return "margin_expansion" in verified or "cashflow_inflection" in verified
        return "margin_expansion" in verified and "cashflow_inflection" in verified

    def _check_s2(self, verified: Dict, rules: TransitionRules) -> bool:
        if not rules.require_bottleneck_verified:
            return "supply_bottleneck" in verified
        sb = verified.get("supply_bottleneck")
        if sb is None:
            return False
        return sb.verdict in (VerificationVerdict.CONFIRMED, VerificationVerdict.PARTIALLY_SUPPORTED)

    # ---- 转换记录 ----
    def _build_transition(self, from_state: ValuationPhase, to_state: ValuationPhase,
                          state: IndustryState, verifications: List[VerificationResult],
                          valuation: ValuationAnalysis) -> StateTransition:
        verified_types = [r.hypothesis_type for r in verifications if not r.is_veto]
        reason_map = {
            ValuationPhase.S1_DEMAND_ACCEL: f"需求增速加速 +{(state.signals.demand_growth_acceleration or 0):.1f}pp",
            ValuationPhase.S2_BOTTLENECK: "供给瓶颈假设通过验证",
            ValuationPhase.S3_PROFIT_MATERIALIZE: "利润率与现金流拐点同时验证通过",
            ValuationPhase.S4_REVALUATION_CANDIDATE:
                f"利润跃迁确认且预期差 +{valuation.expectation_gap:.1f}%",
            ValuationPhase.S0_CYCLICAL: "核心信号减弱，回归周期状态",
        }
        return StateTransition(
            from_state=from_state,
            to_state=to_state,
            timestamp=time.time(),
            reason=reason_map.get(to_state, "状态转换"),
            triggered_by=verified_types,
        )

    # ---- 序列化 ----
    def to_dict(self) -> Dict:
        return {
            "current_state": self._current.value,
            "current_state_name": self._current.display_name,
            "is_early_stage": self._current.is_early_stage,
            "is_key_stage": self._current.is_key_stage,
            "transition_count": len(self._history),
            "history": [t.to_dict() for t in self._history],
        }
