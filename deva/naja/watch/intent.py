"""意向（Intent）—— 把「我想买英伟达」这句话，变成可以被系统等待的目标。

三层分工
========
    意向层（本文件）  人想要什么：买谁、多少钱、等到什么时候为止
    守望层（Watch）   系统在等什么：把意向变成一组机会，然后休息
    决策中心          到底批不批：机会成立只买到「有资格被问一次」

用户的原话（2026-10-14）
======================
    「我最近觉得 AI 不错，我想买入英伟达，但可能现在价格高，我决定不了什么
     时候买入，但是我确实想买入，这个想法应该进入守望台。然后等待一个机会
     来买入。」

拆开是四件事，本文件只做前三件：

1. 登记愿望：标的、市场、预算（可选）、理由。
2. 声明有效期：必须回答「等到什么时候为止」。
3. 接上机会源：默认接 Manas 行动门（见 :mod:`.manas_lens`）。
4. 执行：不归本文件管。机会成立之后要先去问决策中心，批了才谈下单。

为什么意向也必须有结算点
========================
「我决定不了什么时候买」不等于「可以永远等下去」。一个悬着、永不过期的想法，
和一条已经死掉的线程长得一模一样 —— 都表现为「日志里什么都不再出现」。
所以构造时就查：没有 ``max_wait_seconds`` 直接抛
:class:`~.objective.MissingSettlementPoint`。

到期就结算成 ``expired``，把「等了三天没遇到合适的进场点」写进日志。
这条记录和「从来没有这个想法」是两件事，事后复盘必须分得开。

为什么 market 必须写清楚
========================
NVDA 是裸字母，代码形态说不出它属于哪个市场（6 位数字是 A 股、5 位数字是
港股，字母只有查名单才认得）。沿用 ``core_holdings`` 那次的结论：让人在
登记时说清楚，比猜一份可能漏登记的名单可靠。猜错了市场，「每手多少、
什么时候收盘」整套参数都会跟着错，所以这里不准兜底。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .objective import MissingSettlementPoint, Objective
from .registry import WatchRegistry
from .watch import Watch

__all__ = [
    "INTENT_SIDES",
    "INTENT_CONFIDENCE_DEFAULT",
    "INTENT_CONFIDENCE_CAP",
    "SIGNAL_TYPE_FOR_SIDE",
    "clamp_confidence",
    "Intent",
    "BuyIntent",
    "SellIntent",
    "intent_id",
    "to_objective",
    "declare_intent",
    "opportunities_for",
]

#: 支持的方向。扩展时往这里加，并在执行侧实现解析。
INTENT_SIDES = ("buy", "sell", "trim")

#: 认得的市场。认不出来就抛异常，不做静默兜底（见模块 docstring）。
KNOWN_MARKETS = ("CN", "HK", "US")

_SIDE_ZH = {"buy": "买入", "sell": "卖出", "trim": "减仓"}

#: 决策中心的 :func:`~deva.naja.decision.plan.side_from_signal_type` 只认
#: ``BUY`` / ``SELL``，其余一律归成 ``none``。所以「减仓」必须翻译成
#: ``SELL`` —— 直传 ``TRIM`` 会让决策中心以为这笔没有方向。
SIGNAL_TYPE_FOR_SIDE = {"buy": "BUY", "sell": "SELL", "trim": "SELL"}

#: ❗人为意愿的默认强度与**硬上限**。
#: 主动想买确实该比系统自动补仓更有分量（否则「我想买」这句话在打分里
#: 权重是 0），但它只能是一股**输入**，不能变成放行键：
#:   * 默认 0.6 —— 高于系统自动信号的 0.5，低于「自信」那一档
#:   * 封顶 0.75 —— 永远够不到 1.0，也不碰 manas 的 action_threshold
#: 想退回「无差别」就用环境变量 ``NAJA_INTENT_CONFIDENCE=0.5``。
INTENT_CONFIDENCE_DEFAULT = 0.6
INTENT_CONFIDENCE_CAP = 0.75


def clamp_confidence(value: Any, cap: Optional[float] = None) -> float:
    """把意愿强度夹到 ``[0, cap]``。

    ❗上限**不可绕过**：这是「主动意愿 ≠ 放行」这条纪律唯一的量化把手，
    谁都能调但谁都调不过 0.75。认不出来的输入按默认值处理，不抛异常 ——
    一份清单里有一条填坏，不该让整批意向挂不上。
    """
    top = float(INTENT_CONFIDENCE_CAP if cap is None else cap)
    try:
        v = float(value)
    except (TypeError, ValueError):
        return min(INTENT_CONFIDENCE_DEFAULT, top)
    if v != v:  # NaN
        return min(INTENT_CONFIDENCE_DEFAULT, top)
    return max(0.0, min(top, v))


@dataclass(frozen=True)
class Intent:
    """一个人工意向。请用 :func:`BuyIntent` / :func:`SellIntent` 来造。

    :param max_wait_seconds: 必填。等多久没等到就结算成 expired。
    :param budget: 打算投多少钱（本币币种跟随 market）。给 None 表示
        「还没想好金额」，额度交给决策中心的定量器决定。
    :param rationale: 为什么想要。写下来不是为了好看：几个月后回看
        「NVDA 过期了」，必须想得起当初为什么在等。
    :param min_action: 交给 Manas 机会判据的门槛。
    :param confidence: 意愿强度，交给决策中心当融合输入（**不是放行键**）。
        None 表示用默认；上限见 :data:`INTENT_CONFIDENCE_CAP`。
    :param extra_opportunities: 追加的机会判据（价格回撤、时间窗等）。
    """

    code: str
    market: str
    side: str = "buy"
    name: str = ""
    budget: Optional[float] = None
    max_wait_seconds: Optional[float] = None
    note: str = ""
    rationale: str = ""
    min_action: str = "act_minimally"
    reading_max_age: float = 600.0
    confidence: Optional[float] = None
    extra_opportunities: Tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        code = str(self.code or "").strip()
        if not code:
            raise ValueError("Intent.code 不能为空")
        # frozen dataclass：归一化只能在这里用 object.__setattr__
        object.__setattr__(self, "code", code.upper())

        market = str(self.market or "").strip().upper()
        if market not in KNOWN_MARKETS:
            raise ValueError(
                f"{code} 的市场 {market!r} 认不出来；只能是 {KNOWN_MARKETS} 之一。"
                "猜错市场会让「每手多少、什么时候收盘」整套参数跟着错，"
                "所以这里不兜底"
            )
        object.__setattr__(self, "market", market)

        side = str(self.side or "buy").strip().lower()
        if side not in INTENT_SIDES:
            raise ValueError(f"不支持的方向 {side!r}；只有 {INTENT_SIDES}")
        object.__setattr__(self, "side", side)

        wait = self.max_wait_seconds
        if wait is None or float(wait) <= 0:
            raise MissingSettlementPoint(
                f"意向 {side}:{market}:{code} 没有结算点"
                "（max_wait_seconds 必须是正数）——"
                "「还没想好什么时候买」不等于「可以永远等下去」"
            )

        if self.budget is not None and float(self.budget) <= 0:
            raise ValueError(f"意向 {code} 的预算必须是正数，收到 {self.budget}")

        # ❗先记下「这个值是人给的还是默认值」，再封顶。审计时「系统默认」
        # 和「用户明确写了 0.7」是两件事，写错标签会把复盘带偏。
        object.__setattr__(self, "_explicit_confidence", self.confidence is not None)
        # 意愿强度在这里就封顶：无论谁消费这份意向，都拿不到超过上限的值
        object.__setattr__(self, "confidence", clamp_confidence(self.confidence))

    # ------------------------------------------------------------------
    @property
    def confidence_explicit(self) -> bool:
        """True = 这个强度是登记时明确给的，不是系统默认值。"""
        return bool(getattr(self, "_explicit_confidence", False))

    @property
    def signal_type(self) -> str:
        """交给决策中心的方向。``trim`` 翻译成 ``SELL``（见常量处说明）。"""
        return SIGNAL_TYPE_FOR_SIDE.get(self.side, "BUY")

    def label(self) -> str:
        who = self.name or self.code
        return f"{_SIDE_ZH.get(self.side, self.side)} {who}（{self.market}）"

    def describe(self) -> str:
        bits = [self.label()]
        if self.budget:
            bits.append(f"预算 {self.budget:,.0f}")
        if self.rationale:
            bits.append(f"理由：{self.rationale}")
        return "；".join(bits)


def BuyIntent(  # noqa: N802 - 刻意做成「一句话登记意向」的写法
    code: str,
    market: str,
    *,
    max_wait_seconds: float,
    name: str = "",
    budget: Optional[float] = None,
    note: str = "",
    rationale: str = "",
    min_action: str = "act_minimally",
    reading_max_age: float = 600.0,
    confidence: Optional[float] = None,
    extra_opportunities: Sequence[Any] = (),
) -> Intent:
    """「我想买它，但什么时候买交给守望台决定」。"""
    return Intent(
        code=code, market=market, side="buy", name=name, budget=budget,
        max_wait_seconds=max_wait_seconds, note=note, rationale=rationale,
        min_action=min_action, reading_max_age=reading_max_age,
        confidence=confidence,
        extra_opportunities=tuple(extra_opportunities),
    )


def SellIntent(  # noqa: N802
    code: str,
    market: str,
    *,
    max_wait_seconds: float,
    name: str = "",
    budget: Optional[float] = None,
    note: str = "",
    rationale: str = "",
    min_action: str = "act_minimally",
    reading_max_age: float = 600.0,
    confidence: Optional[float] = None,
    extra_opportunities: Sequence[Any] = (),
) -> Intent:
    """「我想卖/减它，但什么时候卖交给守望台决定」。"""
    return Intent(
        code=code, market=market, side="sell", name=name, budget=budget,
        max_wait_seconds=max_wait_seconds, note=note, rationale=rationale,
        min_action=min_action, reading_max_age=reading_max_age,
        confidence=confidence,
        extra_opportunities=tuple(extra_opportunities),
    )


# ---------------------------------------------------------------- 登记

def intent_id(intent: Intent) -> str:
    return f"intent:{intent.side}:{intent.market}:{intent.code}"


def to_objective(intent: Intent) -> Objective:
    """意向变成目标。金额留在参数里，不由意向层折算股数（那是决策中心的事）。"""
    params: Dict[str, Any] = {
        "side": intent.side,
        "rationale": intent.rationale,
        #: ❗意愿强度必须随目标一起走：决策中心那边要看得见「这笔是人想买的」，
        #: 否则它跟系统自动补底仓的信号长得一模一样，权重为 0。
        "confidence": clamp_confidence(intent.confidence),
        "confidence_explicit": intent.confidence_explicit,
        "signal_type": intent.signal_type,
    }
    if intent.budget is not None:
        params["budget"] = float(intent.budget)
    return Objective(
        id=intent_id(intent),
        kind=f"{intent.side}_intent",
        subject=intent.code,
        market=intent.market,
        max_wait_seconds=float(intent.max_wait_seconds or 0.0),
        params=params,
        note=intent.note or intent.describe(),
    )


def opportunities_for(intent: Intent) -> List[Any]:
    """意向默认的机会集合：Manas 行动门 + 自带的额外判据。

    第一条是 Manas 而不是价格，因为用户就是这么说的 ——
    数据先汇聚到 Manas，机会在那里出现。价格回撤这类判据通过
    ``extra_opportunities`` 追加，才有资格待在同一个守望里。
    """
    opps: List[Any] = [
        {
            "kind": "manas_window",
            "min_action": intent.min_action,
            "max_age_seconds": float(intent.reading_max_age),
        }
    ]
    opps.extend(intent.extra_opportunities)
    return opps


def declare_intent(
    registry: WatchRegistry,
    intent: Intent,
    *,
    now: Optional[float] = None,
    max_silence_seconds: Optional[float] = None,
    bootstrap: bool = False,
) -> Watch:
    """把一个意向挂到守望台上。同 id 会覆盖（视为重新瞄准，比如改了金额）。"""
    return registry.declare(
        to_objective(intent),
        opportunities_for(intent),
        now=now,
        max_silence_seconds=max_silence_seconds,
        bootstrap=bootstrap,
    )
