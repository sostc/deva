"""
SoftInfoConfidence - 认知系统/软信息/置信度

别名/关键词: 软信息、置信度、confidence、soft_info

核心思想：给每个软信息打一个置信度，决定它对决策的影响程度

设计原则：
1. 硬数据（量价）= 主角，权重固定
2. 软信息（新闻/叙事）= 调味剂，权重=置信度
3. 置信度低时，软信息影响减小
4. 硬数据和软信息矛盾时，以硬数据为主
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class SoftInfoSource(Enum):
    """软信息来源"""
    NARRATIVE_TRACKER = "narrative_tracker"    # 叙事追踪
    NEWS_MIND = "news_mind"                    # 新闻舆情
    MARKET_SENTIMENT = "market_sentiment"     # 市场情绪
    CROSS_SIGNAL = "cross_signal"             # 跨信号共振


@dataclass
class SoftInfoSignal:
    """
    软信息信号

    包含值和置信度
    """
    source: str
    value: float           # 信号值，如 0.8 (看多)
    confidence: float     # 置信度 0-1
    reason: str           # 原因说明
    metadata: Dict[str, Any] = None

    def effective_weight(self, base_weight: float) -> float:
        """
        计算有效权重

        effective_weight = base_weight * confidence

        置信度越高，软信息影响越大
        置信度越低，软信息影响越小
        """
        return base_weight * self.confidence

    def is_reliable(self, threshold: float = 0.5) -> bool:
        """是否可靠"""
        return self.confidence >= threshold


class SoftInfoConfidence:
    """
    软信息置信度评估器

    职责：
    1. 评估软信息的置信度
    2. 将置信度应用到决策权重
    3. 处理硬数据和软信息的矛盾
    """

    def __init__(self):
        self._source_confidences: Dict[str, float] = {
            SoftInfoSource.NARRATIVE_TRACKER.value: 0.6,
            SoftInfoSource.NEWS_MIND.value: 0.5,
            SoftInfoSource.MARKET_SENTIMENT.value: 0.7,
            SoftInfoSource.CROSS_SIGNAL.value: 0.65,
        }
        self._base_soft_weight = 0.30  # 软信息基础权重30%

    def evaluate_narrative_confidence(
        self,
        narratives: list,
        narrative_stability: float = 0.5,
        source_reliability: float = 0.5
    ) -> SoftInfoSignal:
        """
        评估叙事置信度

        Args:
            narratives: 叙事列表
            narrative_stability: 叙事稳定性（同一叙事持续时间）
            source_reliability: 来源可靠性（新闻质量）

        Returns:
            SoftInfoSignal with value and confidence
        """
        if not narratives:
            return SoftInfoSignal(
                source=SoftInfoSource.NARRATIVE_TRACKER.value,
                value=0.5,
                confidence=0.0,
                reason="无叙事数据"
            )

        narrative_count = len(narratives)

        confidence = (
            source_reliability * 0.4 +
            min(narrative_count / 10.0, 1.0) * 0.3 +
            min(narrative_stability, 1.0) * 0.3
        )
        confidence = min(confidence, 0.85)

        sentiment_score = 0.5
        if any("利好" in n or "上涨" in n for n in narratives):
            sentiment_score = 0.6
        if any("利空" in n or "下跌" in n for n in narratives):
            sentiment_score = 0.4

        return SoftInfoSignal(
            source=SoftInfoSource.NARRATIVE_TRACKER.value,
            value=sentiment_score,
            confidence=confidence,
            reason=f"叙事数量:{narrative_count}, 稳定性:{narrative_stability:.2f}",
            metadata={"narratives": narratives[:5]}
        )

    def evaluate_sentiment_confidence(
        self,
        sentiment: str,
        sentiment_strength: float = 0.5,
        source_reliability: float = 0.6
    ) -> SoftInfoSignal:
        """
        评估情绪置信度

        Args:
            sentiment: 情绪 "bullish" | "neutral" | "fearful"
            sentiment_strength: 情绪强度 0-1
            source_reliability: 来源可靠性

        Returns:
            SoftInfoSignal with value and confidence
        """
        sentiment_map = {
            "bullish": 0.7,
            "neutral": 0.5,
            "fearful": 0.3,
        }

        value = sentiment_map.get(sentiment, 0.5)
        confidence = source_reliability * (0.5 + sentiment_strength * 0.5)
        confidence = min(confidence, 0.9)

        return SoftInfoSignal(
            source=SoftInfoSource.MARKET_SENTIMENT.value,
            value=value,
            confidence=confidence,
            reason=f"情绪:{sentiment}, 强度:{sentiment_strength:.2f}",
            metadata={"sentiment": sentiment, "strength": sentiment_strength}
        )

    def evaluate_cross_signal_confidence(
        self,
        resonance_count: int,
        sector_count: int,
        source_reliability: float = 0.65
    ) -> SoftInfoSignal:
        """
        评估跨信号共振置信度

        Args:
            resonance_count: 共振信号数量
            sector_count: 涉及板块数量
            source_reliability: 来源可靠性

        Returns:
            SoftInfoSignal with value and confidence
        """
        if resonance_count == 0:
            return SoftInfoSignal(
                source=SoftInfoSource.CROSS_SIGNAL.value,
                value=0.5,
                confidence=0.0,
                reason="无共振信号"
            )

        resonance_score = min(resonance_count / 5.0, 1.0)
        confidence = source_reliability * (0.4 + resonance_score * 0.6)
        confidence = min(confidence, 0.85)

        direction_score = 0.5 + resonance_score * 0.3

        return SoftInfoSignal(
            source=SoftInfoSource.CROSS_SIGNAL.value,
            value=direction_score,
            confidence=confidence,
            reason=f"共振:{resonance_count}信号, {sector_count}板块",
            metadata={"resonance_count": resonance_count, "sector_count": sector_count}
        )

    def combine_with_hard_data(
        self,
        hard_signal: float,
        hard_confidence: float,
        soft_signals: list,
        hard_weight: float = 0.70
    ) -> Tuple[float, float]:
        """
        合并硬数据和软信息

        核心公式：
        final = hard * hard_weight + Σ(soft_i * soft_weight_i)

        其中 soft_weight_i = base_soft_weight * soft_i.confidence

        Args:
            hard_signal: 硬数据信号值 0-1
            hard_confidence: 硬数据置信度 0-1
            soft_signals: 软信息信号列表
            hard_weight: 硬数据基础权重

        Returns:
            (final_signal, final_confidence)
        """
        soft_weight_total = 0.0
        soft_signal_weighted = 0.0

        for soft in soft_signals:
            if not soft.is_reliable(threshold=0.3):
                continue

            effective_w = soft.effective_weight(self._base_soft_weight)
            soft_signal_weighted += soft.value * effective_w
            soft_weight_total += effective_w

        total_weight = hard_weight * hard_confidence + soft_weight_total
        if total_weight == 0:
            return 0.5, 0.0

        final_signal = (
            hard_signal * hard_weight * hard_confidence +
            soft_signal_weighted
        ) / total_weight

        final_confidence = min(total_weight, 1.0)

        return final_signal, final_confidence

    def check_contradiction(
        self,
        hard_signal: float,
        soft_signals: list,
        threshold: float = 0.2
    ) -> Optional[Dict[str, Any]]:
        """
        检查硬数据和软信息的矛盾

        Args:
            hard_signal: 硬数据信号
            soft_signals: 软信息信号列表
            threshold: 矛盾阈值

        Returns:
            如果有矛盾返回详情，否则返回 None
        """
        if not soft_signals:
            return None

        reliable_soft = [s for s in soft_signals if s.is_reliable(threshold=0.4)]
        if not reliable_soft:
            return None

        avg_soft = sum(s.value for s in reliable_soft) / len(reliable_soft)

        hard_direction = "up" if hard_signal > 0.55 else "down" if hard_signal < 0.45 else "neutral"
        soft_direction = "up" if avg_soft > 0.55 else "down" if avg_soft < 0.45 else "neutral"

        if hard_direction != "neutral" and soft_direction != "neutral" and hard_direction != soft_direction:
            avg_soft_confidence = sum(s.confidence for s in reliable_soft) / len(reliable_soft)
            return {
                "has_contradiction": True,
                "hard_direction": hard_direction,
                "soft_direction": soft_direction,
                "severity": abs(hard_signal - avg_soft),
                "soft_confidence": avg_soft_confidence,
                "resolution": "follow_hard_data" if avg_soft_confidence < 0.6 else "reduce_confidence"
            }

        return None

    def get_source_confidence(self, source: str) -> float:
        """获取来源的基准置信度"""
        return self._source_confidences.get(source, 0.5)

    def set_source_confidence(self, source: str, confidence: float):
        """设置来源的基准置信度"""
        self._source_confidences[source] = min(max(confidence, 0.0), 1.0)
