"""基本面打分：质量 + 估值 + 风险 → 四档。

为什么是规则而不是 LLM
----------------------
每一分都要能追到具体数字。LLM 打分不可复现、不可回测，也没法解释
「为什么这家从 A 掉到 C」。所以这里只有阈值和加减法，参数集中在
:data:`QUALITY_BANDS` 等常量里，调松紧改数字即可。

三个维度的分工
--------------
- **质量（60）**：它是不是好公司 —— ROE、现金转化、毛利率、成长
- **估值（25）**：现在贵不贵 —— PE/PB 的**自身历史分位**
- **风险（15）**：有没有雷 —— 扣分项，可一票否决

``None ≠ 0`` 仍然成立：银行没有毛利率、ETF 没有财报，缺数据时**不扣分也不给分**，
最后按已知维度归一化，并把缺失项写进 ``caveats``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .points import FundamentalPoint
from .valuation import Valuation

log = logging.getLogger(__name__)

#: 档位 → 正 T 的仓位系数（0 = 禁止）
TIER_SCALE: Dict[str, float] = {"A": 1.0, "B": 0.6, "C": 0.0, "D": 0.0}

#: 允许逆势低吸的最低档位
MIN_DIP_TIER = "B"


@dataclass
class Score:
    symbol: str
    quality: float = 0.0
    valuation: float = 0.0
    risk: float = 0.0
    total: float = 0.0
    tier: str = "NA"
    flags: List[str] = field(default_factory=list)
    fatal: Optional[str] = None
    parts: Dict[str, Any] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quality": round(self.quality, 1),
            "valuation": round(self.valuation, 1),
            "risk": round(self.risk, 1),
            "total": round(self.total, 1),
            "tier": self.tier,
            "flags": list(self.flags),
            "fatal": self.fatal,
            "parts": self.parts,
            "caveats": list(self.caveats),
            "forward_scale": TIER_SCALE.get(self.tier, 0.0),
        }


def _band(value: Optional[float], bands: List[tuple], default: float = 0.0) -> Optional[float]:
    """``bands`` 为 [(下界, 分数), ...]，按降序取第一个满足的。"""
    if value is None:
        return None
    for lower, points in bands:
        if value >= lower:
            return float(points)
    return float(default)


def _roe_score(roe: Optional[float]) -> Optional[float]:
    return _band(roe, [(15, 24), (10, 18), (6, 11), (0, 5)], default=0.0)


def _cash_score(ratio: Optional[float]) -> Optional[float]:
    return _band(ratio, [(1.0, 16), (0.8, 12), (0.5, 7), (0, 3)], default=0.0)


def _margin_score(gm: Optional[float]) -> Optional[float]:
    # 毛利率是**行业相对**指标，这里只做粗筛：<10% 说明缺定价权
    return _band(gm, [(40, 12), (25, 9), (10, 5)], default=2.0)


def _growth_score(rev_yoy: Optional[float], np_yoy: Optional[float]) -> tuple:
    """返回 (分数, 是否触发「营收大幅下滑」风险标记)。"""
    if rev_yoy is None and np_yoy is None:
        return None, False
    worse = min(v for v in (rev_yoy, np_yoy) if v is not None)
    better = max(v for v in (rev_yoy, np_yoy) if v is not None)
    if rev_yoy is not None and rev_yoy <= -20:
        return 0.0, True
    if better >= 15:
        return 8.0, False
    if better >= 5:
        return 6.0, False
    if worse >= 0:
        return 4.0, False
    return 1.0, False


def score(
    symbol: str,
    point: Optional[FundamentalPoint],
    valuation: Optional[Valuation] = None,
    rev_yoy: Optional[float] = None,
    np_yoy: Optional[float] = None,
) -> Score:
    s = Score(symbol=str(symbol))

    if point is None:
        s.tier = "NA"
        s.caveats.append("无财报（ETF/基金），不参与基本面裁决")
        return s

    parts: Dict[str, Optional[float]] = {}
    parts["roe"] = _roe_score(point.roe)
    parts["cash"] = _cash_score(point.cash_conversion)
    parts["margin"] = _margin_score(point.gross_margin)
    growth, rev_collapse = _growth_score(rev_yoy, np_yoy)
    parts["growth"] = growth

    known = {k: v for k, v in parts.items() if v is not None}
    if not known:
        s.tier = "NA"
        s.caveats.append("财报字段全部缺失，无法评分")
        return s
    # 缺失维度按**满分的一半**中性填充，而不是把它归一化掉。
    # 归一化会让「只算得出 ROE 一只指标」的票直接拿 60/60，等于奖励信息缺失。
    max_known = {"roe": 24, "cash": 16, "margin": 12, "growth": 8}
    raw = sum(known.values())
    missing_weight = sum(w for k, w in max_known.items() if k not in known)
    s.quality = raw + missing_weight * 0.5
    if missing_weight:
        s.caveats.append(
            f"质量维度缺 {sorted(set(max_known) - set(known))}，按满分一半中性填充"
        )

    # ---- 估值：PE 占 7 成、PB 占 3 成；分位越低越好
    if valuation and valuation.ok:
        pe_pct = valuation.pe_percentile
        pb_pct = valuation.pb_percentile
        if pe_pct is not None and pb_pct is not None:
            s.valuation = (1 - pe_pct) * 0.7 * 25 + (1 - pb_pct) * 0.3 * 25
        elif pe_pct is not None:
            s.valuation = (1 - pe_pct) * 25
            s.caveats.append("无 PB 分位，估值仅按 PE 计")
        elif pb_pct is not None:
            s.valuation = (1 - pb_pct) * 25
            s.caveats.append("无 PE 分位（或亏损），估值仅按 PB 计")
        else:
            s.valuation = 12.5
            s.caveats.append("估值分位不可用，按中位 12.5 分处理")
    else:
        s.valuation = 12.5
        s.caveats.append("无估值数据，按中位 12.5 分处理")

    # ---- 风险：15 分起扣
    risk = 15.0
    if point.net_profit_ttm is not None and point.net_profit_ttm <= 0:
        s.fatal = "最近 12 个月亏损"
        s.flags.append("loss")
        risk -= 15
    if point.equity is not None and point.equity <= 0:
        s.fatal = s.fatal or "净资产为负"
        s.flags.append("negative_equity")
        risk -= 15
    cc = point.cash_conversion
    if cc is not None:
        if cc < 0:
            s.flags.append("negative_cashflow")
            risk -= 10
        elif cc < 0.5:
            s.flags.append("weak_cash_conversion")
            risk -= 8
    if rev_collapse:
        s.flags.append("revenue_collapse")
        risk -= 8
    if point.roe is not None and point.roe < 3 and not s.fatal:
        s.flags.append("low_roe")
        risk -= 5
    s.risk = max(0.0, risk)

    s.total = s.quality + s.valuation + s.risk
    if s.fatal:
        s.tier = "D"
    elif s.total >= 75 and not s.flags:
        s.tier = "A"
    elif s.total >= 60:
        s.tier = "B"
    elif s.total >= 45:
        s.tier = "C"
    else:
        s.tier = "D"

    s.parts = {k: (None if v is None else round(v, 1)) for k, v in parts.items()}
    s.parts.update(
        {
            "roe_pct": None if point.roe is None else round(point.roe, 1),
            "cash_conversion": None if cc is None else round(cc, 2),
            "gross_margin": point.gross_margin,
            "pe": valuation.pe if valuation else None,
            "pe_percentile": valuation.pe_percentile if valuation else None,
            "pb": valuation.pb if valuation else None,
            "pb_percentile": valuation.pb_percentile if valuation else None,
        }
    )
    return s


def allows_dip(tier: Optional[str]) -> bool:
    """逆势低吸许可：只有 A/B 档可以接刀，C/D/未知一律不行。

    ``NA``（ETF 等无财报标的）**不放行**：没有基本面就无法判断「好公司」，
    这时只保留核心持仓 + 相对强度，不让它冒充合格。
    """
    return tier in ("A", "B")
