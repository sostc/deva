"""做 T 守望（RotationIntent）—— 一直挂在台上等买卖机会的那种。

用户原话（2026-10-14）
====================
    「比如说他终归是要 40% 的仓位嘛，但是平时可能仓位是 30%，
      那他一个是在守望一个机会把它加仓加到 40%……
      还有一个是守望一个什么机会呢，就是做 T，可能判断要跌，
      那他现在可以卖掉，等一个买点的时候再把它买回来……
      这个做 t 的守望应该是**持续一直存在**的，一直在等待机会来买卖」

这一句把长期配置**拆成了两层**，之前只做了上面那层：

    ┌─ 目标层（Allocation）────────────────────────────────┐
    │  「我最终要持有 40%」  ← 慢变量，人拍板，轻易不动      │
    └───────────────┬───────────────────────────────────────┘
                    │ 派生
        ┌───────────┴───────────┐
        ▼                       ▼
   补缺口守望              做 T 守望（本模块）
   30% → 40%              一直存在，抓到就问、问完继续等
   补齐即消失              ❗不是机会型，也不是循环型

为什么做 T 守望必须是第三种生命周期
==================================
守望系统原来只有两种，都装不下「一直等机会」：

    ==========  ====================  ====================  ==================
                机会型（Intent）       循环型（Allocation）   **常驻型（本模块）**
    续期条件     不续，成交即结束       时间到了就续          **抓到机会就续**
    到期含义     没等到 → expired      这期看过了 → reviewed  这期没轮到 → expired
    撤下后       消失                  不再续                **不再续**
    典型         「我想买入英伟达」     「长期持有腾讯」      「有空就做个 T」
    ==========  ====================  ====================  ==================

❗若把做 T 装进机会型，它做成一次就消失 —— 用户明明说「持续一直存在」；
若装进循环型，它要等一个回顾周期才重新挂起，日内机会早过去了。
所以 :class:`~.watch.Watch` 有了第三种：``standing``（见 :mod:`.watch`）。

方向
====
做 T 引擎（``bandit/t_rotation.py``）里两种打法，这里一一对应：

    ``sell_t``  倒 T：判断要涨上去了 → **先卖**，等跌回来买回
                （用户说的「判断要跌先卖掉、等买点买回来」在工程上表现为
                  涨偏离时先卖，因为「要跌」的判据就是涨过头了）
    ``buy_t``   正 T：判断跌过头了 → **先买**，等涨回去卖回
    ``repay``   回购：已经卖出、欠着的份额要买回来。
                ❗这是**债务不是机会** —— 判据可以一样（跌到买点），
                但它存在的前提是「有未了结的轮次」，而且优先级最高。

❗不下单
========
本模块只把「我在等一个做 T 的机会」这件事挂到台上，让它在守望台上
**看得见、问得到、留得下痕**。真下单仍然是做 T 引擎的事，要过
``TRotationRunner`` 与决策中心两道。守望台从不碰账户 —— 这条纪律
在这里尤其要紧：一旦守望台能下单，「等机会」就变成了「自动交易」。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .intent import (
    KNOWN_MARKETS,
    clamp_confidence,
)
from .objective import MissingSettlementPoint, Objective
from .registry import WatchRegistry
from .watch import Watch

__all__ = [
    "T_SIDES",
    "T_SIDE_ZH",
    "T_SIDE_OPPORTUNITY",
    "DEFAULT_ROTATION_PCT",
    "DEFAULT_ROTATION_WINDOW",
    "RotationIntent",
    "rotation_id",
    "to_objective",
    "opportunities_for",
    "declare_rotation",
    "rotation_row_of",
]

#: 三种做 T 守望。
T_SIDES = ("sell_t", "buy_t", "repay")

T_SIDE_ZH = {
    "sell_t": "卖 T（先卖，等跌回来买回）",
    "buy_t": "买 T（先买，等涨回去卖回）",
    "repay": "回购（欠着的份额要买回来）",
}

#: 每种方向对应的机会判据。
#: ❗卖 T 是**高于**锚才卖（涨过头 = 要跌），买 T 是**低于**锚才买
#: （跌过头 = 要涨）。方向搞反了就变成追涨杀跌，那不是做 T。
T_SIDE_OPPORTUNITY: Dict[str, Dict[str, Any]] = {
    "sell_t": {"kind": "price_deviation", "direction": "above"},
    "buy_t": {"kind": "price_deviation", "direction": "below"},
    "repay": {"kind": "price_deviation", "direction": "below"},
}

#: 偏离锚多少个百分点算一个机会。做 T 吃的是小价差，默认 1%。
DEFAULT_ROTATION_PCT = 1.0

#: 一期观察窗口。
#: ❗常驻不等于无限期 —— 它只是「每一期都很短且永不停止」。
#: 一期一个观察窗，到期没轮到就记「这期没等到」再立刻重挂。
DEFAULT_ROTATION_WINDOW = 1800.0


@dataclass(frozen=True)
class RotationIntent:
    """一份「我要在这个标的上一直做 T」的意愿。

    与 :class:`~.allocation.Allocation` 的关系：那个定**持有多少**，
    这个定**在这个持有量的基础上来回搓价差**。前者是慢变量（人拍板），
    后者是常驻的快变量（行情驱动）。

    :param t_side: 方向，见 :data:`T_SIDES`。
    :param alloc_id: 属于哪份长期配置。用它把做 T 守望挂回它的目标，
        否则页面上就只剩一堆散落的「卖 T」而看不出是为谁做的。
    :param anchor_shares: 约定持有份额（真实持仓 + 未履行回购义务）。
        ❗做 T 的**底线**：任何一轮结束时持有不得低于这个数。
    :param pct: 偏离锚多少算机会。
    :param window_seconds: 一期多长。不给就用 :data:`DEFAULT_ROTATION_WINDOW`。
    """

    code: str
    market: str
    t_side: str = "sell_t"
    alloc_id: str = ""
    name: str = ""
    anchor_shares: float = 0.0
    pct: float = DEFAULT_ROTATION_PCT
    window_seconds: Optional[float] = None
    confidence: Optional[float] = None
    rationale: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        code = str(self.code or "").strip()
        if not code:
            raise ValueError("RotationIntent.code 不能为空")
        object.__setattr__(self, "code", code.upper())

        market = str(self.market or "").strip().upper()
        if market not in KNOWN_MARKETS:
            raise ValueError(
                f"{code} 的市场 {market!r} 认不出来；只能是 {KNOWN_MARKETS} 之一"
            )
        object.__setattr__(self, "market", market)

        side = str(self.t_side or "").strip().lower()
        if side not in T_SIDES:
            raise ValueError(
                f"做 T 方向 {self.t_side!r} 认不出来；只能是 {T_SIDES} 之一"
            )
        object.__setattr__(self, "t_side", side)

        try:
            pct = abs(float(self.pct))
        except (TypeError, ValueError):
            pct = DEFAULT_ROTATION_PCT
        if pct <= 0:
            raise ValueError(f"做 T 的偏离阈值必须为正，收到 {self.pct}")
        object.__setattr__(self, "pct", pct)

        wait = self.window_seconds
        if wait is None:
            wait = DEFAULT_ROTATION_WINDOW
        wait = float(wait)
        if wait <= 0:
            # ❗常驻守望也必须有结算点 —— 没有终点的守望和死线程没法区分，
            # 「一直在等」是靠「每一期都很短且不断重挂」表达的，不是靠无限期。
            raise MissingSettlementPoint(
                f"做 T 守望 {market}:{code}:{side} 没有观察窗口"
                "（window_seconds 必须为正数）"
            )
        object.__setattr__(self, "window_seconds", wait)

        try:
            shares = float(self.anchor_shares or 0.0)
        except (TypeError, ValueError):
            shares = 0.0
        object.__setattr__(self, "anchor_shares", max(0.0, shares))

        object.__setattr__(self, "_explicit_confidence", self.confidence is not None)
        object.__setattr__(self, "confidence", clamp_confidence(self.confidence))

    # ------------------------------------------------------------------
    @property
    def confidence_explicit(self) -> bool:
        return bool(getattr(self, "_explicit_confidence", False))

    @property
    def is_debt(self) -> bool:
        """True = 这不是机会，是债务（必须还）。"""
        return self.t_side == "repay"

    def label(self) -> str:
        who = self.name or self.code
        return f"{who} {T_SIDE_ZH.get(self.t_side, self.t_side)}"

    def describe(self) -> str:
        bits = [self.label()]
        bits.append(f"偏离 {self.pct:g}% 出手")
        bits.append(f"每期 {self.window_seconds / 60:.0f} 分钟")
        if self.anchor_shares > 0:
            bits.append(f"底线 {self.anchor_shares:.0f} 份")
        if self.rationale:
            bits.append(f"理由：{self.rationale}")
        return "；".join(bits)


# ---------------------------------------------------------------- 登记

def rotation_id(intent: RotationIntent) -> str:
    """守望 id。**方向进 id**：同一个标的的卖 T 和买 T 是两个守望。"""
    return f"rotation:{intent.market}:{intent.code}:{intent.t_side}"


def to_objective(intent: RotationIntent) -> Objective:
    """做 T 守望变成目标。

    ❗``max_wait_seconds`` 是**一期观察窗口**，不是「等多久放弃」——
    常驻守望到期只是「这期没轮到」，它马上会重新挂起。
    """
    return Objective(
        id=rotation_id(intent),
        kind="rotation_t",
        subject=intent.code,
        market=intent.market,
        max_wait_seconds=float(intent.window_seconds or 0.0),
        params={
            "name": intent.name or intent.code,
            "t_side": intent.t_side,
            "t_side_zh": T_SIDE_ZH.get(intent.t_side, intent.t_side),
            "alloc_id": intent.alloc_id,
            "anchor_shares": float(intent.anchor_shares),
            "pct": float(intent.pct),
            "is_debt": intent.is_debt,
            "confidence": clamp_confidence(intent.confidence),
            "confidence_explicit": intent.confidence_explicit,
            #: ❗做 T 卖出方向的 signal_type 是 SELL、买入方向是 BUY ——
            #: 决策中心的 ``side_from_signal_type`` 只认这两个，
            #: 传别的会被归成 none，意愿权重就白算了。
            "signal_type": "SELL" if intent.t_side == "sell_t" else "BUY",
        },
        note=intent.note or intent.describe(),
    )


def opportunities_for(intent: RotationIntent) -> List[Any]:
    """机会判据：价格偏离锚。

    回购（``repay``）额外要求「确实欠着份额」—— 没欠就不该有这个守望，
    少了这条会挂出一个永远成立、永远在喊的假债务。
    """
    spec = dict(T_SIDE_OPPORTUNITY.get(intent.t_side, {}))
    spec["pct"] = float(intent.pct)
    return [spec]


def declare_rotation(
    registry: WatchRegistry,
    intent: RotationIntent,
    *,
    now: Optional[float] = None,
    max_silence_seconds: Optional[float] = None,
) -> Watch:
    """把一份做 T 意愿挂上守望台。**常驻守望**：问过一次就重挂下一期。

    ❗``bootstrap=False``（与长期配置不同）：做 T 是价格类判据，
    首次就该安静 —— 无条件催问会让「刚挂上、价格还没动」的第一轮
    被白白浪费，而且会在刚启动时集中问一轮决策中心。
    """
    return registry.declare(
        to_objective(intent),
        opportunities_for(intent),
        now=now,
        max_silence_seconds=max_silence_seconds,
        bootstrap=False,
        standing=True,
    )


def rotation_row_of(intent: RotationIntent) -> Dict[str, Any]:
    """变回清单里的一行。**只写装载方认得的键**。"""
    row: Dict[str, Any] = {
        "code": intent.code,
        "market": intent.market,
        "t_side": intent.t_side,
        "pct": float(intent.pct),
        "window_seconds": float(intent.window_seconds or 0.0),
    }
    if intent.alloc_id:
        row["alloc_id"] = intent.alloc_id
    if intent.name:
        row["name"] = intent.name
    if intent.anchor_shares:
        row["anchor_shares"] = float(intent.anchor_shares)
    if intent.rationale:
        row["rationale"] = intent.rationale
    if intent.note:
        row["note"] = intent.note
    if intent.confidence_explicit:
        row["confidence"] = clamp_confidence(intent.confidence)
    return row
