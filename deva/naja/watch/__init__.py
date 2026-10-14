"""守望系统 —— 「等待机会」的一等公民化。

来历
====
2026-10-14 用户提了一句：「等待机会是个很好的概念，有了目标，寻求买入或者
卖出机会，或者等待做 T 的机会。这个等待机会能否做成一个系统」。

核查结论是：此前系统里**根本没有「等待」这个对象**。每 30 秒轮询一次，
顺手判断一下，判断为「不能」就**什么都不做也不记录** —— 30 秒后整个循环
重来，系统对自己刚才在等什么一无所知。缺三样东西：

1. 没记录「我在等什么」
2. 没声明「等到什么才动手」
3. 没度量「等了多久算异常」

本包就是补这三样。

五个概念
========
    Objective    声明「要达成什么状态」，不写怎么做
    Opportunity  「值得重新问一次」的时刻（价格 / 环境 / 时间 / 自定义钩子）
    Watch        目标 + 机会的绑定，大部分时间休眠
    WatchRegistry 守望台：登记、扫描、结算、自证心跳
    Settlement   达成 / 过期 / 放弃 —— **必须显式结算**

❗核心纪律：机会 ≠ 放行
========================
机会到的那一刻，守望只买到「有资格去问一次决策中心」。批准权始终在
决策中心手里（见 :mod:`deva.naja.bandit.core_establish_gate`）。
若把机会直接接成下单，若干个兜底条件叠起来就是一台必然放行的机器 ——
这在 :mod:`deva.naja.decision.fusion` 上已经发生过一次。

❗第二条纪律：不准有无限期的守望
================================
一个没有结算点的守望，和一条已经死掉的线程长得一模一样。
所以 :class:`~deva.naja.watch.objective.Objective` 在**构造时**就要求有
``max_wait_seconds``，缺了直接抛异常。

❗第三条纪律：None ≠ []
========================
判据返回三态（yes / no / unknown）。行情没取到是 unknown，绝不能当成 no。
"""

from .objective import (
    MissingSettlementPoint,
    Objective,
    OBJECTIVE_KINDS,
    WatchContext,
    make_context,
)
from .manas_lens import ACTION_LADDER, ManasLens, ManasReading
from .opportunity import (
    BUILTIN_KINDS,
    CallableOpportunity,
    DeadlineWindow,
    EnvironmentUpgrade,
    ManasWindow,
    Opportunity,
    OpportunityHit,
    PriceDeviation,
    UnknownOpportunityKind,
    build_opportunity,
    register_opportunity_kind,
)
from .intent import (
    BuyIntent,
    Intent,
    SellIntent,
    declare_intent,
    intent_id,
    to_objective,
)
from .allocation import (
    HORIZONS,
    Allocation,
    allocation_id,
    declare_allocation,
    anchor_if_needed,
    derive_watches,
)
from .rotation import (
    T_SIDES,
    T_SIDE_ZH,
    RotationIntent,
    declare_rotation,
    rotation_id,
)
from .desk import DeskTicket, WatchDesk
from .registry import WatchRegistry
from .watch import Settlement, Watch, WatchScan, WatchState

__all__ = [
    "MissingSettlementPoint",
    "Objective",
    "OBJECTIVE_KINDS",
    "WatchContext",
    "make_context",
    "Opportunity",
    "OpportunityHit",
    "PriceDeviation",
    "EnvironmentUpgrade",
    "DeadlineWindow",
    "CallableOpportunity",
    "UnknownOpportunityKind",
    "BUILTIN_KINDS",
    "build_opportunity",
    "register_opportunity_kind",
    "ACTION_LADDER",
    "ManasLens",
    "ManasReading",
    "ManasWindow",
    "Watch",
    "WatchScan",
    "WatchState",
    "Settlement",
    "WatchRegistry",
    "Intent",
    "BuyIntent",
    "SellIntent",
    "intent_id",
    "to_objective",
    "declare_intent",
    "HORIZONS",
    "Allocation",
    "allocation_id",
    "declare_allocation",
    "anchor_if_needed",
    "derive_watches",
    "T_SIDES",
    "T_SIDE_ZH",
    "RotationIntent",
    "rotation_id",
    "declare_rotation",
    "WatchDesk",
    "DeskTicket",
]
