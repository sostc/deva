"""
压力测试：情景参数 + 敏感性矩阵

三个情景参数（报告 §5）：
    - china_churn：中国相关客户流失比例（0~1），只作用于 china_linked_share 那部分需求；
    - rent_decline：租赁价下行幅度（0~1），同时作为抵押物价格的代理跌幅；
    - refinance_bps：再融资利率上行（基点），按债务余额折算成额外年息。

纯函数、无 IO；一次日更跑完即退出，不进 tick、不 sleep。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from deva.naja.geo_risk.model.dscr import annual_lease_cashflow, assess_dscr
from deva.naja.geo_risk.model.ltv import assess_ltv, collateral_value

#: 单个项目快照的必填字段（都是可 json 化的原始值，不塞对象）
SNAPSHOT_KEYS = (
    "gpu_count",
    "monthly_rent_per_gpu_usd",
    "utilization",
    "china_linked_share",
    "annual_debt_service_usd",
    "debt_usd",
    "gpu_models",
)

SCENARIO_KEYS = ("china_churn", "rent_decline", "refinance_bps")
DEFAULT_SCENARIO = {"china_churn": 0.0, "rent_decline": 0.0, "refinance_bps": 0.0}

DEFAULT_CHURN_AXIS = (0.0, 0.25, 0.50, 0.75)
DEFAULT_RENT_DECLINE_AXIS = (0.0, 0.10, 0.20, 0.30)


def _ratio(value: Any, name: str) -> float:
    v = float(value)
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"{name} 必须在 [0,1]: {v}")
    return v


def _base_metrics(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    cashflow = annual_lease_cashflow(
        snapshot["gpu_count"],
        snapshot["monthly_rent_per_gpu_usd"],
        snapshot["utilization"],
    )
    dscr = assess_dscr(cashflow, snapshot["annual_debt_service_usd"])
    collateral = collateral_value(snapshot["gpu_models"])
    ltv = assess_ltv(snapshot["debt_usd"], collateral["total_usd"])
    return {
        "lease_cashflow_usd": round(cashflow, 2),
        "debt_service_usd": round(float(snapshot["annual_debt_service_usd"]), 2),
        "collateral_usd": collateral["total_usd"],
        "gpu_breakdown": collateral["items"],
        "dscr": dscr,
        "ltv": ltv,
    }


def apply_scenario(
    snapshot: Dict[str, Any],
    scenario: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """把一个情景施加到项目快照，返回基准/压力后指标与变化量。"""
    missing = [k for k in SNAPSHOT_KEYS if k not in snapshot]
    if missing:
        raise ValueError(f"项目快照缺少字段: {missing}")

    sc = dict(DEFAULT_SCENARIO)
    sc.update(scenario or {})
    unknown = set(sc) - set(SCENARIO_KEYS)
    if unknown:
        raise ValueError(f"未知情景参数: {sorted(unknown)}")

    churn = _ratio(sc["china_churn"], "china_churn")
    rent_decline = _ratio(sc["rent_decline"], "rent_decline")
    bps = float(sc["refinance_bps"])
    if bps < 0:
        raise ValueError(f"refinance_bps 不能为负: {bps}")

    china_share = _ratio(snapshot["china_linked_share"], "china_linked_share")

    base = _base_metrics(snapshot)

    lost_demand = min(1.0, churn * china_share)
    stressed_util = float(snapshot["utilization"]) * (1.0 - lost_demand)
    stressed_rent = float(snapshot["monthly_rent_per_gpu_usd"]) * (1.0 - rent_decline)

    stressed_cashflow = annual_lease_cashflow(
        snapshot["gpu_count"], stressed_rent, stressed_util,
    )
    stressed_service = float(snapshot["annual_debt_service_usd"]) + \
        float(snapshot["debt_usd"]) * bps / 10000.0
    stressed_dscr = assess_dscr(stressed_cashflow, stressed_service)

    # 租赁价与抵押物价格同向变动（假设，不是事实）：跌价按同一幅度打到残值
    stressed_collateral = float(base["collateral_usd"]) * (1.0 - rent_decline)
    stressed_ltv = assess_ltv(snapshot["debt_usd"], stressed_collateral)

    flags: List[str] = []
    if stressed_dscr["alert"]:
        flags.append("dscr_below_1")
    if stressed_ltv["grade"] == "red":
        flags.append("ltv_red")

    base_rev = base["lease_cashflow_usd"]
    rev_pct = ((stressed_cashflow - base_rev) / base_rev) if base_rev else None

    return {
        "scenario": {
            "china_churn": churn,
            "rent_decline": rent_decline,
            "refinance_bps": bps,
            "lost_demand_share": round(lost_demand, 4),
            "utilization_after": round(stressed_util, 4),
            "rent_after": round(stressed_rent, 2),
        },
        "base": {
            "lease_cashflow_usd": base["lease_cashflow_usd"],
            "debt_service_usd": base["debt_service_usd"],
            "collateral_usd": base["collateral_usd"],
            "dscr": base["dscr"]["dscr"],
            "dscr_grade": base["dscr"]["grade"],
            "ltv": base["ltv"]["ltv"],
            "ltv_grade": base["ltv"]["grade"],
        },
        "stressed": {
            "lease_cashflow_usd": round(stressed_cashflow, 2),
            "debt_service_usd": round(stressed_service, 2),
            "collateral_usd": round(stressed_collateral, 2),
            "dscr": stressed_dscr["dscr"],
            "dscr_grade": stressed_dscr["grade"],
            "ltv": stressed_ltv["ltv"],
            "ltv_grade": stressed_ltv["grade"],
        },
        "delta": {
            "lease_cashflow_usd": round(stressed_cashflow - base_rev, 2),
            "lease_cashflow_pct": round(rev_pct, 4) if rev_pct is not None else None,
            "dscr": (round(stressed_dscr["dscr"] - base["dscr"]["dscr"], 4)
                     if stressed_dscr["dscr"] is not None and base["dscr"]["dscr"] is not None
                     else None),
            "ltv": round(stressed_ltv["ltv"] - base["ltv"]["ltv"], 4),
        },
        "flags": flags,
    }


def sensitivity_matrix(
    snapshot: Dict[str, Any],
    churns: Sequence[float] = DEFAULT_CHURN_AXIS,
    rent_declines: Sequence[float] = DEFAULT_RENT_DECLINE_AXIS,
) -> Dict[str, Any]:
    """中国客户流失 × 租赁价下跌 的敏感性网格；worst 取 DSCR 最低的格。"""
    cells: List[Dict[str, Any]] = []
    for churn in churns:
        for decline in rent_declines:
            out = apply_scenario(snapshot, {"china_churn": churn, "rent_decline": decline})
            cell = {
                "china_churn": float(churn),
                "rent_decline": float(decline),
                "dscr": out["stressed"]["dscr"],
                "dscr_grade": out["stressed"]["dscr_grade"],
                "ltv": out["stressed"]["ltv"],
                "ltv_grade": out["stressed"]["ltv_grade"],
                "flags": out["flags"],
            }
            cells.append(cell)

    if not cells:
        raise ValueError("敏感性矩阵至少要有 1 个轴值")

    def _sort_key(c: Dict[str, Any]):
        d = c["dscr"]
        return (d if d is not None else float("inf"), -c["ltv"])

    worst = min(cells, key=_sort_key)
    return {
        "axes": {"china_churn": [float(x) for x in churns],
                 "rent_decline": [float(x) for x in rent_declines]},
        "cells": cells,
        "worst": worst,
    }
