"""
评级：政策 / 利用率 / 价格 / 信用 四维加权 → 红橙黄绿

规则可单测、可回算；评级**不用 LLM**，也不写在页面或采集器里。

维度分值统一为 0~100 的「风险分」：越高越危险。
最终等级 = max(加权分对应的等级, 命中硬规则的下限等级)。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

GRADE_ORDER = ("green", "yellow", "orange", "red")
GRADE_LABEL = {"green": "绿", "yellow": "黄", "orange": "橙", "red": "红"}

WEIGHTS = {"policy": 0.35, "utilization": 0.25, "price": 0.20, "credit": 0.20}

#: 加权分上界：<25 绿，<50 黄，<70 橙，其余红
SCORE_CUTS = (("green", 25.0), ("yellow", 50.0), ("orange", 70.0))

#: 硬规则：某维风险分达到阈值时，最终等级不得低于 floor（防止加权平均掩盖单点爆雷）
FLOOR_RULES = (
    ("credit", 85.0, "red", "credit_critical"),
    ("policy", 85.0, "orange", "policy_severe"),
    ("utilization", 85.0, "orange", "utilization_collapsed"),
    ("price", 85.0, "orange", "price_collapsed"),
)


def grade_rank(grade: str) -> int:
    try:
        return GRADE_ORDER.index(grade)
    except ValueError:
        raise ValueError(f"未知等级 {grade!r}，允许值: {GRADE_ORDER}")


def worse_grade(a: str, b: str) -> str:
    return a if grade_rank(a) >= grade_rank(b) else b


def grade_from_score(score: float) -> str:
    for grade, cut in SCORE_CUTS:
        if score < cut:
            return grade
    return "red"


def _check_dimension(name: str, value: Any) -> float:
    v = float(value)
    if not 0.0 <= v <= 100.0:
        raise ValueError(f"{name} 维度风险分必须在 [0,100]: {v}")
    return v


def credit_dimension(ltv_ratio: Optional[float], dscr_ratio: Optional[float]) -> Dict[str, Any]:
    """把 LTV / DSCR 折算成信用维风险分（取两者中更危险的一个）。"""
    ltv_score = 20.0
    ltv_note = "LTV 低"
    if ltv_ratio is not None:
        r = float(ltv_ratio)
        if r >= 0.90:
            ltv_score, ltv_note = 95.0, "LTV >= 0.90"
        elif r >= 0.85:
            ltv_score, ltv_note = 80.0, "LTV >= 0.85"
        elif r >= 0.75:
            ltv_score, ltv_note = 60.0, "LTV >= 0.75"
        elif r >= 0.60:
            ltv_score, ltv_note = 40.0, "LTV >= 0.60"

    dscr_score = 20.0
    dscr_note = "DSCR 健康"
    if dscr_ratio is not None:
        d = float(dscr_ratio)
        if d < 1.0:
            dscr_score, dscr_note = 100.0, "DSCR < 1"
        elif d < 1.2:
            dscr_score, dscr_note = 85.0, "DSCR < 1.2"
        elif d < 1.5:
            dscr_score, dscr_note = 60.0, "DSCR < 1.5"
        elif d < 2.0:
            dscr_score, dscr_note = 40.0, "DSCR < 2.0"

    return {
        "score": max(ltv_score, dscr_score),
        "drivers": [ltv_note, dscr_note],
    }


def rate(
    dimensions: Dict[str, Any],
    previous_grade: Optional[str] = None,
) -> Dict[str, Any]:
    """四维加权评级。

    Args:
        dimensions: 必须且只能包含 ``policy/utilization/price/credit``，值为 0~100 风险分。
        previous_grade: 上次等级；用于判断是否发生跃迁，只有跃迁才推告警。
    """
    unknown = set(dimensions) - set(WEIGHTS)
    missing = [k for k in WEIGHTS if k not in dimensions]
    if unknown:
        raise ValueError(f"未知评级维度: {sorted(unknown)}")
    if missing:
        raise ValueError(f"缺少评级维度: {missing}")

    scores = {k: _check_dimension(k, dimensions[k]) for k in WEIGHTS}
    contributions = {k: round(scores[k] * WEIGHTS[k], 2) for k in WEIGHTS}
    weighted = round(sum(contributions.values()), 2)
    raw_grade = grade_from_score(weighted)

    floors: List[Dict[str, Any]] = []
    final_grade = raw_grade
    for dim, threshold, floor, reason in FLOOR_RULES:
        if scores[dim] >= threshold:
            floors.append({
                "dimension": dim,
                "score": scores[dim],
                "threshold": threshold,
                "floor_grade": floor,
                "reason": reason,
            })
            final_grade = worse_grade(final_grade, floor)

    reasons = [
        f"{dim}: {scores[dim]:.0f} × {WEIGHTS[dim]:.2f} = {contributions[dim]}"
        for dim in WEIGHTS
    ]
    reasons.extend(f"硬规则 {f['reason']}: {f['dimension']}={f['score']:.0f} → 不低于 {f['floor_grade']}"
                   for f in floors)

    prev = previous_grade.lower() if isinstance(previous_grade, str) else previous_grade
    if prev is None:
        transition = {"previous": None, "changed": False, "direction": "initial",
                      "from_rank": None, "to_rank": grade_rank(final_grade)}
    else:
        if prev not in GRADE_ORDER:
            raise ValueError(f"previous_grade 未知: {previous_grade!r}")
        from_rank, to_rank = grade_rank(prev), grade_rank(final_grade)
        changed = prev != final_grade
        direction = "unchanged"
        if to_rank > from_rank:
            direction = "escalated"
        elif to_rank < from_rank:
            direction = "deescalated"
        transition = {"previous": prev, "changed": changed, "direction": direction,
                      "from_rank": from_rank, "to_rank": to_rank}

    return {
        "score": weighted,
        "grade": final_grade,
        "grade_label": GRADE_LABEL[final_grade],
        "raw_grade": raw_grade,
        "dimensions": scores,
        "weighted_contributions": contributions,
        "floors_triggered": floors,
        "reasons": reasons,
        "transition": transition,
        "should_notify": bool(transition["changed"]),
    }
