"""
ActionExecutor - 行动执行层

觉醒系统的最终输出：将所有觉醒智慧合成为可执行决策

核心能力：
1. WisdomSynthesizer: 觉醒智慧综合
2. ActionGenerator: 行动生成器
3. ExecutionCoordinator: 执行协调器
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


class ActionType(Enum):
    """行动类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    INCREASE = "increase"    # 加仓
    DECREASE = "decrease"    # 减仓
    STOP_LOSS = "stop_loss"  # 止损
    TAKE_PROFIT = "take_profit"  # 止盈


class ActionPriority(Enum):
    """行动优先级"""
    URGENT = "urgent"       # 紧急
    HIGH = "high"           # 高
    NORMAL = "normal"       # 普通
    LOW = "low"            # 低


@dataclass
class TradingAction:
    """交易行动"""
    action_type: ActionType
    symbol: str
    quantity: int
    priority: ActionPriority
    confidence: float       # 行动置信度
    reason: str             # 行动原因
    source_wisdom: List[str]  # 智慧来源
    timestamp: float
    expires_at: float


@dataclass
class WisdomInput:
    """觉醒智慧输入"""
    prophet_signal: Optional[Any] = None      # 天眼通信号
    taste_signal: Optional[Any] = None        # 舌识信号
    illuminated_patterns: List[Any] = None   # 光明藏模式
    adaptive_decision: Optional[Any] = None   # 顺应决策
    narrative_summary: Optional[str] = None    # 叙事摘要
    opportunities: List[Any] = None           # 发现的机会
    epiphany: Optional[Any] = None            # 顿悟


class WisdomSynthesizer:
    """
    觉醒智慧综合器

    将多个觉醒模块的输出综合分析
    """

    def __init__(self):
        self._synthesis_history: List[Dict] = []

    def synthesize(
        self,
        wisdom: WisdomInput,
        market_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        综合智慧

        Args:
            wisdom: 觉醒智慧输入
            market_state: 市场状态

        Returns:
            综合分析结果
        """
        signals = []

        if wisdom.prophet_signal:
            signals.append({
                "source": "天眼通",
                "signal": wisdom.prophet_signal,
                "weight": 0.25
            })

        if wisdom.taste_signal:
            signals.append({
                "source": "舌识",
                "signal": wisdom.taste_signal,
                "weight": 0.20
            })

        if wisdom.illuminated_patterns:
            signals.append({
                "source": "光明藏",
                "signal": wisdom.illuminated_patterns,
                "weight": 0.20
            })

        if wisdom.adaptive_decision:
            signals.append({
                "source": "顺应型末那识",
                "signal": wisdom.adaptive_decision,
                "weight": 0.25
            })

        if wisdom.opportunities:
            signals.append({
                "source": "主动机会",
                "signal": wisdom.opportunities,
                "weight": 0.10
            })

        overall_confidence = sum(s["weight"] for s in signals if self._has_signal(s["signal"]))

        synthesis = {
            "signals": signals,
            "signal_count": len(signals),
            "overall_confidence": overall_confidence,
            "dominant_signal": self._find_dominant(signals),
            "timestamp": time.time()
        }

        self._synthesis_history.append(synthesis)
        return synthesis

    def _has_signal(self, signal: Any) -> bool:
        """检查是否有有效信号"""
        if signal is None:
            return False
        if isinstance(signal, list) and len(signal) == 0:
            return False
        return True

    def _find_dominant(self, signals: List[Dict]) -> Optional[str]:
        """找主导信号"""
        if not signals:
            return None

        valid_signals = [s for s in signals if self._has_signal(s["signal"])]
        if not valid_signals:
            return None

        return valid_signals[0]["source"]


class ActionGenerator:
    """
    行动生成器

    根据综合智慧生成具体行动
    """

    def __init__(self):
        self._action_templates = {
            ActionType.BUY: "买入 {symbol}",
            ActionType.SELL: "卖出 {symbol}",
            ActionType.HOLD: "持仓观望",
            ActionType.INCREASE: "加仓 {symbol}",
            ActionType.DECREASE: "减仓 {symbol}",
            ActionType.STOP_LOSS: "止损 {symbol}",
            ActionType.TAKE_PROFIT: "止盈 {symbol}",
        }

    def generate(
        self,
        synthesis: Dict[str, Any],
        wisdom: WisdomInput,
        current_positions: Dict[str, Dict]
    ) -> List[TradingAction]:
        """
        生成行动

        Args:
            synthesis: 综合结果
            wisdom: 智慧输入
            current_positions: 当前持仓

        Returns:
            行动列表
        """
        actions = []

        if wisdom.opportunities:
            for opp in wisdom.opportunities:
                action = self._create_action_from_opportunity(opp, wisdom)
                if action:
                    actions.append(action)

        if wisdom.taste_signal:
            taste_actions = self._create_actions_from_taste(wisdom.taste_signal, current_positions)
            actions.extend(taste_actions)

        if wisdom.adaptive_decision:
            adaptive_action = self._create_action_from_adaptive(wisdom.adaptive_decision, wisdom)
            if adaptive_action:
                actions.append(adaptive_action)

        actions = self._prioritize_actions(actions)
        return actions

    def _create_action_from_opportunity(self, opportunity, wisdom: WisdomInput) -> Optional[TradingAction]:
        """从机会创建行动"""
        if opportunity.stage.value in ["ready", "confirming"]:
            action_type = ActionType.BUY if opportunity.opportunity_type.value in ["momentum", "breakout"] else ActionType.HOLD

            confidence = opportunity.confidence * 0.8
            priority = ActionPriority.HIGH if opportunity.stage.value == "ready" else ActionPriority.NORMAL

            reason = f"主动机会: {opportunity.opportunity_type.value} | 预期收益: {opportunity.expected_return:.1%}"

            sources = ["主动机会创造", "天眼通"]
            if wisdom.prophet_signal:
                sources.append("天眼通")
            if wisdom.illuminated_patterns:
                sources.append("光明藏")

            return TradingAction(
                action_type=action_type,
                symbol=opportunity.symbol,
                quantity=100,  # 默认数量，待 PositionSizer 调整
                priority=priority,
                confidence=confidence,
                reason=reason,
                source_wisdom=sources,
                timestamp=time.time(),
                expires_at=time.time() + opportunity.entry_horizon
            )

        return None

    def _create_actions_from_taste(self, taste_signals: Dict, positions: Dict[str, Dict]) -> List[TradingAction]:
        """从舌识创建行动"""
        actions = []

        for symbol, signal in taste_signals.items():
            if signal.should_adjust:
                if signal.floating_pnl < -0.05:
                    action_type = ActionType.STOP_LOSS
                    priority = ActionPriority.URGENT
                elif signal.freshness < 0.3:
                    action_type = ActionType.TAKE_PROFIT
                    priority = ActionPriority.HIGH
                else:
                    action_type = ActionType.DECREASE
                    priority = ActionPriority.NORMAL

                actions.append(TradingAction(
                    action_type=action_type,
                    symbol=symbol,
                    quantity=50,
                    priority=priority,
                    confidence=signal.freshness,
                    reason=f"舌识: 鲜度={signal.freshness:.0%}, 浮盈={signal.floating_pnl:.1%}",
                    source_wisdom=["舌识"],
                    timestamp=time.time(),
                    expires_at=time.time() + 300
                ))

        return actions

    def _create_action_from_adaptive(self, adaptive_decision, wisdom: WisdomInput) -> Optional[TradingAction]:
        """从顺应决策创建行动"""
        if adaptive_decision.harmony_state.value == "resistance":
            return TradingAction(
                action_type=ActionType.HOLD,
                symbol="",
                quantity=0,
                priority=ActionPriority.NORMAL,
                confidence=adaptive_decision.intensity,
                reason=f"顺应决策: {adaptive_decision.harmony_state.value} | 市场不顺应，保持观望",
                source_wisdom=["顺应型末那识"],
                timestamp=time.time(),
                expires_at=time.time() + 600
            )

        return None

    def _prioritize_actions(self, actions: List[TradingAction]) -> List[TradingAction]:
        """优先级排序"""
        priority_order = {
            ActionPriority.URGENT: 0,
            ActionPriority.HIGH: 1,
            ActionPriority.NORMAL: 2,
            ActionPriority.LOW: 3
        }

        return sorted(actions, key=lambda a: (priority_order[a.priority], -a.confidence))


class ExecutionCoordinator:
    """
    执行协调器

    协调行动执行，处理冲突
    """

    def __init__(self):
        self._executed_actions: List[TradingAction] = []
        self._pending_actions: List[TradingAction] = []

    def coordinate(
        self,
        actions: List[TradingAction]
    ) -> List[TradingAction]:
        """
        协调行动

        - 去重
        - 处理冲突
        - 确定执行顺序
        """
        if not actions:
            return []

        coordinated = []
        seen = set()

        for action in sorted(actions, key=lambda a: (a.priority.value, -a.confidence)):
            key = (action.action_type, action.symbol)

            if key in seen:
                continue

            if self._has_conflict(action, coordinated):
                continue

            coordinated.append(action)
            seen.add(key)

        self._pending_actions = coordinated
        return coordinated

    def _has_conflict(self, action: TradingAction, existing: List[TradingAction]) -> bool:
        """检查冲突"""
        for e in existing:
            if e.symbol == action.symbol:
                if action.action_type == ActionType.BUY and e.action_type == ActionType.SELL:
                    return True
                if action.action_type == ActionType.SELL and e.action_type == ActionType.BUY:
                    return True
        return False

    def mark_executed(self, action: TradingAction):
        """标记已执行"""
        self._executed_actions.append(action)
        if action in self._pending_actions:
            self._pending_actions.remove(action)

    def get_pending(self) -> List[TradingAction]:
        """获取待执行行动"""
        return self._pending_actions

    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        return {
            "pending": len(self._pending_actions),
            "executed_today": len(self._executed_actions),
            "by_priority": self._count_by_priority(self._executed_actions)
        }

    def _count_by_priority(self, actions: List[TradingAction]) -> Dict[str, int]:
        """按优先级统计"""
        counts = {}
        for a in actions:
            counts[a.priority.value] = counts.get(a.priority.value, 0) + 1
        return counts


class ActionExecutor:
    """
    行动执行器（觉醒系统的最终输出）

    整合所有觉醒智慧，生成并协调可执行行动
    """

    def __init__(self):
        self.synthesizer = WisdomSynthesizer()
        self.generator = ActionGenerator()
        self.coordinator = ExecutionCoordinator()

    def execute(
        self,
        wisdom: WisdomInput,
        market_state: Dict[str, Any],
        current_positions: Dict[str, Dict]
    ) -> List[TradingAction]:
        """
        执行觉醒智慧

        Args:
            wisdom: 觉醒智慧输入
            market_state: 市场状态
            current_positions: 当前持仓

        Returns:
            可执行行动列表
        """
        synthesis = self.synthesizer.synthesize(wisdom, market_state)

        actions = self.generator.generate(synthesis, wisdom, current_positions)

        coordinated = self.coordinator.coordinate(actions)

        return coordinated

    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        return self.coordinator.get_execution_summary()