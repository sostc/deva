"""
LTV：GPU 抵押物估值与贷款价值比

纯函数、无 IO、无行情订阅。输入输出都是可 json 化的 dict，供日更任务调用。

抵押物价值 = Σ(分型号残值曲线 × 数量 × 单价)
LTV = 债务余额 / 抵押物价值

❗残值曲线与单价是 **假设参数**（fixture 级），不是市场事实。
后续应由采集到的二手成交价/租赁价回算，并写入 model_runs 留痕；
不要把这些常数当成真相，也不要在采集器里改它们。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

#: 分型号残值曲线（首元组是「月龄, 残值率」），按线性插值
RESIDUAL_CURVES = {
    "b200": [(0, 1.00), (12, 0.94), (24, 0.86), (36, 0.74), (48, 0.58), (60, 0.40)],
    "h200": [(0, 1.00), (12, 0.92), (24, 0.82), (36, 0.66), (48, 0.48), (60, 0.30)],
    "h100": [(0, 1.00), (12, 0.90), (24, 0.78), (36, 0.60), (48, 0.42), (60, 0.25)],
    "a100": [(0, 1.00), (12, 0.80), (24, 0.62), (36, 0.44), (48, 0.28), (60, 0.15)],
    "a800": [(0, 1.00), (12, 0.78), (24, 0.58), (36, 0.38), (48, 0.22), (60, 0.12)],
}
DEFAULT_RESIDUAL_CURVE = [(0, 1.00), (12, 0.85), (24, 0.70), (36, 0.52), (48, 0.35), (60, 0.20)]

#: 默认单价（USD/卡）；item 里给了 unit_price_usd 时以 item 为准
DEFAULT_UNIT_PRICE_USD = {
    "b200": 42000,
    "h200": 32000,
    "h100": 28000,
    "a100": 15000,
    "a800": 12000,
}
DEFAULT_UNIT_PRICE_FALLBACK = 20000

#: LTV 分档上界：<= green，<= yellow，<= orange，其余 red
DEFAULT_LTV_THRESHOLDS = {"green": 0.60, "yellow": 0.75, "orange": 0.85}

CURVE_VERSION = "2026-11-assumption"


def residual_fraction(model: str, age_months: float) -> float:
    """某型号在给定月龄的残值率（0~1），线性插值，超出曲线末尾按末值持有。"""
    if age_months < 0:
        raise ValueError(f"age_months 不能为负: {age_months}")
    curve = RESIDUAL_CURVES.get((model or "").lower(), DEFAULT_RESIDUAL_CURVE)
    if age_months >= curve[-1][0]:
        return curve[-1][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= age_months <= x1:
            span = x1 - x0
            t = (age_months - x0) / span if span else 0.0
            return y0 + (y1 - y0) * t
    return curve[0][1]


def _unit_price(model: str, overrides: Optional[Dict[str, float]]) -> float:
    key = (model or "").lower()
    table = dict(DEFAULT_UNIT_PRICE_USD)
    if overrides:
        table.update({k.lower(): float(v) for k, v in overrides.items()})
    return float(table.get(key, DEFAULT_UNIT_PRICE_FALLBACK))


def collateral_value(
    gpus: Sequence[Dict[str, Any]],
    unit_prices: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """按「型号 + 数量 + 月龄」估值。

    Args:
        gpus: 每项需含 ``model`` / ``count``，可选 ``age_months``（默认 0）、``unit_price_usd``。
        unit_prices: 覆盖默认单价表（键为小写型号）。
    """
    items = []
    total = 0.0
    for g in gpus:
        model = str(g.get("model") or "")
        count = float(g.get("count") or 0)
        if count < 0:
            raise ValueError(f"count 不能为负: {count}")
        age = float(g.get("age_months") or 0)
        price = float(g["unit_price_usd"]) if g.get("unit_price_usd") is not None \
            else _unit_price(model, unit_prices)
        frac = residual_fraction(model, age)
        value = count * price * frac
        total += value
        items.append({
            "model": model,
            "count": int(count) if count.is_integer() else count,
            "age_months": age,
            "unit_price_usd": price,
            "residual_fraction": round(frac, 4),
            "value_usd": round(value, 2),
        })
    return {"items": items, "total_usd": round(total, 2), "curve_version": CURVE_VERSION}


def ltv_grade(ratio: float, thresholds: Optional[Dict[str, float]] = None) -> str:
    t = dict(DEFAULT_LTV_THRESHOLDS)
    if thresholds:
        t.update(thresholds)
    if ratio <= t["green"]:
        return "green"
    if ratio <= t["yellow"]:
        return "yellow"
    if ratio <= t["orange"]:
        return "orange"
    return "red"


def assess_ltv(
    debt_usd: float,
    collateral_usd: float,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """LTV = 债务 / 抵押物价值；抵押物为 0 时无法计算，直接报错而不是返回 inf。"""
    debt = float(debt_usd)
    collateral = float(collateral_usd)
    if debt < 0:
        raise ValueError(f"debt_usd 不能为负: {debt}")
    if collateral <= 0:
        raise ValueError("collateral_usd 必须大于 0，否则 LTV 无意义")
    ratio = debt / collateral
    grade = ltv_grade(ratio, thresholds)
    return {
        "ltv": round(ratio, 4),
        "grade": grade,
        "alert": grade == "red",
        "debt_usd": round(debt, 2),
        "collateral_usd": round(collateral, 2),
        "thresholds": dict(DEFAULT_LTV_THRESHOLDS, **(thresholds or {})),
    }
