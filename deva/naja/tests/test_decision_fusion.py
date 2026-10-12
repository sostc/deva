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


# ──────────────────────────────────────────────────────────────────────────────
# D1：DecisionPlan 契约 + 仓位定量（见 docs/naja/decision_action_center_design.md）
# ──────────────────────────────────────────────────────────────────────────────


def test_action_severity_ordering_and_downgrade_only():
    """档位有严格程度；融合层只能取更保守的一档。"""
    from deva.naja.decision import action_severity, more_conservative

    assert action_severity("hold") == 0
    assert action_severity("act_minimally") < action_severity("act_carefully")
    assert action_severity("act_carefully") < action_severity("act_fully")
    # 未知档位一律当 hold（保守失败）
    assert action_severity("wat") == 0
    assert action_severity(None) == 0
    # 只能下调，不能上调
    assert more_conservative("act_fully", "act_carefully") == "act_carefully"
    assert more_conservative("act_minimally", "act_fully") == "act_minimally"
    assert more_conservative("act_fully", "act_fully") == "act_fully"


def test_sizing_multiplier_bounded_and_hold_is_zero():
    from deva.naja.decision import compute_position_multiplier

    assert compute_position_multiplier("hold", 0.5, 1.0) == 0.0
    for action in ("act_minimally", "act_carefully", "act_fully"):
        for alpha in (0.1, 0.3, 0.45, 0.9, 5.0):
            for risk_t in (0.5, 1.0, 1.4, 2.0, 9.0):
                value = compute_position_multiplier(action, alpha, risk_t)
                assert 0.0 <= value <= 1.0, (action, alpha, risk_t, value)


def test_sizing_risk_temperature_brakes_position():
    from deva.naja.decision import compute_position_multiplier

    calm = compute_position_multiplier("act_fully", 0.45, 1.0)
    warm = compute_position_multiplier("act_fully", 0.45, 1.4)
    hot = compute_position_multiplier("act_fully", 0.45, 2.0)
    assert calm > warm > hot


def test_sizing_never_degrades_to_constant():
    """不同档位必须给出不同量——防止公式退化成常数。"""
    from deva.naja.decision import compute_position_multiplier

    values = {
        a: compute_position_multiplier(a, 0.45, 1.0)
        for a in ("act_minimally", "act_carefully", "act_fully")
    }
    assert len(set(values.values())) == 3, values


def test_compute_order_amount_respects_floor_and_hold():
    from deva.naja.decision import compute_order_amount

    assert compute_order_amount(0.0, 10000) == 0.0
    assert compute_order_amount(1.0, 10000) == 10000.0
    assert compute_order_amount(0.6, 10000) == 6000.0
    # 乘子极小但确有动作时，不低于最小额
    assert compute_order_amount(0.001, 10000, min_amount=1000.0) == 1000.0
    # 脏输入不炸
    assert compute_order_amount("x", 10000) == 0.0


def test_decision_plan_from_fusion_and_actionable():
    from deva.naja.decision import DecisionPlan, compute_plan_size_hint
    from deva.naja.decision.fusion import FusionOutput

    fusion = FusionOutput(
        should_act=True,
        action_type="act_carefully",
        fused_confidence=0.55,
        risk_temperature=1.2,
        alpha=0.5,
        gate_reason="时机尚可，轻仓试探",
        final_decision={"reasoning": ["r1"]},
    )
    plan = DecisionPlan.from_fusion(
        fusion,
        symbol="600000",
        side="buy",
        source_signal={"strategy_id": "s1"},
        size_hint=compute_plan_size_hint(fusion),
    )

    assert plan.symbol == "600000"
    assert plan.side == "buy"
    assert plan.action_type == "act_carefully"
    assert plan.gate_reason == "时机尚可，轻仓试探"
    assert 0.0 < plan.size_hint <= 1.0
    assert plan.is_actionable() is True
    assert set(plan.to_dict()) == set(plan.__dataclass_fields__)

    # hold 不可执行
    hold_plan = DecisionPlan.from_fusion(
        FusionOutput(should_act=False, action_type="hold"), symbol="600000"
    )
    assert hold_plan.is_actionable() is False


def test_side_from_signal_type_normalizes():
    from deva.naja.decision import side_from_signal_type

    assert side_from_signal_type("buy") == "buy"
    assert side_from_signal_type("BUY_SIGNAL") == "buy"
    assert side_from_signal_type("卖出") == "sell"
    assert side_from_signal_type(None) == "none"
    assert side_from_signal_type("neutral") == "none"


def test_kernel_output_carries_action_gate_reason():
    from deva.naja.attention.models.output import AttentionKernelOutput

    out = AttentionKernelOutput(action_gate_reason="风险温度过高，保持观望")
    assert out.to_dict()["action_gate_reason"] == "风险温度过高，保持观望"
    # 不把 fusion_output 之外的新字段漏进 to_dict
    assert set(out.to_dict()) == set(out.__dataclass_fields__) - {"fusion_output"}


def test_fusion_output_to_dict_includes_decision_context():
    from deva.naja.decision.fusion import FusionOutput

    out = FusionOutput(risk_temperature=1.4, alpha=0.8, gate_reason="轻仓")
    dumped = out.to_dict()
    assert set(dumped) == set(out.__dataclass_fields__)
    assert dumped["risk_temperature"] == 1.4
    assert dumped["alpha"] == 0.8
    assert dumped["gate_reason"] == "轻仓"


# ──────────────────────────────────────────────────────────────────────────────
# D2：action_type 权威规则在融合层生效 + 执行层按计划定量
# ──────────────────────────────────────────────────────────────────────────────


def test_fusion_downgrades_when_manas_is_more_conservative():
    """融合层自身想给 act_fully，但 Manas 只说 act_carefully → 必须被下调。"""
    fusion = DecisionFusion()
    kernel_output = make_kernel_output(action_type="act_carefully")
    fp_insights = [{"type": "opportunity", "level": "first_principles", "confidence": 0.95}]

    result = fusion.fuse(fp_insights=fp_insights, kernel_output=kernel_output, current_position=0.0)

    assert result.action_type == "act_carefully"
    assert any("权威下调" in r for r in result.reasoning)


def test_fusion_never_promotes_beyond_manas_ceiling():
    """Manas 档位是上限：自身档位不得高于它。"""
    fusion = DecisionFusion()
    kernel_output = make_kernel_output(action_type="act_minimally")
    fp_insights = [{"type": "opportunity", "level": "first_principles", "confidence": 0.99}]

    result = fusion.fuse(fp_insights=fp_insights, kernel_output=kernel_output, current_position=0.0)

    assert result.action_type == "act_minimally"


def test_fusion_manas_act_fully_is_preserved():
    """Manas 说全力，且自身也够格 → 保持 act_fully（不被误降）。"""
    fusion = DecisionFusion()
    kernel_output = make_kernel_output(action_type="act_fully")
    fp_insights = [{"type": "opportunity", "level": "first_principles", "confidence": 0.95}]

    result = fusion.fuse(fp_insights=fp_insights, kernel_output=kernel_output, current_position=0.0)

    assert result.action_type == "act_fully"


def test_adaptive_cycle_sizing_follows_plan(monkeypatch):
    """执行层按 DecisionPlan.size_hint 定量；无 plan / 关开关则回落固定量。"""
    from deva.naja.bandit.adaptive_cycle import AdaptiveCycle

    cycle = AdaptiveCycle.__new__(AdaptiveCycle)
    cycle._base_order_amount = 10000.0
    cycle._min_order_amount = 1000.0
    monkeypatch.delenv("NAJA_MANAS_SIZING", raising=False)

    # 有 plan：按乘子缩放
    assert cycle._resolve_order_amount({"plan": {"size_hint": 0.6}}) == 6000.0
    # 极小乘子仍不低于 min
    assert cycle._resolve_order_amount({"plan": {"size_hint": 0.001}}) == 1000.0
    # hold（size_hint=0）→ 0，调用方会跳过建仓
    assert cycle._resolve_order_amount({"plan": {"size_hint": 0.0}}) == 0.0
    # 降级路径：决策不带 plan → 保持原固定量
    assert cycle._resolve_order_amount({"approved": True}) == 10000.0

    # 回滚开关：关闭 Manas 定量 → 固定量
    monkeypatch.setenv("NAJA_MANAS_SIZING", "0")
    assert cycle._resolve_order_amount({"plan": {"size_hint": 0.6}}) == 10000.0


def test_adaptive_stop_loss_extreme_risk_branch_is_reachable():
    """极高风险分支必须可达（原实现被 >1.3 分支挡住，是死代码）。"""
    from deva.naja.bandit.adaptive_cycle import AdaptiveCycle

    cycle = AdaptiveCycle.__new__(AdaptiveCycle)
    cycle._manas_context_cache = {"risk_temperature": 2.0, "timing_score": 0.6}
    cycle._last_manas_update = 9e18  # 避免刷新缓存
    cycle._manas_update_interval = 60.0
    stop_loss, take_profit = cycle._get_adaptive_stop_loss()
    # 极高风险：-8*0.4 = -3.2，15*0.6 = 9.0
    assert stop_loss == -3.2
    assert take_profit == 9.0


