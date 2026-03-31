"""SupplyChainValuationEngine - 供应链综合估值引擎

整合多维度数据源，对供应链中的公司进行综合估值分析：
1. 供应链位置（瓶颈效应、替代难度）
2. 叙事热度（新闻、社交媒体关注度）
3. 基本面数据（营收、利润、增长）
4. 认知数据（Manas风险评分、反思洞察）
5. 市场数据（价格变化、成交量、估值指标）
6. 宏观算力需求（TOKEN消耗增长作为AI需求代理）

输出：
- 估值评分 (0-100)
- 低估/合理/高估 分类
- 投资亮点和风险提示
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ValuationLevel(Enum):
    """估值等级"""
    SEVERELY_UNDERVALUED = "严重低估"
    UNDERVALUED = "低估"
    FAIR = "合理"
    OVERVALUED = "高估"
    SEVERELY_OVERVALUED = "严重高估"


@dataclass
class FundamentalMetrics:
    """基本面指标"""
    revenue_growth: float = 0.0
    profit_margin: float = 0.0
    pe_ratio: float = 0.0
    pb_ratio: float = 0.0
    market_cap: float = 0.0
    revenue: float = 0.0
    profit: float = 0.0


@dataclass
class NarrativeMetrics:
    """叙事热度指标"""
    narrative_importance: float = 1.0
    heat_level: float = 0.0
    sentiment_score: float = 0.5
    momentum: float = 0.0


@dataclass
class SupplyChainMetrics:
    """供应链位置指标"""
    is_bottleneck: bool = False
    upstream_count: int = 0
    downstream_count: int = 0
    replaceability: float = 1.0
    concentration_risk: float = 0.0


@dataclass
class ValuationResult:
    """估值结果"""
    stock_code: str
    stock_name: str
    valuation_score: float
    valuation_level: ValuationLevel

    fundamental_score: float = 0.0
    narrative_score: float = 0.0
    supply_chain_score: float = 0.0
    momentum_score: float = 0.0

    fundamentals: FundamentalMetrics = None
    narrative: NarrativeMetrics = None
    supply_chain: SupplyChainMetrics = None

    upside: float = 0.0
    risk_factors: List[str] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)

    recommendation: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "valuation_score": self.valuation_score,
            "valuation_level": self.valuation_level.value if isinstance(self.valuation_level, ValuationLevel) else self.valuation_level,
            "fundamental_score": self.fundamental_score,
            "narrative_score": self.narrative_score,
            "supply_chain_score": self.supply_chain_score,
            "momentum_score": self.momentum_score,
            "upside": self.upside,
            "risk_factors": self.risk_factors,
            "highlights": self.highlights,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
        }


from enum import Enum


class SupplyChainValuationEngine:
    """
    供应链综合估值引擎

    通过整合供应链关系、叙事热度、基本面、认知评分等多维度数据，
    计算每家公司的综合估值评分，识别低估/高估机会。
    """

    def __init__(self):
        self._linker = None
        self._graph = None
        self._valuation_cache: Dict[str, ValuationResult] = {}
        self._last_update: float = 0.0
        self._update_interval: float = 300.0

    def _get_linker(self):
        """获取叙事-供应链联动器"""
        if self._linker is None:
            try:
                from deva.naja.cognition import get_supply_chain_linker
                self._linker = get_supply_chain_linker()
            except ImportError:
                pass
        return self._linker

    def _get_graph(self):
        """获取供应链知识图谱"""
        if self._graph is None:
            try:
                from deva.naja.bandit import get_supply_chain_graph
                self._graph = get_supply_chain_graph()
            except ImportError:
                pass
        return self._graph

    def analyze_stock(self, stock_code: str) -> Optional[ValuationResult]:
        """
        分析单只股票的综合估值

        Args:
            stock_code: 股票代码

        Returns:
            估值结果
        """
        graph = self._get_graph()
        linker = self._get_linker()
        if not graph:
            return None

        node = graph.get_stock_node(stock_code)
        if not node:
            return None

        fundamental_score = self._calc_fundamental_score(stock_code, node)
        narrative_score = self._calc_narrative_score(stock_code, linker)
        supply_chain_score = self._calc_supply_chain_score(stock_code, graph)
        momentum_score = self._calc_momentum_score(stock_code)

        total_score = (
            fundamental_score * 0.35 +
            narrative_score * 0.25 +
            supply_chain_score * 0.25 +
            momentum_score * 0.15
        )

        if total_score >= 75:
            level = ValuationLevel.SEVERELY_UNDERVALUED
        elif total_score >= 60:
            level = ValuationLevel.UNDERVALUED
        elif total_score >= 45:
            level = ValuationLevel.FAIR
        elif total_score >= 30:
            level = ValuationLevel.OVERVALUED
        else:
            level = ValuationLevel.SEVERELY_OVERVALUED

        upside = self._calc_upside_potential(total_score, supply_chain_score, narrative_score)

        result = ValuationResult(
            stock_code=stock_code,
            stock_name=node.name,
            valuation_score=total_score,
            valuation_level=level,
            fundamental_score=fundamental_score,
            narrative_score=narrative_score,
            supply_chain_score=supply_chain_score,
            momentum_score=momentum_score,
            upside=upside,
            confidence=self._calc_confidence(supply_chain_score, narrative_score),
        )

        result.risk_factors = self._identify_risk_factors(stock_code, supply_chain_score, narrative_score)
        result.highlights = self._identify_highlights(stock_code, supply_chain_score, narrative_score)
        result.recommendation = self._generate_recommendation(result)

        self._valuation_cache[stock_code] = result
        return result

    def _calc_fundamental_score(self, stock_code: str, node) -> float:
        """计算基本面评分（整合真实市场数据）"""
        score = 50.0

        try:
            from deva.naja.bandit import get_fundamental_data_fetcher
            fetcher = get_fundamental_data_fetcher()
            fundamental = fetcher.get_fundamental(stock_code)

            if fundamental and fundamental.is_valid:
                if fundamental.pe_ratio > 0:
                    if fundamental.pe_ratio < 20:
                        score += 20.0
                    elif fundamental.pe_ratio < 40:
                        score += 10.0
                    elif fundamental.pe_ratio > 80:
                        score -= 15.0

                if fundamental.change_pct > 5:
                    score += 10.0
                elif fundamental.change_pct > 0:
                    score += 5.0
                elif fundamental.change_pct < -5:
                    score -= 10.0

                distance_high = fundamental.get_distance_from_52w_high()
                if distance_high < -30:
                    score += 15.0
                elif distance_high < -20:
                    score += 10.0

                if fundamental.market_cap > 0:
                    if fundamental.market_cap > 1000000000000:
                        score += 10.0
                    elif fundamental.market_cap > 100000000000:
                        score += 5.0
        except Exception as e:
            logger.debug(f"[ValuationEngine] 获取基本面数据失败: {e}")

        if node.metadata.get("market") == "A":
            score += 10.0

        if node.sector in ["ai_chip", "semiconductor", "ai_infrastructure"]:
            score += 15.0

        if node.metadata.get("description"):
            desc = node.metadata.get("description", "").lower()
            if "替代" in desc or "国产" in desc:
                score += 10.0

        return min(100.0, max(0.0, score))

    def _calc_narrative_score(self, stock_code: str, linker) -> float:
        """计算叙事热度评分"""
        if not linker:
            return 50.0

        narratives = linker.get_narratives_by_stock(stock_code)
        if not narratives:
            return 50.0

        total_importance = 0.0
        for narrative in narratives:
            weighted_stocks = linker.get_related_stocks_with_weight(narrative)
            if weighted_stocks:
                for code, weight in weighted_stocks:
                    if code == stock_code:
                        total_importance += weight
                        break

        score = min(100.0, 50.0 + total_importance * 10.0)
        return score

    def _calc_supply_chain_score(self, stock_code: str, graph) -> float:
        """计算供应链位置评分"""
        node = graph.get_stock_node(stock_code)
        if not node:
            return 50.0

        score = 50.0

        bottlenecks = graph.get_bottleneck_nodes(stock_code)
        if bottlenecks:
            score += 20.0

        risk_report = graph.analyze_supply_chain_risk(stock_code)
        if risk_report:
            if risk_report.upstream_risks:
                score += 10.0
            if risk_report.bottleneck_risks:
                score += 10.0

        upstream = graph.get_upstream_companies(stock_code)
        downstream = graph.get_downstream_companies(stock_code)

        if len(upstream) > 3:
            score += 5.0
        if len(downstream) > 3:
            score += 5.0

        if node.metadata.get("market") == "A":
            score += 5.0

        return min(100.0, score)

    def _calc_momentum_score(self, stock_code: str) -> float:
        """计算动量评分"""
        score = 50.0

        try:
            from deva.naja.bandit import get_us_stock_price_manager
            price_mgr = get_us_stock_price_manager()
            if price_mgr:
                history = price_mgr.get_price_history(stock_code, days=30)
                if len(history) >= 5:
                    recent_change = (history[-1] - history[0]) / history[0] * 100
                    if recent_change > 10:
                        score += 15.0
                    elif recent_change > 0:
                        score += 10.0
                    elif recent_change < -10:
                        score -= 10.0
                    else:
                        score -= 5.0
        except Exception:
            pass

        try:
            from deva.naja.bandit import get_market_observer
            observer = get_market_observer()
            if observer and hasattr(observer, '_price_cache'):
                if stock_code in observer._price_cache:
                    score += 10.0
        except Exception:
            pass

        return min(100.0, max(0.0, score))

    def _calc_upside_potential(self, valuation_score: float, supply_chain_score: float, narrative_score: float) -> float:
        """计算上涨潜力"""
        base_upside = (100 - valuation_score) * 0.5

        if supply_chain_score > 70:
            base_upside *= 1.2

        if narrative_score > 70:
            base_upside *= 1.1

        return round(base_upside, 1)

    def _calc_confidence(self, supply_chain_score: float, narrative_score: float) -> float:
        """计算置信度"""
        base = 0.5

        if supply_chain_score > 60:
            base += 0.2
        if narrative_score > 60:
            base += 0.2

        return min(1.0, base)

    def _identify_risk_factors(self, stock_code: str, supply_chain_score: float, narrative_score: float) -> List[str]:
        """识别风险因素"""
        risks = []
        graph = self._get_graph()

        risk_report = graph.analyze_supply_chain_risk(stock_code) if graph else None
        if risk_report:
            for risk in risk_report.upstream_risks:
                risks.append(f"上游风险: {risk.node_name}")
            for risk in risk_report.bottleneck_risks:
                risks.append(f"瓶颈风险: {risk.node_name}")

        if supply_chain_score < 40:
            risks.append("供应链位置较弱，可替代性高")

        if narrative_score > 80:
            risks.append("叙事热度极高，可能存在泡沫")

        if risk_report and risk_report.overall_risk_level == "HIGH":
            risks.append("整体供应链风险等级高")

        return risks[:3]

    def _identify_highlights(self, stock_code: str, supply_chain_score: float, narrative_score: float) -> List[str]:
        """识别亮点"""
        highlights = []
        graph = self._get_graph()

        if supply_chain_score > 70:
            highlights.append("供应链关键节点，议价能力强")

        if narrative_score > 60:
            highlights.append("叙事热度支撑，资本关注")

        risk_report = graph.analyze_supply_chain_risk(stock_code) if graph else None
        if risk_report:
            if not risk_report.upstream_risks:
                highlights.append("供应链稳定，无明显上游风险")

        node = graph.get_stock_node(stock_code) if graph else None
        if node and node.metadata.get("market") == "A":
            highlights.append("A 股市场，国产替代受益")

        return highlights[:3]

    def _generate_recommendation(self, result: ValuationResult) -> str:
        """生成投资建议"""
        if result.valuation_level in [ValuationLevel.SEVERELY_UNDERVALUED, ValuationLevel.UNDERVALUED]:
            if result.upside > 30:
                return "强烈推荐买入"
            elif result.upside > 15:
                return "建议关注"
            else:
                return "估值偏低，谨慎观望"
        elif result.valuation_level == ValuationLevel.FAIR:
            return "估值合理，可观望"
        else:
            return "估值偏高，注意风险"

    def analyze_all_stocks(self) -> Dict[str, ValuationResult]:
        """分析所有供应链中的股票"""
        graph = self._get_graph()
        if not graph:
            return {}

        results = {}
        for node in graph._nodes.values():
            if node.type.value == "company" and node.stock_code:
                result = self.analyze_stock(node.stock_code)
                if result:
                    results[node.stock_code] = result

        self._last_update = datetime.now().timestamp()
        return results

    def get_top_undervalued(self, limit: int = 5) -> List[ValuationResult]:
        """获取最被低估的股票"""
        all_results = self.analyze_all_stocks()
        undervalued = [
            r for r in all_results.values()
            if r.valuation_level in [ValuationLevel.SEVERELY_UNDERVALUED, ValuationLevel.UNDERVALUED]
        ]
        undervalued.sort(key=lambda x: x.valuation_score)
        return undervalued[:limit]

    def get_top_overvalued(self, limit: int = 5) -> List[ValuationResult]:
        """获取最被高估的股票"""
        all_results = self.analyze_all_stocks()
        overvalued = [
            r for r in all_results.values()
            if r.valuation_level in [ValuationLevel.SEVERELY_OVERVALUED, ValuationLevel.OVERVALUED]
        ]
        overvalued.sort(key=lambda x: x.valuation_score, reverse=True)
        return overvalued[:limit]

    def get_valuation_summary(self) -> Dict:
        """获取估值摘要"""
        all_results = self.analyze_all_stocks()

        undervalued = self.get_top_undervalued(3)
        overvalued = self.get_top_overvalued(3)

        return {
            "total_stocks": len(all_results),
            "undervalued_count": len([r for r in all_results.values() if r.valuation_level in [ValuationLevel.SEVERELY_UNDERVALUED, ValuationLevel.UNDERVALUED]]),
            "fair_count": len([r for r in all_results.values() if r.valuation_level == ValuationLevel.FAIR]),
            "overvalued_count": len([r for r in all_results.values() if r.valuation_level in [ValuationLevel.SEVERELY_OVERVALUED, ValuationLevel.OVERVALUED]]),
            "top_undervalued": [r.to_dict() for r in undervalued],
            "top_overvalued": [r.to_dict() for r in overvalued],
            "last_update": datetime.fromtimestamp(self._last_update).strftime("%Y-%m-%d %H:%M") if self._last_update else "从未更新",
        }


_valuation_engine: Optional[SupplyChainValuationEngine] = None


def get_supply_chain_valuation_engine() -> SupplyChainValuationEngine:
    """获取供应链估值引擎（单例）"""
    global _valuation_engine
    if _valuation_engine is None:
        _valuation_engine = SupplyChainValuationEngine()
    return _valuation_engine
