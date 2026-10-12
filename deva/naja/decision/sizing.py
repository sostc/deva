"""仓位定量：把「行动档位 + α + 风险温度」折算成一个 0~1 的仓位乘子。

设计口径（单一来源，执行层不再自己拍数）：

    multiplier = action_factor(action_type) × alpha_factor(α) × risk_factor(T)

- ``action_factor`` 是**主驱动**，直接来自判断层的档位（hold=0 → act_fully=1）。
- ``alpha_factor`` 是**轻微置信缩放**。注意：``α`` 实测自然落在 [0.3, ~0.6]，
  且被 ``alpha_min=0.3`` 支配（见 ``docs/naja/manas_upgrade_plan.md`` §4），
  因此这里把它当作"围绕中位的小幅修正"，不当作主缩放——若将来重新定标 α，
  只需调 ``ALPHA_REFERENCE``。
- ``risk_factor`` 是**风险刹车**：温度越高，仓位越轻。

乘子与档位的乘积仍会被夹到 [0, 1]；``hold`` 恒为 0（不动就是不动）。
"""

from __future__ import annotations

import os
from typing import Any

from .plan import action_severity

# 档位 → 基础仓位因子（主驱动）
ACTION_FACTORS: dict[str, float] = {
    "hold": 0.0,
    "act_minimally": 0.25,
    "act_carefully": 0.6,
    "act_fully": 1.0,
}

# α 的参考中位与缩放上下限
ALPHA_REFERENCE = 0.45
ALPHA_FACTOR_MIN = 0.8
ALPHA_FACTOR_MAX = 1.2

# 风险温度刹车：(温度下限（含）, 因子)，从高到低匹配
RISK_TIERS: tuple[tuple[float, float], ...] = (
    (1.5, 0.4),
    (1.3, 0.6),
    (1.0, 0.85),
)
RISK_FACTOR_DEFAULT = 1.0

# 是否启用 manas 定量（关掉则执行层回落固定量，用于灰度/回滚）
ENV_FLAG = "NAJA_MANAS_SIZING"


def manas_sizing_enabled() -> bool:
    """是否启用 Manas 驱动的仓位定量。

    默认**开启**；设 ``NAJA_MANAS_SIZING=0`` 可一键回落固定量（回滚开关）。
    """
    return os.environ.get(ENV_FLAG, "1").strip().lower() not in ("0", "false", "no", "off")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def action_factor(action_type: Any) -> float:
    value = getattr(action_type, "value", action_type)
    return ACTION_FACTORS.get(str(value), 0.0)


def alpha_factor(alpha: float) -> float:
    """把 α 折算为 [ALPHA_FACTOR_MIN, ALPHA_FACTOR_MAX] 的轻微缩放。"""
    try:
        ratio = float(alpha) / ALPHA_REFERENCE
    except (TypeError, ValueError, ZeroDivisionError):
        return 1.0
    return _clamp(ratio, ALPHA_FACTOR_MIN, ALPHA_FACTOR_MAX)


def risk_factor(risk_temperature: float) -> float:
    """风险刹车：温度越高，因子越小。"""
    try:
        t = float(risk_temperature)
    except (TypeError, ValueError):
        return RISK_FACTOR_DEFAULT
    for threshold, factor in RISK_TIERS:
        if t > threshold:
            return factor
    return RISK_FACTOR_DEFAULT


def compute_position_multiplier(
    action_type: Any,
    alpha: float = 1.0,
    risk_temperature: float = 1.0,
) -> float:
    """核心公式：0~1 的仓位乘子。"""
    if action_severity(action_type) <= 0:
        return 0.0
    multiplier = action_factor(action_type) * alpha_factor(alpha) * risk_factor(risk_temperature)
    return round(_clamp(multiplier, 0.0, 1.0), 4)


def compute_plan_size_hint(fusion: Any) -> float:
    """从融合层输出（``FusionOutput``）算 ``DecisionPlan.size_hint``。"""
    return compute_position_multiplier(
        getattr(fusion, "action_type", "hold"),
        getattr(fusion, "alpha", 1.0),
        getattr(fusion, "risk_temperature", 1.0),
    )


def compute_order_amount(
    size_hint: float,
    base_amount: float,
    *,
    min_amount: float = 0.0,
) -> float:
    """把仓位乘子折算成下单金额（执行层唯一入口）。

    ``hold``（size_hint=0）恒返回 0；有动作时不低于 ``min_amount``，
    避免乘子很小时算出个买不起 1 股的金额。
    """
    try:
        hint = float(size_hint)
        base = float(base_amount)
    except (TypeError, ValueError):
        return 0.0
    if hint <= 0.0 or base <= 0.0:
        return 0.0
    return round(max(min_amount, base * hint), 2)


__all__ = [
    "ACTION_FACTORS",
    "ALPHA_REFERENCE",
    "RISK_TIERS",
    "ENV_FLAG",
    "manas_sizing_enabled",
    "action_factor",
    "alpha_factor",
    "risk_factor",
    "compute_position_multiplier",
    "compute_plan_size_hint",
    "compute_order_amount",
]
