from types import SimpleNamespace

from deva.naja.decision.fusion import DecisionFusion


def make_kernel_output(**overrides):
    base = {
        "timing_score": 0.75,
        "regime_score": 0.2,
        "risk_temperature": 1.0,
        "bias_state": "neutral",
        "bias_correction": 1.0,
        "action_type": "act_fully",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_decision_fusion_promotes_high_quality_opportunity():
    fusion = DecisionFusion()
    kernel_output = make_kernel_output()
    fp_insights = [
        {"type": "opportunity", "level": "first_principles", "confidence": 0.9},
    ]

    result = fusion.fuse(fp_insights=fp_insights, kernel_output=kernel_output, current_position=0.2)

    assert result.should_act is True
    assert result.final_confidence >= 0.7
    assert result.final_position >= 0.3


def test_decision_fusion_penalizes_bad_timing():
    fusion = DecisionFusion()
    kernel_output = make_kernel_output(timing_score=0.2, action_type="hold")

    result = fusion.fuse(fp_insights=[], kernel_output=kernel_output, current_position=0.2)

    assert result.final_confidence <= 0.35
    assert result.action_type == "hold"
