"""
PreTasteSense - 预尝能力

在买入之前感知"味道"：这个股票好不好、值不值得买

核心能力：
1. PreTasteAnalyzer: 预尝分析器
2. OpportunityTaster: 机会品尝器
3. RiskTaster: 风险品尝器
4. CompositeTaster: 综合品尝器
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


class TasteQuality(Enum):
    """味道品质"""
    EXCELLENT = "excellent"       # 绝佳
    GOOD = "good"                # 不错
    MEDIUM = "medium"            # 一般
    BAD = "bad"                  # 不好
    TERRIBLE = "terrible"       # 糟糕


@dataclass
class PreTasteResult:
    """预尝结果"""
    quality: TasteQuality
    score: float                  # 综合评分 [0, 1]
    flavors: List[str]          # 味道描述
    risk_flavors: List[str]     # 风险味道
    opportunity: str            # 机会描述
    warning: str                 # 警告
    recommended_action: str     # 建议行动
    confidence: float           # 置信度


@dataclass
class FlavorProfile:
    """味道画像"""
    sweetness: float            # 甜度（上涨空间）
    bitterness: float           # 苦度（下跌风险）
    spiciness: float           # 辣度（波动风险）
    freshness: float           # 鲜度（动量）
    richness: float            # 醇度（基本面）
    sentiment: float = 0.5      # 情绪（新闻/叙事情绪）NEW


class MomentumTaster:
    """
    动量味道品尝器

    品尝股票的动量"味道"
    """

    def __init__(self):
        self._taste_history: Dict[str, List[float]] = {}

    def taste(
        self,
        symbol: str,
        price_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        品尝动量味道

        Returns:
            动量味道指标
        """
        price_changes = price_data.get("price_changes", [])
        if len(price_changes) < 3:
            return {"momentum_score": 0.5}

        recent_changes = price_changes[-5:] if len(price_changes) >= 5 else price_changes
        avg_change = sum(recent_changes) / len(recent_changes)
        change_trend = recent_changes[-1] - recent_changes[0] if len(recent_changes) > 1 else 0

        momentum_score = min(1.0, max(0.0, 0.5 + avg_change / 10 + change_trend / 20))

        if symbol not in self._taste_history:
            self._taste_history[symbol] = []
        self._taste_history[symbol].append(momentum_score)
        if len(self._taste_history[symbol]) > 50:
            self._taste_history[symbol].pop(0)

        return {
            "momentum_score": momentum_score,
            "avg_change": avg_change,
            "change_trend": change_trend
        }


class LiquidityTaster:
    """
    流动性味道品尝器

    品尝股票的流动性"味道"
    """

    def taste(
        self,
        symbol: str,
        volume_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        品尝流动性味道
        """
        volume = volume_data.get("volume", 0)
        amount = volume_data.get("amount", 0)
        price = volume_data.get("price", 10.0)

        if price <= 0 or volume <= 0:
            return {"liquidity_score": 0.5}

        avg_volume = volume_data.get("avg_volume", volume)
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

        turnover_rate = amount / (volume * price) if volume * price > 0 else 0

        liquidity_score = min(1.0, max(0.0, volume_ratio * 0.6 + turnover_rate * 0.4))

        return {
            "liquidity_score": liquidity_score,
            "volume_ratio": volume_ratio,
            "turnover_rate": turnover_rate
        }


class ValuationTaster:
    """
    估值味道品尝器

    品尝股票的估值"味道"
    """

    def taste(
        self,
        symbol: str,
        valuation_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        品尝估值味道
        """
        pe_ratio = valuation_data.get("pe_ratio", 15.0)
        pb_ratio = valuation_data.get("pb_ratio", 2.0)
        roe = valuation_data.get("roe", 0.1)
        growth = valuation_data.get("growth", 0.1)

        if pe_ratio <= 0 or pe_ratio > 100:
            pe_score = 0.5
        elif pe_ratio < 10:
            pe_score = 0.9
        elif pe_ratio < 20:
            pe_score = 0.7
        elif pe_ratio < 40:
            pe_score = 0.4
        else:
            pe_score = 0.2

        pb_ratio = valuation_data.get("pb_ratio", 2.0)
        if pb_ratio <= 0:
            pb_score = 0.5
        elif pb_ratio < 2:
            pb_score = 0.9
        elif pb_ratio < 5:
            pb_score = 0.7
        elif pb_ratio < 10:
            pb_score = 0.5
        elif pb_ratio < 15:
            pb_score = 0.25
        else:
            pb_score = max(0.0, 0.15 - (pb_ratio - 15) * 0.02)

        roe_score = min(1.0, max(0.0, roe * 5)) if roe > 0 else 0.3

        growth_score = min(1.0, max(0.0, growth * 3)) if growth > 0 else 0.3

        valuation_score = pe_score * 0.4 + pb_score * 0.3 + roe_score * 0.2 + growth_score * 0.1

        return {
            "valuation_score": valuation_score,
            "pe_score": pe_score,
            "pb_score": pb_score,
            "roe_score": roe_score,
            "growth_score": growth_score
        }


class RiskTaster:
    """
    风险味道品尝器

    品尝股票的风险"味道"
    """

    def taste(
        self,
        symbol: str,
        risk_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        品尝风险味道
        """
        volatility = risk_data.get("volatility", 0.2)
        beta = risk_data.get("beta", 1.0)
        max_drawdown = risk_data.get("max_drawdown", 0.1)

        vol_score = 1.0 - min(1.0, volatility / 0.5)

        beta_score = 1.0 - abs(beta - 1.0) / 2

        dd_score = 1.0 - min(1.0, max_drawdown / 0.3)

        risk_score = vol_score * 0.4 + beta_score * 0.3 + dd_score * 0.3

        return {
            "risk_score": risk_score,
            "vol_score": vol_score,
            "beta_score": beta_score,
            "dd_score": dd_score
        }


class CompositeTaster:
    """
    综合品尝器

    综合所有味道，形成完整的品尝报告
    """

    def __init__(self):
        self.momentum_taster = MomentumTaster()
        self.liquidity_taster = LiquidityTaster()
        self.valuation_taster = ValuationTaster()
        self.risk_taster = RiskTaster()

    def taste_all(
        self,
        symbol: str,
        price_data: Dict[str, Any],
        volume_data: Dict[str, Any],
        valuation_data: Dict[str, Any],
        risk_data: Dict[str, Any],
        sentiment_data: Optional[Dict[str, Any]] = None
    ) -> PreTasteResult:
        """
        综合品尝

        Args:
            symbol: 股票代码
            price_data: 价格数据
            volume_data: 成交量数据
            valuation_data: 估值数据
            risk_data: 风险数据
            sentiment_data: 叙事情绪数据（可选）NEW
                - topic_sentiment: Dict[str, float] 话题情绪
                - narrative_intensity: float 叙事强度
                - news_count: int 新闻数量
        """
        momentum = self.momentum_taster.taste(symbol, price_data)
        liquidity = self.liquidity_taster.taste(symbol, volume_data)
        valuation = self.valuation_taster.taste(symbol, valuation_data)
        risk = self.risk_taster.taste(symbol, risk_data)

        sentiment_score = 0.5
        if sentiment_data:
            topic_sentiments = sentiment_data.get("topic_sentiment", {})
            if topic_sentiments:
                sentiment_score = sum(topic_sentiments.values()) / len(topic_sentiments)
            else:
                sentiment_score = sentiment_data.get("narrative_intensity", 0.5)
                sentiment_score = sentiment_score if sentiment_score else 0.5

        scores = {
            "momentum": momentum.get("momentum_score", 0.5),
            "liquidity": liquidity.get("liquidity_score", 0.5),
            "valuation": valuation.get("valuation_score", 0.5),
            "risk": risk.get("risk_score", 0.5),
            "sentiment": sentiment_score
        }

        composite_score = (
            scores["momentum"] * 0.20 +
            scores["liquidity"] * 0.15 +
            scores["valuation"] * 0.25 +
            scores["risk"] * 0.20 +
            scores["sentiment"] * 0.20
        )

        quality = self._score_to_quality(composite_score)
        flavors, risk_flavors = self._extract_flavors(scores)
        opportunity, warning = self._generate_opportunity_warning(symbol, scores, quality)
        action = self._recommend_action(quality, composite_score)

        return PreTasteResult(
            quality=quality,
            score=composite_score,
            flavors=flavors,
            risk_flavors=risk_flavors,
            opportunity=opportunity,
            warning=warning,
            recommended_action=action,
            confidence=0.75
        )

    def _score_to_quality(self, score: float) -> TasteQuality:
        """评分转品质"""
        if score >= 0.8:
            return TasteQuality.EXCELLENT
        elif score >= 0.65:
            return TasteQuality.GOOD
        elif score >= 0.5:
            return TasteQuality.MEDIUM
        elif score >= 0.35:
            return TasteQuality.BAD
        else:
            return TasteQuality.TERRIBLE

    def _extract_flavors(self, scores: Dict[str, float]) -> tuple:
        """提取味道"""
        flavors = []
        risk_flavors = []

        if scores["momentum"] > 0.7:
            flavors.append("动量十足")
        elif scores["momentum"] < 0.3:
            risk_flavors.append("动量衰竭")

        if scores["liquidity"] > 0.7:
            flavors.append("流动性充沛")
        elif scores["liquidity"] < 0.3:
            risk_flavors.append("流动性枯竭")

        if scores["valuation"] > 0.7:
            flavors.append("估值便宜")
        elif scores["valuation"] < 0.3:
            risk_flavors.append("估值过高")

        if scores["risk"] > 0.7:
            flavors.append("风险可控")
        elif scores["risk"] < 0.3:
            risk_flavors.append("风险较大")

        return flavors, risk_flavors

    def _generate_opportunity_warning(
        self,
        symbol: str,
        scores: Dict[str, float],
        quality: TasteQuality
    ) -> tuple:
        """生成机会和警告"""
        opportunity = ""
        warning = ""

        if quality == TasteQuality.EXCELLENT:
            opportunity = f"{symbol} 当前味道绝佳，值得买入"
        elif quality == TasteQuality.GOOD:
            opportunity = f"{symbol} 味道不错，可以关注"
        elif quality == TasteQuality.MEDIUM:
            opportunity = f"{symbol} 味道一般，等待更好时机"
        else:
            opportunity = f"{symbol} 味道不佳，建议观望"

        if scores["valuation"] < 0.3 and scores["momentum"] > 0.6:
            warning = "估值偏低但动量强，可能是价值陷阱"
        elif scores["liquidity"] < 0.3:
            warning = "流动性不足，小心无法卖出"
        elif scores["risk"] < 0.3:
            warning = "风险较大，控制仓位"

        return opportunity, warning

    def _recommend_action(self, quality: TasteQuality, score: float) -> str:
        """建议行动"""
        if quality == TasteQuality.EXCELLENT:
            return "强烈建议买入"
        elif quality == TasteQuality.GOOD:
            return "可以考虑买入"
        elif quality == TasteQuality.MEDIUM:
            return "观望为主，等待机会"
        elif quality == TasteQuality.BAD:
            return "不建议买入"
        else:
            return "卖出或回避"


class PreTasteSense:
    """
    预尝能力（舌识的进阶）

    在买入之前感知股票的味道
    """

    def __init__(self):
        self.composite_taster = CompositeTaster()
        self._taste_cache: Dict[str, PreTasteResult] = {}
        self._last_update: float = 0

    def pre_taste(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        sentiment_data: Optional[Dict[str, Any]] = None
    ) -> PreTasteResult:
        """
        预尝股票

        Args:
            symbol: 股票代码
            market_data: 市场数据，包含：
                - price_data: 价格数据
                - volume_data: 成交量数据
                - valuation_data: 估值数据
                - risk_data: 风险数据
            sentiment_data: 叙事情绪数据（可选）NEW
                - topic_sentiment: Dict[str, float] 话题情绪
                - narrative_intensity: float 叙事强度
                - news_count: int 新闻数量
                - sector: str 所属板块

        Returns:
            预尝结果
        """
        price_data = market_data.get("price_data", market_data)
        volume_data = market_data.get("volume_data", market_data)
        valuation_data = market_data.get("valuation_data", {})
        risk_data = market_data.get("risk_data", {})

        result = self.composite_taster.taste_all(
            symbol=symbol,
            price_data=price_data,
            volume_data=volume_data,
            valuation_data=valuation_data,
            risk_data=risk_data,
            sentiment_data=sentiment_data
        )

        self._taste_cache[symbol] = result
        self._last_update = 0

        return result

    def get_cached_taste(self, symbol: str) -> Optional[PreTasteResult]:
        """获取缓存的品尝结果"""
        return self._taste_cache.get(symbol)

    def compare_opportunities(
        self,
        opportunities: List[str],
        market_data: Dict[str, Dict[str, Any]]
    ) -> Dict[str, PreTasteResult]:
        """
        比较多个机会的味道

        Returns:
            各机会的品尝结果，按评分排序
        """
        results = {}

        for symbol in opportunities:
            if symbol in market_data:
                results[symbol] = self.pre_taste(symbol, market_data[symbol])

        return dict(sorted(results.items(), key=lambda x: x[1].score, reverse=True))