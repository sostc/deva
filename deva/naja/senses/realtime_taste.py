"""
RealtimeTaste - 实时舌识尝受

持仓期间持续感知浮盈浮亏、机会成本、仓位鲜度

使用方式：
    taste = RealtimeTaste()

    # 尝受持仓
    signal = taste.taste_position(position, current_price)

    # 尝受所有持仓
    signals = taste.taste_all(positions, current_prices)
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
from collections import deque

log = logging.getLogger(__name__)


class FreshnessLevel(Enum):
    """鲜度等级"""
    VERY_FRESH = "very_fresh"
    FRESH = "fresh"
    STALE = "stale"
    VERY_STALE = "very_stale"


@dataclass
class TasteSignal:
    """尝受信号"""
    symbol: str
    floating_pnl: float
    opportunity_cost: float
    freshness: float
    emotional_intensity: float
    should_adjust: bool
    adjust_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "floating_pnl": self.floating_pnl,
            "opportunity_cost": self.opportunity_cost,
            "freshness": self.freshness,
            "emotional_intensity": self.emotional_intensity,
            "should_adjust": self.should_adjust,
            "adjust_reason": self.adjust_reason,
        }


class PositionState:
    """持仓状态"""

    def __init__(self, symbol: str, entry_price: float, quantity: int, entry_time: float):
        self.symbol = symbol
        self.entry_price = entry_price
        self.quantity = quantity
        self.entry_time = entry_time
        self.peak_pnl = 0.0
        self.trough_pnl = 0.0
        self.pnl_history: deque = deque(maxlen=20)
        self.holding_time = 0.0
        self.last_price = entry_price

    def update(self, current_price: float, current_time: float):
        """更新持仓状态"""
        self.last_price = current_price
        self.holding_time = current_time - self.entry_time

        current_pnl = (current_price - self.entry_price) / self.entry_price
        self.pnl_history.append(current_pnl)

        if current_pnl > self.peak_pnl:
            self.peak_pnl = current_pnl
        if current_pnl < self.trough_pnl:
            self.trough_pnl = current_pnl

    def get_current_pnl(self) -> float:
        return (self.last_price - self.entry_price) / self.entry_price

    def get_pnl_trend(self) -> float:
        """获取盈亏趋势：正=盈利增加，负=盈利回吐"""
        if len(self.pnl_history) < 3:
            return 0.0
        recent = list(self.pnl_history)[-3:]
        return recent[-1] - recent[0]


class RealtimeTaste:
    """
    实时舌识

    持仓期间持续感知：
    1. 浮盈浮亏
    2. 机会成本
    3. 仓位鲜度
    4. 情绪强度
    """

    def __init__(self):
        self._positions: Dict[str, PositionState] = {}
        self._benchmark_pnl: float = 0.0
        self._recent_taste_signals: List[TasteSignal] = []

    def register_position(self, symbol: str, entry_price: float, quantity: int, entry_time: float):
        """注册新持仓"""
        self._positions[symbol] = PositionState(symbol, entry_price, quantity, entry_time)
        log.info(f"[RealtimeTaste] 注册持仓 {symbol} @ {entry_price}")

    def close_position(self, symbol: str):
        """平仓"""
        if symbol in self._positions:
            pos = self._positions[symbol]
            final_pnl = pos.get_current_pnl()
            del self._positions[symbol]
            log.info(f"[RealtimeTaste] 平仓 {symbol}, 最终盈亏 {final_pnl:.2%}")

            self._record_taste_feedback(symbol, final_pnl)

    def update_price(self, symbol: str, current_price: float):
        """更新持仓价格"""
        if symbol in self._positions:
            self._positions[symbol].update(current_price, time.time())

    def set_benchmark(self, benchmark_pnl: float):
        """设置基准收益（用于计算机会成本）"""
        self._benchmark_pnl = benchmark_pnl

    def taste_position(self, symbol: str, current_price: float) -> Optional[TasteSignal]:
        """
        尝受单个持仓

        Returns:
            TasteSignal 或 None
        """
        if symbol not in self._positions:
            return None

        pos = self._positions[symbol]
        pos.update(current_price, time.time())

        floating_pnl = pos.get_current_pnl()
        pnl_trend = pos.get_pnl_trend()

        opportunity_cost = self._calc_opportunity_cost(floating_pnl)
        freshness = self._calc_freshness(floating_pnl, pnl_trend, pos)
        emotional = self._calc_emotional_intensity(floating_pnl, pnl_trend)
        should_adjust, adjust_reason = self._should_adjust_decision(
            floating_pnl, pnl_trend, opportunity_cost, freshness
        )

        signal = TasteSignal(
            symbol=symbol,
            floating_pnl=floating_pnl,
            opportunity_cost=opportunity_cost,
            freshness=freshness,
            emotional_intensity=emotional,
            should_adjust=should_adjust,
            adjust_reason=adjust_reason
        )

        self._recent_taste_signals.append(signal)
        if len(self._recent_taste_signals) > 50:
            self._recent_taste_signals.pop(0)

        return signal

    def taste_all(self, current_prices: Dict[str, float]) -> Dict[str, TasteSignal]:
        """尝受所有持仓"""
        results = {}
        for symbol, price in current_prices.items():
            signal = self.taste_position(symbol, price)
            if signal:
                results[symbol] = signal
        return results

    def _calc_opportunity_cost(self, floating_pnl: float) -> float:
        """计算机会成本：持这个 vs 持基准"""
        return floating_pnl - self._benchmark_pnl

    def _calc_freshness(
        self,
        floating_pnl: float,
        pnl_trend: float,
        pos: PositionState
    ) -> float:
        """
        计算仓位鲜度 [0, 1]

        规则：
        - 盈利持续增加 → 鲜度上升
        - 盈利回吐 → 鲜度下降
        - 亏损扩大 → 鲜度快速下降
        - 持仓时间过长 → 鲜度自然衰减
        """
        base_freshness = 1.0

        if floating_pnl > 0 and pnl_trend > 0:
            freshness = min(1.0, base_freshness + 0.2)
        elif floating_pnl > 0 and pnl_trend < -0.02:
            freshness = max(0.3, base_freshness - abs(pnl_trend) * 5)
        elif floating_pnl < -0.02 and pnl_trend < 0:
            freshness = max(0.1, base_freshness - abs(floating_pnl) * 3)
        elif floating_pnl < 0 and pnl_trend > 0:
            freshness = max(0.4, base_freshness - abs(floating_pnl) * 2)
        else:
            freshness = base_freshness

        time_decay = min(0.3, pos.holding_time / 3600 * 0.05)
        freshness = max(0.1, freshness - time_decay)

        if pos.peak_pnl > 0.05 and floating_pnl < pos.peak_pnl * 0.5:
            freshness *= 0.7

        return freshness

    def _calc_emotional_intensity(self, floating_pnl: float, pnl_trend: float) -> float:
        """
        计算情绪强度 [0, 1]

        反映持仓带来的情绪压力：
        - 盈利大 → 兴奋
        - 亏损大 → 恐惧
        - 波动大 → 焦虑
        """
        base = abs(floating_pnl)

        volatility = abs(pnl_trend) * 10
        emotional = base + volatility * 0.3

        return min(1.0, emotional)

    def _should_adjust_decision(
        self,
        floating_pnl: float,
        pnl_trend: float,
        opportunity_cost: float,
        freshness: float
    ) -> tuple[bool, str]:
        """
        判断是否应该调整仓位

        Returns:
            (should_adjust, reason)
        """
        if freshness < 0.25:
            return True, f"仓位鲜度不足({freshness:.0%})，建议减仓"

        if floating_pnl < -0.05 and freshness < 0.5:
            return True, f"亏损扩大({floating_pnl:.1%})且鲜度不足，建议止损"

        if opportunity_cost < -0.05 and floating_pnl > 0.02:
            return True, f"机会成本高({opportunity_cost:.1%})，换仓可能更好"

        if floating_pnl > 0.08 and pnl_trend < -0.015:
            return True, f"盈利回吐({pnl_trend:.1%})，考虑部分止盈"

        if floating_pnl > 0.15:
            return True, f"盈利丰厚({floating_pnl:.1%})，建议分批止盈"

        return False, ""

    def _record_taste_feedback(self, symbol: str, final_pnl: float):
        """记录尝受反馈（用于学习）"""
        log.info(f"[RealtimeTaste] {symbol} 最终盈亏 {final_pnl:.2%}")

    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "position_count": len(self._positions),
            "positions": list(self._positions.keys()),
            "benchmark_pnl": self._benchmark_pnl,
            "recent_signals_count": len(self._recent_taste_signals),
        }

    def get_positions_summary(self) -> List[Dict[str, Any]]:
        """获取所有持仓摘要"""
        summary = []
        for symbol, pos in self._positions.items():
            summary.append({
                "symbol": symbol,
                "entry_price": pos.entry_price,
                "current_pnl": pos.get_current_pnl(),
                "pnl_trend": pos.get_pnl_trend(),
                "holding_time": pos.holding_time,
                "peak_pnl": pos.peak_pnl,
                "trough_pnl": pos.trough_pnl,
            })
        return summary
