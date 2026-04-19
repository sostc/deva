from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class FusionResult:
    final_confidence: float = 0.5
    position_adjustment: float = 0.0
    final_position: float = 0.0
    action_type: str = "hold"
    should_act: bool = False
    reasoning: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_confidence": self.final_confidence,
            "position_adjustment": self.position_adjustment,
            "final_position": self.final_position,
            "action_type": self.action_type,
            "should_act": self.should_act,
            "reasoning": self.reasoning,
            "risk_warnings": self.risk_warnings,
        }


@dataclass
class FusionOutput:
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


class DecisionFusion:
    LEVEL_BONUS = {
        "first_principles": 0.15,
        "causal": 0.08,
        "surface": 0.0,
    }

    def fuse(
        self,
        fp_insights: List[Dict],
        kernel_output,
        current_position: float = 0.0,
    ) -> FusionResult:
        reasoning = []
        risk_warnings = []
        fp_confidence = 0.5

        if fp_insights:
            by_level: Dict[str, list] = {}
            for insight in fp_insights:
                level = insight.get("level", "surface")
                insight_type = insight.get("type", "unknown")
                confidence = insight.get("confidence", 0.5)
                by_level.setdefault(level, []).append(
                    {
                        "type": insight_type,
                        "confidence": confidence,
                        "content": insight.get("content", ""),
                    }
                )

            for level, bonus in self.LEVEL_BONUS.items():
                if level in by_level and by_level[level]:
                    fp_confidence += bonus
                    reasoning.append(f"FP洞察({level}): +{bonus}")

            if "first_principles" in by_level:
                for insight in by_level["first_principles"]:
                    if insight["type"] == "opportunity":
                        fp_confidence += 0.05
                        reasoning.append("opportunity + first_principles: +0.05")

        timing = kernel_output.timing_score
        if timing < 0.4:
            fp_confidence *= 0.7
            reasoning.append(f"Manas时机低({timing:.2f}): ×0.7")
        elif timing > 0.7:
            fp_confidence *= 1.1
            reasoning.append(f"Manas时机高({timing:.2f}): ×1.1")

        regime = kernel_output.regime_score
        if regime < -0.3:
            fp_confidence *= 0.8
            reasoning.append(f"Manas环境逆风({regime:.2f}): ×0.8")

        risk_t = getattr(kernel_output, "risk_temperature", 1.0)
        position_adjustment = 0.0
        if risk_t > 1.3:
            position_adjustment = -0.15
            risk_warnings.append(f"风险温度高({risk_t:.2f}): 建议减仓")
        elif risk_t > 1.5:
            position_adjustment = -0.25
            risk_warnings.append(f"风险温度很高({risk_t:.2f}): 强烈建议减仓")

        bias_state = getattr(kernel_output, "bias_state", "neutral")
        bias_correction = getattr(kernel_output, "bias_correction", 1.0)
        if bias_state != "neutral":
            fp_confidence *= bias_correction
            reasoning.append(f"bias纠偏({bias_state}): ×{bias_correction:.2f}")

        final_confidence = max(0.0, min(1.0, fp_confidence))

        if final_confidence < 0.3:
            action_type = "hold"
            should_act = False
            reasoning.append("置信度<0.3: 观望")
        elif final_confidence < 0.5:
            action_type = "act_minimally"
            should_act = True
            reasoning.append("置信度0.3-0.5: 轻仓试探")
        elif final_confidence < 0.7:
            action_type = "act_carefully"
            should_act = True
            reasoning.append("置信度0.5-0.7: 谨慎行动")
        else:
            action_type = "act_fully"
            should_act = True
            reasoning.append("置信度>0.7: 全力行动")

        if fp_insights:
            for insight in fp_insights:
                if insight.get("type") == "opportunity" and insight.get("level") == "first_principles":
                    position_adjustment += 0.20
                    reasoning.append("opportunity+first_principles: 仓位+20%")
                elif insight.get("type") == "opportunity" and insight.get("level") == "causal":
                    position_adjustment += 0.10
                    reasoning.append("opportunity+causal: 仓位+10%")
                elif insight.get("type") == "risk" and insight.get("level") == "first_principles":
                    position_adjustment -= 0.30
                    risk_warnings.append("risk+first_principles: 仓位-30%")

        action_type_attr = getattr(kernel_output, "action_type", "hold")
        if action_type_attr == "hold":
            position_adjustment = min(position_adjustment, 0)
        elif action_type_attr == "act_fully":
            position_adjustment = max(position_adjustment, 0.10)

        final_position = max(0.0, min(1.0, current_position + position_adjustment))

        return FusionResult(
            final_confidence=round(final_confidence, 3),
            position_adjustment=round(position_adjustment, 3),
            final_position=round(final_position, 3),
            action_type=action_type,
            should_act=should_act,
            reasoning=reasoning,
            risk_warnings=risk_warnings,
        )
