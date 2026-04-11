"""
AttentionOS - 注意力操作系统

分层架构：
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Attention OS (注意力操作系统)                          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    OS 应用层 (Applications)                            │   │
│  │                                                                      │   │
│  │  • StrategyDecisionMaker - 市场调度（题材/个股权重 + 频率控制）               │   │
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
│  │  • ValueSystem - 价值观驱动                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘

核心能力（被各方调用）：
    • compute_attention() - QKV 注意力计算
    • make_decision() - ManasEngine 决策
    • get_harmony() - 获取和谐状态

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

from .kernel.event_encoder import Encoder
from .kernel.multi_scorer import MultiHeadAttention
from .kernel.manas_engine import ManasEngine
from .kernel import get_default_heads
from .values.system import ValueSystem
from .text_importance_scorer import TextImportanceScorer

from .attention_fusion import get_attention_fusion

log = logging.getLogger(__name__)


@dataclass
class AttentionFusionOutput:
    """
    【融合层输出】AttentionFusion 的完整输出

    ════════════════════════════════════════════════════════════════════════════
                                字 段 归 属
    ════════════════════════════════════════════════════════════════════════════

    【桥接层-差异检测】
        consensus_blocks      = 外部热 ∩ 我们持有（坚定持有）
        divergence_blocks     = 外部热 ∩ 我们持有（方向分歧→验证）
        blind_spots          = 外部热 ∩ 我们没关注（→探究）
        new_hot_blocks       = 新出现的热点（→跟踪）
        conviction_score     = 信念验证整体分数

    【被动发现-盲区】
        blind_spot_investigations = BlindSpotInvestigator探究结果列表
            每个元素: {block_id, root_cause, resolvers, recommendation, is_actionable}

    【主动发现-天道】
        value_score          = 天道价值分数（我们认定的重要变化）
        market_narrative_score = 民心市场叙事分数（参考）
        value_signals        = 天道信号详情（哪些关键词被命中）
        market_narrative_signals = 民心信号详情（参考）

    【时机】
        fusion_timing_signal = 时机信号

    【融合信号】
        fusion_signals       = 各 block 融合信号列表
        fusion_warnings      = 融合过程中的警告信息
    """
    conviction_score: float = 0.0                                     # 【桥接】信念分数
    fusion_signals: List[Dict] = field(default_factory=list)          # 【融合】融合信号列表
    consensus_blocks: List[str] = field(default_factory=list)          # 【桥接】共识block
    divergence_blocks: List[str] = field(default_factory=list)         # 【桥接】分歧block
    blind_spots: List[str] = field(default_factory=list)               # 【被动发现】盲区block
    new_hot_blocks: List[str] = field(default_factory=list)            # 【外部】新热点block
    fusion_timing_signal: str = "unknown"                              # 【时机】融合时机信号

    blind_spot_investigations: List[Dict] = field(default_factory=list)  # 【被动发现】盲区探究结果

    value_score: float = 0.0                                          # 【主动发现-天道】价值分数
    market_narrative_score: float = 0.0                                # 【主动发现-民心】市场叙事分数
    value_signals: Dict[str, List[str]] = field(default_factory=dict)  # 【主动发现-天道】价值信号
    market_narrative_signals: Dict[str, List[str]] = field(default_factory=dict)  # 【主动发现-民心】市场叙事信号

    fusion_warnings: List[str] = field(default_factory=list)          # 【健康检查】警告信息
    fusion_success: bool = True                                       # 【健康检查】融合是否成功

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conviction_score": self.conviction_score,
            "fusion_signals": self.fusion_signals,
            "consensus_blocks": self.consensus_blocks,
            "divergence_blocks": self.divergence_blocks,
            "blind_spots": self.blind_spots,
            "new_hot_blocks": self.new_hot_blocks,
            "fusion_timing_signal": self.fusion_timing_signal,
            "blind_spot_investigations": self.blind_spot_investigations,
            "value_score": self.value_score,
            "market_narrative_score": self.market_narrative_score,
            "value_signals": self.value_signals,
            "market_narrative_signals": self.market_narrative_signals,
            "fusion_warnings": self.fusion_warnings,
            "fusion_success": self.fusion_success,
        }


@dataclass
class AttentionKernelOutput:
    """
    【内核输出层】注意力内核完整输出

    ════════════════════════════════════════════════════════════════════════════
                                字 段 归 属
    ════════════════════════════════════════════════════════════════════════════

    【内核核心】（QKV 注意力计算产生）
        alpha              = 注意力系数（控制整体行动强度）
        confidence         = 注意力置信度
        attention_weights  = 各 symbol 的注意力权重
        focus_symbols      = 焦点 symbol 列表（权重 top-k）

    【时机/市场状态】（来自 ManasEngine）
        timing_score       = 时机分数
        regime_score       = 市场状态分数

    【行动决策】（来自 ManasEngine）
        should_act         = 是否应行动
        action_type        = 行动类型（hold/buy/sell 等）
        harmony_state      = 和谐状态
        harmony_strength   = 和谐强度
        confidence_score   = Manas 置信度

    【风险/偏差】（来自 ManasEngine）
        risk_temperature  = 风险温度
        bias_state        = 偏差状态
        bias_correction   = 偏差校正

    【认知层】（来自 ManasEngine）
        narrative_risk     = 叙事风险
        ai_compute_direction = AI 算力方向
        awakening_level    = 觉醒水平

    【融合层-请使用 fusion_output 字段】（由 AttentionFusion 生成）
        ⚠️ 以下字段已迁移到 fusion_output，请勿在此类中直接使用
        conviction_score, fusion_signals, consensus_blocks, divergence_blocks,
        blind_spots, new_hot_blocks, fusion_timing_signal,
        blind_spot_investigations, value_score, market_narrative_score,
        value_signals, market_narrative_signals

    ════════════════════════════════════════════════════════════════════════════
                                使 用 方 式
    ════════════════════════════════════════════════════════════════════════════

        kernel_output = attention_kernel.compute(events, market_state)
        kernel_output.alpha                    # ← 内核核心
        kernel_output.should_act               # ← 行动决策
        kernel_output.fusion_output.to_dict()  # ← 融合层输出（如果需要）
    """
    alpha: float = 1.0
    confidence: float = 0.5
    attention_weights: Dict[str, float] = field(default_factory=dict)  # 【内核】注意力权重
    focus_symbols: List[str] = field(default_factory=list)              # 【内核】焦点符号

    manas_score: float = 0.5                                         # 【内核】Manas分数
    timing_score: float = 0.5                                        # 【时机】timing分数
    regime_score: float = 0.0                                         # 【时机】市场状态
    confidence_score: float = 0.5                                    # 【内核】置信度

    risk_temperature: float = 1.0                                    # 【风险】风险温度

    should_act: bool = False                                         # 【决策】是否应行动
    action_type: str = "hold"                                        # 【决策】行动类型
    harmony_state: str = "neutral"                                    # 【决策】和谐状态
    harmony_strength: float = 0.5                                     # 【决策】和谐强度

    bias_state: str = "neutral"                                      # 【偏差】偏差状态
    bias_correction: float = 1.0                                      # 【偏差】偏差校正

    narrative_risk: float = 0.5                                       # 【认知】叙事风险
    ai_compute_direction: str = "unknown"                            # 【认知】AI算力方向
    awakening_level: str = "dormant"                                  # 【认知】觉醒水平

    fusion_output: Optional[AttentionFusionOutput] = None             # 【融合层】融合结果（单独存储）

    def to_dict(self) -> Dict[str, Any]:
        result = {
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
        if self.fusion_output is not None:
            result["fusion_output"] = self.fusion_output.to_dict()
        return result


class AttentionKernel:
    """
    注意力内核

    核心组件：
    - Encoder: 事件编码
    - MultiHeadAttention: QKV 注意力计算
    - ManasEngine: 决策中枢
    - ValueSystem: 价值观驱动
    """

    def __init__(self):
        self.encoder = Encoder()
        heads = get_default_heads()
        self.multi_head = MultiHeadAttention(heads)
        self.manas_engine = ManasEngine()
        self._value_system = None

        self._last_output: Optional[AttentionKernelOutput] = None
        self._update_interval = 1.0
        self._last_update = 0.0

    def _get_value_system(self) -> ValueSystem:
        if self._value_system is None:
            self._value_system = SR('value_system')
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

        fusion_output: Optional[AttentionFusionOutput] = None
        fusion_warnings: List[str] = []

        try:
            from deva.naja.attention.attention_fusion import get_attention_fusion
            fusion = get_attention_fusion()
            if attention_weights:
                fusion_result = fusion.fuse(
                    market_attention=attention_weights,
                    portfolio_summary=None,
                    world_narrative=None,
                )
                if fusion_result:
                    fusion_signals = [
                        {"block_id": s.block_id, "score": s.fused_score,
                         "action": s.action_recommendation, "should_act": s.should_act}
                        for s in fusion_result.signals[:10]
                    ]
                    consensus_blocks = [b for b, _ in fusion_result.consensus_blocks[:5]]
                    divergence_blocks = [b for b, _ in fusion_result.divergence_blocks[:5]]
                    blind_spots = [b for b, _ in fusion_result.blind_spots[:5]]
                    new_hot_blocks = [b for b, _ in fusion_result.new_hot_blocks[:5]]

                    blind_spot_investigations = []
                    try:
                        from deva.naja.attention.discovery import get_blind_spot_investigator
                        investigator = get_blind_spot_investigator()
                        blind_spot_with_scores = [
                            (b, fusion_result.blind_spots[i][1])
                            for i, b in enumerate(blind_spots)
                        ]
                        if blind_spot_with_scores:
                            investigation_result = investigator.investigate_all(blind_spot_with_scores)
                            if investigation_result:
                                blind_spot_investigations = [
                                    {
                                        "block_id": r.block_id,
                                        "root_cause": r.root_cause,
                                        "resolvers": r.resolvers,
                                        "auto_followed": r.auto_followed_stocks,
                                        "confidence": r.investigation_confidence,
                                    }
                                    for r in investigation_result.investigations
                                    if r.is_actionable
                                ]
                    except Exception as e:
                        fusion_warnings.append(f"blind_spot_investigation_failed: {e}")

                    fusion_output = AttentionFusionOutput(
                        conviction_score=fusion_result.conviction_score,
                        fusion_signals=fusion_signals,
                        consensus_blocks=consensus_blocks,
                        divergence_blocks=divergence_blocks,
                        blind_spots=blind_spots,
                        new_hot_blocks=new_hot_blocks,
                        fusion_timing_signal=fusion_result.timing_signal,
                        blind_spot_investigations=blind_spot_investigations,
                        value_score=fusion_result.value_score,
                        market_narrative_score=fusion_result.market_narrative_score,
                        value_signals=fusion_result.value_signals,
                        market_narrative_signals=fusion_result.market_narrative_signals,
                        fusion_warnings=fusion_warnings,
                        fusion_success=True,
                    )
                else:
                    fusion_output = AttentionFusionOutput(
                        fusion_warnings=["fusion_returned_none"],
                        fusion_success=False,
                    )
            else:
                fusion_output = AttentionFusionOutput(
                    fusion_warnings=["no_attention_weights"],
                    fusion_success=True,
                )
        except Exception as e:
            log.warning(f"[AttentionKernel] AttentionFusion 调用失败: {e}")
            fusion_output = AttentionFusionOutput(
                fusion_warnings=[f"fusion_exception: {e}"],
                fusion_success=False,
            )

        for e in encoded_events:
            symbol = getattr(e, 'symbol', None) or e.source if hasattr(e, 'source') else "unknown"
            alignment = e.features.get("_value_alignment", 0.5)
            reason = vs.generate_focus_reason(e.features)
            vs.record_attention(symbol, alignment, reason)
            vs.set_last_decision_reason(reason)

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
            fusion_output=fusion_output,
        )

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

    def get_manas_engine(self) -> ManasEngine:
        """获取 ManasEngine 实例"""
        return self.manas_engine

    def get_focus_weights(self) -> Dict[str, float]:
        """获取焦点权重（兼容 BanditOptimizer）"""
        if self._last_output is None:
            return {}
        return self._last_output.attention_weights

    def get_latest_output(self) -> Optional["AttentionKernelOutput"]:
        """获取最新的内核输出（兼容 BanditOptimizer）"""
        return self._last_output

    def _get_session_manager(self):
        try:
            return SR('trading_clock')
        except ImportError:
            return None

    def _get_portfolio(self):
        try:
            return SR('virtual_portfolio')
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
            return SR('bandit_tracker')
        except ImportError:
            return None


class StrategyDecisionMaker:
    """
    策略决策器 - Attention OS 应用层

    职责：
    - 基于 AttentionKernel 的决策进行策略执行判断
    - 决定是否应该执行交易策略
    - 时机选择和置信度评估

    依托 AttentionKernel 获取和谐度、时机评分和置信度
    """

    def __init__(self, kernel: AttentionKernel):
        self.kernel = kernel

        self._block_weights: Dict[str, float] = {}
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
            "block_weights": self._block_weights,
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
        """分配个股权重和题材权重（支持多 blocks）"""
        base_weights = market_data.get("symbol_weights", {})
        block_hotspot = market_data.get("block_hotspot", {})

        if not base_weights:
            log.debug(f"[StrategyDecisionMaker] 警告: market_data 中没有 symbol_weights")
            return

        alpha = kernel_output.alpha
        harmony = kernel_output.harmony_strength
        confidence = kernel_output.confidence_score

        self._symbol_weights = {}
        self._block_weights = {}

        block_totals: Dict[str, float] = {}

        for symbol, base_weight in base_weights.items():
            attention_weight = kernel_output.attention_weights.get(symbol, 0.5)

            final_weight = base_weight * attention_weight * alpha * harmony * confidence

            self._symbol_weights[symbol] = max(0.0, min(1.0, final_weight))

            blocks = self._get_symbol_blocks(symbol, block_hotspot)
            if not blocks:
                blocks = ["other"]
            weight_per_block = final_weight / len(blocks)
            for block in blocks:
                if block not in block_totals:
                    block_totals[block] = 0.0
                block_totals[block] += weight_per_block

        for block, total in block_totals.items():
            self._block_weights[block] = min(1.0, total / max(1, len(block_totals)))

    def _get_symbol_blocks(self, symbol: str, block_hotspot: Dict[str, float]) -> List[str]:
        """根据个股代码和题材热点确定该个股属于哪些题材"""
        blocks = []
        symbol_upper = symbol.upper()
        for block_name in block_hotspot.keys():
            if block_name.upper() in symbol_upper or any(c in symbol_upper for c in ['AI', 'TECH', 'FIN', 'MED', 'ENE', 'CON']):
                blocks.append(block_name)
        return blocks if blocks else list(block_hotspot.keys())[:3]

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

    def get_top_blocks(self, n: int = 5) -> List[Dict[str, Any]]:
        """获取权重最高的 n 个 block"""
        sorted_weights = sorted(
            self._block_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [
            {"block": blk, "weight": wgt}
            for blk, wgt in sorted_weights[:n]
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
        self.strategy_decision_maker = StrategyDecisionMaker(self.kernel)
        self._text_scorer = TextImportanceScorer(self)

        self._strategy_manager = None
        self._subscribe_to_hotspot_events()
        self._subscribe_to_text_events()

        self._initialized = True

    def initialize_strategies(self):
        """初始化所有交易策略"""
        if self._strategy_manager is not None:
            return

        from deva.naja.attention.strategies import (
            GlobalMarketSentinel,
            BlockRotationHunter,
            MomentumSurgeTracker,
            AnomalyPatternSniper,
            SmartMoneyFlowDetector,
            LiquidityCrisisTracker,
            PanicPeakDetector,
            RecoveryConfirmationMonitor,
        )
        from deva.naja.attention.strategies.us_strategies import (
            USGlobalMarketSentinel,
            USBlockRotationHunter,
            USMomentumSurgeTracker,
            USAnomalyPatternSniper,
            USSmartMoneyFlowDetector,
        )

        self._strategy_manager = {
            'cn_global_sentinel': GlobalMarketSentinel(market='CN'),
            'cn_block_rotation': BlockRotationHunter(market='CN'),
            'cn_momentum_tracker': MomentumSurgeTracker(market='CN'),
            'cn_anomaly_sniper': AnomalyPatternSniper(market='CN'),
            'cn_smart_money': SmartMoneyFlowDetector(market='CN'),
            'cn_liquidity_crisis': LiquidityCrisisTracker(market='CN'),
            'cn_panic_peak': PanicPeakDetector(market='CN'),
            'cn_recovery_monitor': RecoveryConfirmationMonitor(market='CN'),
            'us_global_sentinel': USGlobalMarketSentinel(),
            'us_block_rotation': USBlockRotationHunter(),
            'us_momentum_tracker': USMomentumSurgeTracker(),
            'us_anomaly_sniper': USAnomalyPatternSniper(),
            'us_smart_money': USSmartMoneyFlowDetector(),
        }

        for strategy in self._strategy_manager.values():
            strategy.subscribe_to_events()

        log.info(f"[AttentionOS] 已初始化 {len(self._strategy_manager)} 个策略 (A股 {8}, 美股 {5})")

    def get_strategy_signals(self, strategy_id: Optional[str] = None, n: int = 20) -> List[Dict]:
        """获取策略信号"""
        if self._strategy_manager is None:
            return []

        if strategy_id:
            strategy = self._strategy_manager.get(strategy_id)
            return strategy.get_recent_signals(n) if strategy else []

        all_signals = []
        for strategy in self._strategy_manager.values():
            all_signals.extend(strategy.get_recent_signals(n))

        return sorted(all_signals, key=lambda x: x['timestamp'], reverse=True)[:n]

    def _subscribe_to_hotspot_events(self):
        """订阅市场热点事件"""
        try:
            from deva.naja.events import get_event_bus
            event_bus = get_event_bus()
            event_bus.subscribe(
                'HotspotComputedEvent',
                self._on_hotspot_computed,
                markets={'US', 'CN'},
                priority=10
            )
            event_bus.subscribe(
                'HotspotShiftEvent',
                self._on_hotspot_shift,
                priority=5
            )
            log.info("[AttentionOS] 已订阅市场热点事件和热点转移事件")
        except Exception as e:
            log.warning(f"[AttentionOS] 订阅市场热点事件失败: {e}")

    def _subscribe_to_text_events(self):
        """订阅文本获取事件"""
        try:
            from deva.naja.events import get_event_bus
            event_bus = get_event_bus()
            event_bus.subscribe(
                'TextFetchedEvent',
                self._on_text_fetched,
                priority=10
            )
            log.info("[AttentionOS] 已订阅文本获取事件")
        except Exception as e:
            log.warning(f"[AttentionOS] 订阅文本获取事件失败: {e}")

    def _on_text_fetched(self, event):
        """处理文本获取事件 - TextImportanceScorer 进行重要性评分"""
        try:
            self._text_scorer.on_text_fetched(event)
        except Exception as e:
            log.debug(f"[AttentionOS] 处理文本获取事件失败: {e}")

    def _on_hotspot_computed(self, event):
        """处理热点计算完成事件"""
        try:
            market_data = {
                'market': event.market,
                'global_hotspot': event.global_hotspot,
                'activity': event.activity,
                'block_hotspot': event.block_hotspot,
                'symbol_weights': event.symbol_weights,
                'symbols': event.symbols,
            }

            self.strategy_decision_maker.schedule(market_data)

            log.debug(f"[AttentionOS] 处理热点事件: market={event.market}, global_hotspot={event.global_hotspot:.3f}")
        except Exception as e:
            log.debug(f"[AttentionOS] 处理热点事件失败: {e}")

    def _on_hotspot_shift(self, event):
        """处理热点转移事件 - 内核决定是否发送到 InsightPool"""
        try:
            should_emit = self._should_emit_to_insight(event)
            if should_emit:
                self._emit_shift_to_insight(event)
            log.debug(f"[AttentionOS] 处理热点转移事件: type={event.event_type}, emitted={should_emit}")
        except Exception as e:
            log.debug(f"[AttentionOS] 处理热点转移事件失败: {e}")

    def _should_emit_to_insight(self, event) -> bool:
        """根据事件类型和分数决定是否发送到 InsightPool"""
        score = getattr(event, 'score', 0.0)
        event_type = getattr(event, 'event_type', '')
        old_value = getattr(event, 'old_value', None)
        new_value = getattr(event, 'new_value', None)

        if score < 0.1:
            return False

        if event_type in ("global_hotspot_shift", "market_state_shift"):
            return True

        if event_type in ("block_concentration_shift", "market_activity_shift"):
            if old_value is not None and new_value is not None:
                change = abs(new_value - old_value) if old_value else 0
                return change >= 0.15
            return score >= 0.3

        if event_type in ("block_hotspot", "symbol_hotspot_change"):
            return score >= 0.3

        if event_type in ("effective_pattern", "ineffective_pattern"):
            return True

        if event_type == "hotspot_shift":
            return True

        return score >= 0.2

    def _emit_shift_to_insight(self, event):
        """发送热点转移事件到 InsightPool（带用户个性化打分）"""
        try:
            from deva.naja.cognition.singletons import SR
            pool = SR('insight_pool')
            if not pool:
                return

            insight_data = {
                "theme": getattr(event, 'title', ''),
                "summary": getattr(event, 'content', ''),
                "symbols": [getattr(event, 'symbol', '')] if getattr(event, 'symbol', '') else [],
                "blocks": [getattr(event, 'block', '')] if getattr(event, 'block', '') else [],
                "confidence": min(0.9, max(0.3, getattr(event, 'score', 0.5))),
                "actionability": 0.5,
                "system_hotspot": getattr(event, 'score', 0.5),
                "source": "hotspot_shift",
                "signal_type": getattr(event, 'event_type', 'hotspot_shift'),
                "ts": getattr(event, 'timestamp', time.time()),
                "payload": getattr(event, 'payload', {}),
            }

            personalized = self.kernel.personalize_event(insight_data)
            pool.ingest_hotspot_event(personalized)
        except Exception as e:
            log.debug(f"[AttentionOS] 发送热点转移事件到 InsightPool 失败: {e}")

    def initialize(self):
        """初始化"""
        log.info("[AttentionOS] 初始化完成")

    def compute_attention(
        self,
        events: List[Any],
        market_state: Optional[Dict[str, Any]] = None,
        query_state: Optional[Any] = None
    ) -> AttentionKernelOutput:
        """
        计算注意力

        数据流与子系统影响：
        ┌─────────────────────────────────────────────────────────────────────────────┐
        │                         compute_attention()                               │
        │                                                                             │
        │  输出:                                                                       │
        │    • attention_weights ──────────────→ _allocate_weights()                  │
        │    • alpha ─────────────────────────→ final_weight 乘因子                  │
        │    • harmony_strength ──────────────→ _adjust_frequency()                   │
        │    • action_type ──────────────────→ _allocate_strategies()                │
        │    • regime ────────────────────────→ regime_factor *= 策略权重              │
        │    • vs.record_attention() ─────────→ ValueSystem                          │
        └─────────────────────────────────────────────────────────────────────────────┘

        影响的子系统：
          1. StrategyDecisionMaker.symbol_weights / block_weights
             final_weight = base_weight * attention_weight * alpha * harmony * confidence
          2. StrategyDecisionMaker.frequency_level
             composite_score = harmony * 0.5 + timing * 0.3 + (1.0 if regime > 0 else 0.3) * 0.2
          3. StrategyDecisionMaker.strategy_allocations
             根据 action_type 分配 momentum/mean_reversion/breakout/grid/wait 权重
        """
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
        return self.strategy_decision_maker.schedule(market_data)

    def get_harmony(self) -> Dict[str, Any]:
        """获取和谐状态"""
        return self.kernel.get_harmony()

    def get_kernel(self) -> AttentionKernel:
        """获取 AttentionKernel 实例（兼容 BanditOptimizer）"""
        return self.kernel


_attention_os: Optional[AttentionOS] = None


def get_attention_os() -> AttentionOS:
    """获取 AttentionOS 单例"""
    from deva.naja.register import SR
    return SR('attention_os')

    global _attention_os
    if _attention_os is None:
        _attention_os = AttentionOS()
    return _attention_os
