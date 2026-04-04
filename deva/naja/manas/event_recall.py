"""
PortfolioDrivenEventRecall - 持仓驱动事件召回

根据 ManasOutput 的 attention_focus 召回相关事件
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from collections import deque

log = logging.getLogger(__name__)


@dataclass
class RecalledEvent:
    """召回的事件"""
    event_type: str
    symbol: str
    content: str
    confidence: float
    priority: float
    conditions: Dict[str, Any]


class PortfolioDrivenEventRecall:
    """
    持仓驱动事件召回

    根据 ManasOutput 的 attention_focus 动态召回相关事件：
    - stop_loss: 召回高亏损持仓 + 市场恶化事件
    - take_profit: 召回高盈利持仓 + 市场转弱事件
    - rebalance: 召回板块偏离事件
    - accumulate: 召回加仓时机事件
    """

    def __init__(self):
        self._event_pool: deque = deque(maxlen=500)
        self._focus_history: List[Dict[str, Any]] = []

    def register_event(
        self,
        event_type: str,
        symbol: str,
        content: str,
        confidence: float,
        conditions: Dict[str, Any]
    ):
        """注册事件到池中"""
        self._event_pool.append({
            "event_type": event_type,
            "symbol": symbol,
            "content": content,
            "confidence": confidence,
            "conditions": conditions,
            "timestamp": time.time()
        })

    def recall(
        self,
        attention_focus: str,
        portfolio_state: Dict[str, Any],
        market_data: Dict[str, Any],
        limit: int = 10
    ) -> List[RecalledEvent]:
        """
        根据 attention_focus 召回相关事件

        Args:
            attention_focus: watch/stop_loss/take_profit/rebalance/accumulate
            portfolio_state: 持仓状态
            market_data: 市场数据
            limit: 召回数量限制

        Returns:
            召回的事件列表
        """
        if attention_focus == "watch":
            return self._recall_watch_events(portfolio_state, market_data, limit)

        elif attention_focus == "stop_loss":
            return self._recall_stop_loss_events(portfolio_state, market_data, limit)

        elif attention_focus == "take_profit":
            return self._recall_take_profit_events(portfolio_state, market_data, limit)

        elif attention_focus == "rebalance":
            return self._recall_rebalance_events(portfolio_state, market_data, limit)

        elif attention_focus == "accumulate":
            return self._recall_accumulate_events(portfolio_state, market_data, limit)

        return []

    def _recall_watch_events(
        self,
        portfolio_state: Dict[str, Any],
        market_data: Dict[str, Any],
        limit: int
    ) -> List[RecalledEvent]:
        """召回观察类事件"""
        candidates = []

        for event in list(self._event_pool):
            age = time.time() - event["timestamp"]
            if age > 3600:
                continue

            priority = event["confidence"] * (1.0 - age / 3600)
            candidates.append(RecalledEvent(
                event_type=event["event_type"],
                symbol=event["symbol"],
                content=event["content"],
                confidence=event["confidence"],
                priority=priority,
                conditions=event["conditions"]
            ))

        candidates.sort(key=lambda x: x.priority, reverse=True)
        self._focus_history.append({"focus": "watch", "recalled": len(candidates)})
        return candidates[:limit]

    def _recall_stop_loss_events(
        self,
        portfolio_state: Dict[str, Any],
        market_data: Dict[str, Any],
        limit: int
    ) -> List[RecalledEvent]:
        """
        召回止损相关事件

        多维度权重评分：
        1. 个股亏损 (40%)：这只股票本身跌了多少
        2. 板块拖累 (30%)：所属板块是否也在跌
        3. 持仓集中度 (20%)：仓位越重风险越大
        4. 相对表现 (10%)：跑输板块还是跑赢
        """
        loss_threshold = portfolio_state.get("stop_loss_threshold", -0.05)
        held_symbols = set(portfolio_state.get("held_symbols", []))

        sector_performance = market_data.get("sector_performance", {})
        sector_alloc = portfolio_state.get("sector_alloc", {})
        holdings = portfolio_state.get("holdings", {})

        candidates = []
        market_deterioration = market_data.get("deterioration", False)

        for event in list(self._event_pool):
            conditions = event.get("conditions", {})
            event_symbol = event.get("symbol", "")
            event_sector = conditions.get("sector", None)

            is_loss_event = conditions.get("return_pct", 0) < loss_threshold
            is_held = event_symbol in held_symbols
            is_market_bad = market_deterioration or conditions.get("market_deterioration", False)

            if is_loss_event or is_held or is_market_bad or event_sector:
                base_priority = 0.3

                individual_score = 0.0
                if is_loss_event:
                    loss_pct = abs(conditions.get("return_pct", 0))
                    individual_score = min(loss_pct / 0.1, 1.0) * 0.4

                sector_score = 0.0
                if event_sector and event_sector in sector_performance:
                    sector_change = sector_performance[event_sector]
                    if sector_change < 0:
                        sector_score = min(abs(sector_change) / 0.05, 1.0) * 0.3

                concentration_score = 0.0
                if event_symbol in holdings:
                    weight = holdings[event_symbol].get("weight", 0)
                    concentration_score = weight * 0.2

                relative_score = 0.0
                if is_held and event_sector:
                    stock_change = conditions.get("return_pct", 0)
                    sector_change = sector_performance.get(event_sector, 0)
                    if stock_change < sector_change:
                        relative_score = min(abs(stock_change - sector_change) / 0.03, 1.0) * 0.1

                held_bonus = 0.15 if is_held else 0

                priority = base_priority + individual_score + sector_score + concentration_score + relative_score + held_bonus

                age = time.time() - event["timestamp"]
                priority *= (1.0 - min(age / 7200, 0.5))

                candidates.append(RecalledEvent(
                    event_type=event["event_type"],
                    symbol=event_symbol,
                    content=event["content"],
                    confidence=event["confidence"],
                    priority=priority,
                    conditions={
                        **conditions,
                        "_individual_score": individual_score,
                        "_sector_score": sector_score,
                        "_concentration_score": concentration_score,
                        "_relative_score": relative_score,
                    }
                ))

        candidates.sort(key=lambda x: x.priority, reverse=True)
        self._focus_history.append({"focus": "stop_loss", "recalled": len(candidates)})
        log.info(f"[EventRecall] 召回止损事件 {len(candidates)} 个")
        return candidates[:limit]

    def _recall_take_profit_events(
        self,
        portfolio_state: Dict[str, Any],
        market_data: Dict[str, Any],
        limit: int
    ) -> List[RecalledEvent]:
        """召回止盈相关事件"""
        profit_threshold = portfolio_state.get("take_profit_threshold", 0.10)
        held_symbols = set(portfolio_state.get("held_symbols", []))

        candidates = []
        market_strength = market_data.get("strength", 0.5)

        for event in list(self._event_pool):
            conditions = event.get("conditions", {})
            event_symbol = event.get("symbol", "")

            is_profit_event = conditions.get("return_pct", 0) > profit_threshold
            is_held = event_symbol in held_symbols
            is_profit_taking_signal = conditions.get("profit_taking_signal", False)

            if is_profit_event or is_held or is_profit_taking_signal:
                priority = 0.5
                if is_profit_event:
                    priority += conditions.get("return_pct", 0) * 3
                if market_strength < 0.4:
                    priority += 0.4
                if is_held:
                    priority += 0.1

                age = time.time() - event["timestamp"]
                priority *= (1.0 - min(age / 7200, 0.5))

                candidates.append(RecalledEvent(
                    event_type=event["event_type"],
                    symbol=event_symbol,
                    content=event["content"],
                    confidence=event["confidence"],
                    priority=priority,
                    conditions=conditions
                ))

        candidates.sort(key=lambda x: x.priority, reverse=True)
        self._focus_history.append({"focus": "take_profit", "recalled": len(candidates)})
        log.info(f"[EventRecall] 召回止盈事件 {len(candidates)} 个")
        return candidates[:limit]

    def _recall_rebalance_events(
        self,
        portfolio_state: Dict[str, Any],
        market_data: Dict[str, Any],
        limit: int
    ) -> List[RecalledEvent]:
        """召回再平衡相关事件"""
        sector_alloc = portfolio_state.get("sector_allocations", {})
        target_alloc = portfolio_state.get("target_allocations", {})

        candidates = []

        for event in list(self._event_pool):
            conditions = event.get("conditions", {})
            event_sector = conditions.get("sector", "")

            if event_sector in sector_alloc:
                current_weight = sector_alloc.get(event_sector, 0)
                target_weight = target_alloc.get(event_sector, current_weight)
                deviation = abs(current_weight - target_weight)

                if deviation > 0.05:
                    priority = deviation * 5
                    age = time.time() - event["timestamp"]
                    priority *= (1.0 - min(age / 7200, 0.5))

                    candidates.append(RecalledEvent(
                        event_type=event["event_type"],
                        symbol=event.get("symbol", ""),
                        content=event["content"],
                        confidence=event["confidence"],
                        priority=priority,
                        conditions=conditions
                    ))

        candidates.sort(key=lambda x: x.priority, reverse=True)
        self._focus_history.append({"focus": "rebalance", "recalled": len(candidates)})
        return candidates[:limit]

    def _recall_accumulate_events(
        self,
        portfolio_state: Dict[str, Any],
        market_data: Dict[str, Any],
        limit: int
    ) -> List[RecalledEvent]:
        """召回加仓相关事件"""
        cash_ratio = portfolio_state.get("cash_ratio", 0.5)
        market_opportunity = market_data.get("opportunity_score", 0.5)

        candidates = []

        for event in list(self._event_pool):
            conditions = event.get("conditions", {})
            is_uptrend = conditions.get("trend", 0) > 0.3
            is_support = conditions.get("support_level", False)

            if (cash_ratio > 0.3 and market_opportunity > 0.6) or is_uptrend or is_support:
                priority = 0.3
                if is_uptrend:
                    priority += 0.3
                if is_support:
                    priority += 0.2
                if market_opportunity > 0.7:
                    priority += 0.2

                age = time.time() - event["timestamp"]
                priority *= (1.0 - min(age / 7200, 0.5))

                candidates.append(RecalledEvent(
                    event_type=event["event_type"],
                    symbol=event.get("symbol", ""),
                    content=event["content"],
                    confidence=event["confidence"],
                    priority=priority,
                    conditions=conditions
                ))

        candidates.sort(key=lambda x: x.priority, reverse=True)
        self._focus_history.append({"focus": "accumulate", "recalled": len(candidates)})
        return candidates[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "event_pool_size": len(self._event_pool),
            "recent_focus": self._focus_history[-10:] if self._focus_history else [],
        }