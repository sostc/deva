"""
LiquidityCognition - 流动性认知协调器

核心功能：
1. 接收来自 Radar 的全球市场事件
2. 通过 PropagationEngine 进行流动性传播
3. 生成认知洞察并反馈到 Attention 系统
4. 管理全球市场状态的统一视图

闭环流程：
Radar (GlobalMarketScanner) → InsightPool → LiquidityCognition → Attention
                                ↑                               ↓
                                └─────────── Feedback ─────────┘
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

from deva.naja.cognition.liquidity.propagation_engine import (
    PropagationEngine,
    PropagationSignal,
)
from deva.naja.cognition.liquidity.global_market_config import (
    MARKET_CONFIGS,
    get_market_config,
)

log = logging.getLogger(__name__)


@dataclass
class GlobalMarketInsight:
    """全球市场洞察"""
    insight_type: str
    source_market: str
    target_markets: List[str]
    severity: float
    propagation_probability: float
    narrative: Optional[str]
    timestamp: float
    raw_data: Dict[str, Any]


class LiquidityCognition:
    """
    流动性认知协调器

    职责：
    1. 接收全球市场事件（从 Radar 的 GlobalMarketScanner）
    2. 更新 PropagationEngine 中的市场状态
    3. 触发流动性传播
    4. 生成认知洞察
    5. 反馈到 Attention 系统
    """

    def __init__(self):
        self._propagation_engine = PropagationEngine()
        self._propagation_engine.initialize()

        self._callbacks: List[callable] = []
        self._insights_history: List[GlobalMarketInsight] = []

        self._market_states: Dict[str, Dict[str, Any]] = {}

        self._stats = {
            "events_received": 0,
            "propagations_triggered": 0,
            "insights_generated": 0,
            "last_event_time": 0,
        }

        self._auto_emit_to_insight_pool = True

    def register_callback(self, callback: callable):
        """注册回调，接收认知洞察"""
        self._callbacks.append(callback)

    def ingest_global_market_event(self, event: Dict[str, Any]) -> Optional[GlobalMarketInsight]:
        """
        处理来自 Radar 的全球市场事件

        Args:
            event: RadarEvent 转换的 dict，应包含：
                - market_id: 市场标识 (如 "nasdaq100", "nvda")
                - current: 当前价格
                - change_pct: 涨跌幅
                - volume: 成交量
                - name: 市场名称
                - is_abnormal: 是否异常

        Returns:
            GlobalMarketInsight: 生成的洞察
        """
        self._stats["events_received"] += 1
        self._stats["last_event_time"] = time.time()

        market_id = event.get("market_id", "")
        current = event.get("current", 0)
        change_pct = event.get("change_pct", 0)
        volume = event.get("volume", 0)
        is_abnormal = event.get("is_abnormal", False)

        if not market_id or current == 0:
            return None

        node = self._propagation_engine._nodes.get(market_id)
        if not node:
            config = get_market_config(market_id)
            if config:
                from deva.naja.cognition.liquidity.market_node import MarketNode
                node = MarketNode(
                    market_id=market_id,
                    name=config.name,
                    market_type=config.market_type,
                )
                self._propagation_engine._nodes[market_id] = node
            else:
                log.debug(f"[LiquidityCognition] 市场 {market_id} 不在配置中，跳过传播")

        self._market_states[market_id] = {
            "current": current,
            "change_pct": change_pct,
            "volume": volume,
            "is_abnormal": is_abnormal,
            "timestamp": time.time(),
        }

        severity = abs(change_pct) / 5.0
        severity = min(1.0, severity)

        narrative_score = severity if is_abnormal else severity * 0.5

        if node is not None:
            state = self._propagation_engine.update_market(
                market_id=market_id,
                price=current,
                volume=volume,
                narrative_score=narrative_score,
            )
            propagation_signals = self._get_pending_propagations(market_id)
        else:
            propagation_signals = []

        insight = GlobalMarketInsight(
            insight_type="global_market_alert" if is_abnormal else "global_market_update",
            source_market=market_id,
            target_markets=[sig.to_market for sig in propagation_signals],
            severity=severity,
            propagation_probability=sum(s.propagation_probability for s in propagation_signals) / len(propagation_signals) if propagation_signals else 0,
            narrative=self._determine_narrative(change_pct, is_abnormal),
            timestamp=time.time(),
            raw_data=event,
        )

        self._insights_history.append(insight)
        self._stats["propagations_triggered"] += len(propagation_signals)
        self._stats["insights_generated"] += 1

        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(insight))
                else:
                    callback(insight)
            except Exception as e:
                log.error(f"[LiquidityCognition] 回调异常: {e}")

        self.emit_insight_to_pool(insight)

        return insight

    def _get_pending_propagations(self, from_market: str) -> List[PropagationSignal]:
        """获取待传播的信号"""
        signals = []
        for edge_key, edge in self._propagation_engine._edges.items():
            if edge.from_market == from_market:
                pending = edge.get_pending_events()
                if pending:
                    signal = PropagationSignal(
                        from_market=from_market,
                        to_market=edge.to_market,
                        timestamp=time.time(),
                        change=pending[0].predicted_change if pending else 0,
                        propagation_probability=edge.get_propagation_probability(),
                        status="pending",
                    )
                    signals.append(signal)
        return signals

    def _determine_narrative(self, change_pct: float, is_abnormal: bool) -> str:
        """确定叙事"""
        if is_abnormal:
            if change_pct > 0:
                return "全球市场恐慌性上涨"
            else:
                return "全球市场恐慌性下跌"
        else:
            if abs(change_pct) > 3:
                if change_pct > 0:
                    return "全球市场显著上涨"
                else:
                    return "全球市场显著下跌"
        return "全球市场波动"

    def get_market_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有市场状态"""
        return self._market_states.copy()

    def get_market_state(self, market_id: str) -> Optional[Dict[str, Any]]:
        """获取特定市场状态"""
        return self._market_states.get(market_id)

    def get_propagation_engine(self) -> PropagationEngine:
        """获取传播引擎"""
        return self._propagation_engine

    def get_insights(self, limit: int = 20) -> List[GlobalMarketInsight]:
        """获取最近的洞察"""
        return self._insights_history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "tracked_markets": list(self._market_states.keys()),
            "insights_in_history": len(self._insights_history),
        }

    def get_summary(self) -> Dict[str, Any]:
        """获取认知摘要"""
        if not self._market_states:
            return {}

        summary = {
            "total_markets": len(self._market_states),
            "abnormal_markets": [],
            "severe_markets": [],
            "global_sentiment": "neutral",
        }

        for market_id, state in self._market_states.items():
            if state.get("is_abnormal"):
                summary["abnormal_markets"].append({
                    "market_id": market_id,
                    "change_pct": state["change_pct"],
                })
            if abs(state.get("change_pct", 0)) > 3:
                summary["severe_markets"].append({
                    "market_id": market_id,
                    "change_pct": state["change_pct"],
                })

        all_changes = [s.get("change_pct", 0) for s in self._market_states.values()]
        avg_change = sum(all_changes) / len(all_changes) if all_changes else 0

        if avg_change > 1:
            summary["global_sentiment"] = "bullish"
        elif avg_change < -1:
            summary["global_sentiment"] = "bearish"

        return summary

    def emit_insight_to_pool(self, insight: GlobalMarketInsight) -> None:
        """将洞察发送到 InsightPool（形成完整闭环）"""
        if not self._auto_emit_to_insight_pool:
            return

        try:
            from deva.naja.cognition.insight import emit_to_insight_pool

            summary = self.get_summary()

            insight_data = {
                "source": "liquidity_cognition",
                "signal_type": f"global_market_{insight.insight_type}",
                "theme": f"🌍 {insight.narrative}",
                "summary": f"{insight.source_market} → {', '.join(insight.target_markets) if insight.target_markets else '全球'}",
                "system_attention": insight.severity,
                "confidence": insight.propagation_probability,
                "actionability": insight.severity * insight.propagation_probability,
                "novelty": 0.6,
                "payload": {
                    "source_market": insight.source_market,
                    "target_markets": insight.target_markets,
                    "severity": insight.severity,
                    "propagation_probability": insight.propagation_probability,
                    "narrative": insight.narrative,
                    "global_sentiment": summary.get("global_sentiment", "neutral"),
                    "abnormal_count": len(summary.get("abnormal_markets", [])),
                    "raw_data": insight.raw_data,
                },
                "timestamp": insight.timestamp,
            }

            emit_to_insight_pool(insight_data)
            log.info(f"[LiquidityCognition] 洞察已发送到 InsightPool: {insight.narrative}")

        except ImportError as e:
            log.warning(f"[LiquidityCognition] 无法导入 InsightPool: {e}")
        except Exception as e:
            log.error(f"[LiquidityCognition] 发送洞察失败: {e}")


_liquidity_cognition: Optional[LiquidityCognition] = None


def get_liquidity_cognition() -> LiquidityCognition:
    """获取全局流动性认知实例"""
    global _liquidity_cognition
    if _liquidity_cognition is None:
        _liquidity_cognition = LiquidityCognition()
    return _liquidity_cognition
