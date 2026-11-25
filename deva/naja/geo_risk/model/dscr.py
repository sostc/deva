"""
DSCR：租赁现金流 / 本息

纯函数、无 IO。DSCR < 1 表示租赁收入覆盖不了当年本息，必须告警。

租赁价（``monthly_rent_per_gpu_usd``）由采集层（GPU 定价/二手市场）提供；
本模块只做计算，不去抓价、也不读库。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

#: DSCR 分档下界：>= green，>= yellow，>= orange，其余 red
DEFAULT_DSCR_THRESHOLDS = {"green": 1.50, "yellow": 1.20, "orange": 1.00}


def annual_lease_cashflow(
    gpu_count: float,
    monthly_rent_per_gpu_usd: float,
    utilization: float = 1.0,
) -> float:
    """年化租赁现金流 = 卡数 × 月租 × 12 × 利用率。"""
    if gpu_count < 0:
        raise ValueError(f"gpu_count 不能为负: {gpu_count}")
    if monthly_rent_per_gpu_usd < 0:
        raise ValueError(f"monthly_rent_per_gpu_usd 不能为负: {monthly_rent_per_gpu_usd}")
    if not 0.0 <= utilization <= 1.0:
        raise ValueError(f"utilization 必须在 [0,1]: {utilization}")
    return float(gpu_count) * float(monthly_rent_per_gpu_usd) * 12.0 * float(utilization)


def dscr_grade(ratio: float, thresholds: Optional[Dict[str, float]] = None) -> str:
    t = dict(DEFAULT_DSCR_THRESHOLDS)
    if thresholds:
        t.update(thresholds)
    if ratio >= t["green"]:
        return "green"
    if ratio >= t["yellow"]:
        return "yellow"
    if ratio >= t["orange"]:
        return "orange"
    return "red"


def assess_dscr(
    annual_lease_cashflow_usd: float,
    annual_debt_service_usd: float,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """DSCR = 现金流 / 本息；本息为 0 时视为无负债，返回 None 而不是 inf。"""
    cashflow = float(annual_lease_cashflow_usd)
    service = float(annual_debt_service_usd)
    if cashflow < 0:
        raise ValueError(f"annual_lease_cashflow_usd 不能为负: {cashflow}")
    if service < 0:
        raise ValueError(f"annual_debt_service_usd 不能为负: {service}")

    if service == 0:
        return {
            "dscr": None,
            "grade": "green",
            "alert": False,
            "cashflow_usd": round(cashflow, 2),
            "debt_service_usd": 0.0,
            "note": "无本息，DSCR 不适用",
        }

    ratio = cashflow / service
    grade = dscr_grade(ratio, thresholds)
    return {
        "dscr": round(ratio, 4),
        "grade": grade,
        "alert": ratio < 1.0,
        "cashflow_usd": round(cashflow, 2),
        "debt_service_usd": round(service, 2),
        "thresholds": dict(DEFAULT_DSCR_THRESHOLDS, **(thresholds or {})),
    }
