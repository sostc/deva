"""
Attention 输出数据模型

包含：
- AttentionFusionOutput: 融合层输出
- AttentionKernelOutput: 内核输出
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


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
