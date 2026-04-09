"""
MarketBreadthCalculator - 市场广度计算器

计算市场涨跌停家数等指标，用于流动性救援价值观

指标:
- 涨停家数
- 跌停家数
- 涨跌家数比
- 市场广度指标
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from collections import deque
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class MarketBreadthResult:
    """市场广度计算结果"""
    limit_up_count: int
    limit_down_count: int
    advancing_count: int
    declining_count: int
    breadth_ratio: float
    fear_indicator: float
    level: str
    timestamp: float


class MarketBreadthCalculator:
    """
    市场广度计算器

    用法:
        calc = MarketBreadthCalculator()
        result = calc.update(stock_data_list)

        if result.level == "extreme_fear":
            # 市场极度恐慌
    """

    def __init__(
        self,
        extreme_fear_threshold: float = 0.1,
        high_fear_threshold: float = 0.2,
        extreme_greed_threshold: float = 5.0,
        high_greed_threshold: float = 3.0
    ):
        """
        初始化市场广度计算器

        Args:
            extreme_fear_threshold: 极度恐惧阈值（跌停/涨停比）
            high_fear_threshold: 高度恐惧阈值
            extreme_greed_threshold: 极度贪婪阈值
            high_greed_threshold: 高度贪婪阈值
        """
        self.extreme_fear_threshold = extreme_fear_threshold
        self.high_fear_threshold = high_fear_threshold
        self.extreme_greed_threshold = extreme_greed_threshold
        self.high_greed_threshold = high_greed_threshold
        self._history: deque = deque(maxlen=20)
        self._last_result: Optional[MarketBreadthResult] = None

    def update(self, stock_data_list: List[Dict[str, Any]]) -> MarketBreadthResult:
        """
        更新市场数据并计算广度

        Args:
            stock_data_list: 股票数据列表，每项包含:
                - code: 股票代码
                - change_pct: 涨跌幅
                - is_limit_up: 是否涨停
                - is_limit_down: 是否跌停

        Returns:
            MarketBreadthResult: 市场广度计算结果
        """
        limit_up = 0
        limit_down = 0
        advancing = 0
        declining = 0

        for stock in stock_data_list:
            change_pct = stock.get("change_pct", 0)
            is_limit_up = stock.get("is_limit_up", False)
            is_limit_down = stock.get("is_limit_down", False)

            if is_limit_up or change_pct >= 9.5:
                limit_up += 1
            elif is_limit_down or change_pct <= -9.5:
                limit_down += 1

            if change_pct > 0:
                advancing += 1
            elif change_pct < 0:
                declining += 1

        total = len(stock_data_list) if stock_data_list else 1

        limit_up_ratio = limit_up / total
        limit_down_ratio = limit_down / total
        advancing_ratio = advancing / total
        declining_ratio = declining / total

        breadth_ratio = (advancing - declining) / total if total > 0 else 0

        fear_indicator = self._calculate_fear_indicator(
            limit_up, limit_down, advancing, declining
        )

        level = self._classify_fear_level(fear_indicator)

        result = MarketBreadthResult(
            limit_up_count=limit_up,
            limit_down_count=limit_down,
            advancing_count=advancing,
            declining_count=declining,
            breadth_ratio=breadth_ratio,
            fear_indicator=fear_indicator,
            level=level,
            timestamp=time.time()
        )

        self._history.append(result)
        self._last_result = result
        return result

    def update_from_prices(
        self,
        prices: List[float],
        prev_prices: List[float]
    ) -> MarketBreadthResult:
        """
        从价格数据更新市场广度

        Args:
            prices: 当前价格列表
            prev_prices: 昨日价格列表

        Returns:
            MarketBreadthResult: 市场广度计算结果
        """
        stock_data_list = []
        for i, (curr, prev) in enumerate(zip(prices, prev_prices)):
            if prev == 0:
                change_pct = 0
            else:
                change_pct = (curr - prev) / prev * 100

            stock_data = {
                "code": f"stock_{i}",
                "change_pct": change_pct,
                "is_limit_up": change_pct >= 9.5,
                "is_limit_down": change_pct <= -9.5
            }
            stock_data_list.append(stock_data)

        return self.update(stock_data_list)

    def _calculate_fear_indicator(
        self,
        limit_up: int,
        limit_down: int,
        advancing: int,
        declining: int
    ) -> float:
        """
        计算恐惧指标

        公式:
        fear = (limit_down / max(limit_up, 1)) * (declining / max(advancing, 1))
        """
        if limit_up == 0 and advancing == 0:
            return 10.0

        limit_ratio = limit_down / max(limit_up, 1)
        decline_ratio = declining / max(advancing, 1)

        fear = limit_ratio * decline_ratio * 10

        return min(10.0, max(0.0, fear))

    def _classify_fear_level(self, fear_indicator: float) -> str:
        """分类恐惧等级"""
        if fear_indicator >= self.extreme_fear_threshold * 5:
            return "extreme_fear"
        elif fear_indicator >= self.extreme_fear_threshold:
            return "high_fear"
        elif fear_indicator >= self.high_fear_threshold:
            return "moderate_fear"
        elif fear_indicator >= 1.0:
            return "neutral"
        elif fear_indicator <= self.extreme_greed_threshold / 10:
            return "extreme_greed"
        elif fear_indicator <= self.high_greed_threshold / 10:
            return "high_greed"
        else:
            return "neutral"

    def get_fear_score(self) -> float:
        """
        获取恐惧评分（0-100）

        用于流动性救援系统的情绪指标
        """
        if self._last_result is None:
            return 50.0

        fear = self._last_result.fear_indicator

        if fear >= 5:
            return 90.0
        elif fear >= 2:
            return 70.0 + (fear - 2) * 6.7
        elif fear >= 1:
            return 50.0 + (fear - 1) * 20
        elif fear >= 0.5:
            return 30.0 + (fear - 0.5) * 40
        else:
            return fear * 60

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "thresholds": {
                "extreme_fear": self.extreme_fear_threshold,
                "high_fear": self.high_fear_threshold,
                "extreme_greed": self.extreme_greed_threshold,
                "high_greed": self.high_greed_threshold,
            },
            "data_points": len(self._history),
            "last_result": {
                "limit_up_count": self._last_result.limit_up_count if self._last_result else 0,
                "limit_down_count": self._last_result.limit_down_count if self._last_result else 0,
                "breadth_ratio": self._last_result.breadth_ratio if self._last_result else 0,
                "fear_indicator": self._last_result.fear_indicator if self._last_result else 0,
                "level": self._last_result.level if self._last_result else None,
            } if self._last_result else None,
            "fear_score": self.get_fear_score(),
        }


def calculate_breadth_from_changes(changes: List[float]) -> Dict[str, Any]:
    """
    从涨跌幅列表计算市场广度

    Args:
        changes: 涨跌幅列表 (-10 ~ 10)

    Returns:
        Dict: 市场广度数据
    """
    limit_up = sum(1 for c in changes if c >= 9.5)
    limit_down = sum(1 for c in changes if c <= -9.5)
    advancing = sum(1 for c in changes if c > 0)
    declining = sum(1 for c in changes if c < 0)

    total = len(changes) if changes else 1

    return {
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "advancing_count": advancing,
        "declining_count": declining,
        "limit_up_ratio": limit_up / total,
        "limit_down_ratio": limit_down / total,
        "advancing_ratio": advancing / total,
        "declining_ratio": declining / total,
        "breadth_ratio": (advancing - declining) / total,
    }


def estimate_fear_from_breadth(breadth_data: Dict[str, Any]) -> float:
    """
    从市场广度数据估算恐惧程度

    Args:
        breadth_data: calculate_breadth_from_changes 返回的数据

    Returns:
        float: 恐惧程度 (0-100)
    """
    limit_up = breadth_data.get("limit_up_count", 0)
    limit_down = breadth_data.get("limit_down_count", 0)

    if limit_up == 0:
        limit_ratio = limit_down if limit_down > 0 else 0.1
    else:
        limit_ratio = limit_down / limit_up

    if limit_ratio >= 5:
        return 90.0
    elif limit_ratio >= 2:
        return 70.0 + (limit_ratio - 2) * 6.7
    elif limit_ratio >= 1:
        return 50.0 + (limit_ratio - 1) * 20
    elif limit_ratio >= 0.5:
        return 30.0 + (limit_ratio - 0.5) * 40
    else:
        return limit_ratio * 60