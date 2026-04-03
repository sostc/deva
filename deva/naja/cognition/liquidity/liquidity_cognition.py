"""
LiquidityCognition - 认知系统/流动性认知/跨市场

别名/关键词: 流动性、跨市场、全球流动性、propagation、liquidity、跨市场传导

核心功能：
1. 接收来自 Radar 的全球市场事件
2. 通过 PropagationEngine 进行流动性传播
3. 生成认知洞察并反馈到 Attention 系统
4. 管理全球市场状态的统一视图
5. 预测跟踪和验证机制（新增）

闭环流程：
Radar (GlobalMarketScanner) → LiquidityCognition → Signal 查询
                                      ↓
                               PredictionTracker
                                      ↓
                                验证/取消/确认

时间维度预测系统设计：
1. PredictionTracker - 跟踪所有活跃预测
2. 自动验证循环 - 定期验证 pending 预测
3. 预测查询接口 - get_active_prediction() 供 Signal 使用
4. 取消机制 - 当出现反向事件时取消预测
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

from deva.naja.cognition.liquidity.propagation_engine import (
    PropagationEngine,
    PropagationSignal,
    MARKET_ID_MAP,
)
from deva.naja.cognition.liquidity.global_market_config import (
    MARKET_CONFIGS,
    get_market_config,
)
from deva.naja.cognition.liquidity.verification_scheduler import (
    LiquidityVerificationScheduler,
    VerificationSchedule,
)
from deva.naja.cognition.liquidity.notifier import get_notifier

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


class PredictionStatus(Enum):
    """预测状态"""
    PENDING = "pending"      # 待验证
    CONFIRMED = "confirmed"  # 已确认（预测正确）
    DENIED = "denied"       # 已否认（预测错误）
    CANCELLED = "cancelled" # 已取消（被反向事件取消）


@dataclass
class LiquidityPrediction:
    """
    流动性预测

    表示一个"市场A变化 → 市场B会跟跌/跟涨"的预测
    """
    id: str
    from_market: str           # 源市场
    to_market: str             # 目标市场
    direction: str             # "up" 或 "down"
    probability: float         # 预测置信度
    status: PredictionStatus   # 状态
    created_at: float          # 创建时间
    verify_at: float           # 验证时间
    cancelled_at: Optional[float] = None
    cancel_reason: Optional[str] = None
    confirmed_at: Optional[float] = None
    denied_at: Optional[float] = None

    # 关联的边信息
    edge_key: Optional[str] = None
    source_change: Optional[float] = None

    def is_active(self) -> bool:
        """是否还是活跃预测"""
        return self.status == PredictionStatus.PENDING

    def is_timed_out(self, current_time: float) -> bool:
        """是否超时"""
        return current_time > self.verify_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "from_market": self.from_market,
            "to_market": self.to_market,
            "direction": self.direction,
            "probability": self.probability,
            "status": self.status.value,
            "created_at": self.created_at,
            "verify_at": self.verify_at,
            "is_active": self.is_active(),
        }


class PredictionTracker:
    """
    预测跟踪器

    核心职责：
    1. 跟踪所有活跃预测
    2. 定期验证预测
    3. 提供预测查询接口
    4. 处理预测取消
    """

    def __init__(self, propagation_engine: PropagationEngine):
        self._propagation_engine = propagation_engine

        # 活跃预测: id -> LiquidityPrediction
        self._predictions: Dict[str, LiquidityPrediction] = {}

        # 按目标市场索引: to_market -> [prediction_ids]
        self._predictions_by_target: Dict[str, List[str]] = {}

        # 按状态索引: status -> [prediction_ids]
        self._predictions_by_status: Dict[PredictionStatus, List[str]] = {
            PredictionStatus.PENDING: [],
            PredictionStatus.CONFIRMED: [],
            PredictionStatus.DENIED: [],
            PredictionStatus.CANCELLED: [],
        }

        # 历史记录（用于统计分析）
        self._history: deque = deque(maxlen=1000)

        # 配置
        self._default_verify_minutes = 30  # 默认30分钟后验证
        self._max_pending_age = 2 * 3600   # 最大pending时间2小时

        # 统计
        self._stats = {
            "total_created": 0,
            "total_confirmed": 0,
            "total_denied": 0,
            "total_cancelled": 0,
        }

    def create_prediction(
        self,
        from_market: str,
        to_market: str,
        direction: str,
        probability: float,
        verify_minutes: Optional[float] = None,
        source_change: Optional[float] = None,
    ) -> str:
        """
        创建新预测

        Args:
            from_market: 源市场
            to_market: 目标市场
            direction: "up" 或 "down"
            probability: 预测置信度
            verify_minutes: 多少分钟后验证，默认30分钟
            source_change: 源市场变化幅度

        Returns:
            prediction_id
        """
        if verify_minutes is None:
            verify_minutes = self._default_verify_minutes

        prediction_id = f"liq_pred_{uuid.uuid4().hex[:12]}"

        prediction = LiquidityPrediction(
            id=prediction_id,
            from_market=from_market,
            to_market=to_market,
            direction=direction,
            probability=probability,
            status=PredictionStatus.PENDING,
            created_at=time.time(),
            verify_at=time.time() + verify_minutes * 60,
            edge_key=f"{from_market}->{to_market}",
            source_change=source_change,
        )

        self._predictions[prediction_id] = prediction
        self._predictions_by_target.setdefault(to_market, []).append(prediction_id)
        self._predictions_by_status[PredictionStatus.PENDING].append(prediction_id)
        self._stats["total_created"] += 1

        log.info(f"[PredictionTracker] 创建预测 {prediction_id}: {from_market} → {to_market} ({direction}), 验证时间: {verify_minutes}分钟后")

        return prediction_id

    def create_prediction_with_schedule(
        self,
        from_market: str,
        to_market: str,
        direction: str,
        probability: float,
        source_change: Optional[float] = None,
        schedule: Optional[VerificationSchedule] = None,
    ) -> str:
        """
        创建新预测（使用智能调度）

        Args:
            from_market: 源市场
            to_market: 目标市场
            direction: "up" 或 "down"
            probability: 预测置信度
            source_change: 源市场变化幅度
            schedule: 验证时间调度

        Returns:
            prediction_id
        """
        prediction_id = f"liq_pred_{uuid.uuid4().hex[:12]}"

        if schedule:
            verify_at = schedule.verify_at
            verify_reason = schedule.verify_type
        else:
            verify_at = time.time() + self._default_verify_minutes * 60
            verify_reason = "default"

        prediction = LiquidityPrediction(
            id=prediction_id,
            from_market=from_market,
            to_market=to_market,
            direction=direction,
            probability=probability,
            status=PredictionStatus.PENDING,
            created_at=time.time(),
            verify_at=verify_at,
            edge_key=f"{from_market}->{to_market}",
            source_change=source_change,
        )

        self._predictions[prediction_id] = prediction
        self._predictions_by_target.setdefault(to_market, []).append(prediction_id)
        self._predictions_by_status[PredictionStatus.PENDING].append(prediction_id)
        self._stats["total_created"] += 1

        from datetime import datetime
        verify_time_str = datetime.fromtimestamp(verify_at).strftime("%H:%M:%S")
        log.info(f"[PredictionTracker] 创建预测 {prediction_id}: {from_market} → {to_market} ({direction}), 验证时间：{verify_time_str} ({verify_reason})")

        # 发送通知（高置信度预测）
        if probability > 0.7:
            notifier = get_notifier()
            verify_minutes = (verify_at - time.time()) / 60
            notifier.send_prediction_created(
                from_market=from_market,
                to_market=to_market,
                direction=direction,
                probability=probability,
                source_change=source_change or 0,
                verify_minutes=verify_minutes,
            )

        return prediction_id

    def get_active_prediction(self, to_market: str) -> Optional[LiquidityPrediction]:
        """
        获取目标市场的活跃预测（供 Signal 查询）

        Args:
            to_market: 目标市场

        Returns:
            最近的 pending 预测，如果没有则返回 None
        """
        prediction_ids = self._predictions_by_target.get(to_market, [])
        if not prediction_ids:
            return None

        # 找最近的 pending 预测
        for pred_id in reversed(prediction_ids):
            pred = self._predictions.get(pred_id)
            if pred and pred.status == PredictionStatus.PENDING:
                return pred

        return None

    def get_prediction(self, prediction_id: str) -> Optional[LiquidityPrediction]:
        """获取单个预测"""
        return self._predictions.get(prediction_id)

    def get_active_predictions(
        self,
        to_markets: Optional[List[str]] = None,
        direction: Optional[str] = None,
    ) -> List[LiquidityPrediction]:
        """
        获取活跃预测列表

        Args:
            to_markets: 目标市场列表，None 表示所有
            direction: 方向过滤，"up" 或 "down"

        Returns:
            符合条件的活跃预测列表
        """
        results = []

        markets_to_check = to_markets or list(self._predictions_by_target.keys())

        for market in markets_to_check:
            pred_id = self._predictions_by_target.get(market, [])
            for pred_id in pred_id:
                pred = self._predictions.get(pred_id)
                if not pred or pred.status != PredictionStatus.PENDING:
                    continue
                if direction and pred.direction != direction:
                    continue
                results.append(pred)

        return results

    def cancel_prediction(self, prediction_id: str, reason: str) -> bool:
        """
        取消预测（当出现反向事件时调用）

        Args:
            prediction_id: 预测ID
            reason: 取消原因

        Returns:
            是否成功取消
        """
        prediction = self._predictions.get(prediction_id)
        if not prediction:
            return False

        if prediction.status != PredictionStatus.PENDING:
            log.debug(f"[PredictionTracker] 预测 {prediction_id} 状态不是 PENDING，无法取消: {prediction.status}")
            return False

        prediction.status = PredictionStatus.CANCELLED
        prediction.cancelled_at = time.time()
        prediction.cancel_reason = reason

        # 更新索引
        self._predictions_by_status[PredictionStatus.PENDING].remove(prediction_id)
        self._predictions_by_status[PredictionStatus.CANCELLED].append(prediction_id)
        self._stats["total_cancelled"] += 1

        log.info(f"[PredictionTracker] 取消预测 {prediction_id}: {reason}")

        # 记录到历史
        self._history.append(prediction.to_dict())

        return True

    def cancel_predictions_for_market(
        self,
        to_market: str,
        reason: str,
        direction: Optional[str] = None,
    ) -> int:
        """
        取消某个目标市场的所有预测（通常是因为出现了反向信号）

        Args:
            to_market: 目标市场
            reason: 取消原因
            direction: 如果指定，只取消这个方向的预测

        Returns:
            取消了几个预测
        """
        cancelled_count = 0
        prediction_ids = self._predictions_by_target.get(to_market, []).copy()

        for pred_id in prediction_ids:
            pred = self._predictions.get(pred_id)
            if not pred or pred.status != PredictionStatus.PENDING:
                continue
            if direction and pred.direction != direction:
                continue

            if self.cancel_prediction(pred_id, reason):
                cancelled_count += 1

        return cancelled_count

    def verify_prediction(
        self,
        prediction_id: str,
        actual_direction: str,
        actual_change: float,
    ) -> bool:
        """
        验证预测是否正确

        Args:
            prediction_id: 预测ID
            actual_direction: 实际方向 "up" 或 "down"
            actual_change: 实际变化幅度

        Returns:
            预测是否验证通过
        """
        prediction = self._predictions.get(prediction_id)
        if not prediction:
            return False

        if prediction.status != PredictionStatus.PENDING:
            log.debug(f"[PredictionTracker] 预测 {prediction_id} 状态不是 PENDING: {prediction.status}")
            return False

        # 检查方向是否匹配
        verified = prediction.direction == actual_direction

        if verified:
            prediction.status = PredictionStatus.CONFIRMED
            prediction.confirmed_at = time.time()
            self._predictions_by_status[PredictionStatus.PENDING].remove(prediction_id)
            self._predictions_by_status[PredictionStatus.CONFIRMED].append(prediction_id)
            self._stats["total_confirmed"] += 1

            log.info(f"[PredictionTracker] 预测 {prediction_id} 验证通过：{prediction.direction} == {actual_direction}")

            # 增强边权重
            self._boost_edge(prediction.edge_key)

            # 发送通知（高置信度预测验证成功）
            if prediction.probability > 0.7:
                notifier = get_notifier()
                notifier.send_prediction_confirmed(
                    from_market=prediction.from_market,
                    to_market=prediction.to_market,
                    direction=prediction.direction,
                    probability=prediction.probability,
                    actual_change=actual_change,
                )
        else:
            prediction.status = PredictionStatus.DENIED
            prediction.denied_at = time.time()
            self._predictions_by_status[PredictionStatus.PENDING].remove(prediction_id)
            self._predictions_by_status[PredictionStatus.DENIED].append(prediction_id)
            self._stats["total_denied"] += 1

            log.info(f"[PredictionTracker] 预测 {prediction_id} 验证失败：{prediction.direction} != {actual_direction}")

            # 衰减边权重
            self._decay_edge(prediction.edge_key)

            # 发送通知（预测验证失败）
            notifier = get_notifier()
            notifier.send_prediction_denied(
                from_market=prediction.from_market,
                to_market=prediction.to_market,
                direction=prediction.direction,
                probability=prediction.probability,
                actual_change=actual_change,
                reason="direction_mismatch",
            )

        # 记录到历史
        self._history.append(prediction.to_dict())

        return verified

    def _boost_edge(self, edge_key: Optional[str]):
        """增强边权重"""
        if not edge_key:
            return
        edge = self._propagation_engine._edges.get(edge_key)
        if edge:
            edge._boost_weight()

    def _decay_edge(self, edge_key: Optional[str]):
        """衰减边权重"""
        if not edge_key:
            return
        edge = self._propagation_engine._edges.get(edge_key)
        if edge:
            edge._decay_weight()

    def verify_and_update(self, current_time: Optional[float] = None) -> Dict[str, int]:
        """
        验证所有超时的预测（自动验证循环调用）

        Args:
            current_time: 当前时间，默认 time.time()

        Returns:
            验证统计 {"confirmed": N, "denied": N, "cancelled": N}
        """
        if current_time is None:
            current_time = time.time()

        stats = {"confirmed": 0, "denied": 0, "cancelled": 0, "still_pending": 0}

        pending_ids = self._predictions_by_status[PredictionStatus.PENDING].copy()

        for pred_id in pending_ids:
            prediction = self._predictions.get(pred_id)
            if not prediction:
                continue

            # 检查是否超时
            if current_time > prediction.verify_at:
                # 超时未验证，视为失败
                prediction.status = PredictionStatus.DENIED
                prediction.denied_at = current_time
                prediction.cancel_reason = "timeout"

                self._predictions_by_status[PredictionStatus.PENDING].remove(pred_id)
                self._predictions_by_status[PredictionStatus.DENIED].append(pred_id)
                self._stats["total_denied"] += 1
                stats["denied"] += 1

                # 衰减边
                self._decay_edge(prediction.edge_key)

                log.debug(f"[PredictionTracker] 预测 {pred_id} 超时未验证，标记为 DENIED")

                # 记录到历史
                self._history.append(prediction.to_dict())
            else:
                stats["still_pending"] += 1

        return stats

    def cleanup_old_predictions(self, max_age_hours: float = 24):
        """清理过老的预测"""
        current_time = time.time()
        cutoff = current_time - max_age_hours * 3600

        to_remove = []
        for pred_id, pred in self._predictions.items():
            if pred.status != PredictionStatus.PENDING:
                if pred.confirmed_at and pred.confirmed_at < cutoff:
                    to_remove.append(pred_id)
                elif pred.denied_at and pred.denied_at < cutoff:
                    to_remove.append(pred_id)
                elif pred.cancelled_at and pred.cancelled_at < cutoff:
                    to_remove.append(pred_id)

        for pred_id in to_remove:
            del self._predictions[pred_id]

        if to_remove:
            log.debug(f"[PredictionTracker] 清理了 {len(to_remove)} 个过老预测")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "active_count": len(self._predictions_by_status[PredictionStatus.PENDING]),
            "total_predictions": len(self._predictions),
        }

    def get_prediction_rate(self) -> float:
        """获取预测准确率"""
        total = self._stats["total_confirmed"] + self._stats["total_denied"]
        if total == 0:
            return 0.5  # 无数据时返回0.5
        return self._stats["total_confirmed"] / total


class LiquidityCognition:
    """
    流动性认知协调器

    职责：
    1. 接收全球市场事件（从 Radar 的 GlobalMarketScanner）
    2. 更新 PropagationEngine 中的市场状态
    3. 触发流动性传播并创建预测
    4. 生成认知洞察
    5. 反馈到 Attention 系统
    6. 预测跟踪和验证（新功能）
    """

    def __init__(self):
        self._propagation_engine = PropagationEngine()
        self._propagation_engine.initialize()

        # 预测跟踪器（新）
        self._prediction_tracker = PredictionTracker(self._propagation_engine)

        # 智能验证调度器
        self._verification_scheduler = LiquidityVerificationScheduler()

        self._callbacks: List[callable] = []
        self._insights_history: List[GlobalMarketInsight] = []

        self._market_states: Dict[str, Dict[str, Any]] = {}

        self._stats = {
            "events_received": 0,
            "propagations_triggered": 0,
            "insights_generated": 0,
            "last_event_time": 0,
            "predictions_created": 0,
        }

        self._auto_emit_to_insight_pool = True

        # 验证循环
        self._verification_interval = 60  # 每60秒验证一次
        self._last_verification_time = 0.0

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

        mapped_market_id = MARKET_ID_MAP.get(market_id, market_id)

        node = self._propagation_engine._nodes.get(mapped_market_id)
        if not node:
            config = get_market_config(mapped_market_id)
            if config:
                from deva.naja.cognition.liquidity.market_node import MarketNode
                node = MarketNode(
                    market_id=mapped_market_id,
                    name=config.name,
                    market_type=config.market_type,
                )
                self._propagation_engine._nodes[mapped_market_id] = node
            else:
                log.debug(f"[LiquidityCognition] 市场 {mapped_market_id} 不在配置中，跳过传播")

        self._market_states[mapped_market_id] = {
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
                market_id=mapped_market_id,
                price=current,
                volume=volume,
                narrative_score=narrative_score,
            )
            propagation_signals = self._get_pending_propagations(mapped_market_id)

            # 为每个传播创建预测（新功能）
            for sig in propagation_signals:
                direction = "up" if sig.change > 0 else "down"

                schedule = self._verification_scheduler.calculate_verification_time(
                    event_time=time.time(),
                    from_market=sig.from_market,
                    to_market=sig.to_market,
                    event_severity=severity,
                    is_emergency=is_abnormal,
                )

                self._prediction_tracker.create_prediction_with_schedule(
                    from_market=sig.from_market,
                    to_market=sig.to_market,
                    direction=direction,
                    probability=sig.propagation_probability,
                    source_change=sig.change,
                    schedule=schedule,
                )
                self._stats["predictions_created"] += 1
        else:
            propagation_signals = []

        insight = GlobalMarketInsight(
            insight_type="global_market_alert" if is_abnormal else "global_market_update",
            source_market=mapped_market_id,
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

        # 自动验证（检查是否需要）
        self._maybe_verify()

        return insight

    def _maybe_verify(self):
        """检查是否需要执行验证循环"""
        current_time = time.time()
        if current_time - self._last_verification_time >= self._verification_interval:
            self.verify_pending_predictions()
            self._last_verification_time = current_time

    def verify_pending_predictions(self) -> Dict[str, int]:
        """
        验证所有待验证的预测

        这个方法应该被定期调用（比如每分钟）

        Returns:
            验证统计
        """
        stats = self._prediction_tracker.verify_and_update()

        # 检查是否有需要验证的市场状态
        for to_market, state in list(self._market_states.items()):
            prediction = self._prediction_tracker.get_active_prediction(to_market)
            if not prediction:
                continue

            if not prediction.is_timed_out(time.time()):
                continue

            # 获取最新变化
            actual_change = state.get("change_pct", 0)
            actual_direction = "up" if actual_change > 0 else "down" if actual_change < 0 else "flat"

            # 验证预测
            self._prediction_tracker.verify_prediction(
                prediction.id,
                actual_direction,
                actual_change,
            )

            # 重新计算统计
            stats = self._prediction_tracker.verify_and_update()

        return stats

    def get_active_prediction(self, to_market: str) -> Optional[Dict[str, Any]]:
        """
        获取目标市场的活跃预测（供 Signal 查询）

        这是供外部系统（如 SignalGenerator）调用的主要接口

        Args:
            to_market: 目标市场，如 "a_share" 或 "hk_equity"

        Returns:
            预测信息 dict，如果没有活跃预测返回 None
            {
                "has_prediction": True/False,
                "direction": "up" 或 "down",
                "probability": 0.8,
                "confidence": 0.75,
                "minutes_until_verify": 15,
            }
        """
        prediction = self._prediction_tracker.get_active_prediction(to_market)
        if not prediction:
            return None

        minutes_until_verify = (prediction.verify_at - time.time()) / 60

        return {
            "has_prediction": True,
            "prediction_id": prediction.id,
            "from_market": prediction.from_market,
            "to_market": prediction.to_market,
            "direction": prediction.direction,
            "probability": prediction.probability,
            "confidence": prediction.probability,
            "minutes_until_verify": max(0, minutes_until_verify),
            "is_timed_out": prediction.is_timed_out(time.time()),
            "created_at": prediction.created_at,
            "verify_at": prediction.verify_at,
        }

    def query_for_signals(
        self,
        target_markets: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        批量查询多个市场的预测（供 SignalGenerator 批量使用）

        Args:
            target_markets: 目标市场列表

        Returns:
            Dict[market_id, prediction_info]
        """
        results = {}
        for market in target_markets:
            pred = self.get_active_prediction(market)
            if pred:
                results[market] = pred
            else:
                results[market] = {"has_prediction": False}
        return results

    def cancel_predictions_for_event(self, event_market: str, reason: str) -> int:
        """
        当某个市场出现反向事件时，取消所有以它为目标市场的预测

        Args:
            event_market: 事件市场
            reason: 取消原因

        Returns:
            取消了几个预测
        """
        return self._prediction_tracker.cancel_predictions_for_market(
            event_market,
            reason,
        )

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

    def get_prediction_tracker(self) -> PredictionTracker:
        """获取预测跟踪器"""
        return self._prediction_tracker

    def get_insights(self, limit: int = 20) -> List[GlobalMarketInsight]:
        """获取最近的洞察"""
        return self._insights_history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            **self._prediction_tracker.get_stats(),
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
            "active_predictions": len(self._prediction_tracker._predictions_by_status[PredictionStatus.PENDING]),
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
                    "active_predictions": summary.get("active_predictions", 0),
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
