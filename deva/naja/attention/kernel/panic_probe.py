"""超跌机会探测：恐慌分 + 「跌多了是不是买点」评估（**只读，不下单**）。

================================================================================
为什么要有这个模块
================================================================================

项目里本来有一个 `market_hotspot/filters/panic_analyzer.py`（恐慌指数 0~100、
三档分级、甚至能判「恐慌见顶」），但它**只被 `attention/kernel/kernel.py` 调用**，
而那是死代码 —— 生产内核是 `attention/os/os_kernel.py`，两者无继承关系。
所以「恐慌」这一维在生产链路上从来没有存在过。

这里做两件事：

1. `probe_panic()` 把恐慌分真正算出来（接生产 scanner 的实时快照 + 广度）
2. `evaluate_dip()` 判断当前是否构成「超跌买入机会」

================================================================================
顺手修掉 PanicAnalyzer 的一个致命前提
================================================================================

它的权重总和是 1.0：
    price 0.25 / volume 0.25 / spread 0.20 / fear 0.20 / event 0.10

但生产环境拿不到 spread（无盘口）和 event_impact（无事件严重度），
于是实际最高只能到 **70 分** —— 而它的 `panic_threshold` 恰好就是 70。
结果是「永远差一点就触发」，看起来在算、其实永远不触发。

本模块对**可用维度重归一**（见 `PanicAnalyzer._calculate_panic_score` 的改动），
并把「用了哪几维、缺了哪几维」如实写在结果里。

================================================================================
只读约定（重要）
================================================================================

- 不写 NB、不下单、不改 `action_type`
- `opportunity=True` **只是一个标记**，不等于放行（守望系统五纪律第一条：机会≠放行）
- 拿不到数据一律返回 `None` 或 `blockers`，不返回 0 分假装「安全」
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

#: 恐慌分阈值（与 PanicAnalyzerConfig.panic_threshold 对齐）
PANIC_EXTREME = 70.0
#: 判定「在跌」的当日平均跌幅门槛（%）
DROP_AVG_CHANGE = -1.0
#: 首笔仓位上限（占正常仓位的比例）。分批建仓，不许一把梭。
FIRST_TRANCHE_RATIO = 0.3


@dataclass
class PanicSample:
    """一次恐慌探测的结果。

    `None` 与 `0` 的区别是本项目的头号病理，这里显式区分：
    字段为 None = 该维度**没数据**，不是「正常」。
    """

    panic_score: float
    level: str
    avg_change: Optional[float] = None
    breadth_ratio: Optional[float] = None
    delta_breadth: Optional[float] = None
    fear_score: Optional[float] = None
    sample_size: int = 0
    dimensions_used: List[str] = field(default_factory=list)
    dimensions_missing: List[str] = field(default_factory=list)
    fear_source: str = ""
    liquidity_score: Optional[float] = None
    ts: float = 0.0

    @property
    def quality(self) -> float:
        """数据可信度 0~1。

        只用了 1 维 = 0.4；2 维 = 0.6；3 维 = 0.8；4 维以上 = 1.0。
        样本数不足 10 再打七折 —— 三个标的算出来的「普跌」不能当市场。
        """
        base = {0: 0.0, 1: 0.4, 2: 0.6, 3: 0.8}.get(len(self.dimensions_used), 1.0)
        if self.sample_size and self.sample_size < 10:
            base *= 0.7
        return round(base, 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "panic_score": round(self.panic_score, 2),
            "level": self.level,
            "avg_change": None if self.avg_change is None else round(self.avg_change, 3),
            "breadth_ratio": None if self.breadth_ratio is None else round(self.breadth_ratio, 3),
            "delta_breadth": None if self.delta_breadth is None else round(self.delta_breadth, 3),
            "fear_score": None if self.fear_score is None else round(self.fear_score, 2),
            "sample_size": self.sample_size,
            "dimensions_used": list(self.dimensions_used),
            "dimensions_missing": list(self.dimensions_missing),
            "fear_source": self.fear_source,
            "liquidity_score": None if self.liquidity_score is None else round(self.liquidity_score, 3),
            "quality": self.quality,
            "ts": self.ts,
        }


class _FeatureCarrier:
    """PanicAnalyzer.analyze() 只要求对象有 .features，用它做最小载体。"""

    __slots__ = ("features",)

    def __init__(self, features: Dict[str, Any]):
        self.features = features


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _breadth_snapshot(scanner) -> Dict[str, Any]:
    """取最新广度快照。三个接口都试一遍，拿不到返回 {}。"""
    for name in ("get_latest_breadth", "get_breadth_status"):
        fn = getattr(scanner, name, None)
        if fn is None:
            continue
        try:
            data = fn() or {}
            if isinstance(data, dict) and data.get("fear_score") is not None:
                return data
        except Exception:
            continue
    return {}


def _breadth_history(scanner) -> List[Dict[str, Any]]:
    """读广度历史（只读私有字段，拿不到返回 []）。

    ❗没有历史就无法判断「跌势是否收敛」，而「止跌确认」正是抄底与接飞刀的分界线。
    """
    tracker = getattr(scanner, "_breadth_tracker", None)
    hist = getattr(tracker, "_history", None)
    if not hist:
        return []
    try:
        return list(hist)
    except Exception:
        return []


def probe_panic(scanner, market_state: Optional[Dict[str, Any]] = None) -> Optional[PanicSample]:
    """用实时快照 + 广度数据估一个恐慌分。

    Returns:
        PanicSample；数据不足以判断时返回 None（**不是** 0 分）。
    """
    if scanner is None:
        return None

    last_data = {}
    try:
        last_data = scanner.get_last_data() or {}
    except Exception:
        last_data = {}

    changes: List[float] = []
    for md in last_data.values():
        ch = _safe_float(getattr(md, "change_pct", None))
        if ch is not None:
            changes.append(ch)

    breadth = _breadth_snapshot(scanner)
    fear_score = _safe_float(breadth.get("fear_score"))
    breadth_ratio = _safe_float(breadth.get("breadth_ratio"))
    fear_source = "tracker" if fear_score is not None else ""

    # 既没有行情也没有广度 → 如实说拿不到
    if not changes and fear_score is None:
        return None

    avg_change = (sum(changes) / len(changes)) if changes else None

    # ❗fear 维兜底：scanner 的广度 tracker 在实盘里经常是空的
    #   （`update_from_market_data` 的日志一次都没打出来过），
    #   但涨跌家数就在行情里，就地按 PanicAnalyzer 的**原公式**算即可。
    #   复用它的方法而不是另写一份，避免两套口径。
    if fear_score is None and changes:
        try:
            # 用**同一个** MarketBreadthTracker 把行情折算成广度，
            # 而不是另写一份 fear 公式 —— 两套口径迟早会对不上。
            from ...radar.global_market_scanner import MarketBreadthTracker

            advancing = sum(1 for c in changes if c > 0)
            declining = sum(1 for c in changes if c < 0)
            # ❗它的 `_calculate_fear_indicator` 在「无涨停且无上涨」时直接返回 10
            #   （那是按**个股**分布的假设：总该有涨的）。scanner 追踪的是指数/期货，
            #   普跌时 advancing 天然为 0 → 会被判成「极度恐慌 90 分」，
            #   而「跌 0.9%」和「跌 5%」得到同一个 90，等于这一维失效。
            #   这种情况下宁可不采信，让 fear 记为缺失，由 price 单维承担。
            if advancing == 0 and declining > 0:
                fear_score = None
            else:
                tracker = MarketBreadthTracker()
                result = tracker.update([{"change_pct": c} for c in changes]) or {}
                fear_score = _safe_float(result.get("fear_score"))
                if breadth_ratio is None:
                    breadth_ratio = _safe_float(result.get("breadth_ratio"))
                fear_source = "local"
        except Exception as exc:
            log.debug("panic_probe: 本地广度兜底失败: %s", exc)
            fear_score = None

    history = _breadth_history(scanner)
    delta_breadth = None
    if len(history) >= 2:
        prev = _safe_float((history[-2] or {}).get("breadth_ratio"))
        cur = _safe_float((history[-1] or {}).get("breadth_ratio"))
        if prev is not None and cur is not None:
            delta_breadth = cur - prev

    features: Dict[str, Any] = {}
    used: List[str] = []
    missing: List[str] = []

    # 价格失稳：只认下跌，跌得越深分越高（-5% 封顶）
    if avg_change is not None:
        features["price_destabilization_speed"] = abs(min(avg_change, 0.0))
        used.append("price")
    else:
        features["price_destabilization_speed"] = None
        missing.append("price")

    # 情绪恐慌：breadth 的 fear_score 已是 0~100
    if fear_score is not None:
        features["fear_score"] = fear_score
        used.append("fear")
    else:
        features["fear_score"] = None
        missing.append("fear")

    # 以下三维生产环境拿不到 —— 显式传 None，绝不用「默认值假值」冒充
    features["volume_shrink_ratio"] = None
    features["spread_ratio"] = None
    features["event_impact"] = None
    missing.extend(["volume", "spread", "event"])

    try:
        from ...market_hotspot.filters.panic_analyzer import PanicAnalyzer

        analyzer = PanicAnalyzer()
        result = analyzer.analyze(_FeatureCarrier(features))
        panic_score = float(result.panic_score)
        level = str(result.level)
        liquidity_score = float(result.liquidity_score)
    except Exception as exc:  # 分析器自身不可用时降级成粗算，并留痕
        log.debug("panic_probe: PanicAnalyzer 不可用，降级粗算: %s", exc)
        parts: List[float] = []
        if avg_change is not None:
            parts.append(min(1.0, abs(min(avg_change, 0.0)) / 5.0))
        if fear_score is not None:
            parts.append(min(1.0, fear_score / 100.0))
        panic_score = (sum(parts) / len(parts) * 100.0) if parts else 0.0
        level = "extreme" if panic_score >= 80 else ("high" if panic_score >= 70 else "moderate")
        liquidity_score = None

    return PanicSample(
        panic_score=panic_score,
        level=level,
        avg_change=avg_change,
        breadth_ratio=breadth_ratio,
        delta_breadth=delta_breadth,
        fear_score=fear_score,
        sample_size=len(changes),
        dimensions_used=used,
        dimensions_missing=missing,
        fear_source=fear_source,
        liquidity_score=liquidity_score,
        ts=time.time(),
    )


@dataclass
class DipOpportunity:
    """超跌机会评估结果。`opportunity=False` 时 `blockers` 会说明差在哪。"""

    opportunity: bool
    score: float
    reasons: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    size_hint: float = 0.0
    panic: Optional[Dict[str, Any]] = None
    available: bool = True
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity": self.opportunity,
            "score": round(self.score, 3),
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "size_hint": self.size_hint,
            "panic": self.panic,
            "available": self.available,
            "note": self.note,
        }


def evaluate_dip(
    panic: Optional[PanicSample],
    regime: Optional[float] = None,
    portfolio_loss_pct: Optional[float] = None,
) -> DipOpportunity:
    """判断「现在跌得够多、够恐慌、且止跌了吗」。

    三个条件**必须同时满足**，缺一即不成立：
      1. 在跌        —— 当日均跌 <= -1.0% 或 regime < -0.2
      2. 恐慌极端    —— panic_score >= 70
      3. 止跌迹象    —— 广度环比回升（delta_breadth > 0）

    第 3 条是抄底与「接飞刀」的分界线。拿不到环比就**不给机会**，
    因为「不知道有没有止跌」和「已确认止跌」是两回事。

    这是刻意保守：宁可错过，不可在下跌中继里把首笔仓位打光。
    """
    if panic is None:
        return DipOpportunity(
            opportunity=False,
            score=0.0,
            available=False,
            blockers=["恐慌数据不可用（scanner 无行情也无广度）"],
            note="拿不到数据时不判机会，也不假装安全",
        )

    blockers: List[str] = []
    reasons: List[str] = []

    falling = False
    if panic.avg_change is not None and panic.avg_change <= DROP_AVG_CHANGE:
        falling = True
        # 理由由下面的单维/多维分支统一写，这里不重复同一句话
    elif regime is not None and regime < -0.2:
        falling = True
        reasons.append(f"环境走弱 regime={regime:.2f}")
    if not falling:
        blockers.append(f"没在跌（均跌 {panic.avg_change if panic.avg_change is None else round(panic.avg_change, 2)}%）")

    # 「情绪是否极端」有两条口径：
    #   多维（price+fear）→ 看恐慌分 ≥70；
    #   单维（只有跌幅）→ panic 就是 price_norm×100，按 /5% 封顶，
    #     指数均跌 3.5% 才得 70，等于把门槛设在崩盘日。改为直接看跌幅 ≥3%。
    only_price = len(panic.dimensions_used) <= 1
    if only_price:
        if panic.avg_change is None or panic.avg_change > -3.0:
            blockers.append(
                f"仅跌幅单维，需均跌 ≥3.0%（当前 {panic.avg_change if panic.avg_change is None else round(panic.avg_change, 2)}%）"
            )
        else:
            reasons.append(f"均跌 {panic.avg_change:.2f}%·仅跌幅单维（无情绪/量能确认）")
    elif panic.panic_score >= PANIC_EXTREME:
        reasons.append(f"恐慌 {panic.panic_score:.0f}/100（{panic.level}）")
    else:
        blockers.append(f"恐慌不足（{panic.panic_score:.0f} < {PANIC_EXTREME:.0f}）")

    if panic.delta_breadth is None:
        blockers.append("无广度环比，止跌未确认")
    elif panic.delta_breadth > 0:
        reasons.append(f"广度回升 {panic.delta_breadth:+.3f}")
    else:
        blockers.append(f"广度仍在恶化 {panic.delta_breadth:+.3f}")

    # 单维的收紧已在上面的跌幅分支里做过，这里不再重复判一次。
    ok = not blockers
    score = 0.0
    if ok:
        # 恐慌 0.5 + 跌幅 0.3 + 止跌 0.2
        p = min(1.0, panic.panic_score / 100.0)
        d = min(1.0, abs(panic.avg_change or 0.0) / 5.0)
        s = min(1.0, max(0.0, (panic.delta_breadth or 0.0) / 0.15))
        score = p * 0.5 + d * 0.3 + s * 0.2

    note = "只读标记，不下单；真执行须经守望层（机会≠放行）"
    if portfolio_loss_pct is not None and portfolio_loss_pct < -0.05:
        note += f"；当前持仓已亏 {portfolio_loss_pct * 100:.1f}%，先看风控再谈加仓"

    return DipOpportunity(
        opportunity=ok,
        score=score,
        reasons=reasons,
        blockers=blockers,
        size_hint=FIRST_TRANCHE_RATIO if ok else 0.0,
        panic=panic.to_dict(),
        note=note,
    )
