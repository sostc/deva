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

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .intent import (
    KNOWN_MARKETS,
    clamp_confidence,
)
from .objective import MissingSettlementPoint, Objective
from .registry import WatchRegistry
from .watch import Watch

__all__ = [
    "HORIZONS",
    "HORIZON_ZH",
    "REVIEW_SECONDS_FOR_HORIZON",
    "DEFAULT_HORIZON",
    "Allocation",
    "allocation_id",
    "to_objective",
    "opportunities_for",
    "declare_allocation",
    "allocation_row_of",
]

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
    def target_set(self) -> bool:
        """目标仓位有没有拍板。False 时 UI 必须如实标「未设定」。"""
        return self.alloc_pct > 0

    @property
    def review_days(self) -> float:
        return round(float(self.review_seconds or 0.0) / 86400.0, 2)

    def label(self) -> str:
        who = self.name or self.code
        return f"长期持有 {who}（{self.market}）"

    def describe(self) -> str:
        bits = [self.label()]
        bits.append(
            f"目标 {self.alloc_pct:.0f}% 总资产"
            if self.target_set
            else "目标未设定"
        )
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
    return row
