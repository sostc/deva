"""周期 / 结构性成长分类器

回答一个问题：**这家公司是周期股还是成长股？** 这个答案决定了用哪把尺子给它定价。

为什么必须有这一层（2026-10-20）：
    ``valuation_agent.ScenarioType`` 里的 CYCLICAL / BASE / STRUCTURAL 是
    **三个估值情景**，不是**对公司的分类**。于是系统能算出「结构性情景的隐含
    PE 是 35x」，却答不出「这家公司到底配不配 35x」。周期股冲进结构性带叫泡沫，
    成长股蹲在周期带叫错杀 —— 同一个 PE 数值，含义完全相反。

设计原则：
- **分类靠可观测特征，不靠行业标签**。行业叫"半导体"不代表这家公司是周期股。
- **每个结论都要带证据**（命中了哪几条、具体数值），不许只吐一个标签。
- **``UNKNOWN`` 是一等公民**：数据不够就报不知道，绝不默认成 ``BASE``。
  （默认成 BASE 的后果：「没数据」被读成「稳态」，进而被拿去重定价。）
- 纯函数，不碰网络、不碰数据库，好测。

判据（各指向一个方向，**加权**计分，见下方「为什么不是等权计数」）：

    ── 强证据（权重 2）：直接刻画利润的时间行为
    C1 利润波动：净利同比的**对数尺度**标准差 > 3.5
    C2 利润转负：负增长期数占比 ≥ 1/3，**或**出现过同比 < −100%（由盈转亏）
    S1 持续增长：最近 3 期净利同比全为正

    ── 弱证据（权重 1）：周期上行期同样会出现，单独不足以定类
    C3 毛利剧摆：毛利率极差 > 10pp（周期反转特征，见下方 ❗）
    S2 毛利扩张：毛利率单调不降，累计提升 ∈ [1pp, 20pp]
    S3 利润质量：最近一期 经营现金流/净利润 ≥ 1.2

    ── 当前无数据源，恒不生效（调用方未传序列）
    C4 毛利随价：毛利率与同期价格因子相关系数 > 0.5（需 ``price_series``）
    C5 低估值中枢：自身 PE 历史中位数 < 20（需 ``pe_history``）

定类规则：**某一侧必须至少命中 1 条强证据**才够格定该类。
两侧都够格 → 分高者；打平 → ``BASE`` + 记冲突（不猜）。

❗为什么 C1 用「对数尺度标准差」而不是原始标准差（2026-10-20 校准）：
    净利同比是**比率**，分布重尾到没法用：WDC 有一期 +3242%（低基数反弹），
    原始标准差 1393.6 —— 这一个数就支配了整批样本的尺度，阈值怎么切都
    区分不开（25pp→76% 命中，80pp→还有 55%）。
    改成 ``sign(x)·ln(1+|x|)`` 后取标准差，即压缩量纲又不丢方向：
      ISRG（稳定成长）原始 sd 94.5 → 对数 sd **0.93**，落到全池倒数第 5
      WDC / MU / INTC（典型周期）→ **5.71 / 4.96 / 4.40**，排前三
    排序的语义正确性远好于原始 sd（后者会把 ISRG 排到 LRCX 前面）。

❗为什么不是等权计数（2026-10-20 校准，实测踩出来）：
    等权时「命中 2 条就定类」，于是 **CRM**（对数 sd 4.37，全池第 8 大波动）
    被判「稳态」—— 因为 S2+S3 两条**弱**证据凑够 2 条，把 C1 这条**强**证据打平了；
    **LRCX / KLAC / AMAT**（半导体设备周期股）被判「结构性成长」，靠的同样是
    S2（毛利率温和扩张）+ S3（现金流≥0.8）这两条 —— 可这两条在**周期上行期
    一样会成立**，它们根本不区分周期与成长。
    一句话：**弱证据不该有扳倒强证据的票数**。所以改成加权 + 强证据门槛。

❗为什么「毛利率大幅扩张」不算结构性成长（2026-10-20 实测 MU 踩出来）：
    MU 的毛利率 4 期是 **−9.11% → 22.35% → 39.79% → 80.72%**，单调上升 +89.8pp。
    只看"单调扩张"的话它是全场最像成长股的一个 —— 但它其实是**典型周期股**：
    2023 年净利同比 **−167%**（巨亏），2026 年 **+895%**。毛利率从负数爬回来
    是**周期反转**，不是**结构性改善**。用它去支撑"结构性重定价"，等于把
    周期顶部的低 PE（MU 现在 20.37x）误读成"便宜的成长股"—— 这正是周期股
    最经典的估值陷阱。

    所以 S2 设了 **20pp 上限**（与 ``valuation_agent.MAX_STRUCTURAL_MARGIN_UPLIFT_PP``
    同一把尺子），超过上限不但不算成长证据，反而记一条周期证据（C3）。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence

# ❗最少需要几个数据点才敢分类。3 期以下算不出"趋势"，只能算噪声。
MIN_PERIODS = 4
# ❗净利同比的**对数尺度**标准差阈值（见模块 docstring）。
# 33 只实测分布：>3.0→61% 命中，>3.5→55%，>4.0→36%。取 3.5。
LOG_SD_THRESHOLD = 3.5
# ❗负增长期数占比门槛。4 期里只有 1 期负增长太常见了（2022-23 下行几乎普遍命中），
# 实测「出现即命中」有 88% 命中率 —— 那是必然事件，不是证据。
NEG_SHARE_MIN = 1.0 / 3.0
# ❗「由盈转亏」的同比深度门槛（%）。低于它说明当年净利为负，是硬周期信号。
DEEP_NEGATIVE_PCT = -100.0
# 毛利率与价格因子的相关系数阈值（需 price_series，当前无数据源）
MARGIN_PRICE_CORR = 0.5
# 周期股 PE 中枢上限（需 pe_history，当前无数据源）
CYCLICAL_PE_CENTER = 20.0
# 结构性成长：毛利率累计扩张下限（百分点）
MARGIN_EXPANSION_PP = 1.0
# ❗毛利率扩张上限：超过它就不是"结构性改善"，而是"周期反转"。
# 与 valuation_agent.MAX_STRUCTURAL_MARGIN_UPLIFT_PP 保持同一把尺子（20pp）。
MAX_MARGIN_UPLIFT_PP = 20.0
# ❗毛利率极差阈值（C3）。原 20pp 只抓到 2/33（6%），太钝；实测 10pp→19%。
MARGIN_SWING_PP = 10.0
# ❗结构性成长：现金流/净利润下限。原 0.8 有 76% 命中 —— 周期股在景气顶部
# 现金流同样漂亮，这不是成长的证据。提到 1.2（≈实测样本中位数）→ 52%。
CASHFLOW_QUALITY = 1.2
# ❗判据权重：强证据（刻画利润时间行为）vs 弱证据（周期上行期也会有）
STRONG_WEIGHT = 2
WEAK_WEIGHT = 1
# 定类所需的最少加权分（等价于「至少命中 1 条强证据」）
MIN_SCORE = STRONG_WEIGHT
# 理想期数：用来算样本充分度。年度 8 期才谈得上"看过一个完整周期"。
IDEAL_PERIODS = 8
# ❗confidence 的分母：该侧**所有判据都可用时**的满分。
#   不能用「当前可用判据的满分」—— 那样缺失数据反而更容易拿满分
#   （实测 ONEHIT：只有 S1 可用时 2/2 = 1.00，看着比数据齐全的票还确定）。
#   C4/C5 依赖 price_series / pe_history，当前**无数据源**，不计入，
#   否则永远达不到 1.00，confidence 就变成不可达的摆设。
CYC_IDEAL_SCORE = STRONG_WEIGHT * 2 + WEAK_WEIGHT      # C1 + C2 + C3
STR_IDEAL_SCORE = STRONG_WEIGHT + WEAK_WEIGHT * 2      # S1 + S2 + S3


class ValuationRegime(Enum):
    """估值属性分类（对**公司**的分类，不是情景）"""
    CYCLICAL = "cyclical"                  # 周期：利润均值回归，不配成长估值
    STRUCTURAL_GROWTH = "structural"       # 结构性成长：利润跃迁可持续
    BASE = "base"                          # 稳态：趋势延续，两边都不够格
    UNKNOWN = "unknown"                    # 数据不足 —— ❗绝不能默认成 BASE

    @property
    def display_name(self) -> str:
        return {
            "cyclical": "周期",
            "structural": "结构性成长",
            "base": "稳态",
            "unknown": "未分类",
        }[self.value]

    @property
    def is_usable(self) -> bool:
        """这个分类能不能拿去做重定价。``UNKNOWN`` 不行。"""
        return self is not ValuationRegime.UNKNOWN


@dataclass
class ClassificationInput:
    """分类输入（全部「旧 → 新」排列）

    ❗缺失用空列表表达，不要用 0 填充 —— 0 会被算进标准差和相关性里，
    把「没数据」算成「零增长 / 零相关」。
    """
    code: str
    net_profit_yoy: List[float] = field(default_factory=list)      # %
    gross_margin: List[float] = field(default_factory=list)        # %
    cashflow_to_profit: List[float] = field(default_factory=list)  # 比值
    price_series: List[float] = field(default_factory=list)        # 同期价格因子（可选）
    pe_history: List[float] = field(default_factory=list)          # PE 历史（可选）
    # ❗因「上游标记为缺失」而被剔除的样本数（按字段）。
    #   剔除必须可见 —— 悄悄丢掉样本会让"4 期"看起来是完整的 4 期。
    excluded: Dict[str, int] = field(default_factory=dict)
    # 最近一期净利润（判「持续亏损」用）。None = 不知道。
    latest_net_profit: Optional[float] = None

    @property
    def periods(self) -> int:
        """有效期数：以净利同比为准（分类的主轴是利润行为）。"""
        return len(self.net_profit_yoy)


@dataclass
class ClassificationResult:
    """分类结果"""
    code: str
    regime: ValuationRegime
    confidence: float                       # 命中数 / 可用判据数，∈[0,1]
    evidence: List[str] = field(default_factory=list)      # 命中的判据 + 具体数值
    counter_evidence: List[str] = field(default_factory=list)  # 反向命中的判据
    missing_fields: List[str] = field(default_factory=list)    # 缺哪些数据
    periods: int = 0
    cyc_score: int = 0          # 周期侧加权分
    str_score: int = 0          # 成长侧加权分
    sample_sufficiency: float = 0.0   # 样本充分度 ∈[0,1]
    # ❗因上游标记缺失而剔除的期数（按字段）。结构化保留是为了 UI 能单独上屏，
    #   而不是只能从 note 文本里挖。
    excluded: Dict[str, int] = field(default_factory=dict)
    note: str = ""

    @property
    def is_confident(self) -> bool:
        """是否够格拿去做重定价。

        ❗``BASE``（未定类）不返回 True —— 它表示"分不出来"，不是"稳态所以安全"。
        """
        return self.regime in (ValuationRegime.CYCLICAL,
                               ValuationRegime.STRUCTURAL_GROWTH)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "regime": self.regime.value,
            "regime_name": self.regime.display_name,
            "confidence": round(self.confidence, 2),
            "evidence": list(self.evidence),
            "counter_evidence": list(self.counter_evidence),
            "missing_fields": list(self.missing_fields),
            "periods": self.periods,
            "cyc_score": self.cyc_score,
            "str_score": self.str_score,
            "sample_sufficiency": self.sample_sufficiency,
            "excluded": dict(self.excluded),
            "is_confident": self.is_confident,
            "note": self.note,
        }


def build_input_from_financials(code: str, fins, price_series=None,
                                pe_history=None) -> ClassificationInput:
    """把财报序列转成分类输入。

    ❗``fins`` 是**最新在前**（``financial_data_fetcher.fetch`` 的既有约定），
    而分类器要的是**旧 → 新**。不反转的话，"趋势"和"加速度"全是反的 ——
    这种错不会报错，只是结论一直反着来。

    另外：净利为负时**不生成**现金流质量样本（比值没有意义），
    而不是填 0 —— 填 0 会把"巨亏"算成"现金流质量 0"（即极差），
    反而把周期股误判得更像周期股。
    """
    ordered = list(reversed(list(fins or [])))

    yoy: List[float] = []
    gm: List[float] = []
    cf_ratio: List[float] = []
    excluded: Dict[str, int] = {}
    latest_net: Optional[float] = None

    def _missing(f, key: str) -> bool:
        return key in (getattr(f, "missing", None) or [])

    for f in ordered:
        # ❗上游把「取不到」填成 0.0 塞进字段（净利同比 0、毛利率 0、现金流 0），
        #   但它同时在 ``missing`` 里写了名字。只判 ``is not None`` 会把假 0 当真值：
        #   - 净利同比假 0 → 拉低标准差、破坏「全为正增长」判据
        #   - 毛利率假 0   → 极差 0、升降 0，被读成「毛利率纹丝不动」
        #   - 现金流假 0   → 现金流/净利=0，被读成「利润质量极差」
        #   三者全是「没数据」被读成「坏数据」，方向一致地偏向"不像成长股"。
        y = getattr(f, "net_profit_yoy", None)
        if y is None or _missing(f, "net_profit_yoy"):
            excluded["net_profit_yoy"] = excluded.get("net_profit_yoy", 0) + 1
        else:
            yoy.append(float(y))

        m = getattr(f, "gross_margin", None)
        if m is None or _missing(f, "gross_margin"):
            excluded["gross_margin"] = excluded.get("gross_margin", 0) + 1
        else:
            gm.append(float(m))

        net = getattr(f, "net_profit", None)
        cf = getattr(f, "cashflow", None)
        if net is None or cf is None or float(net) <= 0 or _missing(f, "cashflow"):
            excluded["cashflow_to_profit"] = excluded.get("cashflow_to_profit", 0) + 1
        else:
            cf_ratio.append(float(cf) / float(net))

        if net is not None:
            latest_net = float(net)  # ordered 是旧→新，最后一个即最近一期

    return ClassificationInput(
        code=code,
        net_profit_yoy=yoy,
        gross_margin=gm,
        cashflow_to_profit=cf_ratio,
        price_series=list(price_series or []),
        pe_history=list(pe_history or []),
        excluded=excluded,
        latest_net_profit=latest_net,
    )


def _log_sd(yoy: Sequence[float]) -> Optional[float]:
    """净利同比的**对数尺度**标准差。

    ❗为什么不能直接 ``pstdev(yoy)``：同比是比率，分布重尾到没法用 ——
    WDC 有一期 +3242%（低基数反弹），原始标准差 1393.6，一个数就支配了
    整批样本的尺度。这里先做 ``sign(x)·ln(1+|x|)`` 的保号压缩再取标准差：
    压缩量纲但不丢方向，且不需要额外拍一个截断阈值（log 本身就是平滑压缩）。
    """
    if len(yoy) < 2:
        return None
    try:
        compressed = [math.copysign(math.log1p(abs(v)), v) for v in yoy]
    except (TypeError, ValueError):
        return None
    return statistics.pstdev(compressed)


def _sufficiency(periods: int) -> float:
    """样本充分度 ∈[0,1]。

    ❗年度 4 期只能看到一个周期片段（一轮半导体下行 2 年就过去了），
    谈不上有多可靠。这个系数就是为了让「结论看起来很确定」这件事付出代价。
    """
    return round(min(1.0, periods / IDEAL_PERIODS), 2)


def _corr(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """皮尔逊相关系数。长度不足、方差为 0 时返回 ``None``。

    ❗方差为 0（价格一条直线）时相关系数的分母是 0 —— 这不是「相关性为 0」，
    而是「算不出来」，必须区分开。
    """
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    a = list(xs[-n:])
    b = list(ys[-n:])
    try:
        ma, mb = statistics.mean(a), statistics.mean(b)
        da = [v - ma for v in a]
        db = [v - mb for v in b]
        num = sum(x * y for x, y in zip(da, db))
        den = (sum(x * x for x in da) ** 0.5) * (sum(y * y for y in db) ** 0.5)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if den <= 0:
        return None
    return num / den


def classify(inp: ClassificationInput) -> ClassificationResult:
    """对单只股票做周期 / 结构性成长分类。

    判定顺序：
    1. 期数 < ``MIN_PERIODS`` → ``UNKNOWN``（❗这一步必须在最前面，
       否则「只有 2 期数据」会被后面宽松的判据误定成 CYCLICAL）
    2. 分别统计 CYCLICAL / STRUCTURAL 的命中数
    3. 两边都不够 → ``BASE``；两边都够 → 命中多者，相等则记冲突并落 ``BASE``
    """
    periods = inp.periods
    missing: List[str] = []

    if not inp.net_profit_yoy:
        missing.append("净利同比")
    if not inp.gross_margin:
        missing.append("毛利率")
    if not inp.cashflow_to_profit:
        missing.append("现金流/净利")
    if not inp.price_series:
        missing.append("价格因子（C2 判据不可用）")
    if not inp.pe_history:
        missing.append("PE 历史（C5 判据不可用）")

    # ❗剔除必须上屏：悄悄丢样本会让"4 期"看起来是完整的 4 期
    for key, cnt in sorted((inp.excluded or {}).items()):
        missing.append(f"{key} 有 {cnt} 期被判缺失已剔除")

    # ❗1. 数据不足一律 UNKNOWN，绝不往下走
    if periods < MIN_PERIODS:
        return ClassificationResult(
            code=inp.code,
            regime=ValuationRegime.UNKNOWN,
            confidence=0.0,
            missing_fields=missing,
            periods=periods,
            sample_sufficiency=_sufficiency(periods),
            excluded=dict(inp.excluded or {}),
            note=f"数据不足：有效 {periods} 期，分类至少需要 {MIN_PERIODS} 期",
        )

    cyc_hits: List[str] = []
    str_hits: List[str] = []
    cyc_score = 0
    str_score = 0
    cyc_strong = 0  # ❗强证据**条数**（不是分数）
    str_strong = 0
    cyc_max = 0     # 该侧「可用判据」的最大可能加权分（confidence 的分母）
    str_max = 0

    # ---- C1 利润波动（强）----
    yoy = inp.net_profit_yoy
    cyc_max += STRONG_WEIGHT
    sd_log = _log_sd(yoy)
    if sd_log is not None and sd_log > LOG_SD_THRESHOLD:
        cyc_score += STRONG_WEIGHT
        cyc_strong += 1
        cyc_hits.append(f"利润波动大（净利同比对数尺度标准差 {sd_log:.2f}）")

    # ---- C2 利润转负（强）----
    cyc_max += STRONG_WEIGHT
    neg_share = sum(1 for v in yoy if v < 0) / len(yoy)
    worst = min(yoy)
    # ❗最近一期**真亏损**的公司（INTC / SNOW / MDB / ZS），C2 降为弱证据。
    #   理由：对亏损公司，"净利同比为负"衡量的是**亏损扩大速度**，不是周期波动 ——
    #   SNOW 4 期同比全负（−381/−5/−54/−4），按占比 100% 会命中强 C2 被判成周期股，
    #   但它是"还没盈利的成长股"，不是周期股。降级后 SNOW 落稳态（无强周期证据），
    #   而 INTC 靠 C1（波动 4.40）仍然正确判周期 —— 分得开。
    unprofitable = inp.latest_net_profit is not None and inp.latest_net_profit < 0
    c2_weight = WEAK_WEIGHT if unprofitable else STRONG_WEIGHT
    if neg_share >= NEG_SHARE_MIN:
        cyc_score += c2_weight
        if not unprofitable:
            cyc_strong += 1
        cyc_hits.append(f"负增长期数占比 {neg_share:.0%}（≥{NEG_SHARE_MIN:.0%}）"
                        + ("，但公司仍亏损，仅作弱证据" if unprofitable else ""))
    elif worst < DEEP_NEGATIVE_PCT:
        cyc_score += c2_weight
        if not unprofitable:
            cyc_strong += 1
        cyc_hits.append(f"出现过由盈转亏（最低同比 {worst:.1f}%）"
                        + ("，但公司仍亏损，仅作弱证据" if unprofitable else ""))

    # ---- C3 毛利率剧烈摆动（弱：周期反转，不是结构改善）----
    if inp.gross_margin:
        cyc_max += WEAK_WEIGHT
        swing = max(inp.gross_margin) - min(inp.gross_margin)
        if swing > MARGIN_SWING_PP:
            cyc_score += WEAK_WEIGHT
            cyc_hits.append(
                f"毛利率剧烈摆动 {swing:.1f}pp（>{MARGIN_SWING_PP:.0f}pp，周期反转特征）"
            )

    # ---- C4 毛利率随价格摆动（弱，需 price_series）----
    if inp.price_series:
        cyc_max += WEAK_WEIGHT
        c = _corr(inp.gross_margin, inp.price_series)
        if c is not None and c > MARGIN_PRICE_CORR:
            cyc_score += WEAK_WEIGHT
            cyc_hits.append(f"毛利率随价格同向摆动（相关系数 {c:.2f}）")

    # ---- C5 低估值中枢（弱，需 pe_history）----
    if inp.pe_history:
        cyc_max += WEAK_WEIGHT
        med = statistics.median(inp.pe_history)
        if med < CYCLICAL_PE_CENTER:
            cyc_score += WEAK_WEIGHT
            cyc_hits.append(f"PE 中枢偏低（历史中位 {med:.1f}x）")

    # ---- S1 持续增长（强）----
    str_max += STRONG_WEIGHT
    window = yoy[-3:] if len(yoy) >= 3 else yoy
    if len(window) >= 3 and all(v > 0 for v in window):
        str_score += STRONG_WEIGHT
        str_strong += 1
        str_hits.append(
            f"最近 3 期净利同比持续为正（{' → '.join(f'{v:.0f}%' for v in window)}）"
        )

    # ---- S2 毛利率扩张（弱）----
    if inp.gross_margin:
        str_max += WEAK_WEIGHT
        gm = inp.gross_margin[-4:] if len(inp.gross_margin) >= 4 else inp.gross_margin
        if len(gm) >= 3:
            monotonic = all(gm[i + 1] >= gm[i] for i in range(len(gm) - 1))
            uplift = gm[-1] - gm[0]
            # ❗上限很关键：+89.8pp 那种是周期反转，不是结构性改善（见模块 docstring）
            if monotonic and MARGIN_EXPANSION_PP <= uplift <= MAX_MARGIN_UPLIFT_PP:
                str_score += WEAK_WEIGHT
                str_hits.append(f"毛利率单调扩张 +{uplift:.1f}pp")

    # ---- S3 利润质量（弱）----
    if inp.cashflow_to_profit:
        str_max += WEAK_WEIGHT
        latest_cf = inp.cashflow_to_profit[-1]
        if latest_cf >= CASHFLOW_QUALITY:
            str_score += WEAK_WEIGHT
            str_hits.append(f"现金流匹配利润（现金流/净利 {latest_cf:.2f}）")

    # ---- 定类 ----
    # ❗每侧都必须至少命中 1 条**强证据**才够格（弱证据在周期上行期照样成立，
    #   两条弱证据凑不出一个结论 —— 见模块 docstring「为什么不是等权计数」）。
    #   ❗门槛必须数「强证据条数」，不能用分数：S2(弱)+S3(弱) 也等于 2 分，
    #   用 score>=2 判断会让 EQIX 这种「只有两条弱证据」的票照样定成成长股。
    cyc_ok = cyc_strong >= 1
    str_ok = str_strong >= 1

    if cyc_ok and str_ok:
        if cyc_score > str_score:
            regime, evidence, counter = ValuationRegime.CYCLICAL, cyc_hits, str_hits
        elif str_score > cyc_score:
            regime, evidence, counter = ValuationRegime.STRUCTURAL_GROWTH, str_hits, cyc_hits
        else:
            # 打平 = 真的分不出来，不猜
            return ClassificationResult(
                code=inp.code,
                regime=ValuationRegime.BASE,
                confidence=0.0,
                evidence=cyc_hits,
                counter_evidence=str_hits,
                missing_fields=missing,
                periods=periods,
                cyc_score=cyc_score,
                str_score=str_score,
                sample_sufficiency=_sufficiency(periods),
                excluded=dict(inp.excluded or {}),
                note=(f"周期与成长证据打平（{cyc_score} vs {str_score}），"
                      f"两侧都成立 → 不猜，按稳态处理"),
            )
    elif cyc_ok:
        regime, evidence, counter = ValuationRegime.CYCLICAL, cyc_hits, str_hits
    elif str_ok:
        regime, evidence, counter = ValuationRegime.STRUCTURAL_GROWTH, str_hits, cyc_hits
    else:
        # ❗都不够格：两侧都只有弱证据（或没有证据）
        note = "两侧都只有弱证据（周期上行期也会出现），不足以定类"
        if inp.latest_net_profit is not None and inp.latest_net_profit <= 0:
            note += "；且最近一期净利 ≤ 0，PE 与重定价均不适用"
        return ClassificationResult(
            code=inp.code,
            regime=ValuationRegime.BASE,
            confidence=0.0,
            evidence=cyc_hits,
            counter_evidence=str_hits,
            missing_fields=missing,
            periods=periods,
            cyc_score=cyc_score,
            str_score=str_score,
            sample_sufficiency=_sufficiency(periods),
            excluded=dict(inp.excluded or {}),
            note=note,
        )

    is_cyc = regime is ValuationRegime.CYCLICAL
    side_max = cyc_max if is_cyc else str_max
    side_score = cyc_score if is_cyc else str_score
    other_score = str_score if is_cyc else cyc_score
    ideal = CYC_IDEAL_SCORE if is_cyc else STR_IDEAL_SCORE
    # ❗confidence = **净优势 / 理想满分**，三个因素同时起作用：
    #   1) 反侧证据：自己一侧 4 分、反侧也有 2 分强证据（实测 CRM），
    #      真实确定性远不到 100% → 净优势只剩 2，confidence 0.50
    #   2) 证据绝对量：只命中 1 条强证据就给 1.00 是**过度自信**
    #      （实测 ENPH 周期侧仅 2 分、MDB 成长侧仅 2 分，原来都显示 1.00）
    #      → 除以理想满分后 ENPH 0.40、MDB 0.50
    #   3) 数据完整度：分母是**理想满分**而不是"当前可用满分"，
    #      所以缺毛利率/现金流的票（C3/S2/S3 不可用）天然拿不到高分 ——
    #      数据不全就不该显得确定。
    #   只有像 WDC 那样「5/5 且反侧 0 分」才配得上 1.00。
    margin = side_score - other_score
    confidence = round(max(0.0, margin) / ideal, 2) if ideal else 0.0

    note = (f"{regime.display_name}：{side_score}/{side_max} 分"
            f"（周期 {cyc_score} vs 成长 {str_score}，净优势 {margin}）")
    if inp.latest_net_profit is not None and inp.latest_net_profit <= 0:
        note += "；❗最近一期净利 ≤ 0，PE 不适用"

    return ClassificationResult(
        code=inp.code,
        regime=regime,
        confidence=confidence,
        evidence=evidence,
        counter_evidence=counter,
        missing_fields=missing,
        periods=periods,
        cyc_score=cyc_score,
        str_score=str_score,
        sample_sufficiency=_sufficiency(periods),
        excluded=dict(inp.excluded or {}),
        note=note,
    )
