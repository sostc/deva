"""长期配置意图（Allocation）—— 「我要长期持有它」这一层。

用户原话（2026-10-14）
====================
    「比如希望长期来说持有科创 ETF 腾讯 qqq，这也是一个守望意愿吧，
      如何体现在系统里」

是守望意愿，但**不是和「我想买英伟达」同一种守望**。这个区别必须写在
最前面，否则会把长期持有错装进机会型的框里：

    ============  =========================  =========================
                   机会型（Intent）            状态型（Allocation）
    ============  =========================  =========================
    想表达什么     想买 / 想卖，等个好价钱      想一直持有它
    有没有完成态   有 —— 成交即结束             没有 —— 补到位也不算完
    到期意味着     没等到 → expired             这期看过了 → reviewed
    到期之后       守望消失                     自动挂上下一期
    典型标的       NVDA（还没买、在择时）        588200 / 00700 / QQQ
    ============  =========================  =========================

为什么必须强行区分
==================
守望系统有一条硬纪律：**不准有无限期的守望** —— 一个没有结算点的守望，
和一条已经死掉的线程长得一模一样，都表现为「日志里什么都不再出现」。
而「长期持有」听上去恰恰是无限期的。

循环守望是这两者的和解办法，**不是放宽纪律**：把「永远」切成
**一串有终点的周期**。每一期都有明确终点，所以纪律没破；每一期都留痕，
所以事后能回答「这周它等了什么、问过几次」；整体不结束，所以「长期」
这件事真的被表达了。

它派生什么
==========
一个 Allocation 本身不下单，也不自己判断机会，它派生两类守望：

    establish   当前仓位 < 目标 → 等机会补上去（已由 CoreEstablishWatch 负责）
    review      到回顾周期 → 提醒人复核这笔配置还成不成立（本模块新增）

❗``review`` 为什么是必需的：如果只有 ``establish``，那么一个**仓位已满**
的长期持仓在守望台上就是**完全隐形的** —— 它既不触发、也不留痕，和
「我从来没说过要长期持有它」没有任何区别。这正是本仓库头号病理
（静默失效家族）的标准形态：配置写好了，链路没接。

目标仓位由人拍板
================
``alloc_pct`` **必须**由人给。默认 ``0`` 表示「还没定」，此时守望照挂
（先记录这个意愿），但页面上必须明确写出「目标未设定」，
❗绝不能拿一个默认值假装用户拍过板 —— 那正是幽灵配置的长法。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from .intent import (
    KNOWN_MARKETS,
    clamp_confidence,
)
from .objective import MissingSettlementPoint, Objective
from .registry import WatchRegistry
from .rotation import (
    DEFAULT_ROTATION_PCT,
    RotationIntent,
    opportunities_for as opportunities_of_rotation,
    to_objective as to_objective_of_rotation,
)
from .watch import Watch

__all__ = [
    "HORIZONS",
    "HORIZON_ZH",
    "REVIEW_SECONDS_FOR_HORIZON",
    "DEFAULT_HORIZON",
    "ANCHOR_SOURCE_ZH",
    "Allocation",
    "allocation_id",
    "to_objective",
    "opportunities_for",
    "declare_allocation",
    "allocation_row_of",
    "anchor_if_needed",
    "GAP_WINDOW_SECONDS",
    "derive_gap_objective",
    "derive_watches",
]

#: 锚定来源的中文。
ANCHOR_SOURCE_ZH = {
    "user": "人拍板",
    "holdings": "默认锚定当前持仓",
    "": "未锚定",
}

#: 支持的时间尺度。
HORIZONS = ("long", "swing")

HORIZON_ZH = {"long": "长期", "swing": "波段"}

#: 每个尺度的回顾周期。回头看「这期发生了什么」的频率，
#: 也是守望系统要求的**结算点**—— 长期不等于无限期。
REVIEW_SECONDS_FOR_HORIZON: Dict[str, float] = {
    "long": 7 * 86400.0,   # 长期：一周回头看一次
    "swing": 1 * 86400.0,  # 波段：一天一次
}

DEFAULT_HORIZON = "long"


@dataclass(frozen=True)
class Allocation:
    """一份「长期持有」的意愿。

    与 :class:`~.intent.Intent` 的关系：那个回答「什么时候下手」，
    这个回答「到底想持有什么、持到什么程度」。
    前者有终点、后者没有 —— 所以后者必须自带周期性回顾。

    :param alloc_pct: 目标占**总资产**的百分比。**0 = 还没定**。
        ❗代码不替用户决定动用多少资金（core_holdings 已立过这条规矩）。
    :param horizon: 时间尺度，决定默认回顾周期。
    :param review_seconds: 显式指定回顾周期；不给就按 ``horizon`` 推。
    :param confidence: 意愿强度，交给决策中心当融合输入（**不是放行键**）。
    :param rationale: 为什么想长期拿着。
    """

    code: str
    market: str
    name: str = ""
    alloc_pct: float = 0.0
    horizon: str = DEFAULT_HORIZON
    review_seconds: Optional[float] = None
    confidence: Optional[float] = None
    rationale: str = ""
    note: str = ""
    #: ★锚定的**份额**目标。与 ``alloc_pct`` 二选一：
    #:     * ``alloc_pct`` —— 人拍板「占总资产百分之多少」（慢变量）
    #:     * ``anchor_shares`` —— 「就持有这么多份」（可以是人给的，
    #:       也可以是**没设定时默认锚定当前持仓**得来的，见 :func:`anchor_if_needed`）
    anchor_shares: Optional[float] = None
    #: 锚定发生在什么时候。❗必须留痕 —— 「目标是多少」和「什么时候定的」
    #: 在复盘时是两件事：做 T 卖飞之后回看，得知道目标是当初哪天锁的。
    anchor_at: Optional[float] = None
    #: 锚定来源：``"user"`` 人拍板 / ``"holdings"`` 默认锚定当前持仓 / ``""`` 没锚。
    anchor_source: str = ""
    anchor_note: str = ""
    extra_opportunities: Tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        code = str(self.code or "").strip()
        if not code:
            raise ValueError("Allocation.code 不能为空")
        object.__setattr__(self, "code", code.upper())

        market = str(self.market or "").strip().upper()
        if market not in KNOWN_MARKETS:
            raise ValueError(
                f"{code} 的市场 {market!r} 认不出来；只能是 {KNOWN_MARKETS} 之一。"
                "猜错市场会让「每手多少、什么时候收盘」整套参数跟着错，"
                "所以这里不兜底"
            )
        object.__setattr__(self, "market", market)

        horizon = str(self.horizon or DEFAULT_HORIZON).strip().lower()
        if horizon not in HORIZONS:
            raise ValueError(f"不支持的时间尺度 {horizon!r}；只有 {HORIZONS}")
        object.__setattr__(self, "horizon", horizon)

        try:
            pct = float(self.alloc_pct)
        except (TypeError, ValueError):
            pct = 0.0
        if pct < 0:
            raise ValueError(f"意向 {code} 的目标占比不能为负，收到 {self.alloc_pct}")
        object.__setattr__(self, "alloc_pct", pct)

        shares = self.anchor_shares
        if shares is not None:
            try:
                shares = float(shares)
            except (TypeError, ValueError):
                shares = None
            else:
                if shares < 0:
                    raise ValueError(
                        f"意向 {code} 的锚定份额不能为负，收到 {self.anchor_shares}"
                    )
        object.__setattr__(self, "anchor_shares", shares)

        wait = self.review_seconds
        if wait is None:
            wait = REVIEW_SECONDS_FOR_HORIZON.get(horizon, 7 * 86400.0)
        wait = float(wait)
        if wait <= 0:
            # ❗长期不等于无限期：没有回顾周期的长期持仓和死线程没法区分
            raise MissingSettlementPoint(
                f"长期配置 {market}:{code} 没有回顾周期（review_seconds 必须为正数）——"
                "「长期持有」也必须周期性回头看一次"
            )
        object.__setattr__(self, "review_seconds", wait)

        object.__setattr__(self, "_explicit_confidence", self.confidence is not None)
        object.__setattr__(self, "confidence", clamp_confidence(self.confidence))

    # ------------------------------------------------------------------
    @property
    def confidence_explicit(self) -> bool:
        """True = 这个强度是人给的，不是系统默认值。"""
        return bool(getattr(self, "_explicit_confidence", False))

    @property
    def anchored(self) -> bool:
        """有没有锚定份额目标（人给的，或默认锚定当前持仓得来的）。"""
        shares = self.anchor_shares
        return shares is not None and float(shares) > 0

    @property
    def target_set(self) -> bool:
        """目标有没有定下来。**占比或锚定份额任一**都算定了。

        False 时 UI 必须如实标「未设定」，❗不能拿默认值假装人拍过板。
        """
        return self.alloc_pct > 0 or self.anchored

    @property
    def target_kind(self) -> str:
        """目标以什么形式表达：``pct`` / ``shares`` / ``""``（未设定）。"""
        if self.alloc_pct > 0:
            return "pct"
        if self.anchored:
            return "shares"
        return ""

    @property
    def review_days(self) -> float:
        return round(float(self.review_seconds or 0.0) / 86400.0, 2)

    # ------------------------------------------------------------------
    def with_anchor(
        self,
        shares: float,
        now: Optional[float] = None,
        source: str = "holdings",
        note: str = "",
    ) -> "Allocation":
        """返回一份**锚定后**的新 Allocation（frozen，不改原对象）。

        ❗锚定要**显式留痕**：什么时候、按什么锚的。少了这些，三个月后
        回看「为什么要补到 900 股」就无从回答。
        """
        return replace(
            self,
            anchor_shares=max(0.0, float(shares)),
            anchor_at=now if now is not None else time.time(),
            anchor_source=str(source or "holdings"),
            anchor_note=str(note or ""),
        )

    def target_shares(
        self,
        total_assets: Optional[float] = None,
        price: Optional[float] = None,
    ) -> Optional[float]:
        """目标折算成**份额**。算不出来就返回 ``None``（❗不是 0）。

        ``None`` 和 ``0`` 的区别是这里最要紧的事：``0`` 会被下游当成
        「目标就是空仓」，于是缺口守望算出「目标 0 份 → 不用补」，
        一个根本没设定目标的持仓就这样被静默地判定为「已达标」。
        """
        if self.alloc_pct > 0:
            if not total_assets or not price or price <= 0:
                return None
            return float(total_assets) * (float(self.alloc_pct) / 100.0) / float(price)
        if self.anchored:
            return float(self.anchor_shares or 0.0)
        return None

    def gap_shares(
        self,
        committed_shares: Optional[float],
        total_assets: Optional[float] = None,
        price: Optional[float] = None,
    ) -> Optional[float]:
        """离目标还差多少份。``None`` = 目标没定，**不能当成 0**。"""
        target = self.target_shares(total_assets, price)
        if target is None or committed_shares is None:
            return None
        return max(0.0, float(target) - float(committed_shares))

    def derive_rotations(
        self,
        committed_shares: Optional[float] = None,
        *,
        pct: float = DEFAULT_ROTATION_PCT,
        window_seconds: Optional[float] = None,
    ) -> List["RotationIntent"]:
        """从这份长期配置派生出**常驻的做 T 守望**。

        ❗前提是有持仓（``committed_shares`` > 0）：做 T 搓的是已有持仓的
        价差，空仓时挂做 T 守望等于凭空造出一个「等机会买入」的机会型
        守望 —— 那是 :class:`~.intent.Intent` 的活，不是做 T。

        :return: 卖 T 与买 T 各一条。两个方向都挂，因为「判断要跌」和
            「判断要涨」是同一个标的上的两种机会，事先不知道哪个先来。
        """
        from .rotation import RotationIntent

        shares = float(committed_shares or 0.0)
        if shares <= 0:
            return []
        return [
            RotationIntent(
                code=self.code,
                market=self.market,
                t_side="sell_t",
                alloc_id=allocation_id(self),
                name=self.name,
                anchor_shares=shares,
                pct=pct,
                window_seconds=window_seconds,
                confidence=self.confidence if self.confidence_explicit else None,
                rationale=self.rationale,
            ),
            RotationIntent(
                code=self.code,
                market=self.market,
                t_side="buy_t",
                alloc_id=allocation_id(self),
                name=self.name,
                anchor_shares=shares,
                pct=pct,
                window_seconds=window_seconds,
                confidence=self.confidence if self.confidence_explicit else None,
                rationale=self.rationale,
            ),
        ]

    def label(self) -> str:
        who = self.name or self.code
        return f"长期持有 {who}（{self.market}）"

    def describe(self) -> str:
        bits = [self.label()]
        if self.alloc_pct > 0:
            bits.append(f"目标 {self.alloc_pct:.0f}% 总资产")
        elif self.anchored:
            bits.append(f"目标锚定 {float(self.anchor_shares):.0f} 份")
        else:
            bits.append("目标未设定")
        bits.append(f"每 {self.review_days:g} 天回顾一次")
        if self.rationale:
            bits.append(f"理由：{self.rationale}")
        return "；".join(bits)


# ---------------------------------------------------------------- 登记

def allocation_id(alloc: Allocation) -> str:
    return f"allocation:{alloc.market}:{alloc.code}"


def to_objective(alloc: Allocation) -> Objective:
    """长期配置变成目标。

    ❗``max_wait_seconds`` 就是**回顾周期**：到期不代表失败，
    只意味「这一期结束了，回头看一眼」。
    """
    return Objective(
        id=allocation_id(alloc),
        kind="allocation",
        subject=alloc.code,
        market=alloc.market,
        max_wait_seconds=float(alloc.review_seconds or 0.0),
        params={
            #: ❗``name`` 必须进 params：UI 的守望表从 params 里读名字，
            #: 漏了就退化成显示代码。
            "name": alloc.name or alloc.code,
            "alloc_pct": float(alloc.alloc_pct),
            "target_set": alloc.target_set,
            "target_kind": alloc.target_kind,
            "anchor_shares": (
                None if alloc.anchor_shares is None
                else float(alloc.anchor_shares)
            ),
            "anchor_at": alloc.anchor_at,
            "anchor_source": alloc.anchor_source,
            "anchor_note": alloc.anchor_note,
            "horizon": alloc.horizon,
            "review_seconds": float(alloc.review_seconds or 0.0),
            "rationale": alloc.rationale,
            "confidence": clamp_confidence(alloc.confidence),
            "confidence_explicit": alloc.confidence_explicit,
            "signal_type": "BUY",
        },
        note=alloc.note or alloc.describe(),
    )


def opportunities_for(alloc: Allocation) -> List[Any]:
    """机会集合：Manas 行动门 + 自带的额外判据。

    与 :func:`~.intent.opportunities_for` 一致 —— 数据先汇聚到 Manas，
    机会在那里出现。
    """
    opps: List[Any] = [
        {
            "kind": "manas_window",
            "min_action": "act_minimally",
            "max_age_seconds": 600.0,
        }
    ]
    opps.extend(alloc.extra_opportunities)
    return opps


def declare_allocation(
    registry: WatchRegistry,
    alloc: Allocation,
    *,
    now: Optional[float] = None,
    max_silence_seconds: Optional[float] = None,
    bootstrap: bool = True,
) -> Watch:
    """把一份长期配置挂上守望台。**循环守望**：到期自动续下一期。

    ❗``bootstrap=True``（与一次性意向不同）：长期持仓的仓位可能早就够了，
    这时它永远不会触发机会判据 —— 没有 bootstrap 就等于**从第一天起就
    完全隐形**。开一次是为了先拿到一份基线，证明它真的挂在台上。
    """
    return registry.declare(
        to_objective(alloc),
        opportunities_for(alloc),
        now=now,
        max_silence_seconds=max_silence_seconds,
        bootstrap=bootstrap,
        recurring=True,
    )


def allocation_row_of(alloc: Allocation) -> Dict[str, Any]:
    """变回清单里的一行。**只写装载方认得的键**。"""
    row: Dict[str, Any] = {
        "code": alloc.code,
        "market": alloc.market,
        "horizon": alloc.horizon,
        "review_seconds": float(alloc.review_seconds or 0.0),
        "alloc_pct": float(alloc.alloc_pct),
    }
    if alloc.name:
        row["name"] = alloc.name
    if alloc.rationale:
        row["rationale"] = alloc.rationale
    if alloc.note:
        row["note"] = alloc.note
    if alloc.confidence_explicit:
        row["confidence"] = clamp_confidence(alloc.confidence)
    # -- 锚定：必须写回，否则服务一重启锚就丢了，目标又变成「未设定」 --
    if alloc.anchor_shares is not None:
        row["anchor_shares"] = float(alloc.anchor_shares)
    if alloc.anchor_at is not None:
        row["anchor_at"] = float(alloc.anchor_at)
    if alloc.anchor_source:
        row["anchor_source"] = alloc.anchor_source
    if alloc.anchor_note:
        row["anchor_note"] = alloc.anchor_note
    return row


#: 补缺口守望的一期多长。到点看看还差多少，还差就挂下一期。
#: ❗不用 ``review_seconds``（那是一周）：补仓等的是行情机会，
#: 一期一个交易时段才谈得上「这期有没有等到」。
GAP_WINDOW_SECONDS = 6 * 3600.0


def derive_gap_objective(
    alloc: Allocation,
    committed_shares: Optional[float],
    total_assets: Optional[float] = None,
    price: Optional[float] = None,
) -> Optional[Objective]:
    """「还差多少没补到位」变成一个守望目标。

    ❗没有缺口就返回 ``None`` —— 不挂守望。挂一个「缺口为 0」的守望
    等于造出一条永远成立、永远在喊、却无事可做的假守望。

    ❗目标没定（:meth:`Allocation.target_shares` 返回 ``None``）也返回
    ``None``：不知道要持有多少，就谈不上「还差多少」。
    """
    gap = alloc.gap_shares(committed_shares, total_assets, price)
    if gap is None or gap <= 0:
        return None
    target = alloc.target_shares(total_assets, price) or 0.0
    return Objective(
        id=f"gap:{alloc.market}:{alloc.code}",
        kind="establish_core",
        subject=alloc.code,
        market=alloc.market,
        max_wait_seconds=GAP_WINDOW_SECONDS,
        params={
            "name": alloc.name or alloc.code,
            "alloc_id": allocation_id(alloc),
            "gap_shares": float(gap),
            "target_shares": float(target),
            "committed_shares": float(committed_shares or 0.0),
            "target_kind": alloc.target_kind,
            "alloc_pct": float(alloc.alloc_pct),
            "anchor_shares": (
                None if alloc.anchor_shares is None
                else float(alloc.anchor_shares)
            ),
            "confidence": clamp_confidence(alloc.confidence),
            "confidence_explicit": alloc.confidence_explicit,
            "signal_type": "BUY",
        },
        note=(
            f"补缺口：还差 {gap:.0f} 份"
            f"（目标 {target:.0f} / 现有 {float(committed_shares or 0.0):.0f}）"
        ),
    )


def derive_watches(
    alloc: Allocation,
    committed_shares: Optional[float] = None,
    total_assets: Optional[float] = None,
    price: Optional[float] = None,
    *,
    rotation_pct: float = DEFAULT_ROTATION_PCT,
    rotation_window: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """一份长期配置派生出**它旗下的整组守望**。

    用户原话（2026-10-14）：「他终归是要 40% 的仓位……一个是守望一个
    机会把它加仓加到 40%；还有一个是守望做 T 的机会……守望的类型很多」。

    所以「长期持有 40%」在系统里**不是一条守望，是一组**：

        ├ 补缺口守望   一次性/循环：还差 10% → 等机会加仓（补满即不挂）
        ├ 卖 T 守望    常驻：涨过头先卖，等跌回来买回
        └ 买 T 守望    常驻：跌过头先买，等涨回去卖回

    ❗做 T 守望的前提是**有持仓**（空仓谈不上搓价差）；
    补缺口守望的前提是**真有缺口**（补满了就不该再挂）。

    :return: 每项含 ``objective / opportunities / recurring / standing / role``
    """
    specs: List[Dict[str, Any]] = []

    gap = derive_gap_objective(alloc, committed_shares, total_assets, price)
    if gap is not None:
        specs.append({
            "objective": gap,
            "opportunities": list(opportunities_for(alloc)),
            "recurring": True,
            "standing": False,
            "role": "gap",
        })

    for intent in alloc.derive_rotations(
        committed_shares, pct=rotation_pct, window_seconds=rotation_window
    ):
        specs.append({
            "objective": to_objective_of_rotation(intent),
            "opportunities": opportunities_of_rotation(intent),
            "recurring": False,
            "standing": True,
            "role": intent.t_side,
        })
    return specs


def anchor_if_needed(
    alloc: Allocation,
    committed_shares: Optional[float],
    now: Optional[float] = None,
    note: str = "",
) -> Tuple[Allocation, bool]:
    """目标没定时，**默认把当前持仓锚定为长期目标数量**。

    用户原话（2026-10-14）：「有些我们可能没设定的时候就默认，
    比如说当前持仓，这个就是一个长远一个持仓目标数量」。

    ❗三个必须守住的坑，踩任何一个都会让目标形同虚设：

    1. **只锚一次**。锚定之后目标就固定下来。若每轮都取当前持仓，
       卖 T 卖掉一部分 → 目标跟着降 → 缺口永远是 0 → 补仓守望永远不会
       出现 —— **目标被自己的操作拖着走**，这是最隐蔽的一种失效。
    2. **锚「约定份额」而不是裸持仓**。约定份额 = 真实持仓 + 未履行
       回购义务。卖 T 卖出后真实持仓降了，但那部分**欠着**，目标不能跟着降。
    3. **锚不上就如实说锚不上**（原样返回 + ``False``），❗不要拿 0 顶替 ——
       「还没持仓所以锚不了」和「目标就是空仓」是完全不同的两件事。

    :return: ``(配置, 是不是这一次刚锚上的)``
    """
    if alloc.target_set:
        return alloc, False
    if committed_shares is None or float(committed_shares) <= 0:
        return alloc, False
    return (
        alloc.with_anchor(
            committed_shares,
            now=now,
            source="holdings",
            note=note or "目标未设定，默认以当时的持仓作为长期持有数量",
        ),
        True,
    )
