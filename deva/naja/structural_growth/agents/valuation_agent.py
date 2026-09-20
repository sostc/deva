"""Valuation Agent - 估值分析者

职责：
- 基于已验证的假设，构建利润情景（周期 vs 结构性成长）
- 估算市场预期差（真实产业状态 vs 市场定价隐含的预期）
- 输出研究建议（不是买卖信号）

核心原则：
- 不输出"综合评分 85 分"这类黑箱数字
- 每个情景的假设必须透明可审计
- 最终寻找：真实产业状态向上变化，但市场预期上修速度未跟上的标的
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from ..industry_state import IndustryState
from .discovery_agent import GrowthHypothesis, HypothesisType
from .verification_agent import VerificationResult, VerificationVerdict


class ScenarioType(Enum):
    """估值情景类型"""
    CYCLICAL = "cyclical"           # 周期情景（利润均值回归）
    BASE = "base"                   # 基准情景（当前趋势延续）
    STRUCTURAL = "structural"       # 结构性成长情景（利润跃迁可持续）


@dataclass
class ValuationScenario:
    """单个估值情景"""
    type: ScenarioType
    name: str
    description: str
    # 利润率假设
    margin_current: float = 0.0             # 当前毛利率 (%)
    margin_assumed: float = 0.0             # 该情景下的稳态毛利率 (%)
    margin_change_pp: float = 0.0           # 相对当前的变化 (pp)
    # 利润增速假设
    profit_growth_rate: float = 0.0         # 未来 4-8 季度利润复合增速 (%)
    # 估值倍数假设
    implied_pe: float = 0.0                 # 隐含 PE
    # 关键假设（可审计）
    assumptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "type": self.type.value if isinstance(self.type, ScenarioType) else self.type,
            "name": self.name,
            "description": self.description,
            "margin_current": float(self.margin_current),
            "margin_assumed": float(self.margin_assumed),
            "margin_change_pp": float(self.margin_change_pp),
            "profit_growth_rate": float(self.profit_growth_rate),
            "implied_pe": float(self.implied_pe),
            "assumptions": list(self.assumptions),
        }


@dataclass
class ValuationAnalysis:
    """估值分析结果"""
    industry_id: str
    industry_name: str
    scenarios: List[ValuationScenario] = field(default_factory=list)
    expectation_gap: float = 0.0            # 预期差：结构性成长情景相对市场隐含预期的上修空间 (%)
    expectation_gap_signal: str = ""        # 预期差定性判断
    recommendation: str = ""                # 研究建议
    key_uncertainties: List[str] = field(default_factory=list)
    verified_hypotheses: List[str] = field(default_factory=list)  # 被纳入分析的已验证假设类型
    vetoed_hypotheses: List[str] = field(default_factory=list)    # 被否决的假设类型

    def to_dict(self) -> Dict:
        return {
            "industry_id": self.industry_id,
            "industry_name": self.industry_name,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "expectation_gap_pct": float(self.expectation_gap),
            "expectation_gap_signal": self.expectation_gap_signal,
            "recommendation": self.recommendation,
            "key_uncertainties": list(self.key_uncertainties),
            "verified_hypotheses": list(self.verified_hypotheses),
            "vetoed_hypotheses": list(self.vetoed_hypotheses),
        }


class ValuationAgent:
    """估值分析者 Agent：构建情景 + 估算预期差"""

    # 结构性成长情景下的稳态利润率上浮上限（避免过度乐观）
    MAX_STRUCTURAL_MARGIN_UPLIFT_PP = 20.0
    # 周期情景下利润率回归幅度
    CYCLICAL_MEAN_REVERSION = 0.6  # 假设 60% 的利润改善会回吐

    def __init__(self, max_uplift_pp: float = None, mean_reversion: float = None):
        if max_uplift_pp is not None:
            self.MAX_STRUCTURAL_MARGIN_UPLIFT_PP = max_uplift_pp
        if mean_reversion is not None:
            self.CYCLICAL_MEAN_REVERSION = mean_reversion

    # ---- 主入口 ----
    def analyze(self, state: IndustryState, verification_results: List[VerificationResult]) -> ValuationAnalysis:
        """基于验证结果做估值情景分析"""
        state.recompute_signals()

        # 分离已验证 vs 被否决
        verified = [r for r in verification_results if not r.is_veto]
        vetoed = [r for r in verification_results if r.is_veto]

        verified_types = [r.hypothesis_type for r in verified]
        vetoed_types = [r.hypothesis_type for r in vetoed]

        # 当前利润率（取 profit 维度最新值）
        current_margin = state.profit.current_value or 0.0
        history_margins = [p.value for p in state.profit.history]
        base_margin = history_margins[0] if history_margins else current_margin  # 最早值作为周期中枢参考

        # 已验证假设的平均置信度
        avg_conf = sum(r.confidence for r in verified) / len(verified) if verified else 0.0

        # 构建三个情景
        scenarios = self._build_scenarios(state, current_margin, base_margin, verified, avg_conf)

        # 计算预期差
        gap, signal = self._compute_expectation_gap(scenarios, verified)

        # 研究建议
        recommendation = self._form_recommendation(verified, gap, signal)

        # 关键不确定性
        uncertainties = self._identify_uncertainties(state, verified, vetoed)

        return ValuationAnalysis(
            industry_id=state.industry_id,
            industry_name=state.name,
            scenarios=scenarios,
            expectation_gap=round(gap, 2),
            expectation_gap_signal=signal,
            recommendation=recommendation,
            key_uncertainties=uncertainties,
            verified_hypotheses=verified_types,
            vetoed_hypotheses=vetoed_types,
        )

    # ---- 情景构建 ----
    def _build_scenarios(self, state, current_margin, base_margin,
                         verified, avg_conf) -> List[ValuationScenario]:
        scenarios: List[ValuationScenario] = []

        # 利润改善幅度（当前 vs 最早值）
        margin_uplift = current_margin - base_margin

        # 1. 周期情景：利润改善大部分回吐
        cyclical_margin = base_margin + margin_uplift * (1 - self.CYCLICAL_MEAN_REVERSION)
        cyclical_growth = self._estimate_growth(state, cyclical_margin, base_margin, scenario="cyclical")
        scenarios.append(ValuationScenario(
            type=ScenarioType.CYCLICAL,
            name="周期情景",
            description="假设利润率改善不可持续，大部分回吐至历史中枢，市场按周期股低估值定价。",
            margin_current=current_margin,
            margin_assumed=round(cyclical_margin, 2),
            margin_change_pp=round(cyclical_margin - current_margin, 2),
            profit_growth_rate=round(cyclical_growth, 2),
            implied_pe=self._cyclical_pe(cyclical_growth),
            assumptions=[
                f"利润率回吐 {self.CYCLICAL_MEAN_REVERSION*100:.0f}% 的改善幅度",
                f"稳态利润率回归至 {cyclical_margin:.1f}%",
                "市场按周期股给予低估值倍数",
            ],
        ))

        # 2. 基准情景：当前趋势线性外推
        base_assumed = current_margin
        base_growth = self._estimate_growth(state, base_assumed, base_margin, scenario="base")
        scenarios.append(ValuationScenario(
            type=ScenarioType.BASE,
            name="基准情景",
            description="假设当前利润率水平维持，趋势按近期增速延续。",
            margin_current=current_margin,
            margin_assumed=round(base_assumed, 2),
            margin_change_pp=0.0,
            profit_growth_rate=round(base_growth, 2),
            implied_pe=self._base_pe(base_growth),
            assumptions=[
                f"利润率维持在 {base_assumed:.1f}%",
                "增速按最近一期延续",
                "估值倍数维持当前水平",
            ],
        ))

        # 3. 结构性成长情景：利润跃迁可持续，利润率不回吐并可能小幅上修
        # 结构性 = 当前利润率 + 额外上修（受置信度调节，有上限）
        extra_uplift = min(margin_uplift * avg_conf * 0.3, self.MAX_STRUCTURAL_MARGIN_UPLIFT_PP)
        structural_margin = current_margin + extra_uplift
        structural_growth = self._estimate_growth(state, structural_margin, base_margin, scenario="structural")
        scenarios.append(ValuationScenario(
            type=ScenarioType.STRUCTURAL,
            name="结构性成长情景",
            description="已验证的利润跃迁假设成立，利润率改善可持续，市场从周期估值切换至成长估值。",
            margin_current=current_margin,
            margin_assumed=round(structural_margin, 2),
            margin_change_pp=round(structural_margin - current_margin, 2),
            profit_growth_rate=round(structural_growth, 2),
            implied_pe=self._structural_pe(structural_growth),
            assumptions=[
                f"已验证 {len(verified)} 个假设，平均置信度 {avg_conf:.2f}",
                f"利润率稳态上修至 {structural_margin:.1f}%",
                "市场给予成长股估值溢价",
            ],
        ))

        return scenarios

    def _estimate_growth(self, state, assumed_margin, base_margin, scenario: str) -> float:
        """估算未来 4-8 季度利润复合增速"""
        demand_accel = state.signals.demand_growth_acceleration or 0.0
        price_accel = state.signals.price_change_acceleration or 0.0
        margin_change = assumed_margin - base_margin

        if scenario == "cyclical":
            # 周期情景：增速回落
            return max(0.0, (demand_accel + price_accel) * 0.3)
        elif scenario == "base":
            return max(0.0, (demand_accel + price_accel) * 0.5)
        else:  # structural
            # 结构性：需求 + 价格 + 利润率改善共同驱动
            return max(0.0, demand_accel + price_accel + margin_change * 0.5)

    def _cyclical_pe(self, growth: float) -> float:
        return round(max(8.0, 10.0 + growth * 0.1), 1)

    def _base_pe(self, growth: float) -> float:
        return round(max(10.0, 15.0 + growth * 0.15), 1)

    def _structural_pe(self, growth: float) -> float:
        return round(max(15.0, 20.0 + growth * 0.25), 1)

    # ---- 预期差 ----
    def _compute_expectation_gap(self, scenarios, verified) -> tuple:
        """计算结构性成长情景相对市场隐含预期的上修空间

        近似方法：
        - 市场隐含预期 ≈ 周期情景与基准情景之间（偏周期，因为市场通常滞后）
        - 预期差 = 结构性情景利润增速 - 市场隐含增速
        """
        cyclical = next(s for s in scenarios if s.type == ScenarioType.CYCLICAL)
        base = next(s for s in scenarios if s.type == ScenarioType.BASE)
        structural = next(s for s in scenarios if s.type == ScenarioType.STRUCTURAL)

        # 市场隐含：偏周期，权重 0.6 周期 + 0.4 基准
        market_implied_growth = cyclical.profit_growth_rate * 0.6 + base.profit_growth_rate * 0.4
        gap = structural.profit_growth_rate - market_implied_growth

        if gap > 10:
            signal = "显著正向预期差"
        elif gap > 3:
            signal = "正向预期差"
        elif gap > -3:
            signal = "预期差不明显"
        else:
            signal = "负向预期差（市场预期已偏高）"

        return gap, signal

    # ---- 研究建议 ----
    def _form_recommendation(self, verified, gap, signal) -> str:
        if not verified:
            return "核心假设均被否决，建议暂不将该行业纳入结构性成长观察池。"
        n_confirmed = sum(1 for r in verified if r.verdict == VerificationVerdict.CONFIRMED)
        if n_confirmed >= 2 and gap > 3:
            return f"建议重点研究：{len(verified)} 个假设通过验证（其中 {n_confirmed} 个确认），{signal}，存在估值重估潜力。"
        if gap > 3:
            return f"建议持续跟踪：{len(verified)} 个假设通过验证，{signal}，但确认度不足，需补充证据。"
        return f"建议观察：{len(verified)} 个假设通过验证，但{signal}，暂不具备估值重估条件。"

    # ---- 不确定性 ----
    def _identify_uncertainties(self, state, verified, vetoed) -> List[str]:
        uncertainties = []
        # 供给数据缺失
        if state.supply.current_value is None:
            uncertainties.append("缺少供给端数据，无法确认瓶颈持续性")
        # 现金流缺失
        if state.cashflow.current_value is None:
            uncertainties.append("缺少自由现金流数据，无法验证利润质量")
        # 库存缺失
        if state.inventory.current_value is None:
            uncertainties.append("缺少库存数据，无法验证供需紧张程度")
        # 被否决的假设
        for r in vetoed:
            uncertainties.append(f"假设 [{r.hypothesis_type}] 被否决，需重新评估")
        return uncertainties
