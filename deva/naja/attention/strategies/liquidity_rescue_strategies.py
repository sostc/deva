"""
LiquidityRescueStrategies - 流动性救援策略集

三个核心策略：
1. PanicPeakDetector - 恐慌极点检测器
2. LiquidityCrisisTracker - 流动性危机追踪器
3. RecoveryConfirmationMonitor - 恢复确认监测器
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import time
import logging

log = logging.getLogger(__name__)


class RescueSignalType(Enum):
    """救援信号类型"""
    PANIC_PEAK_DETECTED = "panic_peak_detected"
    LIQUIDITY_CRISIS_WARNING = "liquidity_crisis_warning"
    LIQUIDITY_CRISIS_CONFIRMED = "liquidity_crisis_confirmed"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_CONFIRMED = "recovery_confirmed"
    RESCUE_OPPORTUNITY = "rescue_opportunity"
    EXIT_OPPORTUNITY = "exit_opportunity"
    HOLD = "hold"
    CANCEL = "cancel"


@dataclass
class RescueSignal:
    """救援信号"""
    signal_type: RescueSignalType
    confidence: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    action_recommended: str = "watch"


@dataclass
class LiquidityCrisisState:
    """流动性危机状态"""
    level: str
    panic_score: float
    liquidity_score: float
    spread_ratio: float
    volume_shrink_ratio: float
    trend: str
    is_peak: bool
    peak_confirmed: bool
    recovery_started: bool
    recovery_confirmed: bool
    timestamp: float = field(default_factory=time.time)


class PanicPeakDetector:
    """
    恐慌极点检测器

    核心功能：
    1. 监测恐慌指数的变化趋势
    2. 检测恐慌极点（卖压衰竭点）
    3. 确认恐慌极点是否已经形成

    信号输出：
    - PANIC_PEAK_DETECTED: 恐慌极点被检测到
    - RESCUE_OPPORTUNITY: 救援机会确认
    """

    def __init__(self, window_size: int = 10, peak_confirmation_window: int = 3):
        self.window_size = window_size
        self.peak_confirmation_window = peak_confirmation_window
        self._panic_history: deque = deque(maxlen=window_size)
        self._volume_history: deque = deque(maxlen=window_size)
        self._price_history: deque = deque(maxlen=window_size)

    def update(self, panic_score: float, volume_ratio: float, price_change: float) -> RescueSignal:
        """
        更新数据并检测恐慌极点

        Args:
            panic_score: 当前恐慌指数 (0-100)
            volume_ratio: 当前成交量相对正常值的比例
            price_change: 当前价格变化百分比

        Returns:
            RescueSignal: 如果检测到恐慌极点，返回确认信号
        """
        self._panic_history.append(panic_score)
        self._volume_history.append(volume_ratio)
        self._price_history.append(price_change)

        if len(self._panic_history) < 5:
            return RescueSignal(
                signal_type=RescueSignalType.HOLD,
                confidence=0,
                message="数据不足，等待更多历史数据"
            )

        trend = self._analyze_trend()
        is_peak = self._detect_peak()
        peak_confirmed = is_peak and trend == "deescalating"

        if peak_confirmed:
            return RescueSignal(
                signal_type=RescueSignalType.PANIC_PEAK_DETECTED,
                confidence=0.8,
                message=f"🚨 恐慌极点确认！指数{panic_score:.0f}，趋势{trend}",
                details={
                    "panic_score": panic_score,
                    "trend": trend,
                    "volume_ratio": volume_ratio,
                    "price_change": price_change
                },
                action_recommended="prepare_rescue"
            )

        if trend == "deescalating" and panic_score > 50:
            return RescueSignal(
                signal_type=RescueSignalType.RESCUE_OPPORTUNITY,
                confidence=0.6,
                message=f"📊 救援机会出现，恐慌消退中({trend})",
                details={"panic_score": panic_score, "trend": trend},
                action_recommended="watch"
            )

        return RescueSignal(
            signal_type=RescueSignalType.HOLD,
            confidence=0.3,
            message=f"📈 恐慌{trend}，当前指数{panic_score:.0f}",
            details={"panic_score": panic_score, "trend": trend}
        )

    def _analyze_trend(self) -> str:
        """分析恐慌趋势"""
        if len(self._panic_history) < 3:
            return "unknown"

        recent = list(self._panic_history)[-3:]
        if recent[-1] > recent[0] * 1.05:
            return "escalating"
        elif recent[-1] < recent[0] * 0.95:
            return "deescalating"
        return "stable"

    def _detect_peak(self) -> bool:
        """
        检测恐慌极点

        条件：
        1. 当前恐慌指数处于局部最高点
        2. 成交量开始恢复（萎缩减缓）
        3. 价格下跌速度开始放缓
        """
        if len(self._panic_history) < 5:
            return False

        scores = list(self._panic_history)
        volumes = list(self._volume_history)
        prices = list(self._price_history)

        current_score = scores[-1]
        current_volume = volumes[-1]
        current_price = prices[-1]

        for i, s in enumerate(scores[:-1]):
            if s > current_score * 1.1:
                return False

        volume_recovering = current_volume > volumes[-2] if len(volumes) >= 2 else False
        price_slowing = abs(current_price) < abs(prices[-2]) if len(prices) >= 2 else False

        return volume_recovering or price_slowing

    def get_state(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "panic_history_size": len(self._panic_history),
            "current_panic": list(self._panic_history)[-1] if self._panic_history else None,
            "trend": self._analyze_trend(),
            "is_peak": self._detect_peak(),
        }


class LiquidityCrisisTracker:
    """
    流动性危机追踪器

    核心功能：
    1. 持续追踪流动性状态
    2. 预警流动性危机
    3. 确认流动性危机等级

    信号输出：
    - LIQUIDITY_CRISIS_WARNING: 流动性预警
    - LIQUIDITY_CRISIS_CONFIRMED: 流动性危机确认
    """

    def __init__(
        self,
        normal_spread: float = 0.05,
        crisis_spread: float = 0.15,
        min_crisis_volume_ratio: float = 0.4
    ):
        self.normal_spread = normal_spread
        self.crisis_spread = crisis_spread
        self.min_crisis_volume_ratio = min_crisis_volume_ratio
        self._crisis_history: deque = deque(maxlen=20)

    def update(
        self,
        spread: float,
        volume_ratio: float,
        order_book_depth: float = 1000,
        bid_ask_ratio: float = 1.0
    ) -> RescueSignal:
        """
        更新流动性数据

        Args:
            spread: 当前买卖价差
            volume_ratio: 成交量相对正常比例
            order_book_depth: 订单簿深度
            bid_ask_ratio: 买卖盘比率

        Returns:
            RescueSignal: 流动性状态信号
        """
        crisis_level = self._calculate_crisis_level(
            spread, volume_ratio, order_book_depth, bid_ask_ratio
        )
        self._crisis_history.append(crisis_level)

        if crisis_level >= 0.8:
            return RescueSignal(
                signal_type=RescueSignalType.LIQUIDITY_CRISIS_CONFIRMED,
                confidence=0.9,
                message=f"🚨 流动性危机确认！等级{crisis_level:.2f}",
                details={
                    "crisis_level": crisis_level,
                    "spread": spread,
                    "volume_ratio": volume_ratio
                },
                action_recommended="confirm_rescue"
            )

        elif crisis_level >= 0.5:
            return RescueSignal(
                signal_type=RescueSignalType.LIQUIDITY_CRISIS_WARNING,
                confidence=0.7,
                message=f"⚠️ 流动性预警，等级{crisis_level:.2f}",
                details={"crisis_level": crisis_level},
                action_recommended="watch"
            )

        return RescueSignal(
            signal_type=RescueSignalType.HOLD,
            confidence=0.9,
            message=f"✅ 流动性正常，等级{crisis_level:.2f}",
            details={"crisis_level": crisis_level}
        )

    def _calculate_crisis_level(
        self,
        spread: float,
        volume_ratio: float,
        order_book_depth: float,
        bid_ask_ratio: float
    ) -> float:
        """计算流动性危机等级 (0-1)"""
        spread_crisis = min(1.0, (spread - self.normal_spread) / (self.crisis_spread - self.normal_spread))
        volume_crisis = 1.0 - min(1.0, volume_ratio / self.min_crisis_volume_ratio)
        depth_crisis = max(0, 1.0 - order_book_depth / 1000)
        bid_ask_imbalance = abs(1.0 - bid_ask_ratio)

        crisis_level = (
            spread_crisis * 0.4 +
            volume_crisis * 0.3 +
            depth_crisis * 0.2 +
            bid_ask_imbalance * 0.1
        )

        return min(1.0, max(0.0, crisis_level))

    def get_state(self) -> Dict[str, Any]:
        """获取当前状态"""
        if not self._crisis_history:
            return {"crisis_level": 0, "avg_crisis": None}

        recent = list(self._crisis_history)[-5:]
        return {
            "current_crisis_level": self._crisis_history[-1],
            "avg_crisis_level": sum(recent) / len(recent),
            "history_size": len(self._crisis_history),
        }


class RecoveryConfirmationMonitor:
    """
    恢复确认监测器

    核心功能：
    1. 监测市场是否开始恢复
    2. 确认恢复是否可持续
    3. 发出卖出/退出信号

    信号输出：
    - RECOVERY_STARTED: 恢复开始
    - RECOVERY_CONFIRMED: 恢复确认
    - EXIT_OPPORTUNITY: 退出机会
    """

    def __init__(
        self,
        min_recovery_signals: int = 3,
        price_recovery_threshold: float = 0.5,
        volume_recovery_threshold: float = 0.7
    ):
        self.min_recovery_signals = min_recovery_signals
        self.price_recovery_threshold = price_recovery_threshold
        self.volume_recovery_threshold = volume_recovery_threshold
        self._recovery_signals: deque = deque(maxlen=10)
        self._price_history: deque = deque(maxlen=20)
        self._volume_history: deque = deque(maxlen=20)

    def update(
        self,
        price_change: float,
        volume_ratio: float,
        spread: float,
        sentiment_change: float = 0
    ) -> RescueSignal:
        """
        更新恢复监测数据

        Args:
            price_change: 价格变化（应该是正值表示反弹）
            volume_ratio: 成交量恢复比例
            spread: 当前价差（应该收窄）
            sentiment_change: 情绪变化（应该是正值表示好转）

        Returns:
            RescueSignal: 恢复状态信号
        """
        self._price_history.append(price_change)
        self._volume_history.append(volume_ratio)

        recovery_score = self._calculate_recovery_score(
            price_change, volume_ratio, spread, sentiment_change
        )
        self._recovery_signals.append(recovery_score)

        recent_recoveries = [s for s in self._recovery_signals if s > 0.5]
        consecutive_recoveries = self._count_consecutive_recoveries()

        if len(recent_recoveries) >= self.min_recovery_signals and consecutive_recoveries >= 2:
            return RescueSignal(
                signal_type=RescueSignalType.RECOVERY_CONFIRMED,
                confidence=0.85,
                message=f"✅ 恢复确认！连续{consecutive_recoveries}次恢复信号",
                details={
                    "recovery_score": recovery_score,
                    "consecutive_recoveries": consecutive_recoveries,
                    "price_change": price_change,
                    "volume_ratio": volume_ratio
                },
                action_recommended="consider_exit"
            )

        if recovery_score > 0.5 and len(recent_recoveries) >= 2:
            return RescueSignal(
                signal_type=RescueSignalType.RECOVERY_STARTED,
                confidence=0.6,
                message=f"📈 恢复开始，评分{recovery_score:.2f}",
                details={"recovery_score": recovery_score},
                action_recommended="hold"
            )

        if recovery_score > 0.3:
            return RescueSignal(
                signal_type=RescueSignalType.EXIT_OPPORTUNITY,
                confidence=0.5,
                message=f"💰 退出机会，流动性恢复中",
                details={"recovery_score": recovery_score},
                action_recommended="prepare_exit"
            )

        return RescueSignal(
            signal_type=RescueSignalType.HOLD,
            confidence=0.5,
            message=f"⏳ 等待恢复，当前评分{recovery_score:.2f}",
            details={"recovery_score": recovery_score}
        )

    def _calculate_recovery_score(
        self,
        price_change: float,
        volume_ratio: float,
        spread: float,
        sentiment_change: float
    ) -> float:
        """计算恢复评分 (0-1)"""
        price_score = min(1.0, max(0, price_change / self.price_recovery_threshold))
        volume_score = min(1.0, volume_ratio / self.volume_recovery_threshold)
        spread_score = max(0, 1.0 - spread / 0.1)
        sentiment_score = min(1.0, max(0, sentiment_change / 0.2))

        score = (
            price_score * 0.4 +
            volume_score * 0.3 +
            spread_score * 0.2 +
            sentiment_score * 0.1
        )

        return min(1.0, max(0.0, score))

    def _count_consecutive_recoveries(self) -> int:
        """计算连续恢复次数"""
        if not self._recovery_signals:
            return 0

        consecutive = 0
        for s in reversed(list(self._recovery_signals)):
            if s > 0.5:
                consecutive += 1
            else:
                break

        return consecutive

    def get_state(self) -> Dict[str, Any]:
        """获取当前状态"""
        recent = list(self._recovery_signals)[-5:] if self._recovery_signals else []
        return {
            "recovery_signals_count": len(self._recovery_signals),
            "recent_avg_score": sum(recent) / len(recent) if recent else 0,
            "consecutive_recoveries": self._count_consecutive_recoveries(),
            "price_trend": list(self._price_history)[-3:] if self._price_history else [],
        }


class LiquidityRescueOrchestrator:
    """
    流动性救援协调器

    整合三个策略，统一输出救援决策
    """

    def __init__(self):
        self.panic_detector = PanicPeakDetector()
        self.crisis_tracker = LiquidityCrisisTracker()
        self.recovery_monitor = RecoveryConfirmationMonitor()
        self._state_history: deque = deque(maxlen=100)

    def update(
        self,
        panic_score: float,
        spread: float,
        volume_ratio: float,
        price_change: float,
        order_book_depth: float = 1000,
        sentiment_change: float = 0
    ) -> LiquidityCrisisState:
        """
        更新所有监测器并返回综合状态

        Returns:
            LiquidityCrisisState: 综合流动性危机状态
        """
        panic_signal = self.panic_detector.update(panic_score, volume_ratio, price_change)
        crisis_signal = self.crisis_tracker.update(spread, volume_ratio, order_book_depth)
        recovery_signal = self.recovery_monitor.update(
            price_change, volume_ratio, spread, sentiment_change
        )

        state = LiquidityCrisisState(
            level=self._determine_level(panic_signal, crisis_signal, recovery_signal),
            panic_score=panic_score,
            liquidity_score=1.0 - crisis_signal.details.get("crisis_level", 0),
            spread_ratio=spread / 0.05,
            volume_shrink_ratio=volume_ratio,
            trend=panic_detector._analyze_trend() if hasattr(panic_detector := self.panic_detector, '_analyze_trend') else "unknown",
            is_peak=panic_signal.signal_type == RescueSignalType.PANIC_PEAK_DETECTED,
            peak_confirmed=panic_signal.signal_type == RescueSignalType.RESCUE_OPPORTUNITY,
            recovery_started=recovery_signal.signal_type in [
                RescueSignalType.RECOVERY_STARTED,
                RescueSignalType.RECOVERY_CONFIRMED
            ],
            recovery_confirmed=recovery_signal.signal_type == RescueSignalType.RECOVERY_CONFIRMED
        )

        self._state_history.append(state)
        return state

    def _determine_level(
        self,
        panic_signal: RescueSignal,
        crisis_signal: RescueSignal,
        recovery_signal: RescueSignal
    ) -> str:
        """确定危机等级"""
        if recovery_signal.signal_type == RescueSignalType.RECOVERY_CONFIRMED:
            return "recovery"
        if crisis_signal.signal_type == RescueSignalType.LIQUIDITY_CRISIS_CONFIRMED:
            return "crisis"
        if panic_signal.signal_type == RescueSignalType.PANIC_PEAK_DETECTED:
            return "peak"
        if crisis_signal.signal_type == RescueSignalType.LIQUIDITY_CRISIS_WARNING:
            return "warning"
        if panic_signal.signal_type == RescueSignalType.RESCUE_OPPORTUNITY:
            return "opportunity"
        return "normal"

    def get_recommended_action(self) -> str:
        """获取推荐操作"""
        if not self._state_history:
            return "watch"

        current = self._state_history[-1]

        if current.recovery_confirmed:
            return "exit"
        if current.level == "peak":
            return "rescue"
        if current.level == "crisis":
            return "confirm_rescue"
        if current.level == "opportunity":
            return "prepare_rescue"
        if current.level == "recovery":
            return "hold"
        return "watch"

    def get_state(self) -> Dict[str, Any]:
        """获取完整状态"""
        return {
            "current_state": self._state_history[-1].__dict__ if self._state_history else None,
            "recommended_action": self.get_recommended_action(),
            "panic_detector": self.panic_detector.get_state(),
            "crisis_tracker": self.crisis_tracker.get_state(),
            "recovery_monitor": self.recovery_monitor.get_state(),
        }