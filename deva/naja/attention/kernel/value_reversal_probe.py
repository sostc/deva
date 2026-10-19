"""价值与反转探测：价格相对「企业真实价值」的位置、日线结构、新闻语气、一致预期。

================================================================================
这个模块回答四个问题（全部**只读**，不下单、不改判定）
================================================================================

1. **便宜吗** —— 现价在不在「价值带」里。
   股票：格雷厄姆防守价 ``√(22.5·EPS·BVPS)`` 与 ``BVPS×ROE×合理PE`` 组成的区间；
   ETF：现价对净值的溢价/折价（ETF 没有「企业价值」这回事，必须换口径）。
2. **跌到哪了** —— 日线结构：60 日高点回撤、MA20/MA60 偏离、RSI14、量能萎缩比。
3. **新闻会不会反转** —— 按标的别名筛出相关新闻，用**词表**给极性打分；
   同时看负面密度是升是降（利空钝化 / 利空发酵）。
4. **一致预期是否极端** —— 「无极生太极」：都看空时才有向上反转的土壤，
   都看多时才有向下的风险。**极端一致 ≠ 立即反转**，必须再看到边际改善
   （RSI 回升 / 缩量 / 负面密度下降 / 广度回升 / 收复 MA20）才成立 2 条以上。

================================================================================
三条硬约束（本项目血泪）
================================================================================

* **`None` ≠ `0`**：每个维度拿不到就返回 ``None`` 并写明缺哪维，绝不用
  「0.5 中性」「0 分安全」冒充读数。新闻情绪那一列尤其 —— 新闻池里的
  ``sentiment`` 字段 95% 是默认值 0.5（实测 319 条里 304 条），
  **不能直接拿来求均值**，否则永远显示「中性」，等于死面板。
  本模块自己做词表打分，并如实给出「N 条相关、M 条有极性」。
* **极端 ≠ 买点**：``reversal_watch=True`` 只是「值得盯」，不是「可以买」。
  真执行仍要过守望层与 Manas 闸门（机会≠放行）。
* **口径要说清**：估值锚是 PE/PB 模型，不是 DCF；不含增长调整，
  对高增长股会显得偏贵。这一点写在结果的 ``caveats`` 里，不藏在注释里。

回滚：本模块只被觉醒页调用，出问题直接删调用点即可，不影响决策链。
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- 常量（可调）

#: 格雷厄姆数：``√(22.5 × EPS × BVPS)``，22.5 = 15 倍 PE × 1.5 倍 PB
GRAHAM_MULTIPLE = 22.5
#: 「合理 PB = ROE × 合理 PE」里的合理 PE。15 倍 ≈ 6.7% 盈利收益率
FAIR_PE = 15.0
#: ETF 溢折价 ±2% 内视为平价（申赎套利成本）
ETF_NAV_EDGE = 0.02
#: RSI 周期
RSI_PERIOD = 14
#: 新闻样本下限：少于这个数不给语气结论
MIN_NEWS = 3
#: 词表法里「有极性」的门槛
POLARITY_EPS = 0.15
#: 极端悲观 / 乐观的界线（0~100）
EXTREME_HIGH = 65.0
EXTREME_LOW = 35.0
#: 「一致到极致」的拥挤度门槛
CROWDING_EXTREME = 60.0
#: 缓存时长（秒）。页面可能被反复刷新，别每次都打 OpenD。
CACHE_TTL = 300.0

#: 新闻池（与 /news 页面同源）
NEWS_CACHE_PATH = os.path.expanduser("~/.naja/focused_news_cache.json")
#: 关注配置
INTENTS_PATH = os.path.expanduser("~/.naja/intents.json")
ALLOCATIONS_PATH = os.path.expanduser("~/.naja/allocations.json")

FUTU_HOST = "127.0.0.1"
FUTU_PORT = 11111


# ---------------------------------------------------------------- 词表（极性）

#: 负面向（权重越大越负面）。刻意只收「对公司/对市场基本面有实义」的词，
#: 「下跌」「调整」这类纯行情词不收 —— 否则新闻语气会和价格重复计数。
NEG_WORDS: Dict[str, float] = {
    "下调评级": 1.0, "下调目标价": 1.0, "减持": 0.9, "看空": 0.9, "做空": 0.8,
    "不及预期": 0.9, "低于预期": 0.9, "逊于预期": 0.9, "暴雷": 1.0, "爆雷": 1.0,
    "亏损": 0.8, "净亏损": 0.9, "下调指引": 0.9, "裁员": 0.8, "停产": 0.8,
    "调查": 0.8, "诉讼": 0.7, "罚款": 0.7, "退市": 1.0, "违约": 0.9,
    "召回": 0.7, "制裁": 0.9, "禁售": 0.9, "出口管制": 0.8, "反垄断": 0.6,
    "延期": 0.5, "取消订单": 0.8, "砍单": 0.9, "降价": 0.5, "库存积压": 0.7,
    "miss": 0.8, "downgrade": 0.9, "cut": 0.6, "lawsuit": 0.7, "probe": 0.6,
    "layoff": 0.8, "recall": 0.7, "sanction": 0.9, "delay": 0.5, "plunge": 0.8,
}

#: 正面向
POS_WORDS: Dict[str, float] = {
    "上调评级": 1.0, "上调目标价": 1.0, "增持": 0.9, "回购": 0.9, "超预期": 1.0,
    "好于预期": 0.9, "扭亏": 0.9, "中标": 0.8, "获批": 0.8, "量产": 0.7,
    "涨价": 0.6, "提价": 0.6, "分红": 0.6, "派息": 0.5, "订单": 0.5,
    "合作": 0.4, "降息": 0.7, "放松管制": 0.8, "补贴": 0.6, "减税": 0.6,
    "beat": 0.9, "upgrade": 0.9, "buyback": 0.9, "record high": 0.6,
    "approval": 0.7, "partnership": 0.4, "raise": 0.5,
}

#: 否定词：命中后把同句极性翻号（「不及预期」已在词表里，这里的
#: "not / 未 / 不再" 只处理纯否定句式）
NEGATORS = ("不", "未", "没有", "无", "not ", "no ")


def score_text(text: str) -> float:
    """给一条新闻打极性分，返回 ``[-1, 1]``。0 表示「看不出极性」。

    ❗返回 0 与返回 0.5 是两件事：0 是「这条新闻没有方向」，
    0.5 在情绪坐标里是「中性」。本模块用 [-1,1]，0 就是无信号，
    统计时只数有极性的条目（见 :func:`news_tone`）。
    """
    if not text:
        return 0.0
    low = str(text).casefold()
    score = 0.0
    for word, weight in NEG_WORDS.items():
        if word.casefold() in low:
            score -= weight
    for word, weight in POS_WORDS.items():
        if word.casefold() in low:
            score += weight
    if score == 0.0:
        return 0.0
    return max(-1.0, min(1.0, score / 2.0))


# ---------------------------------------------------------------- 价值


def _f(value: Any) -> Optional[float]:
    """任何东西 → float；``nan`` / 空串 / None / "nan" 一律 ``None``。

    ❗富途 ETF 行的 PE/PB 是 ``nan`` 不是 0。把它当 0 会得出
    「PE=0，极度低估」这种荒唐结论 —— 这是本项目最典型的一类静默失效。
    """
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


@dataclass
class Valuation:
    """一个标的的「价值带」位置。"""

    kind: str                     # "stock" / "etf" / "unknown"
    price: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    eps_ttm: Optional[float] = None
    bvps: Optional[float] = None
    roe: Optional[float] = None
    dividend_yield: Optional[float] = None
    graham: Optional[float] = None
    graham_ratio: Optional[float] = None     # 现价 / 格雷厄姆防守价（>1 = 高于防守价）
    pb_fair: Optional[float] = None          # ROE × 合理PE
    pb_ratio_vs_fair: Optional[float] = None  # 实际PB / 合理PB
    fair_low: Optional[float] = None
    fair_high: Optional[float] = None
    fair_mid: Optional[float] = None
    premium_pct: Optional[float] = None     # 按**最宽容**那把尺子算的溢价（正=贵）
    premium_pct_harsh: Optional[float] = None  # 按最严格那把尺子算的溢价
    level: str = "unknown"                  # cheap / fair / rich / unknown
    nav: Optional[float] = None
    nav_premium_pct: Optional[float] = None
    pos_52w: Optional[float] = None         # 0=52周低点，1=52周高点
    missing: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.level != "unknown"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "kind": self.kind,
            "price": self.price,
            "pe_ttm": self.pe_ttm,
            "pb": self.pb,
            "eps_ttm": self.eps_ttm,
            "bvps": self.bvps,
            "roe": self.roe,
            "dividend_yield": self.dividend_yield,
            "graham": self.graham,
            "graham_ratio": self.graham_ratio,
            "pb_fair": self.pb_fair,
            "pb_ratio_vs_fair": self.pb_ratio_vs_fair,
            "fair_low": self.fair_low,
            "fair_high": self.fair_high,
            "fair_mid": self.fair_mid,
            "premium_pct": self.premium_pct,
            "premium_pct_harsh": self.premium_pct_harsh,
            "level": self.level,
            "nav": self.nav,
            "nav_premium_pct": self.nav_premium_pct,
            "pos_52w": self.pos_52w,
            "missing": list(self.missing),
            "notes": list(self.notes),
            "available": self.available,
        }
        return d


def compute_valuation(
    price: Optional[float],
    pe_ttm: Optional[float] = None,
    pb: Optional[float] = None,
    bvps: Optional[float] = None,
    roe: Optional[float] = None,
    dividend_yield: Optional[float] = None,
    nav: Optional[float] = None,
    high_52w: Optional[float] = None,
    low_52w: Optional[float] = None,
) -> Valuation:
    """算价值带。纯函数，方便守卫构造用例。

    股票口径（需要 ``pe_ttm`` 与 ``bvps`` 至少各一个）::

        EPS(TTM)  = price / pe_ttm
        graham    = sqrt(22.5 × EPS × BVPS)      # 防守下限
        fair_high = BVPS × ROE × FAIR_PE         # 按 ROE 付合理价钱
        中枢      = sqrt(graham × fair_high)     # 几何中枢（对极端值不敏感）

    ETF 口径：只有净值，没有「企业价值」，只算溢折价。

    Returns:
        Valuation；拿不到关键项时 ``level="unknown"`` 并列出 ``missing``。
    """
    v = Valuation(kind="unknown", price=price)

    price = _f(price)
    pe_ttm = _f(pe_ttm)
    pb = _f(pb)
    bvps = _f(bvps)
    roe = _f(roe)
    nav = _f(nav)

    v.price = price
    v.pe_ttm = pe_ttm if (pe_ttm or 0) > 0 else None
    v.pb = pb if (pb or 0) > 0 else None
    v.bvps = bvps if (bvps or 0) > 0 else None
    v.roe = roe if roe is not None else None
    v.dividend_yield = _f(dividend_yield)
    v.nav = nav if (nav or 0) > 0 else None

    hi, lo = _f(high_52w), _f(low_52w)
    if price and hi and lo and hi > lo:
        v.pos_52w = max(0.0, min(1.0, (price - lo) / (hi - lo)))

    if price is None or price <= 0:
        v.missing.append("现价")
        return v

    # ---- ETF：只有净值口径可用 ----
    if v.nav is not None:
        v.kind = "etf"
        v.nav_premium_pct = price / v.nav - 1.0
        if abs(v.nav_premium_pct) <= ETF_NAV_EDGE:
            v.level = "fair"
        elif v.nav_premium_pct < 0:
            v.level = "cheap"
        else:
            v.level = "rich"
        v.notes.append("ETF 没有「企业价值」，只看对净值(NAV)的溢折价")
        # ❗溢折价超过 3% 在正常 ETF 上几乎不可能持续，多半是 NAV 滞后一日
        #   （实测 QQQ 现价 709.8 / NAV 744.5）。这种时候**只能提示核对**，
        #   不能把它当成「便宜 4.7%」—— 假的新鲜比异常更毒。
        if abs(v.nav_premium_pct) > 0.03:
            v.notes.append("溢折价超过 3%，大概率是 NAV 滞后，须核对当日净值再采信")
        return v

    # ---- 股票：两把尺子 ----
    if v.pe_ttm is None or v.bvps is None:
        if v.pe_ttm is None:
            v.missing.append("PE(TTM)")
        if v.bvps is None:
            v.missing.append("每股净资产")
        v.notes.append("缺 PE 或每股净资产，无法构建价值带（不是「便宜」）")
        return v

    v.kind = "stock"
    eps_ttm = price / v.pe_ttm
    v.eps_ttm = eps_ttm

    graham = math.sqrt(GRAHAM_MULTIPLE * max(eps_ttm, 0.0) * v.bvps)
    v.graham = graham if graham > 0 else None

    fair_high = None
    if v.roe is not None and v.roe > 0:
        fair_high = v.bvps * v.roe * FAIR_PE
    elif v.pb is not None and v.roe is None:
        # 没有 net_profit/net_asset 时退一步：ROE ≈ PB / PE
        implied = v.pb / v.pe_ttm if v.pe_ttm else None
        if implied and implied > 0:
            fair_high = v.bvps * implied * FAIR_PE
            v.notes.append("ROE 缺原始字段，用 PB/PE 反推")
    v.fair_high = fair_high

    if v.graham is None and fair_high is None:
        v.missing.append("价值带（EPS×BVPS 或 ROE 均不可用）")
        return v

    # ---- 判定：两把尺子，宁可不说便宜 ----
    # ❗不用「价值中枢 ±15%」这种合成价：把格雷厄姆数（防守价）与
    #   ROE 合理价做几何平均，会造出一个既不防守也不成长的价格，
    #   还会给出「高估 289%」这种看着很精确、其实不可信的结论。
    #   改为各算各的倍数，判定规则：
    #     cheap  = 所有可用尺子都说便宜（≤0.90）
    #     rich   = 任一尺子说贵（≥1.50）
    #     fair   = 其余
    ratios: List[float] = []
    if v.graham and v.graham > 0:
        v.graham_ratio = price / v.graham
        ratios.append(v.graham_ratio)
    if fair_high and fair_high > 0:
        v.fair_high = fair_high
        v.pb_fair = (fair_high / v.bvps) if v.bvps else None
        if v.pb and v.pb_fair and v.pb_fair > 0:
            v.pb_ratio_vs_fair = v.pb / v.pb_fair
            ratios.append(v.pb_ratio_vs_fair)

    if v.graham:
        v.fair_low = v.graham
    if v.fair_high:
        v.fair_mid = v.fair_high

    if ratios:
        v.premium_pct = (min(ratios) - 1.0) * 100.0
        v.premium_pct_harsh = (max(ratios) - 1.0) * 100.0
        if all(r <= 0.90 for r in ratios):
            v.level = "cheap"
        elif any(r >= 1.50 for r in ratios):
            v.level = "rich"
        else:
            v.level = "fair"
    else:
        v.missing.append("估值倍数（缺股价/防守价/合理PB 之一）")

    if v.graham is None:
        v.notes.append("EPS 为负或为 0，算不出格雷厄姆防守价")
    if fair_high is None:
        v.notes.append("缺 ROE，只有格雷厄姆一把尺子")
    v.notes.append("尺子：格雷厄姆 现价÷√(22.5·EPS·BVPS)；ROE 尺 实际PB÷(ROE×15)")
    v.notes.append("不含增长调整 —— 高增长股会被判偏贵，这是口径局限不是结论")
    return v


# ---------------------------------------------------------------- 日线结构


def _sma(values: Sequence[float], n: int) -> Optional[float]:
    if len(values) < n or n <= 0:
        return None
    window = values[-n:]
    return sum(window) / n


def compute_rsi(closes: Sequence[float], period: int = RSI_PERIOD) -> Optional[float]:
    """简单 RSI（等权平均涨跌幅，非 Wilder 平滑）。

    ❗口径必须写死并测：两种 RSI 在震荡市里能差 10 点以上，
    换实现不换注释会让页面读数悄悄变味。
    """
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    window = closes[-(period + 1):]
    for prev, cur in zip(window[:-1], window[1:]):
        diff = cur - prev
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def compute_position(
    closes: Sequence[float],
    volumes: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """日线结构：回撤、均线偏离、RSI、量能。返回的每个字段都可能为 None。"""
    out: Dict[str, Any] = {
        "bars": len(closes) if closes else 0,
        "close": None,
        "high60": None,
        "drawdown60": None,
        "ma20": None,
        "ma60": None,
        "dev20": None,
        "dev60": None,
        "rsi14": None,
        "rsi14_prev": None,
        "vol_ratio": None,
        "down_days": None,
        "level": "unknown",
        "pos_52w_by_bar": None,
    }
    if not closes or len(closes) < 5:
        return out

    closes = [float(c) for c in closes if c is not None]
    if not closes:
        return out

    close = closes[-1]
    out["close"] = close

    window = closes[-60:] if len(closes) >= 60 else closes
    high60 = max(window)
    out["high60"] = high60
    out["drawdown60"] = close / high60 - 1.0 if high60 else None
    out["pos_52w_by_bar"] = (
        (close - min(window)) / (high60 - min(window)) if high60 > min(window) else None
    )

    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)
    out["ma20"], out["ma60"] = ma20, ma60
    out["dev20"] = close / ma20 - 1.0 if ma20 else None
    out["dev60"] = close / ma60 - 1.0 if ma60 else None

    out["rsi14"] = compute_rsi(closes, RSI_PERIOD)
    out["rsi14_prev"] = compute_rsi(closes[:-1], RSI_PERIOD) if len(closes) > RSI_PERIOD + 1 else None

    if volumes and len(volumes) >= 20:
        v = [float(x) for x in volumes if x is not None]
        if len(v) >= 20:
            v5, v20 = _sma(v, 5), _sma(v, 20)
            out["vol_ratio"] = (v5 / v20) if (v5 and v20) else None

    down = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] < closes[i - 1]:
            down += 1
        else:
            break
    out["down_days"] = down

    dd = out["drawdown60"]
    if dd is None:
        out["level"] = "unknown"
    elif dd <= -0.20:
        out["level"] = "deep"
    elif dd <= -0.10:
        out["level"] = "mid"
    elif dd <= -0.03:
        out["level"] = "mild"
    else:
        out["level"] = "near_high"
    return out


# ---------------------------------------------------------------- 新闻语气


def _load_news_items(path: str = NEWS_CACHE_PATH) -> Tuple[List[Dict[str, Any]], Optional[float]]:
    """读新闻池。返回 ``(items, updated_at)``；读不到返回 ``([], None)``。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        log.debug("value_reversal: 新闻池不可读: %s", exc)
        return [], None
    if isinstance(raw, dict):
        items = raw.get("news") or []
        updated = _f(raw.get("updated_at"))
    elif isinstance(raw, list):
        items, updated = raw, None
    else:
        return [], None
    if not isinstance(items, list):
        return [], None
    return [i for i in items if isinstance(i, dict)], updated


def _match_news(item: Dict[str, Any], aliases: Sequence[str]) -> bool:
    blob = f"{item.get('title') or ''} {item.get('text') or ''} {item.get('summary') or ''}".casefold()
    codes = item.get("stock_codes") or []
    for alias in aliases:
        a = str(alias).strip().casefold()
        if not a:
            continue
        if a in blob:
            return True
        if any(a == str(c).strip().casefold() for c in codes):
            return True
    return False


def news_tone(
    items: Sequence[Dict[str, Any]],
    aliases: Sequence[str],
    now: Optional[float] = None,
    window_hours: float = 72.0,
) -> Dict[str, Any]:
    """按标的筛新闻并给语气分。

    Returns:
        dict，其中 ``tone`` ∈ {"negative","positive","split","no_signal"}；
        ``sample_ok=False`` 时**不给结论**（``tone="no_signal"``），
        因为 1 条新闻的「偏空」和 0 条一样没有统计意义。

    ``neg_trend``：窗口前半段 vs 后半段的负面密度差（<0 表示利空在钝化）。
    """
    now = now or time.time()
    cutoff = now - window_hours * 3600.0
    half = now - window_hours * 3600.0 / 2.0

    matched: List[Tuple[float, float, str]] = []
    for item in items:
        ts = _f(item.get("timestamp"))
        if ts is not None and ts < cutoff:
            continue
        if not _match_news(item, aliases):
            continue
        text = f"{item.get('title') or ''} {item.get('text') or ''}"
        matched.append((ts or 0.0, score_text(text), text[:60]))

    n = len(matched)
    scored = [(ts, s) for ts, s, _ in matched if abs(s) >= POLARITY_EPS]
    neg = sum(1 for _, s in scored if s <= -POLARITY_EPS)
    pos = sum(1 for _, s in scored if s >= POLARITY_EPS)

    out: Dict[str, Any] = {
        "n": n,
        "scored": len(scored),
        "neg": neg,
        "pos": pos,
        "neg_ratio": (neg / len(scored)) if scored else None,
        "pos_ratio": (pos / len(scored)) if scored else None,
        "mean": (sum(s for _, s in scored) / len(scored)) if scored else None,
        "one_sided": None,
        "tone": "no_signal",
        "neg_trend": None,
        "sample_ok": len(scored) >= MIN_NEWS,
        "window_hours": window_hours,
        "headlines": [t for _, _, t in sorted(matched, key=lambda x: x[0], reverse=True)[:3]],
    }

    if scored:
        out["one_sided"] = abs(pos - neg) / len(scored)

    first = [s for ts, s in scored if ts < half]
    second = [s for ts, s in scored if ts >= half]
    if first and second:
        f_neg = sum(1 for s in first if s <= -POLARITY_EPS) / len(first)
        s_neg = sum(1 for s in second if s <= -POLARITY_EPS) / len(second)
        out["neg_trend"] = s_neg - f_neg

    if not out["sample_ok"]:
        return out

    mean = out["mean"] or 0.0
    if mean <= -0.20:
        out["tone"] = "negative"
    elif mean >= 0.20:
        out["tone"] = "positive"
    else:
        out["tone"] = "split"
    return out


# ---------------------------------------------------------------- 一致预期


def evaluate_consensus(
    valuation: Optional[Dict[str, Any]] = None,
    position: Optional[Dict[str, Any]] = None,
    news: Optional[Dict[str, Any]] = None,
    panic: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """「无极生太极」：把各维折算成**悲观度 0~100**，再看一致到什么程度。

    悲观度的四维（按可用性重归一）：

    ==============  ======  ==============================================
    维度            权重    取值
    ==============  ======  ==============================================
    52 周位置       0.30    ``(1 - pos_52w) × 100``
    60 日回撤       0.25    ``min(1, -回撤/25%) × 100``
    新闻负面密度    0.25    ``neg_ratio × 100``（需 sample_ok）
    市场恐慌        0.20    ``panic_score``
    ==============  ======  ==============================================

    ``crowding = |悲观度 - 50| × 2``：0 = 多空分歧，100 = 一边倒。

    ❗**必须区分「极端」与「反转」**：极端只说明「向反方向走的赔率变好」，
    不等于已经反转。``triggers`` 里的边际改善才是触发器，命中 <2 条时
    ``watch`` 保持 False，文案只能说「极端但未见转机」。
    """
    dims: List[Tuple[str, float]] = []

    pos52 = _f((valuation or {}).get("pos_52w"))
    if pos52 is not None:
        dims.append(("52周位置", (1.0 - pos52) * 100.0 * 0.30))

    dd = _f((position or {}).get("drawdown60"))
    if dd is not None:
        dims.append(("60日回撤", min(1.0, max(0.0, -dd) / 0.25) * 100.0 * 0.25))

    if (news or {}).get("sample_ok") and (news or {}).get("neg_ratio") is not None:
        dims.append(("新闻负面密度", float(news["neg_ratio"]) * 100.0 * 0.25))

    panic_score = _f((panic or {}).get("panic_score"))
    if panic_score is not None:
        dims.append(("市场恐慌", min(100.0, max(0.0, panic_score)) * 0.20))

    weight_sum = sum({"52周位置": 0.30, "60日回撤": 0.25, "新闻负面密度": 0.25, "市场恐慌": 0.20}[k] for k, _ in dims)
    out: Dict[str, Any] = {
        "pessimism": None,
        "crowding": None,
        "side": "unknown",
        "watch": False,
        "direction": 0,
        "triggers": [],
        "triggers_hit": 0,
        "triggers_total": 0,
        "trigger_side": "",
        "opportunity": False,
        "dimensions_used": [k for k, _ in dims],
        "dimensions_missing": [
            k for k in ("52周位置", "60日回撤", "新闻负面密度", "市场恐慌")
            if k not in [d for d, _ in dims]
        ],
        "label": "未采集",
    }

    if not dims or weight_sum <= 0:
        return out

    pessimism = sum(v for _, v in dims) / weight_sum
    out["pessimism"] = pessimism
    crowding = min(100.0, abs(pessimism - 50.0) * 2.0)
    out["crowding"] = crowding

    if pessimism >= EXTREME_HIGH:
        out["side"] = "pessimistic"
    elif pessimism <= EXTREME_LOW:
        out["side"] = "optimistic"
    else:
        out["side"] = "split"

    # ---- 触发器：悲观侧看「边际改善」，乐观侧看「边际恶化」 ----
    # ❗两个方向的触发器必须成对存在。只写「改善」会得出「极端乐观永远不可验证」
    #   —— 于是阳极生阴只是个标签，永远等不到确认。
    p = position or {}
    n = news or {}
    triggers: List[Tuple[str, bool]] = []
    optimistic = out["side"] == "optimistic"

    rsi, rsi_prev = _f(p.get("rsi14")), _f(p.get("rsi14_prev"))
    vol_ratio = _f(p.get("vol_ratio"))
    close, ma20 = _f(p.get("close")), _f(p.get("ma20"))
    delta_b = _f((panic or {}).get("delta_breadth"))
    neg_trend = _f(n.get("neg_trend"))

    if rsi is not None and rsi_prev is not None:
        if optimistic:
            triggers.append(("RSI 走弱", rsi < rsi_prev))
        else:
            triggers.append(("RSI 回升", rsi > rsi_prev))
    if vol_ratio is not None:
        if optimistic:
            triggers.append(("放量滞涨", vol_ratio > 1.10))
        else:
            triggers.append(("量能萎缩(抛压衰减)", vol_ratio < 0.85))
    if neg_trend is not None:
        if optimistic:
            triggers.append(("利空密度上升", neg_trend > 0))
        else:
            triggers.append(("利空密度下降", neg_trend < 0))
    if delta_b is not None:
        if optimistic:
            triggers.append(("市场广度恶化", delta_b < 0))
        else:
            triggers.append(("市场广度回升", delta_b > 0))
    if close is not None and ma20:
        if optimistic:
            triggers.append(("跌破 MA20", close < ma20))
        else:
            triggers.append(("站上 MA20", close > ma20))

    out["triggers"] = [{"name": name, "hit": hit} for name, hit in triggers]
    out["triggers_total"] = len(triggers)
    out["triggers_hit"] = sum(1 for _, hit in triggers if hit)
    out["trigger_side"] = "deterioration" if optimistic else "improvement"

    # 机会永远是 False：这是只读判断，真执行要过守望层（机会≠放行）
    out["opportunity"] = False

    if out["side"] == "pessimistic" and crowding >= CROWDING_EXTREME:
        out["direction"] = 1
        out["label"] = "极端悲观·阴极生阳观察"
    elif out["side"] == "optimistic" and crowding >= CROWDING_EXTREME:
        out["direction"] = -1
        out["label"] = "极端乐观·阳极生阴风险"
    elif out["side"] == "split":
        out["label"] = "多空分歧·无一致预期"
    elif out["side"] == "pessimistic":
        # ❗「悲观度高」和「一致度高」是两件事：P=79 已经是极端悲观水平，
        #   只是拥挤度还差一点（分歧仍在）。旧文案写「未到极端」把两件事混成一件。
        out["label"] = "极端悲观·但分歧仍大"
    else:
        out["label"] = "极端乐观·但分歧仍大"

    # 「极端 + 至少 2 条同向证据」才算值得盯；极端本身只是赔率
    out["watch"] = bool(out["direction"] != 0 and out["triggers_hit"] >= 2)
    if out["direction"] != 0 and not out["watch"]:
        out["label"] += "（未见转机）"
    return out


# ---------------------------------------------------------------- 取数


def _watch_targets() -> List[Dict[str, str]]:
    """从意向库 + 长期配置里取关注标的（去重，意向优先）。"""
    seen: Dict[str, Dict[str, str]] = {}

    def _add(code: Any, market: Any, name: Any, source: str) -> None:
        code_s = str(code or "").strip()
        if not code_s:
            return
        key = code_s.upper()
        if key in seen:
            return
        seen[key] = {
            "code": code_s,
            "market": str(market or "").strip().upper(),
            "name": str(name or "").strip() or code_s,
            "source": source,
        }

    for path, source in ((INTENTS_PATH, "意向"), (ALLOCATIONS_PATH, "长期配置")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rows = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                _add(row.get("code"), row.get("market"), row.get("name"), source)
    return list(seen.values())


def _news_aliases(target: Dict[str, str]) -> List[str]:
    """标的 → 新闻匹配别名。代码 + 名称 + 少量人工补充。"""
    extra = {
        "NVDA": ["英伟达", "NVIDIA", "nvidia"],
        "00700": ["腾讯", "Tencent"],
        "0700": ["腾讯", "Tencent"],
        "588200": ["芯片", "半导体", "科创"],
        "QQQ": ["纳指", "纳斯达克", "Nasdaq", "QQQ"],
    }
    code = str(target.get("code") or "")
    aliases = {code, str(target.get("name") or "")}
    # 港股代码去前导零再补一份（缓存里两种写法都有）
    if code.isdigit():
        aliases.add(code.lstrip("0"))
        aliases.add(code.lstrip("0").zfill(5))
    aliases.update(extra.get(code.upper(), []))
    return [a for a in aliases if a and len(str(a)) >= 2]


def _fetch_from_futu(futu_codes: Sequence[str], lookback_days: int = 200) -> Dict[str, Dict[str, Any]]:
    """一次连接取快照 + 日线。返回 ``{futu_code: {...}}``，失败写 ``error``。"""
    out: Dict[str, Dict[str, Any]] = {}
    try:
        from futu import KLType, OpenQuoteContext, RET_OK
    except Exception as exc:  # pragma: no cover - futu 未安装
        return {c: {"error": f"futu 不可导入: {exc}"} for c in futu_codes}

    try:
        ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    except Exception as exc:
        return {c: {"error": f"连不上 OpenD: {exc}"} for c in futu_codes}

    try:
        ret, snap = ctx.get_market_snapshot(list(futu_codes))
        if ret != RET_OK or snap is None:
            msg = f"get_market_snapshot 失败: {str(snap)[:120]}"
            for c in futu_codes:
                out.setdefault(c, {})["error"] = msg
        else:
            for _, row in snap.iterrows():
                out.setdefault(str(row.get("code", "")), {})["snapshot"] = row

        end = datetime.now()
        start = end - timedelta(days=lookback_days)
        for code in futu_codes:
            try:
                res = ctx.request_history_kline(
                    code,
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    ktype=KLType.K_DAY,
                    max_count=300,
                )
                # ❗不同 futu-api 版本返回 2 元 / 3 元组，别写死解包（写了就 ValueError）
                ret_k, kd = res[0], res[1]
            except Exception as exc:
                out.setdefault(code, {})["kline_error"] = f"{type(exc).__name__}: {exc}"
                continue
            if ret_k != RET_OK or kd is None or len(kd) == 0:
                out.setdefault(code, {})["kline_error"] = f"K线获取失败: {str(kd)[:100]}"
                continue
            try:
                out.setdefault(code, {})["closes"] = [float(x) for x in kd["close"].tolist()]
                out.setdefault(code, {})["volumes"] = [float(x) for x in kd["volume"].tolist()]
                out.setdefault(code, {})["last_kline"] = str(kd.iloc[-1].get("time_key", ""))
            except Exception as exc:
                out.setdefault(code, {})["kline_error"] = f"K线解析失败: {exc}"
    finally:
        try:
            ctx.close()
        except Exception:
            pass
    return out


def _row_from_snapshot(row: Any, target: Dict[str, str], kline: Dict[str, Any], news_items: Sequence[Dict[str, Any]], panic: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把快照行 + 日线 + 新闻拼成一行结果。"""
    price = _f(row.get("last_price"))
    pe_ttm = _f(row.get("pe_ttm_ratio")) or _f(row.get("pe_ratio"))
    pb = _f(row.get("pb_ratio"))
    bvps = _f(row.get("net_asset_per_share"))
    net_asset = _f(row.get("net_asset"))
    net_profit = _f(row.get("net_profit"))
    roe = (net_profit / net_asset) if (net_profit and net_asset and net_asset > 0) else None

    valuation = compute_valuation(
        price=price,
        pe_ttm=pe_ttm,
        pb=pb,
        bvps=bvps,
        roe=roe,
        dividend_yield=_f(row.get("dividend_ratio_ttm")),
        nav=_f(row.get("trust_netAssetValue")),
        high_52w=_f(row.get("highest52weeks_price")),
        low_52w=_f(row.get("lowest52weeks_price")),
    )

    position = compute_position(kline.get("closes") or [], kline.get("volumes") or [])
    aliases = _news_aliases(target)
    news = news_tone(news_items, aliases)
    consensus = evaluate_consensus(valuation.to_dict(), position, news, panic)

    return {
        "code": target.get("code"),
        "name": target.get("name"),
        "market": target.get("market"),
        "source": target.get("source"),
        "price": price,
        "as_of": str(row.get("update_time") or ""),
        "kline_last": kline.get("last_kline", ""),
        "kline_error": kline.get("kline_error", ""),
        "valuation": valuation.to_dict(),
        "position": position,
        "news": news,
        "consensus": consensus,
    }


# ---------------------------------------------------------------- 缓存 / 编排

_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}


def probe_watchlist(panic: Optional[Dict[str, Any]] = None, force: bool = False) -> Dict[str, Any]:
    """取所有关注标的的价值/反转评估（带 300s 内存缓存）。

    Args:
        panic: 市场级恐慌样本（``probe_panic().to_dict()``）；没有就少一维。
        force: 忽略缓存。

    Returns:
        ``{"ok": bool, "rows": [...], "reason": str, "as_of": float, "targets": n}``
        取不到数据时 ``ok=False`` + ``reason``，**不返回空 rows 假装「没有机会」**。
    """
    now = time.time()
    if not force and _CACHE["payload"] is not None and now - float(_CACHE["ts"]) < CACHE_TTL:
        return _CACHE["payload"]

    targets = _watch_targets()
    if not targets:
        payload = {"ok": False, "rows": [], "targets": 0, "as_of": now,
                   "reason": "意向库与长期配置里都没有标的"}
        _CACHE.update(ts=now, payload=payload)
        return payload

    try:
        from ...bandit.execution import futu_code
    except Exception as exc:
        payload = {"ok": False, "rows": [], "targets": len(targets), "as_of": now,
                   "reason": f"futu_code 不可导入: {exc}"}
        return payload

    mapping: Dict[str, Dict[str, str]] = {}
    unresolved: List[str] = []
    for t in targets:
        full = futu_code(t.get("market", ""), t.get("code", ""))
        if not full:
            unresolved.append(str(t.get("code")))
            continue
        mapping[full] = t

    fetched = _fetch_from_futu(list(mapping.keys())) if mapping else {}
    news_items, news_updated = _load_news_items()

    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for full, target in mapping.items():
        data = fetched.get(full) or {}
        row = data.get("snapshot")
        if row is None:
            errors.append(f"{target['code']}: {data.get('error') or '快照里没有这个标的'}")
            continue
        rows.append(_row_from_snapshot(row, target, data, news_items, panic))

    payload = {
        "ok": bool(rows),
        "rows": rows,
        "targets": len(targets),
        "as_of": now,
        "news_updated": news_updated,
        "errors": errors + [f"{c}: 换算不出富途代码" for c in unresolved],
        "reason": "" if rows else "全部标的都取不到快照（OpenD 未运行或代码换算失败）",
    }
    _CACHE.update(ts=now, payload=payload)
    return payload


__all__ = [
    "Valuation",
    "compute_valuation",
    "compute_position",
    "compute_rsi",
    "score_text",
    "news_tone",
    "evaluate_consensus",
    "probe_watchlist",
]
