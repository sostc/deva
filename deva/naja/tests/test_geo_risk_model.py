"""
P4 模型层验收：LTV / DSCR / 压力测试 / 评级

全部纯函数：不建库、不读库、不订阅行情、不 sleep。
输入快照与输出结果都必须可 json 化，方便日更任务落 model_runs 回算。
"""

import json

import pytest

from deva.naja.geo_risk.model import (
    annual_lease_cashflow,
    apply_scenario,
    assess_dscr,
    assess_ltv,
    collateral_value,
    credit_dimension,
    grade_rank,
    rate,
    residual_fraction,
    sensitivity_matrix,
    worse_grade,
)

#: 一个 20MW 级项目的手工快照（数字是测试夹具，不是生产事实）
SNAPSHOT = {
    "project_id": "prj_model_test",
    "gpu_count": 2000,
    "monthly_rent_per_gpu_usd": 1800.0,
    "utilization": 0.9,
    "china_linked_share": 0.5,
    "annual_debt_service_usd": 30_000_000.0,
    "debt_usd": 20_000_000.0,
    "gpu_models": [
        {"model": "H100", "count": 1000, "age_months": 18},
        {"model": "A100", "count": 1000, "age_months": 36},
    ],
}


# ------------------------------------------------------------------ LTV
def test_residual_curve_interpolates_and_holds_tail():
    assert residual_fraction("H100", 0) == pytest.approx(1.0)
    assert residual_fraction("H100", 18) == pytest.approx(0.84)
    assert residual_fraction("A100", 36) == pytest.approx(0.44)
    # 未知型号走默认曲线：(12,0.85) → (24,0.70)，18 个月取中点
    assert residual_fraction("mystery", 18) == pytest.approx(0.775)
    # 超过曲线末尾按末值持有
    assert residual_fraction("H100", 72) == pytest.approx(0.25)

    ages = [0, 12, 24, 36, 48, 60]
    values = [residual_fraction("H100", a) for a in ages]
    assert all(a >= b for a, b in zip(values, values[1:]))

    with pytest.raises(ValueError):
        residual_fraction("H100", -1)


def test_collateral_value_sums_models_and_allows_price_override():
    out = collateral_value(SNAPSHOT["gpu_models"])
    # H100: 1000 × 28000 × 0.84；A100: 1000 × 15000 × 0.44
    assert out["total_usd"] == pytest.approx(23_520_000 + 6_600_000)
    assert [i["model"] for i in out["items"]] == ["H100", "A100"]

    overridden = collateral_value([{"model": "H100", "count": 2, "age_months": 0,
                                    "unit_price_usd": 30000}])
    assert overridden["total_usd"] == pytest.approx(60000)


def test_ltv_grades_and_guards():
    assert assess_ltv(600, 1000)["grade"] == "green"
    assert assess_ltv(700, 1000)["grade"] == "yellow"
    assert assess_ltv(800, 1000)["grade"] == "orange"
    red = assess_ltv(900, 1000)
    assert red["grade"] == "red" and red["alert"] is True

    with pytest.raises(ValueError):
        assess_ltv(1000, 0)


# ----------------------------------------------------------------- DSCR
def test_dscr_grades_and_below_one_alert():
    cashflow = annual_lease_cashflow(100, 1000, 0.8)
    assert cashflow == pytest.approx(960_000)

    below = assess_dscr(960_000, 1_200_000)
    assert below["dscr"] == pytest.approx(0.8)
    assert below["grade"] == "red" and below["alert"] is True

    at_one = assess_dscr(1_200_000, 1_200_000)
    assert at_one["grade"] == "orange" and at_one["alert"] is False
    assert assess_dscr(1_560_000, 1_200_000)["grade"] == "yellow"
    assert assess_dscr(1_800_000, 1_200_000)["grade"] == "green"


def test_dscr_zero_debt_is_not_infinite():
    out = assess_dscr(960_000, 0)
    assert out["dscr"] is None and out["alert"] is False

    with pytest.raises(ValueError):
        annual_lease_cashflow(100, 1000, 1.2)


# ---------------------------------------------------------------- 压力测试
def test_base_scenario_reproduces_base_metrics():
    out = apply_scenario(SNAPSHOT, {})
    assert out["stressed"]["dscr"] == out["base"]["dscr"] == pytest.approx(1.296)
    assert out["stressed"]["ltv"] == out["base"]["ltv"] == pytest.approx(0.664)
    assert out["delta"]["dscr"] == pytest.approx(0.0)
    assert out["delta"]["ltv"] == pytest.approx(0.0)


def test_severe_scenario_lands_in_red_and_flags():
    out = apply_scenario(SNAPSHOT, {
        "china_churn": 0.8, "rent_decline": 0.3, "refinance_bps": 300,
    })
    # 只丢中国相关那一半需求：0.8 × 0.5 = 40% 需求流失
    assert out["scenario"]["lost_demand_share"] == pytest.approx(0.4)
    assert out["scenario"]["utilization_after"] == pytest.approx(0.54)
    assert out["scenario"]["rent_after"] == pytest.approx(1260)

    assert out["stressed"]["dscr"] < 1.0
    assert out["stressed"]["dscr_grade"] == "red"
    assert out["stressed"]["ltv_grade"] == "red"
    assert out["flags"] == ["dscr_below_1", "ltv_red"]
    assert out["delta"]["ltv"] > 0


def test_sensitivity_matrix_shape_monotonic_and_worst():
    out = sensitivity_matrix(SNAPSHOT)
    assert len(out["cells"]) == 4 * 4
    assert out["axes"]["china_churn"] == [0.0, 0.25, 0.5, 0.75]

    by_churn = [c["dscr"] for c in out["cells"] if c["rent_decline"] == 0.3]
    assert all(a >= b for a, b in zip(by_churn, by_churn[1:]))

    worst = out["worst"]
    assert worst["china_churn"] == pytest.approx(0.75)
    assert worst["rent_decline"] == pytest.approx(0.30)


def test_stress_rejects_unknown_keys_and_bad_snapshot():
    with pytest.raises(ValueError):
        apply_scenario(SNAPSHOT, {"unemployment": 0.1})

    with pytest.raises(ValueError):
        apply_scenario({"gpu_count": 100}, {})


# ------------------------------------------------------------------ 评级
def test_rating_weighted_score_and_floors():
    out = rate({"policy": 50, "utilization": 40, "price": 60, "credit": 70})
    # 17.5 + 10 + 12 + 14 = 53.5 → 橙
    assert out["score"] == pytest.approx(53.5)
    assert out["grade"] == "orange"
    assert out["raw_grade"] == "orange"
    assert out["floors_triggered"] == []

    assert rate({"policy": 0, "utilization": 0, "price": 0, "credit": 0})["grade"] == "green"

    # 加权分只有 20（绿），但信用爆雷必须红
    credit_critical = rate({"policy": 0, "utilization": 0, "price": 0, "credit": 100})
    assert credit_critical["raw_grade"] == "green"
    assert credit_critical["grade"] == "red"
    assert credit_critical["floors_triggered"][0]["reason"] == "credit_critical"

    # 加权 35（黄），政策硬规则抬到橙
    policy_severe = rate({"policy": 100, "utilization": 0, "price": 0, "credit": 0})
    assert policy_severe["grade"] == "orange"


def test_rating_transition_only_notifies_on_change():
    dims = {"policy": 50, "utilization": 40, "price": 60, "credit": 70}

    initial = rate(dims)
    assert initial["transition"]["direction"] == "initial"
    assert initial["should_notify"] is False

    escalated = rate(dims, previous_grade="yellow")
    assert escalated["transition"]["direction"] == "escalated"
    assert escalated["should_notify"] is True

    unchanged = rate(dims, previous_grade="orange")
    assert unchanged["transition"]["direction"] == "unchanged"
    assert unchanged["should_notify"] is False

    deescalated = rate({"policy": 0, "utilization": 0, "price": 0, "credit": 0},
                       previous_grade="orange")
    assert deescalated["transition"]["direction"] == "deescalated"
    assert deescalated["should_notify"] is True


def test_rating_helpers_and_validation():
    assert grade_rank("red") > grade_rank("orange") > grade_rank("yellow") > grade_rank("green")
    assert worse_grade("yellow", "orange") == "orange"

    credit = credit_dimension(0.9, 0.9)
    assert credit["score"] == 100.0
    assert len(credit["drivers"]) == 2

    with pytest.raises(ValueError):
        rate({"policy": 10, "utilization": 10, "price": 10})

    with pytest.raises(ValueError):
        rate({"policy": 10, "utilization": 10, "price": 10, "credit": 10, "foo": 1})

    with pytest.raises(ValueError):
        rate({"policy": 120, "utilization": 10, "price": 10, "credit": 10})


def test_outputs_are_json_serializable():
    json.dumps(collateral_value(SNAPSHOT["gpu_models"]), ensure_ascii=False)
    json.dumps(assess_ltv(2_000_000, 30_000_000), ensure_ascii=False)
    json.dumps(assess_dscr(30_000_000, 25_000_000), ensure_ascii=False)
    json.dumps(apply_scenario(SNAPSHOT, {"china_churn": 0.5}), ensure_ascii=False)
    json.dumps(sensitivity_matrix(SNAPSHOT), ensure_ascii=False)
    json.dumps(rate({"policy": 50, "utilization": 40, "price": 60, "credit": 70}),
               ensure_ascii=False)
