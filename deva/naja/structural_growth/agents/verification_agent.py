"""Verification Agent - 验证者

职责：
- 主动寻找反面证据（反证）
- 对发现者提出的假设做跨因子一致性检验
- 有权否决假设（REFUTED = veto）

判决逻辑：
- REFUTED：强反证或跨因子矛盾 → 否决假设
- INCONCLUSIVE：证据不足/数据缺口 → 无法判断
- PARTIALLY_SUPPORTED：有支持但反证也存在或数据不全
- CONFIRMED：支持证据占优且跨因子一致

关键原则：验证者必须有权否决发现者，
防止系统变成自动确认偏见的机器。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from ..evidence import Evidence, EvidenceChain, EvidenceStatus
from ..industry_state import IndustryState, FactorTrend
from .discovery_agent import GrowthHypothesis, HypothesisType


class VerificationVerdict(Enum):
    """验证判决"""
    CONFIRMED = "confirmed"                   # 确认
    PARTIALLY_SUPPORTED = "partially_supported"  # 部分支持
    INCONCLUSIVE = "inconclusive"             # 证据不足
    REFUTED = "refuted"                       # 否决（veto）

    @property
    def is_veto(self) -> bool:
        return self == VerificationVerdict.REFUTED


@dataclass
class VerificationResult:
    """验证结果"""
    hypothesis_id: str
    hypothesis_type: str
    verdict: VerificationVerdict
    confidence: float = 0.0                   # 验证置信度 0-1
    support_score: float = 0.0                # 加权支持分
    support_ratio: float = 0.5                # 支持占比
    evidence_chain: EvidenceChain = field(default_factory=EvidenceChain)
    weakening_factors: List[str] = field(default_factory=list)   # 削弱因素
    data_gaps: List[str] = field(default_factory=list)           # 数据缺口
    cross_checks: List[Dict] = field(default_factory=list)       # 跨因子检验记录

    @property
    def is_veto(self) -> bool:
        return self.verdict.is_veto

    def to_dict(self) -> Dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_type": self.hypothesis_type,
            "verdict": self.verdict.value if isinstance(self.verdict, VerificationVerdict) else self.verdict,
            "is_veto": self.is_veto,
            "confidence": float(self.confidence),
            "support_score": float(self.support_score),
            "support_ratio": float(self.support_ratio),
            "evidence": self.evidence_chain.to_dict(),
            "weakening_factors": list(self.weakening_factors),
            "data_gaps": list(self.data_gaps),
            "cross_checks": self.cross_checks,
        }


class VerificationAgent:
    """验证者 Agent：收集正反证据 + 跨因子检验，可否决假设"""

    # 判决阈值
    CONFIRM_SUPPORT_RATIO = 0.70     # 支持占比 >= 70% 才考虑确认
    REFUTE_SUPPORT_RATIO = 0.40      # 支持占比 < 40% 触发否决评估
    STRONG_REFUTE_SCORE = -0.5       # 支持分 < -0.5 直接否决

    def __init__(self, confirm_ratio: float = None, refute_ratio: float = None,
                 strong_refute: float = None):
        if confirm_ratio is not None:
            self.CONFIRM_SUPPORT_RATIO = confirm_ratio
        if refute_ratio is not None:
            self.REFUTE_SUPPORT_RATIO = refute_ratio
        if strong_refute is not None:
            self.STRONG_REFUTE_SCORE = strong_refute

    # ---- 主入口 ----
    def verify(self, state: IndustryState, hypothesis: GrowthHypothesis) -> VerificationResult:
        """验证单条假设"""
        state.recompute_signals()
        chain = EvidenceChain(hypothesis_id=hypothesis.id)

        # 1. 收集显式证据
        self._collect_explicit_evidence(state, hypothesis, chain)

        # 2. 跨因子一致性检验（自动生成支持/反证）
        weakening, gaps, cross_checks = self._cross_factor_check(state, hypothesis, chain)

        # 3. 计算支持分
        support_score = chain.support_score()
        support_ratio = chain.support_ratio()

        # 4. 判决
        verdict, conf = self._adjudicate(hypothesis, chain, weakening, gaps, cross_checks)

        return VerificationResult(
            hypothesis_id=hypothesis.id,
            hypothesis_type=hypothesis.type.value if isinstance(hypothesis.type, HypothesisType) else str(hypothesis.type),
            verdict=verdict,
            confidence=round(conf, 3),
            support_score=round(support_score, 4),
            support_ratio=round(support_ratio, 4),
            evidence_chain=chain,
            weakening_factors=weakening,
            data_gaps=gaps,
            cross_checks=cross_checks,
        )

    def verify_many(self, state: IndustryState, hypotheses: List[GrowthHypothesis]) -> List[VerificationResult]:
        """批量验证，按假设置信度降序"""
        results = [self.verify(state, h) for h in hypotheses]
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    # ---- 证据收集 ----
    def _collect_explicit_evidence(self, state: IndustryState, hypothesis: GrowthHypothesis,
                                   chain: EvidenceChain) -> None:
        """收集状态卡上已有的显式证据"""
        relevant_dims = self._relevant_dimensions(hypothesis.type)
        for e in state.evidence:
            if not relevant_dims or e.dimension in relevant_dims or e.dimension == "":
                chain.add(e)
        for e in state.counter_evidence:
            if not relevant_dims or e.dimension in relevant_dims or e.dimension == "":
                chain.add(e)

    def _relevant_dimensions(self, h_type: HypothesisType) -> List[str]:
        mapping = {
            HypothesisType.DEMAND_SURGE: ["demand"],
            HypothesisType.SUPPLY_BOTTLENECK: ["demand", "supply", "inventory"],
            HypothesisType.PRICING_POWER: ["price", "profit"],
            HypothesisType.MARGIN_EXPANSION: ["profit", "cost"],
            HypothesisType.CASHFLOW_INFLECTION: ["cashflow", "profit"],
            HypothesisType.PROFIT_TRANSITION: [],  # 全部维度
        }
        return mapping.get(h_type, [])

    # ---- 跨因子一致性检验 ----
    def _cross_factor_check(self, state: IndustryState, hypothesis: GrowthHypothesis,
                            chain: EvidenceChain) -> tuple:
        """根据假设类型做跨因子检验，返回 (weakening, gaps, cross_checks)"""
        weakening: List[str] = []
        gaps: List[str] = []
        checks: List[Dict] = []

        sig = state.signals
        factors = state.all_factors()

        if hypothesis.type == HypothesisType.DEMAND_SURGE:
            checks.append(self._check_demand_surge(sig, factors, chain, weakening, gaps))

        elif hypothesis.type == HypothesisType.SUPPLY_BOTTLENECK:
            checks.append(self._check_supply_bottleneck(sig, factors, chain, weakening, gaps))

        elif hypothesis.type == HypothesisType.PRICING_POWER:
            checks.append(self._check_pricing_power(sig, factors, chain, weakening, gaps))

        elif hypothesis.type == HypothesisType.MARGIN_EXPANSION:
            checks.append(self._check_margin_expansion(sig, factors, chain, weakening, gaps))

        elif hypothesis.type == HypothesisType.CASHFLOW_INFLECTION:
            checks.append(self._check_cashflow_inflection(sig, factors, chain, weakening, gaps))

        elif hypothesis.type == HypothesisType.PROFIT_TRANSITION:
            # 综合假设：检查核心三因子（需求、价格、利润）是否同向
            checks.append(self._check_profit_transition(sig, factors, chain, weakening, gaps))

        return weakening, gaps, checks

    def _add_derived_evidence(self, chain: EvidenceChain, content: str, dimension: str,
                               status: EvidenceStatus, confidence: float, source: str = "cross_factor_check") -> None:
        chain.add(Evidence(
            content=content,
            source=source,
            dimension=dimension,
            status=status,
            confidence=confidence,
        ))

    def _check_demand_surge(self, sig, factors, chain, weakening, gaps) -> Dict:
        ok = sig.demand_growth_acceleration is not None and sig.demand_growth_acceleration > 0
        if ok:
            self._add_derived_evidence(chain, f"需求增速加速 +{sig.demand_growth_acceleration:.1f}pp",
                                       "demand", EvidenceStatus.SUPPORTING, 0.6)
        else:
            self._add_derived_evidence(chain, "需求增速未加速", "demand", EvidenceStatus.REFUTING, 0.7)
            weakening.append("需求增速未加速，假设基础不成立")
        return {"check": "demand_acceleration_positive", "passed": ok}

    def _check_supply_bottleneck(self, sig, factors, chain, weakening, gaps) -> Dict:
        demand_accel = sig.demand_growth_acceleration or 0.0
        supply_accel = sig.supply_growth_acceleration
        if supply_accel is None:
            gaps.append("缺少供给增速数据，无法确认瓶颈是否真实存在")
            self._add_derived_evidence(chain, "供给数据缺失，瓶颈假设未被证实",
                                       "supply", EvidenceStatus.NEUTRAL, 0.3)
            return {"check": "supply_data_available", "passed": False, "note": "supply data missing"}

        gap = demand_accel - supply_accel
        if supply_accel >= demand_accel:
            self._add_derived_evidence(chain,
                                       f"供给增速加速({supply_accel:.1f}pp) 不低于 需求({demand_accel:.1f}pp)，瓶颈不成立",
                                       "supply", EvidenceStatus.REFUTING, 0.8)
            weakening.append(f"供给增速({supply_accel:.1f}pp) >= 需求增速({demand_accel:.1f}pp)，不存在瓶颈")
            return {"check": "demand_outpaces_supply", "passed": False}

        self._add_derived_evidence(chain,
                                   f"需求加速({demand_accel:.1f}pp) > 供给加速({supply_accel:.1f}pp)，缺口 +{gap:.1f}pp",
                                   "supply", EvidenceStatus.SUPPORTING, 0.7)
        # 库存交叉验证：库存减少支持瓶颈
        inv = factors["inventory"]
        if inv.current_value is not None and inv.trend() == FactorTrend.DECELERATING:
            self._add_derived_evidence(chain, "库存下降，支持供需紧张判断",
                                       "inventory", EvidenceStatus.SUPPORTING, 0.5)
        return {"check": "demand_outpaces_supply", "passed": True}

    def _check_pricing_power(self, sig, factors, chain, weakening, gaps) -> Dict:
        price_accel = sig.price_change_acceleration
        margin_accel = sig.margin_improvement_acceleration
        if price_accel is None:
            gaps.append("缺少价格数据")
            return {"check": "price_and_margin", "passed": False, "note": "price missing"}
        if margin_accel is None:
            gaps.append("缺少利润率数据")
            return {"check": "price_and_margin", "passed": False, "note": "margin missing"}

        if price_accel > 0 and margin_accel > 0:
            self._add_derived_evidence(chain,
                                       f"价格加速(+{price_accel:.1f}pp) 且 毛利率加速(+{margin_accel:.1f}pp)，议价权成立",
                                       "price", EvidenceStatus.SUPPORTING, 0.7)
            return {"check": "price_up_and_margin_up", "passed": True}

        if price_accel > 0 and margin_accel <= 0:
            self._add_derived_evidence(chain,
                                       f"价格上涨但毛利率未改善(+{margin_accel:.1f}pp)，可能是成本压力而非议价权",
                                       "price", EvidenceStatus.REFUTING, 0.8)
            weakening.append("价格上涨但毛利不升，疑似成本推动而非定价权")
            return {"check": "price_up_and_margin_up", "passed": False}

        self._add_derived_evidence(chain, "价格与毛利率未同时改善", "price", EvidenceStatus.NEUTRAL, 0.4)
        return {"check": "price_up_and_margin_up", "passed": False}

    def _check_margin_expansion(self, sig, factors, chain, weakening, gaps) -> Dict:
        margin_accel = sig.margin_improvement_acceleration
        if margin_accel is None:
            gaps.append("缺少利润率数据")
            return {"check": "margin_acceleration", "passed": False}
        if margin_accel > 0:
            self._add_derived_evidence(chain, f"毛利率改善加速 +{margin_accel:.1f}pp",
                                       "profit", EvidenceStatus.SUPPORTING, 0.6)
            # 检查是否靠收入增长而非单纯成本削减
            demand_accel = sig.demand_growth_acceleration or 0.0
            if demand_accel <= 0:
                weakening.append("毛利率改善但需求未加速，可能来自成本削减而非需求拉动")
            return {"check": "margin_acceleration_positive", "passed": True}
        self._add_derived_evidence(chain, "毛利率未加速改善", "profit", EvidenceStatus.REFUTING, 0.7)
        weakening.append("毛利率未加速")
        return {"check": "margin_acceleration_positive", "passed": False}

    def _check_cashflow_inflection(self, sig, factors, chain, weakening, gaps) -> Dict:
        cf = sig.cashflow_conversion_change
        profit_accel = sig.margin_improvement_acceleration or 0.0
        if cf is None:
            gaps.append("缺少现金流数据")
            return {"check": "cashflow", "passed": False}
        if cf > 0 and profit_accel >= 0:
            self._add_derived_evidence(chain,
                                       f"现金流转化率改善 +{cf:.1f}pp 且利润未减速",
                                       "cashflow", EvidenceStatus.SUPPORTING, 0.7)
            return {"check": "cashflow_up_profit_stable", "passed": True}
        if profit_accel > 0 and cf <= 0:
            self._add_derived_evidence(chain,
                                       "利润改善但现金流未跟上，盈利质量存疑",
                                       "cashflow", EvidenceStatus.REFUTING, 0.7)
            weakening.append("利润增但现金流不增，盈利质量存疑")
            return {"check": "cashflow_up_profit_stable", "passed": False}
        self._add_derived_evidence(chain, "现金流与利润未同向改善", "cashflow", EvidenceStatus.NEUTRAL, 0.4)
        return {"check": "cashflow_up_profit_stable", "passed": False}

    def _check_profit_transition(self, sig, factors, chain, weakening, gaps) -> Dict:
        demand_accel = sig.demand_growth_acceleration or 0.0
        price_accel = sig.price_change_acceleration or 0.0
        margin_accel = sig.margin_improvement_acceleration or 0.0
        positives = sum(1 for v in [demand_accel, price_accel, margin_accel] if v > 0)
        if positives >= 2:
            self._add_derived_evidence(chain,
                                       f"需求/价格/利润三因子中 {positives} 项加速，支持利润跃迁",
                                       "profit", EvidenceStatus.SUPPORTING, 0.6)
            return {"check": "multi_factor_resonance", "passed": True, "positive_count": positives}
        weakening.append(f"仅 {positives} 个核心因子加速，共振不足")
        self._add_derived_evidence(chain, f"仅 {positives} 个核心因子加速", "profit", EvidenceStatus.REFUTING, 0.5)
        return {"check": "multi_factor_resonance", "passed": False, "positive_count": positives}

    # ---- 判决 ----
    def _adjudicate(self, hypothesis: GrowthHypothesis, chain: EvidenceChain,
                    weakening: List[str], gaps: List[str], cross_checks: List[Dict]) -> tuple:
        """根据证据链和跨因子检验给出判决"""
        support_score = chain.support_score()
        support_ratio = chain.support_ratio()
        n_evidence = chain.evidence_count()
        passed_checks = sum(1 for c in cross_checks if c.get("passed"))
        total_checks = len(cross_checks)

        # 1. 强反证直接否决
        if support_score < self.STRONG_REFUTE_SCORE:
            return VerificationVerdict.REFUTED, 0.8

        # 2. 跨因子检验全部失败 → 否决
        if total_checks > 0 and passed_checks == 0:
            return VerificationVerdict.REFUTED, 0.7

        # 3. 支持占比过低 → 否决
        if support_ratio < self.REFUTE_SUPPORT_RATIO and n_evidence >= 2:
            return VerificationVerdict.REFUTED, 0.6

        # 4. 数据缺口大且证据少 → 无法判断
        if len(gaps) >= 2 and n_evidence < 3:
            return VerificationVerdict.INCONCLUSIVE, 0.3

        # 5. 确认：高支持占比 + 跨因子多数通过
        if (support_ratio >= self.CONFIRM_SUPPORT_RATIO and
                support_score > 0 and
                (total_checks == 0 or passed_checks >= total_checks * 0.5)):
            conf = min(1.0, 0.5 + support_ratio * 0.3 + (passed_checks / max(total_checks, 1)) * 0.2)
            return VerificationVerdict.CONFIRMED, conf

        # 6. 部分支持
        if support_score > 0 or passed_checks > 0:
            conf = 0.3 + support_ratio * 0.3
            return VerificationVerdict.PARTIALLY_SUPPORTED, conf

        # 7. 兜底
        return VerificationVerdict.INCONCLUSIVE, 0.2
