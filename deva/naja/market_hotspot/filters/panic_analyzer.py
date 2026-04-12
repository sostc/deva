"""
PanicAnalyzer - 恐慌指数计算和第二层评估

第二层过滤：中频评估（5分钟级别）
综合评估事件的恐慌程度和流动性危机水平

计算公式：
panic_score = (
    price_destabilization × 0.25 +
    volume_shrink × 0.25 +
    spread_expansion × 0.20 +
    fear_sentiment × 0.20 +
    event_severity × 0.10
)

liquidity_score = f(spread, volume, order_book_depth)
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
from collections import deque
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class PanicAnalyzerConfig:
    """恐慌分析配置"""
    panic_threshold: float = 70.0
    liquidity_crisis_threshold: float = 0.3
    deep_analysis_threshold: float = 50.0

    weight_price_destabilization: float = 0.25
    weight_volume_shrink: float = 0.25
    weight_spread_expansion: float = 0.20
    weight_fear_sentiment: float = 0.20
    weight_event_severity: float = 0.10

    history_window: int = 10


@dataclass
class PanicAnalysisResult:
    """恐慌分析结果"""
    panic_score: float
    liquidity_score: float
    passed: bool
    level: str
    details: Dict = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


class PanicAnalyzer:
    """
    恐慌指数计算器

    用法:
        analyzer = PanicAnalyzer()
        result = analyzer.analyze(event)

        if result.passed:
            if result.level == "extreme":
                # 立即介入救援
            elif result.level == "high":
                # 密切关注，准备介入
    """

    def __init__(self, config: Optional[PanicAnalyzerConfig] = None):
        self.config = config or PanicAnalyzerConfig()
        self._history: deque = deque(maxlen=self.config.history_window)
        self._last_analysis_time = 0

    def analyze(self, event) -> PanicAnalysisResult:
        """
        分析事件的恐慌程度

        Args:
            event: HotspotEvent 或类似对象

        Returns:
            PanicAnalysisResult: 包含恐慌指数、流动性得分、是否通过等
        """
        features = self._extract_features(event)

        panic_score = self._calculate_panic_score(features)
        liquidity_score = self._calculate_liquidity_score(features)

        self._history.append({
            "timestamp": time.time(),
            "panic_score": panic_score,
            "liquidity_score": liquidity_score,
            "features": features.copy()
        })

        level = self._classify_panic_level(panic_score, liquidity_score)
        passed = panic_score >= self.config.panic_threshold or liquidity_score < self.config.liquidity_crisis_threshold
        recommendations = self._generate_recommendations(panic_score, liquidity_score, level)

        return PanicAnalysisResult(
            panic_score=panic_score,
            liquidity_score=liquidity_score,
            passed=passed,
            level=level,
            details={
                "price_destabilization": features.get("price_destabilization_speed", 0),
                "volume_shrink_ratio": features.get("volume_shrink_ratio", 1.0),
                "spread_expansion": features.get("spread_ratio", 1.0),
                "fear_sentiment": features.get("fear_score", 0),
                "event_severity": features.get("event_impact", 0),
            },
            recommendations=recommendations
        )

    def analyze_batch(self, events: List) -> List[PanicAnalysisResult]:
        """批量分析事件"""
        return [self.analyze(e) for e in events]

    def get_panic_trend(self) -> str:
        """
        获取恐慌趋势

        Returns:
            "escalating": 恐慌正在加剧
            "stable": 恐慌稳定
            "deescalating": 恐慌正在消退
        """
        if len(self._history) < 3:
            return "unknown"

        recent = list(self._history)[-3:]
        scores = [h["panic_score"] for h in recent]

        if scores[-1] > scores[0] * 1.1:
            return "escalating"
        elif scores[-1] < scores[0] * 0.9:
            return "deescalating"
        else:
            return "stable"

    def is_panic_peak(self, tolerance: float = 0.05) -> bool:
        """
        判断是否是恐慌极点

        条件：
        1. 当前恐慌指数处于局部最高点
        2. 且开始出现下降趋势
        """
        if len(self._history) < 5:
            return False

        recent = list(self._history)[-5:]
        scores = [h["panic_score"] for h in recent]

        current = scores[-1]
        previous = scores[-2]

        if current < previous:
            for s in scores[:-1]:
                if s > current * (1 + tolerance):
                    return False
            return True

        return False

    def _calculate_panic_score(self, features: Dict) -> float:
        """计算恐慌指数 (0-100)"""
        cfg = self.config

        price_destabilization = min(1.0, abs(features.get("price_destabilization_speed", 0)) / 5.0)
        volume_shrink = 1.0 - min(1.0, features.get("volume_shrink_ratio", 1.0))
        spread_expansion = min(1.0, (features.get("spread_ratio", 1.0) - 1) / 3.0)
        fear_sentiment = features.get("fear_score", 0) / 100.0
        event_severity = features.get("event_impact", 0)

        panic_score = (
            price_destabilization * cfg.weight_price_destabilization +
            volume_shrink * cfg.weight_volume_shrink +
            spread_expansion * cfg.weight_spread_expansion +
            fear_sentiment * cfg.weight_fear_sentiment +
            event_severity * cfg.weight_event_severity
        ) * 100

        return min(100.0, max(0.0, panic_score))

    def _calculate_liquidity_score(self, features: Dict) -> float:
        """
        计算流动性得分 (0-1)

        1.0 = 正常流动性
        0.0 = 完全枯竭
        """
        spread_ratio = features.get("spread_ratio", 1.0)
        volume_shrink_ratio = features.get("volume_shrink_ratio", 1.0)
        order_book_imbalance = features.get("order_book_imbalance", 0.5)

        spread_score = max(0, 1.0 - (spread_ratio - 1) / 3.0)
        volume_score = volume_shrink_ratio
        obi_score = order_book_imbalance

        liquidity_score = (
            spread_score * 0.4 +
            volume_score * 0.4 +
            obi_score * 0.2
        )

        return min(1.0, max(0.0, liquidity_score))

    def _classify_panic_level(self, panic_score: float, liquidity_score: float) -> str:
        """分类恐慌等级"""
        if panic_score >= 80 or liquidity_score < 0.15:
            return "extreme"
        elif panic_score >= 70 or liquidity_score < 0.25:
            return "high"
        elif panic_score >= 50 or liquidity_score < 0.4:
            return "elevated"
        elif panic_score >= 30:
            return "moderate"
        else:
            return "low"

    def _generate_recommendations(self, panic_score: float, liquidity_score: float, level: str) -> List[str]:
        """生成建议"""
        recommendations = []

        if level == "extreme":
            recommendations.append("🚨 极端恐慌：立即评估救援机会")
            recommendations.append("⚡ 考虑分批建仓")
        elif level == "high":
            recommendations.append("⚠️ 高恐慌：密切监控，准备介入")
            recommendations.append("📊 等待恐慌极点确认")
        elif level == "elevated":
            recommendations.append("📈 恐慌升高：持续关注流动性变化")
            recommendations.append("🔍 等待更明确的信号")
        elif level == "moderate":
            recommendations.append("📉 中度恐慌：正常监控")
        else:
            recommendations.append("✅ 市场正常：无需特殊关注")

        if liquidity_score < 0.3:
            recommendations.append(f"💧 流动性危机：得分{liquidity_score:.2f}，关注价差变化")

        return recommendations

    def _extract_features(self, event) -> Dict:
        """从事件中提取特征"""
        if hasattr(event, "features"):
            return event.features
        elif isinstance(event, dict):
            return event
        else:
            return {}

    def get_stats(self) -> Dict:
        """获取分析统计"""
        return {
            "history_size": len(self._history),
            "last_panic_score": self._history[-1]["panic_score"] if self._history else None,
            "last_liquidity_score": self._history[-1]["liquidity_score"] if self._history else None,
            "panic_trend": self.get_panic_trend(),
            "is_panic_peak": self.is_panic_peak(),
            "config": {
                "panic_threshold": self.config.panic_threshold,
                "liquidity_crisis_threshold": self.config.liquidity_crisis_threshold,
            }
        }


def analyze_panic(event, config: Optional[PanicAnalyzerConfig] = None) -> PanicAnalysisResult:
    """
    快捷恐慌分析函数
    """
    analyzer = PanicAnalyzer(config)
    return analyzer.analyze(event)