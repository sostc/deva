"""Discovery Agent - 发现者

职责：
- 从产业状态卡的二阶导信号中发现异常变化
- 提出"利润跃迁"候选假设
- 不做结论，只输出带初始置信度的候选假设

规则引擎（纯 Python，无 LLM）：
1. 需求增速显著加速 → DEMAND_SURGE
2. 需求加速但供给未跟上 → SUPPLY_BOTTLENECK
3. 价格与毛利率同时加速改善 → PRICING_POWER
4. 毛利率改善加速超过阈值 → MARGIN_EXPANSION
5. 现金流转化率转正且利润改善 → CASHFLOW_INFLECTION
6. 以上多条同时成立 → PROFIT_TRANSITION（利润跃迁综合假设）
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from ..industry_state import IndustryState, FactorTrend


class HypothesisType(Enum):
    """假设类型"""
    DEMAND_SURGE = "demand_surge"                   # 需求激增
    SUPPLY_BOTTLENECK = "supply_bottleneck"         # 供给瓶颈
    PRICING_POWER = "pricing_power"                 # 议价能力提升
    MARGIN_EXPANSION = "margin_expansion"           # 利润率扩张
    CASHFLOW_INFLECTION = "cashflow_inflection"     # 现金流拐点
    PROFIT_TRANSITION = "profit_transition"         # 利润跃迁（综合）


@dataclass
class GrowthHypothesis:
    """利润跃迁候选假设"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    industry_id: str = ""
    type: HypothesisType = HypothesisType.PROFIT_TRANSITION
    title: str = ""
    description: str = ""
    confidence: float = 0.0                       # 初始置信度 0-1（发现者给出）
    supporting_signals: List[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "industry_id": self.industry_id,
            "type": self.type.value if isinstance(self.type, HypothesisType) else self.type,
            "title": self.title,
            "description": self.description,
            "confidence": float(self.confidence),
            "supporting_signals": list(self.supporting_signals),
            "rationale": self.rationale,
        }


class DiscoveryAgent:
    """发现者 Agent：扫描二阶导信号，提出候选假设"""

    # 阈值（百分点）
    DEMAND_ACCEL_THRESHOLD = 5.0      # 需求加速超过 5pp 视为激增
    MARGIN_ACCEL_THRESHOLD = 3.0      # 毛利率加速超过 3pp 视为显著扩张
    PRICE_ACCEL_THRESHOLD = 2.0       # 价格加速超过 2pp 视为有议价权

    def __init__(self, demand_accel_pp: float = None, margin_accel_pp: float = None,
                 price_accel_pp: float = None):
        if demand_accel_pp is not None:
            self.DEMAND_ACCEL_THRESHOLD = demand_accel_pp
        if margin_accel_pp is not None:
            self.MARGIN_ACCEL_THRESHOLD = margin_accel_pp
        if price_accel_pp is not None:
            self.PRICE_ACCEL_THRESHOLD = price_accel_pp

    # ---- 主入口 ----
    def discover(self, state: IndustryState) -> List[GrowthHypothesis]:
        """扫描产业状态，输出候选假设列表（按置信度降序）"""
        state.recompute_signals()
        hypotheses: List[GrowthHypothesis] = []

        sig = state.signals
        factors = state.all_factors()

        # 1. 需求激增
        if sig.demand_growth_acceleration is not None and sig.demand_growth_acceleration > self.DEMAND_ACCEL_THRESHOLD:
            hypotheses.append(self._demand_surge(state, sig))

        # 2. 供给瓶颈：需求加速且供给未同步加速
        demand_accel = sig.demand_growth_acceleration or 0.0
        supply_accel = sig.supply_growth_acceleration
        if demand_accel > 0 and (supply_accel is None or supply_accel <= 0):
            hypotheses.append(self._supply_bottleneck(state, sig))

        # 3. 议价能力：价格加速 + 毛利率加速
        price_accel = sig.price_change_acceleration or 0.0
        margin_accel = sig.margin_improvement_acceleration or 0.0
        if price_accel > self.PRICE_ACCEL_THRESHOLD and margin_accel > 0:
            hypotheses.append(self._pricing_power(state, sig))

        # 4. 利润率扩张
        if margin_accel > self.MARGIN_ACCEL_THRESHOLD:
            hypotheses.append(self._margin_expansion(state, sig))

        # 5. 现金流拐点
        cf_change = sig.cashflow_conversion_change
        profit_trend = factors["profit"].trend()
        if cf_change is not None and cf_change > 0 and profit_trend != FactorTrend.DECELERATING:
            hypotheses.append(self._cashflow_inflection(state, sig))

        # 6. 利润跃迁综合假设：至少 2 条以上子假设成立
        sub_types = {h.type for h in hypotheses}
        if len(sub_types) >= 2:
            hypotheses.append(self._profit_transition(state, sig, list(sub_types)))

        # 按置信度降序
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses

    # ---- 各假设构造 ----
    def _demand_surge(self, state: IndustryState, sig) -> GrowthHypothesis:
        accel = sig.demand_growth_acceleration or 0.0
        conf = min(1.0, 0.4 + accel / 40.0)
        return GrowthHypothesis(
            industry_id=state.industry_id,
            type=HypothesisType.DEMAND_SURGE,
            title=f"{state.name}需求增速显著加速",
            description=f"需求增长率变化 +{accel:.1f}pp，可能存在需求超预期增长。",
            confidence=round(conf, 3),
            supporting_signals=["demand_growth_acceleration"],
            rationale=f"demand_growth_acceleration={accel:.2f}pp > {self.DEMAND_ACCEL_THRESHOLD}pp",
        )

    def _supply_bottleneck(self, state: IndustryState, sig) -> GrowthHypothesis:
        demand_accel = sig.demand_growth_acceleration or 0.0
        supply_accel = sig.supply_growth_acceleration
        gap = demand_accel - (supply_accel if supply_accel is not None else 0.0)
        conf = min(1.0, 0.3 + gap / 30.0)
        supply_txt = f"{supply_accel:.1f}pp" if supply_accel is not None else "无数据/持平"
        return GrowthHypothesis(
            industry_id=state.industry_id,
            type=HypothesisType.SUPPLY_BOTTLENECK,
            title=f"{state.name}供需缺口扩大，供给瓶颈形成",
            description=f"需求增速变化 +{demand_accel:.1f}pp，供给增速变化 {supply_txt}，供需缺口 +{gap:.1f}pp。",
            confidence=round(conf, 3),
            supporting_signals=["demand_growth_acceleration", "supply_growth_acceleration"],
            rationale=f"demand_accel({demand_accel:.2f}) > 0 且 supply_accel({supply_txt}) <= 0",
        )

    def _pricing_power(self, state: IndustryState, sig) -> GrowthHypothesis:
        price_accel = sig.price_change_acceleration or 0.0
        margin_accel = sig.margin_improvement_acceleration or 0.0
        conf = min(1.0, 0.4 + (price_accel + margin_accel) / 30.0)
        return GrowthHypothesis(
            industry_id=state.industry_id,
            type=HypothesisType.PRICING_POWER,
            title=f"{state.name}议价能力提升",
            description=f"价格增速变化 +{price_accel:.1f}pp，毛利率改善加速 +{margin_accel:.1f}pp，企业可能获得定价权。",
            confidence=round(conf, 3),
            supporting_signals=["price_change_acceleration", "margin_improvement_acceleration"],
            rationale=f"price_accel({price_accel:.2f}) > {self.PRICE_ACCEL_THRESHOLD} 且 margin_accel({margin_accel:.2f}) > 0",
        )

    def _margin_expansion(self, state: IndustryState, sig) -> GrowthHypothesis:
        margin_accel = sig.margin_improvement_acceleration or 0.0
        conf = min(1.0, 0.35 + margin_accel / 30.0)
        return GrowthHypothesis(
            industry_id=state.industry_id,
            type=HypothesisType.MARGIN_EXPANSION,
            title=f"{state.name}利润率加速扩张",
            description=f"毛利率改善加速度 +{margin_accel:.1f}pp，超过阈值 {self.MARGIN_ACCEL_THRESHOLD}pp。",
            confidence=round(conf, 3),
            supporting_signals=["margin_improvement_acceleration"],
            rationale=f"margin_accel({margin_accel:.2f}) > {self.MARGIN_ACCEL_THRESHOLD}pp",
        )

    def _cashflow_inflection(self, state: IndustryState, sig) -> GrowthHypothesis:
        cf = sig.cashflow_conversion_change or 0.0
        conf = min(1.0, 0.3 + cf / 20.0)
        return GrowthHypothesis(
            industry_id=state.industry_id,
            type=HypothesisType.CASHFLOW_INFLECTION,
            title=f"{state.name}自由现金流出现拐点",
            description=f"现金流转化率变化 +{cf:.1f}pp，且利润趋势未减速，利润开始转化为真实现金流。",
            confidence=round(conf, 3),
            supporting_signals=["cashflow_conversion_change", "margin_improvement_speed"],
            rationale=f"cashflow_conversion_change({cf:.2f}) > 0 且 profit trend 非减速",
        )

    def _profit_transition(self, state: IndustryState, sig, sub_types: List[HypothesisType]) -> GrowthHypothesis:
        # 综合置信度：子假设数量越多、单项越强，置信度越高
        sub_confs = []
        for h_type in sub_types:
            # 用对应信号强度估算
            if h_type == HypothesisType.DEMAND_SURGE:
                sub_confs.append(min(1.0, (sig.demand_growth_acceleration or 0) / 40.0))
            elif h_type == HypothesisType.SUPPLY_BOTTLENECK:
                gap = (sig.demand_growth_acceleration or 0) - (sig.supply_growth_acceleration or 0)
                sub_confs.append(min(1.0, gap / 30.0))
            elif h_type == HypothesisType.PRICING_POWER:
                sub_confs.append(min(1.0, ((sig.price_change_acceleration or 0) + (sig.margin_improvement_acceleration or 0)) / 30.0))
            elif h_type == HypothesisType.MARGIN_EXPANSION:
                sub_confs.append(min(1.0, (sig.margin_improvement_acceleration or 0) / 30.0))
            elif h_type == HypothesisType.CASHFLOW_INFLECTION:
                sub_confs.append(min(1.0, (sig.cashflow_conversion_change or 0) / 20.0))
        base = 0.4
        avg_sub = sum(sub_confs) / len(sub_confs) if sub_confs else 0.0
        conf = min(1.0, base + 0.15 * len(sub_types) + avg_sub * 0.3)
        sub_names = [t.value for t in sub_types]
        return GrowthHypothesis(
            industry_id=state.industry_id,
            type=HypothesisType.PROFIT_TRANSITION,
            title=f"{state.name}可能发生利润跃迁",
            description=f"多重信号共振：{', '.join(sub_names)}。行业可能从周期状态向结构性成长转变。",
            confidence=round(conf, 3),
            supporting_signals=sub_names,
            rationale=f"{len(sub_types)} 个子假设同时成立: {sub_names}",
        )
