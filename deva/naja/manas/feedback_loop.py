"""
ManasFeedbackLoop - 末那识闭环反馈

记录决策→召回→结果的完整闭环，用于 MetaManas 学习优化
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

log = logging.getLogger(__name__)


class OutcomeType(Enum):
    """结果类型"""
    PROFIT = "profit"
    LOSS = "loss"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    NEUTRAL = "neutral"


@dataclass
class FeedbackRecord:
    """反馈记录"""
    timestamp: float
    attention_focus: str
    recalled_event_count: int
    outcome_type: OutcomeType
    pnl_pct: float
    market_regime: str
    harmony_state: str
    success: bool


class ManasFeedbackLoop:
    """
    末那识闭环反馈系统

    记录每次决策的完整闭环：
    1. ManasOutput (attention_focus, harmony_state, etc.)
    2. 召回的事件列表
    3. 执行结果 (pnl, market_state)

    用于 MetaManas 学习优化不同场景下哪种 focus 更有效
    """

    def __init__(self, max_records: int = 1000):
        self._records: deque = deque(maxlen=max_records)
        self._focus_effectiveness: Dict[str, List[float]] = {}
        self._regime_focus_performance: Dict[str, Dict[str, List[float]]] = {}

    def record(
        self,
        attention_focus: str,
        harmony_state: str,
        recalled_event_count: int,
        outcome: Dict[str, Any],
        market_data: Dict[str, Any]
    ):
        """
        记录一次闭环

        Args:
            attention_focus: 决策时的注意力聚焦
            harmony_state: 决策时的和谐状态
            recalled_event_count: 召回的事件数量
            outcome: 执行结果，包含 pnl_pct, outcome_type 等
            market_data: 市场数据，包含 regime 等
        """
        pnl_pct = outcome.get("pnl_pct", 0.0)
        outcome_type_str = outcome.get("outcome_type", "neutral")

        try:
            outcome_type = OutcomeType(outcome_type_str)
        except ValueError:
            outcome_type = OutcomeType.NEUTRAL

        success = pnl_pct > 0 if outcome_type in [OutcomeType.PROFIT, OutcomeType.TAKE_PROFIT] else pnl_pct >= 0

        record = FeedbackRecord(
            timestamp=time.time(),
            attention_focus=attention_focus,
            recalled_event_count=recalled_event_count,
            outcome_type=outcome_type,
            pnl_pct=pnl_pct,
            market_regime=market_data.get("regime", "unknown"),
            harmony_state=harmony_state,
            success=success
        )

        self._records.append(record)

        self._update_effectiveness(attention_focus, pnl_pct, success)
        self._update_regime_focus_performance(
            market_data.get("regime", "unknown"),
            attention_focus,
            pnl_pct,
            success
        )

        log.info(f"[FeedbackLoop] 记录闭环: focus={attention_focus}, pnl={pnl_pct:.2%}, success={success}")

    def _update_effectiveness(
        self,
        focus: str,
        pnl_pct: float,
        success: bool
    ):
        """更新 focus 的有效性统计"""
        if focus not in self._focus_effectiveness:
            self._focus_effectiveness[focus] = []

        self._focus_effectiveness[focus].append(pnl_pct)
        if len(self._focus_effectiveness[focus]) > 50:
            self._focus_effectiveness[focus].pop(0)

    def _update_regime_focus_performance(
        self,
        regime: str,
        focus: str,
        pnl_pct: float,
        success: bool
    ):
        """更新不同市场环境下 focus 的表现"""
        if regime not in self._regime_focus_performance:
            self._regime_focus_performance[regime] = {}

        if focus not in self._regime_focus_performance[regime]:
            self._regime_focus_performance[regime][focus] = []

        self._regime_focus_performance[regime][focus].append(pnl_pct)
        if len(self._regime_focus_performance[regime][focus]) > 30:
            self._regime_focus_performance[regime][focus].pop(0)

    def get_focus_effectiveness(self, focus: str) -> Dict[str, float]:
        """
        获取某种 attention_focus 的历史有效性

        Returns:
            包含 avg_pnl, win_rate, sample_count 的字典
        """
        if focus not in self._focus_effectiveness:
            return {"avg_pnl": 0.0, "win_rate": 0.5, "sample_count": 0}

        pnls = self._focus_effectiveness[focus]
        wins = sum(1 for p in pnls if p > 0)

        return {
            "avg_pnl": sum(pnls) / len(pnls) if pnls else 0.0,
            "win_rate": wins / len(pnls) if pnls else 0.5,
            "sample_count": len(pnls)
        }

    def get_best_focus_for_regime(self, regime: str) -> Optional[str]:
        """
        获取某种市场环境下最有效的 focus

        Returns:
            最佳 focus 字符串，或 None
        """
        if regime not in self._regime_focus_performance:
            return None

        focus_perfs = self._regime_focus_performance[regime]
        if not focus_perfs:
            return None

        best_focus = None
        best_avg = float('-inf')

        for focus, pnls in focus_perfs.items():
            if len(pnls) >= 3:
                avg = sum(pnls) / len(pnls)
                if avg > best_avg:
                    best_avg = avg
                    best_focus = focus

        return best_focus

    def get_focus_recommendation(
        self,
        current_regime: str,
        portfolio_loss: float,
        market_deterioration: bool
    ) -> str:
        """
        基于历史学习获取 focus 推荐

        Args:
            current_regime: 当前市场环境
            portfolio_loss: 持仓亏损百分比
            market_deterioration: 市场是否恶化

        Returns:
            推荐的 attention_focus
        """
        if portfolio_loss < -0.08 and market_deterioration:
            return "stop_loss"

        if portfolio_loss > 0.15 and market_deterioration:
            return "take_profit"

        best_focus = self.get_best_focus_for_regime(current_regime)
        if best_focus:
            return best_focus

        return "watch"

    def get_recent_records(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的反馈记录"""
        records = list(self._records)[-limit:]
        return [
            {
                "timestamp": r.timestamp,
                "attention_focus": r.attention_focus,
                "pnl_pct": r.pnl_pct,
                "success": r.success,
                "market_regime": r.market_regime
            }
            for r in records
        ]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        focus_stats = {}
        for focus in self._focus_effectiveness:
            focus_stats[focus] = self.get_focus_effectiveness(focus)

        return {
            "total_records": len(self._records),
            "focus_effectiveness": focus_stats,
            "regime_count": len(self._regime_focus_performance)
        }