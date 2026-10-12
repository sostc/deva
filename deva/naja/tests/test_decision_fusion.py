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


# ──────────────────────────────────────────────────────────────────────────────
# D3：闭环反馈事件（执行结果回流）
# ──────────────────────────────────────────────────────────────────────────────


def test_trade_outcome_event_routes_to_trading_bus():
    from deva.naja.events import TradeOutcomeEvent, resolve_event_bus_type

    assert resolve_event_bus_type(TradeOutcomeEvent) == "trading"

    win = TradeOutcomeEvent(symbol="600000", pnl_pct=3.5, close_reason="TAKE_PROFIT")
    dumped = win.to_dict()
    assert dumped["_type"] == "TradeOutcomeEvent"
    assert dumped["is_win"] is True

    loss = TradeOutcomeEvent(symbol="600519", pnl_pct=-1.0, close_reason="STOP_LOSS")
    assert loss.is_win is False
    assert loss.to_dict()["is_win"] is False


# ──────────────────────────────────────────────────────────────────────────────
# UI 接线：DecisionPlan 经 query service 以 dict 暴露给 dashboard（§6.4）
# ──────────────────────────────────────────────────────────────────────────────


def _record_fake_plan(center, approved=None, **overrides):
    """往 TradingCenter 的留痕队列塞一条计划，绕开完整决策管道。"""
    from deva.naja.decision import DecisionPlan

    payload = dict(
        symbol="600000",
        side="buy",
        action_type="act_carefully",
        size_hint=0.6,
        confidence=0.55,
        risk_temperature=1.2,
        gate_reason="时机尚可，轻仓试探",
        should_act=True,
        reasons=["r1"],
        source_signal={"strategy_id": "s1"},
    )
    payload.update(overrides)
    center._record_plan(DecisionPlan(**payload), approved=approved)
    return payload


TEST_JOURNAL_TABLE = "naja_decision_journal_test"


def _temp_journal(center):
    """把 TradingCenter 的落盘日志换成**临时表**，用完清掉。

    必须这么做：TradingCenter 是单例，默认写的是真实决策库
    （``naja_decision_journal`` / ``~/.deva/nb.sqlite``），测试不该污染它。
    """
    from contextlib import contextmanager

    from deva.naja.decision.journal import DecisionJournal

    @contextmanager
    def _cm():
        original = getattr(center, "_decision_journal", None)
        journal = DecisionJournal(table=TEST_JOURNAL_TABLE, maxsize=200)
        journal.clear()
        center._decision_journal = journal
        center._recent_plans.clear()
        try:
            yield journal
        finally:
            journal.clear()
            center._decision_journal = original
            center._recent_plans.clear()

    return _cm()


def test_trading_center_records_decision_plans():
    """每次产出 DecisionPlan 都留痕；查询返回纯 dict 且键集正确。"""
    from deva.naja.attention.orchestration.trading_center import get_trading_center

    center = get_trading_center()
    with _temp_journal(center) as journal:
        _record_fake_plan(center, approved=True)

        summary = center.get_decision_plan_summary(limit=5)
        assert summary["available"] is True
        assert summary["stats"]["total"] == 1
        assert summary["stats"]["persisted"] is True

        latest = center.get_latest_decision()
        assert isinstance(latest, dict)
        # 留痕 = to_dict() 的副本 + recorded_at（+ approved，若有传入）
        from deva.naja.decision import DecisionPlan

        assert set(latest) == set(DecisionPlan.__dataclass_fields__) | {"recorded_at", "approved"}
        assert latest["symbol"] == "600000"
        assert latest["action_type"] == "act_carefully"
        assert latest["approved"] is True
        assert isinstance(latest["recorded_at"], float)

        # 未传 approved 时不硬塞该键（避免 UI 误判"已批准"）
        _record_fake_plan(center, symbol="000002")
        assert "approved" not in center.get_latest_decision()

        # 确实落了盘（而不只是内存队列）
        assert journal.count() == 2
        assert journal.recent(1)[0]["symbol"] == "000002"


def test_recent_decisions_survive_restart():
    """核心诉求：换一个进程（新 TradingCenter）也能读到旧决策。

    这里用"绕过内存队列、直接读落盘"来模拟重启：清空 deque 后
    ``get_recent_decisions`` 仍应返回落盘历史。
    """
    from deva.naja.attention.orchestration.trading_center import get_trading_center

    center = get_trading_center()
    with _temp_journal(center) as journal:
        _record_fake_plan(center, symbol="600519", approved=True)

        # 模拟重启：内存队列清空（落盘不动）
        center._recent_plans.clear()
        assert center.get_latest_decision()["symbol"] == "600519"

        # 再模拟一次"全新进程"：换一个 DecisionJournal 实例指向同一张表
        from deva.naja.decision.journal import DecisionJournal

        fresh = DecisionJournal(table=TEST_JOURNAL_TABLE, maxsize=200)
        assert fresh.recent(5)[0]["symbol"] == "600519"
        assert journal.count() == 1


def test_decision_history_window_filters_by_time():
    """回放窗口按时间过滤：48 小时前的决策不该出现在 24h 窗口里。"""
    import time

    from deva.naja.attention.orchestration.trading_center import get_trading_center
    from deva.naja.decision import get_decision_history

    center = get_trading_center()
    with _temp_journal(center) as journal:
        _record_fake_plan(center, symbol="FRESH")

        # 直接写一条 48 小时前的（绕开 record() 的单调递增护栏）。
        # 表的 maxsize 还有富余，故不会被立刻淘汰——淘汰只在超容时发生。
        old_ts = time.time() - 48 * 3600
        journal._db.append(
            {"symbol": "ANCIENT", "recorded_at": old_ts}, key=old_ts
        )

        window_24h = get_decision_history(hours=24, limit=100)
        assert [e["symbol"] for e in window_24h] == ["FRESH"]

        window_72h = get_decision_history(hours=72, limit=100)
        assert [e["symbol"] for e in window_72h] == ["FRESH", "ANCIENT"]

        # 极窄窗口（cutoff=now）→ 空
        assert get_decision_history(hours=0, limit=100) == []
        # limit 生效
        assert len(get_decision_history(hours=72, limit=1)) == 1


def test_decision_query_returns_copies_not_live_refs():
    """查询结果必须是副本——UI 改不动留痕存储。"""
    from deva.naja.attention.orchestration.trading_center import get_trading_center
    from deva.naja.decision import get_recent_decision_plans

    center = get_trading_center()
    with _temp_journal(center):
        _record_fake_plan(center, symbol="000001")

        recent = get_recent_decision_plans(limit=1)
        assert recent and recent[0]["symbol"] == "000001"
        recent[0]["symbol"] = "TAMPERED"

        again = get_recent_decision_plans(limit=1)
        assert again[0]["symbol"] == "000001", "查询结果被外部修改污染了留痕存储"


def test_record_plan_falls_back_to_deque_when_journal_unavailable():
    """落盘不可用时不能崩——留痕降级到内存队列，且如实标注 persisted=False。"""
    from deva.naja.attention.orchestration.trading_center import get_trading_center
    from deva.naja.decision.journal import DecisionJournal

    center = get_trading_center()
    original = getattr(center, "_decision_journal", None)
    dead = DecisionJournal(table=TEST_JOURNAL_TABLE, db=None)  # 强制不可用
    dead._db = None
    try:
        center._decision_journal = dead
        center._recent_plans.clear()

        _record_fake_plan(center, symbol="DEGRADED")
        assert dead.record({"x": 1}) is None

        summary = center.get_decision_plan_summary(limit=5)
        assert summary["available"] is True          # 内存兜底仍能看到
        assert summary["stats"]["persisted"] is False
        assert summary["latest"]["symbol"] == "DEGRADED"
    finally:
        center._decision_journal = original
        center._recent_plans.clear()


def test_decision_query_is_honest_when_empty():
    """查询服务不兜底合成计划——空就是空，附 reason。"""
    from deva.naja.decision import query

    class _Dead:
        def get_decision_plan_summary(self, limit=10):
            raise RuntimeError("boom")

    original = query._get_center
    query._get_center = lambda: _Dead()
    try:
        summary = query.get_decision_plan_summary()
        assert summary["available"] is False
        assert summary["latest"] is None
        assert summary["recent"] == []
        assert "boom" in (summary.get("reason") or "")
        assert query.get_latest_decision_plan() is None
        assert query.get_recent_decision_plans() == []

        # TradingCenter 直接不可用
        query._get_center = lambda: None
        summary = query.get_decision_plan_summary()
        assert summary["available"] is False
        assert summary["reason"]
    finally:
        query._get_center = original


def test_plan_entry_actionable_matches_decision_plan_semantics():
    """留痕条目的 actionable 判定与 DecisionPlan.is_actionable 同口径。"""
    from deva.naja.attention.orchestration.trading_center import TradingCenter

    assert TradingCenter._plan_entry_actionable(
        {"should_act": True, "action_type": "act_carefully", "size_hint": 0.5}
    ) is True
    # hold / 不行动 / 零仓位 都不是"真会动手"
    assert TradingCenter._plan_entry_actionable(
        {"should_act": True, "action_type": "hold", "size_hint": 0.5}
    ) is False
    assert TradingCenter._plan_entry_actionable(
        {"should_act": False, "action_type": "act_fully", "size_hint": 0.5}
    ) is False
    assert TradingCenter._plan_entry_actionable(
        {"should_act": True, "action_type": "act_fully", "size_hint": 0.0}
    ) is False
    # 未知档位保守当 hold
    assert TradingCenter._plan_entry_actionable(
        {"should_act": True, "action_type": "wat", "size_hint": 0.5}
    ) is False


def test_decision_plan_panel_renders_empty_and_filled():
    """面板空态要诚实（不伪造决策），有数据时按 DecisionPlan 字段渲染。"""
    from deva.naja.attention.ui.components import render_decision_plan_panel

    empty = render_decision_plan_panel(
        {"available": False, "latest": None, "recent": [],
         "stats": {"total": 0, "shown": 0, "approved": 0, "actionable": 0}}
    )
    assert "尚未产生决策" in empty
    assert "决策计划" in empty

    filled = render_decision_plan_panel({
        "available": True,
        "latest": {
            "symbol": "600000", "side": "buy", "action_type": "act_carefully",
            "size_hint": 0.6, "confidence": 0.55, "risk_temperature": 1.2,
            "gate_reason": "时机尚可，轻仓试探", "should_act": True,
            "reasons": ["融合降级"], "approved": True,
        },
        "recent": [],
        "stats": {"total": 1, "shown": 1, "approved": 1, "actionable": 1, "persisted": True},
    })
    assert "600000" in filled
    assert "谨慎行动" in filled          # action_type 有人话标签
    assert "60%" in filled               # size_hint 渲染成百分比
    assert "时机尚可，轻仓试探" in filled  # gate_reason
    assert "融合降级" in filled           # reasons
    assert "已落盘" in filled             # 持久化状态可见

    # 落盘不可用时要如实标注，而不是默默显示"已落盘"
    degraded = render_decision_plan_panel({
        "available": True,
        "latest": {"symbol": "600000", "action_type": "hold", "side": "none"},
        "recent": [],
        "stats": {"total": 1, "shown": 1, "approved": 0, "actionable": 0, "persisted": False},
    })
    assert "仅内存" in degraded
    assert "已落盘" not in degraded


def test_decision_plan_panel_escapes_html():
    """面板里的自由文本必须转义（gate_reason 来自信号，可能含标签）。"""
    from deva.naja.attention.ui.components import render_decision_plan_panel

    html = render_decision_plan_panel({
        "available": True,
        "latest": {"symbol": "600000", "action_type": "hold", "side": "none",
                   "gate_reason": "<script>alert(1)</script>"},
        "recent": [],
        "stats": {"total": 1, "shown": 1, "approved": 0, "actionable": 0},
    })
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_attention_monitor_data_exposes_decision_plan_key():
    """dashboard 的数据出口必须带 decision_plan（UI 走它，而非散字段）。"""
    from deva.naja.attention.ui.dashboard import get_attention_monitor_data

    data = get_attention_monitor_data()
    assert "decision_plan" in data
    plan_state = data["decision_plan"]
    assert set(plan_state) >= {"available", "latest", "recent", "stats"}

