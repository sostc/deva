"""
LiquidityRescueFilter - 流动性救援快速预过滤层

第一层过滤：快速筛选可能符合流动性救援条件的原始事件
只做简单计算，高频执行（1分钟级别）

过滤条件：
1. 价格变化速度：|price_change| > 2% → 进入第二层
2. 成交量萎缩：volume_ratio < 0.6 → 进入第二层
3. 价差扩大：spread > 2x → 进入第二层
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class QuickFilterConfig:
    """快速过滤配置"""
    price_change_threshold: float = 2.0
    volume_shrink_threshold: float = 0.6
    spread_multiplier_threshold: float = 2.0
    panic_score_threshold: float = 70.0

    enable_fast_path: bool = True
    cache_duration: int = 60


@dataclass
class FilterResult:
    """过滤结果"""
    passed: bool
    reason: str
    score: float = 0.0
    details: Dict = field(default_factory=dict)


class LiquidityRescueFilter:
    """
    流动性救援快速预过滤层

    用法:
        filter = LiquidityRescueFilter()
        result = filter.filter(event)
        if result.passed:
            # 进入第二层评估
    """

    def __init__(self, config: Optional[QuickFilterConfig] = None):
        self.config = config or QuickFilterConfig()
        self._last_filter_time = 0
        self._cache = {}

    def filter(self, event) -> FilterResult:
        """
        过滤单个事件

        Args:
            event: AttentionEvent 或类似对象

        Returns:
            FilterResult: 包含 passed, reason, score, details
        """
        if not self.config.enable_fast_path:
            return FilterResult(passed=True, reason="fast_path_disabled")

        features = self._extract_features(event)
        passed = False
        reasons = []
        scores = []
        details = {}

        price_change = abs(features.get("price_change", 0))
        if price_change > self.config.price_change_threshold:
            reasons.append(f"价格变化{price_change:.1f}%超过阈值{self.config.price_change_threshold}%")
            scores.append(min(1.0, price_change / 5.0))

        volume_ratio = features.get("volume_ratio", 1.0)
        if volume_ratio < self.config.volume_shrink_threshold:
            reasons.append(f"成交量萎缩至{volume_ratio:.0%}低于阈值{self.config.volume_shrink_threshold:.0%}")
            scores.append(1.0 - volume_ratio)

        spread_multiplier = features.get("spread_multiplier", 1.0)
        if spread_multiplier > self.config.spread_multiplier_threshold:
            reasons.append(f"价差扩大{spread_multiplier:.1f}x超过阈值{self.config.spread_multiplier_threshold}x")
            scores.append(min(1.0, (spread_multiplier - 1) / 2))

        panic_score = features.get("panic_score", 0)
        if panic_score > self.config.panic_score_threshold:
            reasons.append(f"恐慌指数{panic_score:.0f}超过阈值{self.config.panic_score_threshold:.0f}")
            scores.append(panic_score / 100.0)

        details = {
            "price_change": price_change,
            "volume_ratio": volume_ratio,
            "spread_multiplier": spread_multiplier,
            "panic_score": panic_score,
            "conditions_met": len(scores),
        }

        if scores:
            final_score = min(1.0, sum(scores) / max(1, len(scores)))
        else:
            final_score = 0.0

        passed = len(scores) >= 1

        return FilterResult(
            passed=passed,
            reason="; ".join(reasons) if reasons else "未满足任何条件",
            score=final_score,
            details=details
        )

    def filter_batch(self, events: List) -> tuple:
        """
        批量过滤事件

        Args:
            events: 事件列表

        Returns:
            tuple: (passed_events, rejected_events)
        """
        passed = []
        rejected = []

        for event in events:
            result = self.filter(event)
            if result.passed:
                passed.append((event, result))
            else:
                rejected.append((event, result))

        log.debug(f"[LiquidityRescueFilter] 批量过滤: {len(passed)}/{len(events)} 通过")
        return passed, rejected

    def should_compute_deep_analysis(self, event) -> bool:
        """
        判断是否需要进行深度分析（第三层）

        条件：
        1. 至少满足2个快速过滤条件
        2. 综合分数 > 0.5
        """
        result = self.filter(event)
        return (
            result.passed and
            result.details.get("conditions_met", 0) >= 2 and
            result.score > 0.5
        )

    def _extract_features(self, event) -> Dict:
        """从事件中提取特征"""
        if hasattr(event, "features"):
            return event.features
        elif isinstance(event, dict):
            return event
        else:
            return {}

    def get_filter_stats(self) -> Dict:
        """获取过滤统计"""
        return {
            "config": {
                "price_change_threshold": self.config.price_change_threshold,
                "volume_shrink_threshold": self.config.volume_shrink_threshold,
                "spread_multiplier_threshold": self.config.spread_multiplier_threshold,
                "panic_score_threshold": self.config.panic_score_threshold,
            },
            "enabled": self.config.enable_fast_path,
        }


def quick_filter(event, config: Optional[QuickFilterConfig] = None) -> FilterResult:
    """
    快捷过滤函数

    用法:
        result = quick_filter(some_event)
        if result.passed:
            # 处理事件
    """
    filter_instance = LiquidityRescueFilter(config)
    return filter_instance.filter(event)