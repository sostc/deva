"""重定价度量：市场已经 price in 了多少？还有没有买点？

回答用户那两个问题：
1. 结构性行情是不是来了 / 是不是已经 price in？
2. 现在还有没有买入机会？

三个度量：

``priced_in_ratio``
    当前 PE 在「周期锚 → 结构性锚」之间走了多远。0 = 完全按周期定价，
    1 = 已经进入结构性定价，>1 = 已透支。

    ❗两个锚点取的是 **周期带下沿 / 结构性带下沿**，不是两条带的中值。
    实测教训（2026-10-20）：分位尺子的结构性带上沿被极值拉爆
    （TSLA 306x / PLTR 202x / AMD 174x 把 P90 顶到 176x），用中值当上行目标
    会算出 NVDA 上行 +256%、MSFT +271%、SMCI +661% —— 那是把"池子里最贵的
    那一档"当成了目标价，不是重估空间。
    用**下沿**的语义才对：结构性锚 = "市场开始把它按成长股定价"的门槛，
    周期锚 = "市场把它按最悲观那档定价"的位置。

``asymmetry``
    不对称比 = 上行空间 / 下行空间。这是我对「还有没有买入机会」的翻译：
    **不是问能不能买，而是问「赌对了赚多少、赌错了亏多少」**。

``entry_window``
    基本面阶段（S0–S4）× 定价进度 的九宫格，给出一句人话判读。

❗三个度量的共同纪律：**算不出来就返回 ``None``，绝不返回 0 或 inf**。
特别是 ``asymmetry``：当现价已经跌破周期带时，分母 ≤ 0，若返回 ``inf``
会让「最危险的票」在排序里排最前面 —— 那正是价值陷阱的样子。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# 定价进度分档
PARTIAL_LOW = 0.3
PARTIAL_HIGH = 0.7
# 不对称比门槛
ASYMMETRY_GOOD = 2.0
# ❗下行空间下限（%）。低于它，不对称比会爆炸式乐观 ——
#   实测 GOOGL：PE 25.98 几乎贴着周期锚 25x，下行只有 3.9%，
#   算出来的不对称比 32 完全是分母趋零造成的假象，不是"赔率极好"。
#   此时必须返回 None，并写清原因。
MIN_DOWNSIDE_PCT = 15.0


@dataclass
class PeBand:
    """一个估值情景对应的 PE 区间。

    ❗``mid`` 由 ``low``/``high`` 派生，不单独存 —— 两个真源会分裂。
    """
    name: str
    low: float
    high: float
    source: str = "measured"   # measured = 实测分布；fallback = 兜底常量表
    # ❗样本取自哪一层：industry=同行业同类 / pool=全池同类 / fallback=兜底常量。
    #   逐级放宽和「缺失填 0」是同一类病：读者以为看的是行业尺子，其实是全池尺子。
    scope: str = ""

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2

    def is_valid(self) -> bool:
        return self.low > 0 and self.high >= self.low

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "low": round(self.low, 2),
            "high": round(self.high, 2),
            "mid": round(self.mid, 2),
            "source": self.source,
            "scope": self.scope,
        }


@dataclass
class RepricingResult:
    """重定价度量结果"""
    code: str
    pe_now: Optional[float]
    priced_in: Optional[float] = None
    priced_in_label: str = ""
    asymmetry: Optional[float] = None
    upside_pct: Optional[float] = None
    downside_pct: Optional[float] = None
    entry_window: str = ""
    verdict: str = ""
    note: str = ""

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "pe_now": None if self.pe_now is None else round(self.pe_now, 2),
            "priced_in": None if self.priced_in is None else round(self.priced_in, 2),
            "priced_in_label": self.priced_in_label,
            "asymmetry": None if self.asymmetry is None else round(self.asymmetry, 2),
            "upside_pct": None if self.upside_pct is None else round(self.upside_pct, 1),
            "downside_pct": None if self.downside_pct is None else round(self.downside_pct, 1),
            "entry_window": self.entry_window,
            "verdict": self.verdict,
            "note": self.note,
        }


def _anchors(cyclical: PeBand, structural: PeBand) -> Optional[tuple]:
    """取 (周期锚, 结构性锚)。

    ❗用**下沿**不用中值 —— 见模块 docstring「为什么不用 mid」。
    结构性带下沿 = 进入结构性定价的门槛；周期带下沿 = 被按最悲观那档定价。
    """
    if not cyclical.is_valid() or not structural.is_valid():
        return None
    span = structural.low - cyclical.low
    if span <= 0:
        return None
    return cyclical.low, structural.low


def priced_in_ratio(pe_now: Optional[float], cyclical: PeBand,
                    structural: PeBand) -> Optional[float]:
    """市场已经把「结构性成长」定价了多少。

    返回 ``None`` 的三种情况（都必须如实上报，不许编一个数）：
    - PE 拿不到（亏损股 / 源无数据）
    - 两条带子本身无效（low<=0 或 high<low）
    - 结构性锚不高于周期锚 —— 说明这把尺子本身坏了
    """
    if pe_now is None or pe_now <= 0:
        return None
    anchors = _anchors(cyclical, structural)
    if anchors is None:
        return None
    cyc_a, str_a = anchors
    return (pe_now - cyc_a) / (str_a - cyc_a)


def asymmetry(pe_now: Optional[float], cyclical: PeBand,
              structural: PeBand) -> Tuple[Optional[float], Optional[float],
                                           Optional[float], str]:
    """不对称比 = 上行空间 / 下行空间。

    返回 ``(ratio, upside_pct, downside_pct, note)``。

    ❗**两种情况下返回 ``None``**（都不许用 0 或 inf 凑数）：
    1. 现价已经跌破周期锚 —— 此时"回到周期锚"不再是下跌而是上涨，
       比值语义不成立。它不是"无穷好的机会"，而是**价值陷阱的信号**。
    2. 下行空间 < ``MIN_DOWNSIDE_PCT`` —— 分母趋零会把比值顶到几十上百，
       那是数学假象不是赔率（实测 GOOGL 分母 3.9% → 比值 32）。
    """
    if pe_now is None or pe_now <= 0:
        return None, None, None, "PE 未采集，无法计算不对称比"
    anchors = _anchors(cyclical, structural)
    if anchors is None:
        return None, None, None, "PE 区间无效，无法计算不对称比"
    cyc_a, str_a = anchors

    up = str_a - pe_now
    down = pe_now - cyc_a

    upside_pct = up / pe_now * 100
    downside_pct = down / pe_now * 100

    if down <= 0:
        return (None, upside_pct, downside_pct,
                "已跌破周期锚：下行空间失效，需人工判断（可能是价值陷阱）")
    if downside_pct < MIN_DOWNSIDE_PCT:
        return (None, upside_pct, downside_pct,
                f"下行空间仅 {downside_pct:.1f}%（<{MIN_DOWNSIDE_PCT:.0f}%），"
                f"不对称比会失真，不予计算")
    return up / down, upside_pct, downside_pct, ""


def _priced_in_label(ratio: float) -> str:
    if ratio < PARTIAL_LOW:
        return "市场仍按周期定价"
    if ratio <= PARTIAL_HIGH:
        return "部分 price in"
    if ratio <= 1.0:
        return "基本 price in"
    # ❗超过 1 不是"贵一点"，是**已经把结构性成长全部定价完还多给了**。
    # 实测 PLTR：PE 203x → priced_in 5.2，上行空间已经是 −71%。
    return "已透支（高于结构性定价门槛）"


# ❗九宫格：阶段 × 定价进度。每一格**必须有文案** ——
# 空白格在页面上就是黑屏，那是"合法的空"，比报错更难发现。
_ENTRY_GRID: Dict[Tuple[str, str], str] = {
    ("early", "low"): "最佳赔率区：基本面刚起步、市场还没换尺子。胜率最差，仓位要小。",
    ("early", "mid"): "正常建仓区：故事与证据同步推进，按常规仓位。",
    ("early", "high"): "故事先行：价格已经跑在基本面前面，等证据跟上再动。",
    ("mid", "low"): "认知差窗口：瓶颈已验证但市场没定价，值得重点研究。",
    ("mid", "mid"): "平衡点：有证据、未充分定价，是本框架下最舒服的位置。",
    ("mid", "high"): "需要业绩加速兑现才安全，否则估值先行会回吐。",
    ("late", "low"): "少见的错杀：利润已兑现却仍按周期定价，先核查数据再动手。",
    ("late", "mid"): "趋势跟随：别把它当重估机会，赚的是业绩不是估值。",
    ("late", "high"): "业绩兑现即出货区：利润已兑现且已定价，剩余空间靠不到重估。",
}


def _stage_bucket(phase: str) -> str:
    """S0–S4 → early / mid / late"""
    p = (phase or "").upper()
    if p in ("S0", "S1"):
        return "early"
    if p == "S2":
        return "mid"
    if p in ("S3", "S4"):
        return "late"
    return "mid"


def _ratio_bucket(ratio: float) -> str:
    if ratio < PARTIAL_LOW:
        return "low"
    if ratio <= PARTIAL_HIGH:
        return "mid"
    return "high"


def evaluate_repricing(code: str, pe_now: Optional[float], cyclical: PeBand,
                       structural: PeBand, phase: str = "",
                       regime: str = "") -> RepricingResult:
    """算一只票的重定价三件套。

    ❗``regime`` 必须参与判读：**周期股的 priced_in 高是陷阱不是机会**。
    同样的 0.8，在成长股身上是"快到顶了"，在周期股身上是"已经泡沫了"。
    """
    result = RepricingResult(code=code, pe_now=pe_now)

    ratio = priced_in_ratio(pe_now, cyclical, structural)
    if ratio is None:
        result.note = "PE 或估值带缺失，无法定价进度"
        result.entry_window = "不可用"
        result.verdict = "数据不足，不做判断"
        return result

    result.priced_in = ratio
    result.priced_in_label = _priced_in_label(ratio)

    ratio_b, upside, downside, note = asymmetry(pe_now, cyclical, structural)
    result.asymmetry = ratio_b
    result.upside_pct = upside
    result.downside_pct = downside
    result.note = note

    stage = _stage_bucket(phase)
    rbucket = _ratio_bucket(ratio)
    result.entry_window = _ENTRY_GRID[(stage, rbucket)]

    # ---- 一句话判读 ----
    if regime == "cyclical" and ratio > PARTIAL_HIGH:
        result.verdict = "周期股已被按成长定价 —— 不是机会，是陷阱"
    elif regime == "cyclical":
        result.verdict = "周期股：尺子本身就是周期带，别用结构性空间说服自己"
    elif result.upside_pct is not None and result.upside_pct <= 0:
        # ❗上行空间已经是负的：现价高于结构性定价门槛，"还有没有买入机会"
        # 的答案是"没有" —— 这不是"贵一点"，是已经把好消息全部定价完。
        result.verdict = "无买入空间：现价已高于结构性定价门槛，已充分定价甚至透支"
    elif ratio_b is None:
        result.verdict = "不对称比失效（跌破周期锚或下行空间过小），需人工判断"
    elif ratio_b >= ASYMMETRY_GOOD:
        result.verdict = "赔率合适：上行是下行的 2 倍以上，值得下手"
    elif ratio_b >= 1:
        result.verdict = "鸡肋：上下空间差不多，不值得为它承担波动"
    else:
        result.verdict = "不该下手：赢了赚一点、输了亏很多"

    return result
