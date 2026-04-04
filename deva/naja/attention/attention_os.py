"""
AttentionOS - 注意力操作系统

分层架构：
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Attention OS (注意力操作系统)                          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    OS 应用层 (Applications)                            │   │
│  │                                                                      │   │
│  │  • MarketScheduler - 市场调度（板块/个股权重 + 频率控制）               │   │
│  │  • StrategyAllocator - 策略分配                                      │   │
│  │  • FrequencyController - 频率控制器                                  │   │
│  │  • ...其他模块                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Attention Kernel (注意力内核)                       │   │
│  │                                                                      │   │
│  │  • QKV 注意力计算 - 智能分配注意力权重                                │   │
│  │  • ManasEngine - 三维融合决策中枢（天时+地势+人和）                    │   │
│  │  • Encoder - 事件编码器                                              │   │
│  │  • MultiHeadAttention - 多头注意力                                    │   │
│  │  • AttentionMemory - 注意力记忆                                       │   │
│  │  • ValueSystem - 价值观驱动                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘

核心能力（被各方调用）：
    • compute_attention() - QKV 注意力计算
    • make_decision() - ManasEngine 决策
    • get_harmony() - 获取和谐状态
    • get_memory() - 注意力记忆

使用方式：
    attention_os = AttentionOS()
    attention_os.initialize()

    # 注意力计算
    result = attention_os.compute_attention(events, market_state)

    # 决策
    decision = attention_os.make_decision(market_state, portfolio)
"""

import time
import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
import threading

from .kernel.encoder import Encoder
from .kernel.multi_head import MultiHeadAttention
from .kernel.memory import AttentionMemory
from .kernel.manas_engine import ManasEngine
from .kernel import get_default_heads
from .values.system import ValueSystem, get_value_system

log = logging.getLogger(__name__)


@dataclass
class AttentionKernelOutput:
    """注意力内核输出"""
    alpha: float = 1.0
    confidence: float = 0.5
    attention_weights: Dict[str, float] = field(default_factory=dict)
    focus_symbols: List[str] = field(default_factory=list)

    manas_score: float = 0.5
    timing_score: float = 0.5
    regime_score: float = 0.0
    confidence_score: float = 0.5
    risk_temperature: float = 1.0

    should_act: bool = False
    action_type: str = "hold"
    harmony_state: str = "neutral"
    harmony_strength: float = 0.5

    bias_state: str = "neutral"
    bias_correction: float = 1.0

    narrative_risk: float = 0.5
    ai_compute_direction: str = "unknown"
    awakening_level: str = "dormant"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alpha": self.alpha,
            "confidence": self.confidence,
            "attention_weights": self.attention_weights,
            "focus_symbols": self.focus_symbols,
            "manas_score": self.manas_score,
            "timing_score": self.timing_score,
            "regime_score": self.regime_score,
            "confidence_score": self.confidence_score,
            "risk_temperature": self.risk_temperature,
            "should_act": self.should_act,
            "action_type": self.action_type,
            "harmony_state": self.harmony_state,
            "harmony_strength": self.harmony_strength,
            "bias_state": self.bias_state,
            "bias_correction": self.bias_correction,
            "narrative_risk": self.narrative_risk,
            "ai_compute_direction": self.ai_compute_direction,
            "awakening_level": self.awakening_level,
        }


class AttentionKernel:
    """
    注意力内核

    核心组件：
    - Encoder: 事件编码
    - MultiHeadAttention: QKV 注意力计算
    - AttentionMemory: 记忆存储
    - ManasEngine: 决策中枢
    - ValueSystem: 价值观驱动
    """

    def __init__(self):
        self.encoder = Encoder()
        heads = get_default_heads()
        self.multi_head = MultiHeadAttention(heads)
        self.memory = AttentionMemory(decay_rate=300)
        self.manas_engine = ManasEngine()
        self._value_system = None

        self._last_output: Optional[AttentionKernelOutput] = None
        self._update_interval = 1.0
        self._last_update = 0.0

    def _get_value_system(self) -> ValueSystem:
        if self._value_system is None:
            self._value_system = get_value_system()
        return self._value_system

    def compute(
        self,
        events: List[Any],
        market_state: Optional[Dict[str, Any]] = None,
        query_state: Optional[Any] = None
    ) -> AttentionKernelOutput:
        """
        计算注意力输出

        Args:
            events: 事件列表
            market_state: 市场状态
            query_state: 查询状态

        Returns:
            AttentionKernelOutput
        """
        current_time = time.time()
        if current_time - self._last_update < self._update_interval and self._last_output is not None:
            return self._last_output

        vs = self._get_value_system()

        encoded_events = []
        for e in events:
            e.key = self.encoder.encode_key(e)
            e.value = self.encoder.encode_value(e)
            encoded_events.append(e)

            alignment = vs.calculate_alignment(e.features)
            e.features["_value_alignment"] = alignment

        attention_result = self.multi_head.compute(query_state, encoded_events)

        alpha = attention_result.get("alpha", 1.0)
        attention_weights = attention_result.get("attention_weights", {})

        focus_symbols = []
        if attention_weights:
            sorted_weights = sorted(attention_weights.items(), key=lambda x: x[1], reverse=True)
            focus_symbols = [s for s, _ in sorted_weights[:10]]

        manas_output = self.manas_engine.compute(
            session_manager=self._get_session_manager(),
            portfolio=self._get_portfolio(),
            scanner=self._get_scanner(),
            bandit_tracker=self._get_bandit_tracker(),
            macro_signal=market_state.get("macro_liquidity_signal", 0.5) if market_state else 0.5,
            narratives=market_state.get("narratives", []) if market_state else []
        )

        alpha *= manas_output.alpha
        alpha = max(0.3, min(1.5, alpha))

        output = AttentionKernelOutput(
            alpha=alpha,
            confidence=attention_result.get("confidence", 0.5),
            attention_weights=attention_weights,
            focus_symbols=focus_symbols,
            manas_score=manas_output.manas_score,
            timing_score=manas_output.timing_score,
            regime_score=manas_output.regime_score,
            confidence_score=manas_output.confidence_score,
            risk_temperature=manas_output.risk_temperature,
            should_act=manas_output.should_act,
            action_type=manas_output.action_type.value if hasattr(manas_output.action_type, 'value') else str(manas_output.action_type),
            harmony_state=manas_output.harmony_state.value if hasattr(manas_output.harmony_state, 'value') else str(manas_output.harmony_state),
            harmony_strength=manas_output.harmony_strength,
            bias_state=manas_output.bias_state.value if hasattr(manas_output.bias_state, 'value') else str(manas_output.bias_state),
            bias_correction=manas_output.bias_correction,
            narrative_risk=manas_output.narrative_risk,
            ai_compute_direction=manas_output.ai_compute_direction,
            awakening_level=manas_output.awakening_level,
        )

        for e in encoded_events:
            symbol = getattr(e, 'symbol', None) or e.source if hasattr(e, 'source') else "unknown"
            alignment = e.features.get("_value_alignment", 0.5)
            reason = vs.generate_focus_reason(e.features)
            vs.record_attention(symbol, alignment, reason)
            vs.set_last_decision_reason(reason)
            self.memory.update(symbol=symbol, alignment=alignment, reason=reason)

        self._last_output = output
        self._last_update = current_time

        return output

    def make_decision(
        self,
        market_state: Optional[Dict[str, Any]] = None,
        portfolio: Optional[Any] = None
    ) -> AttentionKernelOutput:
        """
        独立做决策（不经过 QKV）

        用于不需要事件输入的决策场景
        """
        current_time = time.time()
        if current_time - self._last_update < self._update_interval and self._last_output is not None:
            return self._last_output

        manas_output = self.manas_engine.compute(
            session_manager=self._get_session_manager(),
            portfolio=portfolio,
            scanner=self._get_scanner(),
            bandit_tracker=self._get_bandit_tracker(),
            macro_signal=market_state.get("macro_liquidity_signal", 0.5) if market_state else 0.5,
            narratives=market_state.get("narratives", []) if market_state else []
        )

        output = AttentionKernelOutput(
            alpha=manas_output.alpha,
            confidence=manas_output.confidence_score,
            manas_score=manas_output.manas_score,
            timing_score=manas_output.timing_score,
            regime_score=manas_output.regime_score,
            confidence_score=manas_output.confidence_score,
            risk_temperature=manas_output.risk_temperature,
            should_act=manas_output.should_act,
            action_type=manas_output.action_type.value if hasattr(manas_output.action_type, 'value') else str(manas_output.action_type),
            harmony_state=manas_output.harmony_state.value if hasattr(manas_output.harmony_state, 'value') else str(manas_output.harmony_state),
            harmony_strength=manas_output.harmony_strength,
            bias_state=manas_output.bias_state.value if hasattr(manas_output.bias_state, 'value') else str(manas_output.bias_state),
            bias_correction=manas_output.bias_correction,
            narrative_risk=manas_output.narrative_risk,
            ai_compute_direction=manas_output.ai_compute_direction,
            awakening_level=manas_output.awakening_level,
        )

        self._last_output = output
        self._last_update = current_time

        return output

    def get_harmony(self) -> Dict[str, Any]:
        """获取和谐状态"""
        if self._last_output is None:
            return {"harmony_strength": 0.5, "harmony_state": "neutral"}
        return {
            "harmony_strength": self._last_output.harmony_strength,
            "harmony_state": self._last_output.harmony_state,
            "should_act": self._last_output.should_act,
            "action_type": self._last_output.action_type,
        }

    def get_memory(self) -> AttentionMemory:
        """获取注意力记忆"""
        return self.memory

    def get_manas_engine(self) -> ManasEngine:
        """获取 ManasEngine 实例"""
        return self.manas_engine

    def _get_session_manager(self):
        try:
            from deva.naja.radar.trading_clock import get_trading_clock
            return get_trading_clock()
        except ImportError:
            return None

    def _get_portfolio(self):
        try:
            from deva.naja.bandit import get_virtual_portfolio
            return get_virtual_portfolio()
        except ImportError:
            return None

    def _get_scanner(self):
        try:
            from deva.naja.radar import get_market_scanner
            return get_market_scanner()
        except ImportError:
            return None

    def _get_bandit_tracker(self):
        try:
            from deva.naja.bandit import get_bandit_tracker
            return get_bandit_tracker()
        except ImportError:
            return None


class MarketScheduler:
    """
    市场调度器 - Attention OS 应用层

    职责：
    - 板块/个股权重分配
    - 刷新频率控制
    - 策略分配

    依托 Attention Kernel 获取注意力权重和决策调制
    """

    def __init__(self, kernel: AttentionKernel):
        self.kernel = kernel

        self._sector_weights: Dict[str, float] = {}
        self._symbol_weights: Dict[str, float] = {}
        self._frequency_level: str = "medium"
        self._strategy_allocations: Dict[str, float] = {}
        self._last_schedule_time: float = 0.0
        self._schedule_interval: float = 60.0

    def schedule(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行市场调度

        Args:
            market_data: 市场数据

        Returns:
            调度结果
        """
        import time
        current_time = time.time()

        kernel_output = self.kernel.make_decision(market_data)

        harmony_strength = kernel_output.harmony_strength
        should_act = kernel_output.should_act
        action_type = kernel_output.action_type

        timing_score = kernel_output.timing_score
        regime_score = kernel_output.regime_score
        confidence_score = kernel_output.confidence_score

        self._adjust_frequency(harmony_strength, timing_score, regime_score, current_time)

        self._allocate_weights(market_data, kernel_output)

        self._allocate_strategies(kernel_output, market_data)

        self._last_schedule_time = current_time

        return {
            "sector_weights": self._sector_weights,
            "symbol_weights": self._symbol_weights,
            "strategy_allocations": self._strategy_allocations,
            "frequency_level": self._frequency_level,
            "schedule_interval": self._schedule_interval,
            "should_act": should_act,
            "action_type": action_type,
            "harmony_strength": harmony_strength,
            "timing_score": timing_score,
            "regime_score": regime_score,
            "confidence_score": confidence_score,
            "kernel_output": kernel_output.to_dict(),
        }

    def _adjust_frequency(
        self,
        harmony_strength: float,
        timing_score: float = 0.5,
        regime_score: float = 0.0,
        current_time: float = 0.0
    ):
        """
        根据和谐强度和其他因素调整频率

        频率等级：
        - high: harmony > 0.7 且时机好 → 1-5秒
        - medium: harmony 0.4-0.7 → 30-60秒
        - low: harmony < 0.4 或时机差 → 5-10分钟
        """
        composite_score = (
            harmony_strength * 0.5 +
            timing_score * 0.3 +
            (1.0 if regime_score > 0 else 0.3) * 0.2
        )

        if composite_score > 0.75:
            self._frequency_level = "high"
            self._schedule_interval = 1.0 + (1.0 - composite_score) * 4.0
        elif composite_score > 0.5:
            self._frequency_level = "medium"
            self._schedule_interval = 30.0 + (1.0 - composite_score) * 60.0
        elif composite_score > 0.25:
            self._frequency_level = "low"
            self._schedule_interval = 300.0 + (0.5 - composite_score) * 600.0
        else:
            self._frequency_level = "ultra_low"
            self._schedule_interval = 600.0

        self._schedule_interval = max(1.0, min(600.0, self._schedule_interval))

    def _allocate_weights(self, market_data: Dict[str, Any], kernel_output: AttentionKernelOutput):
        """分配个股权重"""
        base_weights = market_data.get("symbol_weights", {})
        sector_map = market_data.get("sector_map", {})

        alpha = kernel_output.alpha
        harmony = kernel_output.harmony_strength
        confidence = kernel_output.confidence_score

        self._symbol_weights = {}
        self._sector_weights = {}

        sector_totals: Dict[str, float] = {}

        for symbol, base_weight in base_weights.items():
            attention_weight = kernel_output.attention_weights.get(symbol, 0.5)

            final_weight = base_weight * attention_weight * alpha * harmony * confidence

            self._symbol_weights[symbol] = max(0.0, min(1.0, final_weight))

            sector = sector_map.get(symbol, "unknown")
            if sector not in sector_totals:
                sector_totals[sector] = 0.0
            sector_totals[sector] += final_weight

        for sector, total in sector_totals.items():
            self._sector_weights[sector] = min(1.0, total / max(1, len(sector_totals)))

    def _allocate_strategies(
        self,
        kernel_output: AttentionKernelOutput,
        market_data: Dict[str, Any]
    ):
        """
        分配策略执行权重

        根据 action_type 和市场状态决定策略分配
        """
        action_type = kernel_output.action_type
        harmony = kernel_output.harmony_strength
        timing = kernel_output.timing_score
        regime = kernel_output.regime_score

        self._strategy_allocations = {}

        if action_type == "hold":
            self._strategy_allocations = {
                "momentum": 0.1,
                "mean_reversion": 0.1,
                "breakout": 0.0,
                "grid": 0.2,
                "wait": 0.6,
            }
        elif action_type in ("act_fully", "buy", "long"):
            if harmony > 0.8 and timing > 0.7:
                self._strategy_allocations = {
                    "momentum": 0.5,
                    "breakout": 0.3,
                    "mean_reversion": 0.1,
                    "grid": 0.0,
                    "wait": 0.1,
                }
            elif harmony > 0.6:
                self._strategy_allocations = {
                    "momentum": 0.3,
                    "breakout": 0.2,
                    "mean_reversion": 0.2,
                    "grid": 0.1,
                    "wait": 0.2,
                }
            else:
                self._strategy_allocations = {
                    "momentum": 0.2,
                    "breakout": 0.1,
                    "mean_reversion": 0.3,
                    "grid": 0.2,
                    "wait": 0.2,
                }
        elif action_type in ("act_carefully", "sell", "short"):
            self._strategy_allocations = {
                "momentum": 0.1,
                "mean_reversion": 0.4,
                "breakout": 0.0,
                "grid": 0.3,
                "wait": 0.2,
            }
        elif action_type == "act_minimally":
            self._strategy_allocations = {
                "momentum": 0.15,
                "mean_reversion": 0.25,
                "breakout": 0.1,
                "grid": 0.25,
                "wait": 0.25,
            }
        else:
            self._strategy_allocations = {
                "momentum": 0.2,
                "mean_reversion": 0.2,
                "breakout": 0.1,
                "grid": 0.2,
                "wait": 0.3,
            }

        regime_factor = 1.0 + regime * 0.2
        for k in self._strategy_allocations:
            self._strategy_allocations[k] *= regime_factor
            self._strategy_allocations[k] = min(1.0, self._strategy_allocations[k])

    def get_frequency_config(self) -> Dict[str, Any]:
        """获取频率配置"""
        return {
            "level": self._frequency_level,
            "interval_seconds": self._schedule_interval,
        }

    def get_top_symbols(self, n: int = 10) -> List[Dict[str, Any]]:
        """获取权重最高的 n 只股票"""
        sorted_weights = sorted(
            self._symbol_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [
            {"symbol": sym, "weight": wgt}
            for sym, wgt in sorted_weights[:n]
        ]

    def get_top_sectors(self, n: int = 5) -> List[Dict[str, Any]]:
        """获取权重最高的 n 个板块"""
        sorted_weights = sorted(
            self._sector_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [
            {"sector": sec, "weight": wgt}
            for sec, wgt in sorted_weights[:n]
        ]


class AttentionOS:
    """
    注意力操作系统

    统一入口，管理内核和应用层
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.kernel = AttentionKernel()
        self.market_scheduler = MarketScheduler(self.kernel)

        self._initialized = True

    def initialize(self):
        """初始化"""
        log.info("[AttentionOS] 初始化完成")

    def compute_attention(
        self,
        events: List[Any],
        market_state: Optional[Dict[str, Any]] = None,
        query_state: Optional[Any] = None
    ) -> AttentionKernelOutput:
        """计算注意力"""
        return self.kernel.compute(events, market_state, query_state)

    def make_decision(
        self,
        market_state: Optional[Dict[str, Any]] = None,
        portfolio: Optional[Any] = None
    ) -> AttentionKernelOutput:
        """做决策"""
        return self.kernel.make_decision(market_state, portfolio)

    def schedule_market(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """市场调度"""
        return self.market_scheduler.schedule(market_data)

    def get_harmony(self) -> Dict[str, Any]:
        """获取和谐状态"""
        return self.kernel.get_harmony()


_attention_os: Optional[AttentionOS] = None


def get_attention_os() -> AttentionOS:
    """获取 AttentionOS 单例"""
    global _attention_os
    if _attention_os is None:
        _attention_os = AttentionOS()
    return _attention_os


def get_attention_kernel() -> AttentionKernel:
    """获取 AttentionKernel（兼容旧接口）"""
    return get_attention_os().kernel
