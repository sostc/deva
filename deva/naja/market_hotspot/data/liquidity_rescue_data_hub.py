"""
LiquidityRescueDataHub - 流动性救援数据中枢

统一管理所有流动性救援相关的数据计算:
- 市场波动率计算
- 市场广度计算
- 恐慌指数综合评估
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
import time
import logging

from .volatility_calculator import MarketVolatilityCalculator
from .market_breadth import MarketBreadthCalculator
from .global_market_futures import GlobalMarketAPI, MarketData, MARKET_ID_TO_CODE

log = logging.getLogger(__name__)


@dataclass
class LiquidityRescueData:
    """流动性救援综合数据"""
    panic_level: float
    liquidity_score: float
    spread_ratio: float
    event_impact: float
    recovery_signal: float
    price_destabilization_speed: float
    volume_shrink_ratio: float
    fear_score: float
    volatility_score: float
    breadth_fear_score: float
    timestamp: float = field(default_factory=time.time)


class LiquidityRescueDataHub:
    """
    流动性救援数据中枢

    用法:
        hub = LiquidityRescueDataHub()
        hub.update_price(3000.0)
        hub.update_market_breadth(stock_changes)
        data = hub.get_liquidity_rescue_data()
    """

    def __init__(self):
        self._volatility_calc = MarketVolatilityCalculator()
        self._breadth_calc = MarketBreadthCalculator()
        self._custom_data_sources: Dict[str, Callable] = {}
        self._last_update = 0
        self._global_futures_api: Optional[GlobalMarketAPI] = None
        self._global_market_data: Dict[str, MarketData] = {}

    def update_price(self, price: float, timestamp: Optional[float] = None) -> None:
        """
        更新价格数据

        Args:
            price: 当前价格
            timestamp: 时间戳
        """
        self._volatility_calc.update(price, timestamp)
        self._last_update = time.time()

    def update_prices(self, prices: List[float], timestamps: Optional[List[float]] = None) -> None:
        """
        批量更新价格数据

        Args:
            prices: 价格列表
            timestamps: 时间戳列表
        """
        self._volatility_calc.update_batch(prices, timestamps)
        self._last_update = time.time()

    def update_market_breadth(self, stock_data_list: List[Dict[str, Any]]) -> None:
        """
        更新市场广度数据

        Args:
            stock_data_list: 股票数据列表
        """
        self._breadth_calc.update(stock_data_list)
        self._last_update = time.time()

    def update_from_changes(self, changes: List[float]) -> None:
        """
        从涨跌幅列表更新市场广度

        Args:
            changes: 涨跌幅列表
        """
        stock_data = [{"change_pct": c} for c in changes]
        self._breadth_calc.update(stock_data)
        self._last_update = time.time()

    def register_data_source(self, name: str, data_func: Callable[[], float]) -> None:
        """
        注册自定义数据源

        Args:
            name: 数据源名称
            data_func: 返回数据的函数
        """
        self._custom_data_sources[name] = data_func
        log.info(f"[LiquidityRescueDataHub] 注册数据源: {name}")

    async def fetch_global_market_data(self) -> Dict[str, MarketData]:
        """
        获取全球市场数据（期货 + 美股）

        Returns:
            Dict[str, MarketData]: 市场数据字典
        """
        if self._global_futures_api is None:
            self._global_futures_api = GlobalMarketAPI()
        data = await self._global_futures_api.fetch_all()
        self._global_market_data = data
        self._last_update = time.time()
        return data

    def get_global_market_data(self) -> Dict[str, MarketData]:
        """获取已缓存的全球市场数据"""
        return self._global_market_data

    def get_global_market_summary(self) -> Dict[str, Any]:
        """
        获取全球市场摘要（用于热点事件）

        Returns:
            Dict: 包含主要市场的涨跌情况
        """
        if not self._global_market_data:
            return {}

        summary = {}
        for code, md in self._global_market_data.items():
            summary[md.market_id] = {
                "name": md.name,
                "current": md.current,
                "change": md.change,
                "change_pct": md.change_pct,
            }

        return summary

    def get_volatility_data(self) -> Dict[str, Any]:
        """获取波动率数据"""
        result = self._volatility_calc._last_result
        if result:
            return {
                "current_volatility": result.current_volatility,
                "historical_avg": result.historical_avg,
                "panic_ratio": result.panic_volatility_ratio,
                "level": result.level,
                "panic_score": self._volatility_calc.get_panic_score(),
            }
        return {}

    def get_breadth_data(self) -> Dict[str, Any]:
        """获取市场广度数据"""
        result = self._breadth_calc._last_result
        if result:
            return {
                "limit_up_count": result.limit_up_count,
                "limit_down_count": result.limit_down_count,
                "breadth_ratio": result.breadth_ratio,
                "fear_indicator": result.fear_indicator,
                "level": result.level,
                "fear_score": self._breadth_calc.get_fear_score(),
            }
        return {}

    def get_liquidity_rescue_data(
        self,
        custom_spread_ratio: Optional[float] = None,
        custom_event_impact: Optional[float] = None,
        custom_recovery_signal: Optional[float] = None,
        custom_volume_ratio: Optional[float] = None,
        custom_fear_score: Optional[float] = None
    ) -> LiquidityRescueData:
        """
        获取流动性救援综合数据

        所有参数都是可选的，如果不提供则使用计算值或默认值

        Args:
            custom_spread_ratio: 自定义价差比例（无Level2数据时用1.0）
            custom_event_impact: 自定义事件影响（无新闻数据时用0.0）
            custom_recovery_signal: 自定义恢复信号（需要实时计算）
            custom_volume_ratio: 自定义成交量比例（无Level2数据时用1.0）
            custom_fear_score: 自定义恐惧分数（无情绪数据时用计算值）

        Returns:
            LiquidityRescueData: 综合数据
        """
        vol_data = self.get_volatility_data()
        breadth_data = self.get_breadth_data()

        volatility_score = vol_data.get("panic_score", 0) if vol_data else 0
        breadth_fear_score = breadth_data.get("fear_score", 50) if breadth_data else 50

        if custom_fear_score is not None:
            fear_score = custom_fear_score
        else:
            fear_score = (volatility_score * 0.6 + breadth_fear_score * 0.4)

        panic_level = fear_score

        liquidity_score = self._estimate_liquidity_score(
            spread_ratio=custom_spread_ratio,
            volume_ratio=custom_volume_ratio
        )

        spread_ratio = custom_spread_ratio if custom_spread_ratio is not None else 1.0
        event_impact = custom_event_impact if custom_event_impact is not None else 0.0
        recovery_signal = custom_recovery_signal if custom_recovery_signal is not None else 0.0
        volume_shrink_ratio = custom_volume_ratio if custom_volume_ratio is not None else 1.0

        price_destabilization_speed = 0.0
        if vol_data and vol_data.get("current_volatility", 0) > 0:
            price_destabilization_speed = vol_data["current_volatility"] / 10.0

        return LiquidityRescueData(
            panic_level=panic_level,
            liquidity_score=liquidity_score,
            spread_ratio=spread_ratio,
            event_impact=event_impact,
            recovery_signal=recovery_signal,
            price_destabilization_speed=price_destabilization_speed,
            volume_shrink_ratio=volume_shrink_ratio,
            fear_score=fear_score,
            volatility_score=volatility_score,
            breadth_fear_score=breadth_fear_score,
            timestamp=time.time()
        )

    def _estimate_liquidity_score(
        self,
        spread_ratio: Optional[float] = None,
        volume_ratio: Optional[float] = None
    ) -> float:
        """
        估算流动性得分

        如果有真实数据使用真实数据，否则用波动率和市场广度估算
        """
        if spread_ratio is not None and volume_ratio is not None:
            spread_score = max(0, 1.0 - (spread_ratio - 1) / 3.0)
            volume_score = volume_ratio
            return min(1.0, (spread_score * 0.4 + volume_score * 0.6))

        vol_data = self.get_volatility_data()
        breadth_data = self.get_breadth_data()

        if not vol_data and not breadth_data:
            return 0.5

        vol_score = 0.5
        if vol_data:
            panic_ratio = vol_data.get("panic_ratio", 1.0)
            vol_score = max(0, 1.0 - (panic_ratio - 1) / 3.0)

        breadth_score = 0.5
        if breadth_data:
            breadth_ratio = breadth_data.get("breadth_ratio", 0)
            breadth_score = (breadth_ratio + 1) / 2

        return min(1.0, (vol_score * 0.5 + breadth_score * 0.5))

    def get_event_features(self) -> Dict[str, Any]:
        """
        获取可用于 AttentionEvent.features 的字典

        用于在没有真实Level2/VIX数据时填充计算值
        """
        data = self.get_liquidity_rescue_data()
        return {
            "panic_level": data.panic_level,
            "liquidity_score": data.liquidity_score,
            "spread_ratio": data.spread_ratio,
            "event_impact": data.event_impact,
            "recovery_signal": data.recovery_signal,
            "price_destabilization_speed": data.price_destabilization_speed,
            "volume_shrink_ratio": data.volume_shrink_ratio,
            "fear_score": data.fear_score,
            "volatility_score": data.volatility_score,
            "breadth_fear_score": data.breadth_fear_score,
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "volatility": self.get_volatility_data(),
            "breadth": self.get_breadth_data(),
            "last_update": self._last_update,
            "custom_sources": list(self._custom_data_sources.keys()),
        }


_liquidity_rescue_data_hub: Optional[LiquidityRescueDataHub] = None


def get_liquidity_rescue_data_hub() -> LiquidityRescueDataHub:
    """获取流动性救援数据中枢单例"""
    global _liquidity_rescue_data_hub
    if _liquidity_rescue_data_hub is None:
        _liquidity_rescue_data_hub = LiquidityRescueDataHub()
    return _liquidity_rescue_data_hub