"""
TradingCenter - 交易中枢

定位：Naja系统的协调中枢，协调各层模块完成交易决策

架构：
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TradingCenter (交易中枢)                               │
│                                                                             │
│  职责：                                                                     │
│    • 数据协调 - 接收市场数据，分发给各模块                                    │
│    • 快速决策 - 通过 AttentionOS.kernel.make_decision()                      │
│    • 慢思考融合 - 调用 FirstPrinciplesMind.think()                           │
│    • 模式匹配 - 调用 AwakenedAlaya.illuminate()                              │
│    • 决策融合 - 融合各模块输出生成最终决策                                    │
│    • 策略协调 - 协调策略执行                                                 │
│                                                                             │
│  内部模块：                                                                 │
│    • AttentionOS - 注意力计算和快速决策                                      │
│    • FirstPrinciplesMind - 因果推理                                           │
│    • AwakenedAlaya - 模式匹配/顿悟                                          │
└─────────────────────────────────────────────────────────────────────────────┘

使用方式：
    center = TradingCenter()
    decision = center.process_market_data(data)
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import threading

from .attention_os import AttentionOS, get_attention_os

log = logging.getLogger(__name__)


@dataclass
class FusionOutput:
    """融合输出"""
    should_act: bool = False
    action_type: str = "hold"
    harmony_strength: float = 0.5
    fused_confidence: float = 0.5
    insight_confidence: float = 0.5
    awakening_level: str = "dormant"

    fp_insights: List[Dict] = field(default_factory=list)
    recalled_patterns: List[Dict] = field(default_factory=list)

    manas_score: float = 0.5
    timing_score: float = 0.5
    regime_score: float = 0.0
    confidence_score: float = 0.5

    bias_state: str = "neutral"
    bias_correction: float = 1.0

    final_decision: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_act": self.should_act,
            "action_type": self.action_type,
            "harmony_strength": self.harmony_strength,
            "fused_confidence": self.fused_confidence,
            "insight_confidence": self.insight_confidence,
            "awakening_level": self.awakening_level,
            "fp_insights": self.fp_insights,
            "recalled_patterns": self.recalled_patterns,
            "manas_score": self.manas_score,
            "timing_score": self.timing_score,
            "regime_score": self.regime_score,
            "confidence_score": self.confidence_score,
            "bias_state": self.bias_state,
            "bias_correction": self.bias_correction,
            "final_decision": self.final_decision,
        }


class TradingCenter:
    """
    交易中枢

    协调 AttentionOS、FirstPrinciplesMind、AwakenedAlaya 完成交易决策
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

        self.attention_os = get_attention_os()

        self._first_principles_mind = None
        self._awakened_alaya = None

        self._awakened_state: Dict[str, Any] = {
            "fused_confidence": 0.5,
            "adaptive_decisions": 0,
            "fusion_note": "",
        }

        self._initialized = True
        log.info("[TradingCenter] 初始化完成")

    def _get_first_principles_mind(self):
        """获取 FirstPrinciplesMind"""
        if self._first_principles_mind is None:
            try:
                from deva.naja.cognition.first_principles_mind import FirstPrinciplesMind
                self._first_principles_mind = FirstPrinciplesMind()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 FirstPrinciplesMind: {e}")
        return self._first_principles_mind

    def _get_awakened_alaya(self):
        """获取 AwakenedAlaya"""
        if self._awakened_alaya is None:
            try:
                from deva.naja.alaya.awakened_alaya import AwakenedAlaya
                self._awakened_alaya = AwakenedAlaya()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 AwakenedAlaya: {e}")
        return self._awakened_alaya

    def process_market_data(
        self,
        data: Dict[str, Any],
        symbols: Optional[List[str]] = None
    ) -> FusionOutput:
        """
        处理市场数据，生成交易决策

        Args:
            data: 市场数据
            symbols: 关注的股票列表

        Returns:
            FusionOutput: 融合后的决策
        """
        market_state = data.get("market_state", {})
        snapshot = data.get("snapshot", {})

        kernel_output = self.attention_os.make_decision(market_state)

        fp_mind = self._get_first_principles_mind()
        fp_insights = []
        if fp_mind and market_state:
            try:
                fp_result = fp_mind.think(market_state, snapshot)
                fp_insights = fp_result.get("insights", []) if fp_result else []
            except Exception as e:
                log.warning(f"[TradingCenter] FirstPrinciplesMind.think 失败: {e}")

        alaya = self._get_awakened_alaya()
        awakening_level = "dormant"
        recalled_patterns = []
        if alaya and market_state:
            try:
                manas_output_dict = kernel_output.to_dict() if hasattr(kernel_output, 'to_dict') else {
                    "timing_score": kernel_output.timing_score,
                    "regime_score": kernel_output.regime_score,
                    "confidence_score": kernel_output.confidence_score,
                    "risk_temperature": kernel_output.risk_temperature,
                    "portfolio_loss_pct": getattr(kernel_output, 'portfolio_loss_pct', 0.0),
                    "market_deterioration": getattr(kernel_output, 'market_deterioration', False),
                }
                alaya_result = alaya.illuminate(
                    market_data=snapshot,
                    unified_manas_output=manas_output_dict,
                    fp_insights=fp_insights
                )
                awakening_level = alaya_result.get("awakening_level", "dormant")
                recalled_patterns = alaya_result.get("recalled_patterns", [])
            except Exception as e:
                log.warning(f"[TradingCenter] AwakenedAlaya.illuminate 失败: {e}")

        fusion = self._fuse_decisions(kernel_output, fp_insights, awakening_level)

        fusion.recalled_patterns = recalled_patterns
        fusion.manas_score = kernel_output.manas_score
        fusion.timing_score = kernel_output.timing_score
        fusion.regime_score = kernel_output.regime_score
        fusion.confidence_score = kernel_output.confidence_score
        fusion.bias_state = kernel_output.bias_state
        fusion.bias_correction = kernel_output.bias_correction

        return fusion

    def _fuse_decisions(
        self,
        kernel_output,
        fp_insights: List[Dict],
        awakening_level: str
    ) -> FusionOutput:
        """
        融合各模块输出

        融合公式：
            fused_confidence = harmony_strength * 0.7 + insight_confidence * 0.3
        """
        harmony_strength = kernel_output.harmony_strength
        should_act = kernel_output.should_act
        action_type = kernel_output.action_type

        insight_confidence = 0.5
        if fp_insights:
            insight_confidence = sum(i.get('confidence', 0.5) for i in fp_insights) / len(fp_insights)

        if should_act and fp_insights:
            fused_confidence = harmony_strength * 0.7 + insight_confidence * 0.3
            fusion_note = f"FP insights={len(fp_insights)}, harmony={harmony_strength:.2f}, fused={fused_confidence:.2f}"
        else:
            fused_confidence = harmony_strength
            if fp_insights:
                fusion_note = f"HOLD but FP stored (insights={len(fp_insights)})"
            else:
                fusion_note = "HOLD (no FP insights)"

        if awakening_level == "enlightened":
            fused_confidence *= 1.1
        elif awakening_level == "illuminated":
            fused_confidence *= 1.05

        fused_confidence = max(0.0, min(1.0, fused_confidence))

        return FusionOutput(
            should_act=should_act,
            action_type=action_type,
            harmony_strength=harmony_strength,
            fused_confidence=fused_confidence,
            insight_confidence=insight_confidence,
            awakening_level=awakening_level,
            fp_insights=fp_insights,
        )

    def make_decision(
        self,
        market_state: Optional[Dict[str, Any]] = None,
        portfolio: Optional[Any] = None
    ) -> FusionOutput:
        """
        快速决策（不经过完整流程）

        用于简单决策场景
        """
        kernel_output = self.attention_os.make_decision(market_state, portfolio)

        return FusionOutput(
            should_act=kernel_output.should_act,
            action_type=kernel_output.action_type,
            harmony_strength=kernel_output.harmony_strength,
            fused_confidence=kernel_output.confidence,
            manas_score=kernel_output.manas_score,
            timing_score=kernel_output.timing_score,
            regime_score=kernel_output.regime_score,
            confidence_score=kernel_output.confidence_score,
            bias_state=kernel_output.bias_state,
            bias_correction=kernel_output.bias_correction,
        )

    def get_harmony(self) -> Dict[str, Any]:
        """获取当前和谐状态"""
        return self.attention_os.get_harmony()

    def get_attention_os(self) -> AttentionOS:
        """获取 AttentionOS"""
        return self.attention_os

    def process_datasource_data(self, datasource_id: str, data: Any) -> None:
        """
        处理数据源数据（兼容旧接口）

        Args:
            datasource_id: 数据源ID
            data: 数据
        """
        try:
            if isinstance(data, dict):
                self.attention_os.market_scheduler.schedule(data)
        except Exception as e:
            log.warning(f"[TradingCenter] process_datasource_data 失败: {e}")

    def register_datasource(self, datasource_id: str) -> None:
        """注册数据源（兼容旧接口）"""
        pass

    def unregister_datasource(self, datasource_id: str) -> None:
        """注销数据源（兼容旧接口）"""
        pass

    def get_cached_market_time(self) -> str:
        """获取缓存的市场时间（兼容旧接口）"""
        try:
            from deva.naja.radar.trading_clock import get_trading_clock
            clock = get_trading_clock()
            if clock:
                return clock.get_formatted_time()
        except Exception:
            pass
        return ""


_trading_center: Optional[TradingCenter] = None


def get_trading_center() -> TradingCenter:
    """获取 TradingCenter 单例"""
    global _trading_center
    if _trading_center is None:
        _trading_center = TradingCenter()
    return _trading_center
