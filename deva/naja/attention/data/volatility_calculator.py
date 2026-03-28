"""
MarketVolatilityCalculator - 市场波动率计算器

计算市场波动率指标，用于流动性救援价值观

公式:
- 日收益率: return = (close - prev_close) / prev_close
- 历史波动率: volatility = std(returns) * sqrt(252) * 100
- 恐慌波动率: panic_volatility = 当前波动率 / 历史平均波动率
"""

import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from collections import deque
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class VolatilityResult:
    """波动率计算结果"""
    current_volatility: float
    historical_avg: float
    panic_volatility_ratio: float
    level: str
    timestamp: float


class MarketVolatilityCalculator:
    """
    市场波动率计算器

    用法:
        calc = MarketVolatilityCalculator()
        result = calc.calculate(price_data)

        if result.level == "extreme_panic":
            # 市场极度恐慌
    """

    def __init__(
        self,
        window_size: int = 20,
        historical_window: int = 60,
        panic_threshold: float = 2.0,
        extreme_panic_threshold: float = 3.0
    ):
        """
        初始化波动率计算器

        Args:
            window_size: 计算窗口大小（天）
            historical_window: 历史平均窗口（天）
            panic_threshold: 恐慌阈值（当前/历史的倍数）
            extreme_panic_threshold: 极度恐慌阈值
        """
        self.window_size = window_size
        self.historical_window = historical_window
        self.panic_threshold = panic_threshold
        self.extreme_panic_threshold = extreme_panic_threshold
        self._price_history: deque = deque(maxlen=historical_window + window_size)
        self._last_result: Optional[VolatilityResult] = None

    def update(self, price: float, timestamp: Optional[float] = None) -> VolatilityResult:
        """
        更新价格数据并计算波动率

        Args:
            price: 当前价格
            timestamp: 时间戳（可选）

        Returns:
            VolatilityResult: 波动率计算结果
        """
        if timestamp is None:
            timestamp = time.time()

        self._price_history.append({"price": price, "timestamp": timestamp})

        if len(self._price_history) < self.window_size + 1:
            return self._create_empty_result(timestamp)

        return self.calculate()

    def update_batch(self, prices: List[float], timestamps: Optional[List[float]] = None) -> VolatilityResult:
        """
        批量更新价格数据

        Args:
            prices: 价格列表
            timestamps: 时间戳列表（可选）

        Returns:
            VolatilityResult: 波动率计算结果
        """
        if timestamps is None:
            timestamps = [time.time()] * len(prices)

        for price, ts in zip(prices, timestamps):
            self._price_history.append({"price": price, "timestamp": ts})

        return self.calculate()

    def calculate(self) -> VolatilityResult:
        """
        计算当前波动率

        Returns:
            VolatilityResult: 波动率计算结果
        """
        if len(self._price_history) < self.window_size + 1:
            return self._create_empty_result()

        prices = [p["price"] for p in self._price_history]
        returns = self._calculate_returns(prices)

        current_volatility = self._calculate_historical_volatility(returns[-self.window_size:])
        historical_avg = self._calculate_historical_average(returns)
        panic_ratio = current_volatility / historical_avg if historical_avg > 0 else 1.0

        level = self._classify_volatility_level(panic_ratio)

        result = VolatilityResult(
            current_volatility=current_volatility,
            historical_avg=historical_avg,
            panic_volatility_ratio=panic_ratio,
            level=level,
            timestamp=time.time()
        )

        self._last_result = result
        return result

    def _calculate_returns(self, prices: List[float]) -> List[float]:
        """计算收益率序列"""
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] != 0:
                ret = (prices[i] - prices[i - 1]) / prices[i - 1]
                returns.append(ret)
            else:
                returns.append(0.0)
        return returns

    def _calculate_historical_volatility(self, returns: List[float]) -> float:
        """计算历史波动率（年化）"""
        if len(returns) < 2:
            return 0.0
        return float(np.std(returns) * np.sqrt(252) * 100)

    def _calculate_historical_average(self, returns: List[float]) -> float:
        """计算历史平均波动率"""
        if len(returns) < self.window_size:
            return 0.0

        volatilities = []
        for i in range(self.window_size, len(returns) + 1):
            window_returns = returns[i - self.window_size:i]
            vol = self._calculate_historical_volatility(window_returns)
            volatilities.append(vol)

        return float(np.mean(volatilities)) if volatilities else 0.0

    def _classify_volatility_level(self, panic_ratio: float) -> str:
        """分类波动率等级"""
        if panic_ratio >= self.extreme_panic_threshold:
            return "extreme_panic"
        elif panic_ratio >= self.panic_threshold:
            return "high_volatility"
        elif panic_ratio >= 1.0:
            return "normal"
        else:
            return "low_volatility"

    def _create_empty_result(self, timestamp: Optional[float] = None) -> VolatilityResult:
        """创建空结果"""
        if timestamp is None:
            timestamp = time.time()
        return VolatilityResult(
            current_volatility=0.0,
            historical_avg=0.0,
            panic_volatility_ratio=1.0,
            level="unknown",
            timestamp=timestamp
        )

    def get_panic_score(self) -> float:
        """
        获取恐慌评分（0-100）

        用于流动性救援系统的 panic_score
        """
        if self._last_result is None:
            return 0.0

        ratio = self._last_result.panic_volatility_ratio

        if ratio >= self.extreme_panic_threshold:
            return min(100, 60 + (ratio - self.extreme_panic_threshold) * 20)
        elif ratio >= self.panic_threshold:
            return 40 + (ratio - self.panic_threshold) * 20
        elif ratio >= 1.0:
            return (ratio - 0.5) * 40
        else:
            return max(0, ratio * 20)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "window_size": self.window_size,
            "historical_window": self.historical_window,
            "panic_threshold": self.panic_threshold,
            "extreme_panic_threshold": self.extreme_panic_threshold,
            "data_points": len(self._price_history),
            "last_result": {
                "current_volatility": self._last_result.current_volatility if self._last_result else None,
                "historical_avg": self._last_result.historical_avg if self._last_result else None,
                "panic_ratio": self._last_result.panic_volatility_ratio if self._last_result else None,
                "level": self._last_result.level if self._last_result else None,
            } if self._last_result else None,
            "panic_score": self.get_panic_score(),
        }


def calculate_volatility_from_prices(prices: List[float], annualize: bool = True) -> float:
    """
    快捷波动率计算函数

    Args:
        prices: 价格列表
        annualize: 是否年化

    Returns:
        float: 波动率
    """
    if len(prices) < 2:
        return 0.0

    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] != 0:
            ret = (prices[i] - prices[i - 1]) / prices[i - 1]
            returns.append(ret)

    if not returns:
        return 0.0

    vol = float(np.std(returns))
    if annualize:
        vol *= np.sqrt(252) * 100

    return vol


def estimate_panic_from_volatility(current_vol: float, historical_avg: float) -> float:
    """
    从波动率估算恐慌程度

    Args:
        current_vol: 当前波动率
        historical_avg: 历史平均波动率

    Returns:
        float: 恐慌程度 (0-100)
    """
    if historical_avg <= 0:
        return 50.0

    ratio = current_vol / historical_avg

    if ratio >= 3.0:
        return 90.0
    elif ratio >= 2.0:
        return 70.0 + (ratio - 2.0) * 15
    elif ratio >= 1.5:
        return 50.0 + (ratio - 1.5) * 40
    elif ratio >= 1.0:
        return 30.0 + (ratio - 1.0) * 40
    else:
        return max(0, ratio * 30)