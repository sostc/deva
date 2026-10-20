"""PE 估值带：周期带 / 基准带 / 结构性带 这三条尺子从哪来。

❗这个文件存在的唯一理由：**不许写死区间**。
写死的下场项目里已经见过一次（OpenRouter 静默 160 天）：尺子错了不报错，
它只会让所有结论**看起来很专业地错下去**。

❗❗但「实测」也分对错的实测 —— 第一版是怎么错的
------------------------------------------------
第一版按 **分类分组** 算 PE 分布：周期组 PE 的分位数 = 周期带，成长组的 = 结构性带。
听起来最贴语义，实测直接废掉：

    带[周期 26–65 / 结构性 37–65]   ← 两条带几乎完全重叠
    priced_in = −2.35 / 24.53 / 59.80
    15/36 只票「尺子不可用」

原因是**分类带保守偏差**（只有 4 期年度财报，2022-23 半导体下行让「出现过负增长」
普遍命中），于是 AMD(174x) / TSLA(306x) 都被判成周期股 → 周期组的 PE 分布
被拉得比结构性组还贵。更根本的问题是：**用今天的横截面去定义"结构性该给多少"**，
在牛市里所有票都贵，这把尺子测不出"重估空间"，只能测出"谁更贵"。

现在的设计：全池共享的**分位尺子**
----------------------------------
不看分类，直接看这只票的 PE 落在**同类池 PE 分布**的哪一段：

    周期带    = P15–P40（市场给"周期定价"的那一段）
    基准带    = P40–P65
    结构性带  = P65–P90（市场给"结构性成长定价"的那一段）

于是 ``priced_in`` 的语义退化成一个**归一化分位**——这恰恰是它该有的样子：

    priced_in = 0.5  ⇔  这只票的 PE 处在同类的中间位置
    priced_in = 1.0  ⇔  已经按池子里最贵那一档在定价

三个好处：
1. **永远不会反转**。分位数天然有序，结构性带中值必然高于周期带中值 ——
   第一版那种「尺子自相矛盾」的情况在结构上不可能发生。
2. **全池共享一把尺子**，所以不同票的 priced_in 可以横向比较。
   （第一版每只票按自己所属行业量，量出来的数互相不可比。）
3. 分类结果不再参与造尺子，只参与**判读** —— 各司其职，不会互相污染。

❗**这是相对尺子，不是绝对估值锚点**。它回答「市场把它当周期还是当成长在定价」，
不回答「它值多少钱」。池子整体高估时，这把尺子测不出高估 —— 必须写在 UI 上。
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .repricing import PeBand

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- 阈值
# ❗多少个样本才敢说「这是分布」。低于它，分位数只是把个例包装成分布。
MIN_SAMPLES = 8
# 三条带的分位切点（见模块 docstring）
LOW_Q = (0.15, 0.40)
MID_Q = (0.40, 0.65)
HIGH_Q = (0.65, 0.90)
# ❗单个 PE 的合理性上界：超过它当作源异常剔除。
#   注意这不是剔除"贵的票"，是剔除"明显算错的数"（例如 EPS 接近 0 导致 PE 爆炸）。
MAX_SANE_PE = 1000.0

# ---------------------------------------------------------------- 兜底常量
# ❗只在样本不足时用，且必须带 source='fallback' 上屏。
# 数值是美股科技板块长期经验区间，不是精算结果 —— 上屏必须如实标注。
FALLBACK_BANDS: Dict[str, tuple] = {
    "cyclical": (12.0, 18.0),
    "base": (20.0, 28.0),
    "structural": (35.0, 48.0),
}

BAND_NAMES: Dict[str, str] = {
    "cyclical": "周期带",
    "base": "基准带",
    "structural": "结构性带",
}


@dataclass
class PeerPe:
    """池子里一只股票的实测 PE。

    ``regime`` 现在**不参与造尺子**，只留作诊断（池子的分类构成）。
    """
    code: str
    pe: Optional[float]
    regime: str = "unknown"
    note: str = ""


@dataclass
class PeBandSet:
    """三条估值带的集合 + 它们的出身。"""
    cyclical: PeBand
    base: PeBand
    structural: PeBand
    # 参与造尺子的样本数（兜底带为 0）
    samples: int = 0
    # ❗被剔除的标的及原因 —— 剔除必须可见，否则「36 只」里有多少真进了尺子没人知道
    excluded: Dict[str, List[str]] = field(default_factory=dict)
    # 池子 PE 的分布摘要，供 UI 判断这把尺子被哪些票主导
    spread: Dict[str, float] = field(default_factory=dict)
    # 池子的分类构成（诊断用）
    composition: Dict[str, int] = field(default_factory=dict)
    note: str = ""
    valid: bool = True

    def is_valid(self) -> bool:
        """三条带是否都能拿去算 priced_in。

        ❗两个否决条件：
        1. 任一区间自身非法（low<=0 或 high<low）
        2. 结构性带中值不高于周期带中值 —— 尺子反了，算出来的是反的结论
        """
        if not self.valid:
            return False
        for b in (self.cyclical, self.base, self.structural):
            if not b.is_valid():
                return False
        return self.structural.mid > self.cyclical.mid

    def discrimination(self) -> Optional[float]:
        """区分度 = 结构性带中值 − 周期带中值。越小说明尺子越钝。"""
        if not self.is_valid():
            return None
        return self.structural.mid - self.cyclical.mid

    def to_dict(self) -> Dict:
        return {
            "cyclical": self.cyclical.to_dict(),
            "base": self.base.to_dict(),
            "structural": self.structural.to_dict(),
            "samples": self.samples,
            "excluded": {k: list(v) for k, v in self.excluded.items()},
            "spread": {k: round(v, 2) for k, v in self.spread.items()},
            "composition": dict(self.composition),
            "discrimination": (None if self.discrimination() is None
                               else round(self.discrimination(), 2)),
            "note": self.note,
            "valid": self.is_valid(),
        }


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    """线性插值分位数。样本 < 2 时返回 None（1 个点算不出分位）。"""
    if len(values) < 2:
        return None
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _band(name: str, values: Sequence[float], qs: tuple) -> Optional[PeBand]:
    lo = _quantile(values, qs[0])
    hi = _quantile(values, qs[1])
    if lo is None or hi is None:
        return None
    return PeBand(name=BAND_NAMES.get(name, name), low=lo, high=hi,
                  source="measured", scope="pool")


def _fallback_band(name: str) -> PeBand:
    lo, hi = FALLBACK_BANDS[name]
    return PeBand(name=BAND_NAMES.get(name, name), low=lo, high=hi,
                  source="fallback", scope="fallback")


def build_bands(peers: Sequence[PeerPe],
                exclude_code: Optional[str] = None) -> PeBandSet:
    """由池子的实测 PE 分布生成三条带。

    Args:
        peers: 池子里所有标的的实测 PE。
        exclude_code: ❗**要把被评估的那只票自己排除掉** —— 一只票不该参与定义
            衡量自己的尺子（小池子里这会把 priced_in 系统性拉向 0.5）。

    Returns:
        ``PeBandSet``，**总是有值**（兜底保证 UI 不黑屏），但 ``is_valid()``
        可能为 False —— 那时调用方必须显示"尺子不可用"，而不是拿它算 priced_in。
    """
    excluded: Dict[str, List[str]] = {"no_pe": [], "insane": []}
    composition: Dict[str, int] = {}
    values: List[float] = []

    skip = (exclude_code or "").upper()
    for p in peers:
        composition[p.regime] = composition.get(p.regime, 0) + 1
        if (p.code or "").upper() == skip:
            continue
        # ❗剔除必须分类记录：亏损股/源缺失 vs 源异常是两回事，混一起就查不了
        if p.pe is None or p.pe <= 0:
            excluded["no_pe"].append(p.code)
            continue
        if p.pe > MAX_SANE_PE:
            excluded["insane"].append(p.code)
            continue
        values.append(float(p.pe))

    notes: List[str] = []
    if len(values) < MIN_SAMPLES:
        bands = {n: _fallback_band(n) for n in ("cyclical", "base", "structural")}
        notes.append(
            f"有效样本仅 {len(values)} 只（需 {MIN_SAMPLES}），三条带全部使用经验常量；"
            f"读数不作数，只作占位"
        )
        samples = 0
    else:
        bands = {
            "cyclical": _band("cyclical", values, LOW_Q),
            "base": _band("base", values, MID_Q),
            "structural": _band("structural", values, HIGH_Q),
        }
        samples = len(values)

    result = PeBandSet(
        cyclical=bands["cyclical"] or _fallback_band("cyclical"),
        base=bands["base"] or _fallback_band("base"),
        structural=bands["structural"] or _fallback_band("structural"),
        samples=samples,
        excluded=excluded,
        spread=({
            "min": min(values), "max": max(values),
            "median": statistics.median(values), "p25": _quantile(values, 0.25),
            "p75": _quantile(values, 0.75),
        } if values else {}),
        composition=composition,
        note="；".join(notes),
    )

    if not result.is_valid():
        result.valid = False
        result.note = (result.note + "；" if result.note else "") + (
            f"❗尺子不可用：结构性带中值 {result.structural.mid:.1f} 未高于"
            f"周期带中值 {result.cyclical.mid:.1f}，禁止据此计算 priced_in"
        )
    return result
