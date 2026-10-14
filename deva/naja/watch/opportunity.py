"""机会（Opportunity）—— 「值得重新问一次决策中心」的时刻。

❗本模块最重要的一句话：**机会不等于放行**。

机会只是买到一次**被询问的资格**。最终做不做，仍然要过决策中心
（详见 :mod:`deva.naja.bandit.core_establish_gate`）。如果把「机会成立」
直接接成「下单」，那么若干个兜底条件叠在一起就会退化成一个必然放行的按钮 ——
2026-10-14 已经在 :mod:`deva.naja.decision.fusion` 见过这个形态：四个入射条件
合并后的 ``wanted`` 不受 ``size_hint`` 约束，会把「不下单」这一条 pwd 整个覆盖掉。

三态而不是布尔
==============
``OpportunityHit`` 有三个取值，不是两个：

    yes(理由)     条件成立，值得去问一次
    no(理由)      条件确实不成立，继续等
    unknown(理由) **看不清**：行情没取到、锚没算出来、链路故障

``unknown`` 必须单独存在，而且**绝不能退化成 ``no``**。这是记忆里反复出现的
那条：``None``（查询失败）≠ ``[]``（确认没有）。一次网络抖动若是被当成
「没机会」，守望就会记下一条根本不存在的判据，事后复盘必被带偏。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional

from .manas_lens import ACTION_LADDER, ManasReading
from .objective import WatchContext

log = logging.getLogger(__name__)

__all__ = [
    "OpportunityHit",
    "Opportunity",
    "UnknownOpportunityKind",
    "PriceDeviation",
    "EnvironmentUpgrade",
    "ManasWindow",
    "DeadlineWindow",
    "CallableOpportunity",
    "BUILTIN_KINDS",
    "build_opportunity",
    "register_opportunity_kind",
]


@dataclass(frozen=True)
class OpportunityHit:
    """一次判定的结果。**三态**，见模块文档。"""

    fired: bool
    #: False = 条件确实不成立；True = 判据本身看不清（行情缺失 / 链路故障）
    unknown: bool = False
    reason: str = ""

    # -- 三个构造器：不允许外部自己拼，**防止 unknown 被漏掉** -------------
    @classmethod
    def yes(cls, reason: str = "") -> "OpportunityHit":
        return cls(fired=True, unknown=False, reason=reason)

    @classmethod
    def no(cls, reason: str = "") -> "OpportunityHit":
        return cls(fired=False, unknown=False, reason=reason)

    @classmethod
    def unclear(cls, reason: str = "") -> "OpportunityHit":
        """看不清。❗语义是「我没法判断」，**不是**「没有机会」。"""
        return cls(fired=False, unknown=True, reason=reason)

    def __bool__(self) -> bool:  # 禁止 ``if hit:`` —— 会把 unknown 当成 False
        raise TypeError(
            "OpportunityHit 不可当布尔用：unknown 不等于 False，"
            "请显式判断 hit.fired / hit.unknown"
        )


class Opportunity:
    """机会判据接口。

    实现只要提供 :meth:`check`。内置的几种均为「声明式配置 + 代码钩子」中的
    声明式部分；确实需要特殊逻辑时用 :class:`CallableOpportunity`。
    """

    kind: str = "abstract"

    def check(self, ctx: WatchContext) -> OpportunityHit:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> str:
        """给 UI / 心跳看的一句话说明「我在等什么」。"""
        return self.kind


class UnknownOpportunityKind(ValueError):
    """机会类型认不出来。

    ❗刻意**抛异常而不是跳过**：静态继承 ``Market`` 那次事故的教训是，
    ``getattr(Market, x, Market.HK)`` 式的兜底会把「认不出来」悄悄变成
    「拿了个错的」，排查时长得跟正常运行没法区分。认不出就喊。
    """


class PriceDeviation(Opportunity):
    """价格偏离锚 ——「跌够了才值得问一次」。

    :param direction: ``"below"`` 低于锚、``"above"`` 高于锚
    :param pct: 偏离百分比（正数）
    :param anchor: 用哪个锚；默认 ``"prev_close"``（外生昨收）
    """

    kind = "price_deviation"

    def __init__(
        self,
        pct: float = 1.0,
        direction: str = "below",
        anchor: str = "prev_close",
    ) -> None:
        self.pct = abs(float(pct))
        direction = str(direction or "below").strip().lower()
        if direction not in ("below", "above"):
            raise ValueError(f"direction 只支持 below/above，收到 {direction!r}")
        self.direction = direction
        self.anchor = str(anchor or "prev_close")

    def _pick_anchor(self, ctx: WatchContext) -> Optional[float]:
        if self.anchor == "prev_close":
            return ctx.anchor
        return ctx.value(self.anchor)

    def check(self, ctx: WatchContext) -> OpportunityHit:
        if ctx.price is None:
            return OpportunityHit.unclear("行情没取到，判不了偏离")
        anchor = self._pick_anchor(ctx)
        if anchor is None or anchor <= 0:
            # ❗锚-value 缺失与「价格没到」是两件事，不能合并
            return OpportunityHit.unclear(f"锚 {self.anchor} 缺失，判不了偏离")
        dev = (ctx.price / anchor - 1.0) * 100.0
        if self.direction == "below":
            hit = dev <= -self.pct
            return (
                OpportunityHit.yes(f"低于锚 {abs(dev):.2f}% ≥ {self.pct}%")
                if hit
                else OpportunityHit.no(f"现价偏离 {dev:+.2f}%，未到 -{self.pct}%")
            )
        hit = dev >= self.pct
        return (
            OpportunityHit.yes(f"高于锚 {dev:+.2f}% ≥ {self.pct}%")
            if hit
            else OpportunityHit.no(f"现价偏离 {dev:+.2f}%，未到 +{self.pct}%")
        )

    def describe(self) -> str:
        rel = "低于" if self.direction == "below" else "高于"
        return f"价格{rel}锚 {self.pct}%（锚={self.anchor}）"


class EnvironmentUpgrade(Opportunity):
    """环境机会 —— 决策中心档位从观望升到动作档。

    例：Manas 长期 ``hold`` 时守望一直睡着；一旦升到 ``act_minimally`` 以上，
    才值得去问一次「现在可以动手了吗」。
    """

    kind = "environment_upgrade"

    #: 由弱到强。低于阈值的档位一律视为「还在观望」
    LADDER = ("hold", "act_minimally", "act_carefully", "act_fully")

    def __init__(self, min_action: str = "act_minimally") -> None:
        min_action = str(min_action or "act_minimally").strip()
        if min_action not in self.LADDER:
            raise UnknownOpportunityKind(
                f"min_action 必须是 {self.LADDER} 之一，收到 {min_action!r}"
            )
        self.min_action = min_action

    def check(self, ctx: WatchContext) -> OpportunityHit:
        cur = (ctx.action_type or "").strip().lower()
        if not cur:
            return OpportunityHit.unclear("拿不到当前档位，判不了环境")
        if cur not in self.LADDER:
            # 认不出的档位 → 看不清而不是观望，否则新档位上线会被静默忽略
            return OpportunityHit.unclear(f"未识别的档位 {cur!r}")
        if self.LADDER.index(cur) >= self.LADDER.index(self.min_action):
            return OpportunityHit.yes(f"档位 {cur} ≥ {self.min_action}")
        return OpportunityHit.no(f"档位仍是 {cur}，未到 {self.min_action}")

    def describe(self) -> str:
        return f"环境升到 {self.min_action} 及以上"


class ManasWindow(Opportunity):
    """环境机会 —— **直接向 Manas 要一份读数**，看行动门有没有开。

    与 :class:`EnvironmentUpgrade` 的区别（这是本判据存在的理由）
    ----------------------------------------------------------
    两者都在比同一个 :data:`~deva.naja.watch.manas_lens.ACTION_LADDER`，
    但**输入来源完全不同**：

        EnvironmentUpgrade  读 ``ctx.action_type`` —— 那是**上一次问过决策中心
                           之后缓存里剩下的东西**（结论的残渣）
        ManasWindow         读 ``ctx.extras["manas_reading"]`` —— 由
                           :class:`~deva.naja.watch.manas_lens.ManasLens`
                           本轮主动向 Manas 要的

    「要不要问决策中心」依赖「问过决策中心的结果」，这道循环是 1 号守望当天
    必须靠 bootstrap + 沉默催醒才不死锁的根因。换成主动读数之后，那两道兜底
    从必需品降级成保险。

    三态的落点（每一步都不能折叠成 no）
    ----------------------------------
        没读数 / 类型不对   → unclear（Manas 不可用造成的沉默 ≠ 没机会）
        没时间戳            → unclear（不敢拿不知道什么时候算的分档当新鲜读数用）
        读数过期            → unclear
        没档位 / 认不出档位 → unclear
        给了门槛但没有分    → unclear（不能用 0 顶替「没给」）
        分数不够 / 档位不够 → **no**（这才是真的「条件不成立」）

    :param min_action: 至少要到哪一档才算「环境松了」
    :param min_score: 可选的 ``manas_score`` 门槛
    :param max_age_seconds: 读数保鲜期，超期按看不清处理
    """

    kind = "manas_window"

    def __init__(
        self,
        min_action: str = "act_minimally",
        min_score: Optional[float] = None,
        max_age_seconds: float = 600.0,
    ) -> None:
        min_action = str(min_action or ACTION_LADDER[1]).strip()
        if min_action not in ACTION_LADDER:
            raise UnknownOpportunityKind(
                f"min_action 必须是 {ACTION_LADDER} 之一，收到 {min_action!r}"
            )
        self.min_action = min_action
        self.min_score = None if min_score is None else float(min_score)
        self.max_age_seconds = abs(float(max_age_seconds))
        #: ❗沿变触发用：记住**上一次真的放行去问**的那个档位。
        #: 机会是「档位变了」，不是「档位还开着」—— 不记住的话，行动门
        #: 一开就会在每一个轮询周期里重复问一次决策中心（旧行为每 30s 一轮）。
        self._last_fired_action: Optional[str] = None

    def check(self, ctx: WatchContext) -> OpportunityHit:
        reading = ctx.value("manas_reading")
        if reading is None:
            return OpportunityHit.unclear("本轮没有 Manas 读数（看不清 ≠ 没机会）")
        if not isinstance(reading, ManasReading):
            return OpportunityHit.unclear(
                f"Manas 读数类型不对（{type(reading).__name__}），判不了档位"
            )
        if not reading.stamped:
            return OpportunityHit.unclear("Manas 读数没有可信时刻，不敢当新鲜读数用")

        age = reading.age(ctx.now)
        if age > self.max_age_seconds:
            return OpportunityHit.unclear(
                f"Manas 读数已过期 {age:.0f}s > 保鲜期 {self.max_age_seconds:.0f}s"
            )

        cur = (reading.action_type or "").strip().lower()
        if not cur:
            return OpportunityHit.unclear("Manas 没给出档位")

        idx = reading.ladder_index()
        if idx is None:
            # 认不出的档位 → 看不清而不是观望，否则新档位上线会被静默忽略
            return OpportunityHit.unclear(f"未识别的档位 {cur!r}")

        if self.min_score is not None:
            score = reading.manas_score
            if score is None:
                return OpportunityHit.unclear(
                    "Manas 没给 manas_score，无法比对门槛（不拿 0 顶替「没给」）"
                )
            if score < self.min_score:
                return OpportunityHit.no(
                    f"manas {score:.3f} < 门槛 {self.min_score:.3f}"
                )

        if idx < ACTION_LADDER.index(self.min_action):
            return OpportunityHit.no(f"{reading.describe()} 未到 {self.min_action}")
        if cur == self._last_fired_action:
            # 同一档位已经问过一次了。继续问只是把决策中心当成心跳用，
            # 真正的「再问一次」由 Watch 的沉默催醒（liveness）兜底。
            return OpportunityHit.no(
                f"档位 {cur} 已经问过一次，等档位变化再问（避免每轮都问）"
            )
        self._last_fired_action = cur
        tail = f"（{reading.gate_reason}）" if reading.gate_reason else ""
        return OpportunityHit.yes(f"{reading.describe()} ≥ {self.min_action}{tail}")

    def describe(self) -> str:
        extra = (
            f" 且 manas ≥ {self.min_score:.2f}"
            if self.min_score is not None
            else ""
        )
        return f"Manas 行动门开到 {self.min_action} 及以上{extra}"


class DeadlineWindow(Opportunity):
    """时间机会 —— 距结算点不足 N 分钟。

    ❗这条是「最后通牒」而不是普通机会：它的存在理由是防止守望无限期睡着。
    今天的底仓闸门里它就是那条「距收盘 30 分钟兜底」。
    """

    kind = "deadline_window"

    def __init__(self, minutes: float = 30.0) -> None:
        self.minutes = abs(float(minutes))

    def check(self, ctx: WatchContext) -> OpportunityHit:
        left = ctx.minutes_to_close
        if left is None:
            # 休市 / 未知 → **不触发**兜底，宁可继续等，也不替它放行
            return OpportunityHit.no("距收盘未知，不触发最后通牒")
        if left <= self.minutes:
            return OpportunityHit.yes(f"距结算仅 {left:.0f}min ≤ {self.minutes:.0f}min")
        return OpportunityHit.no(f"距结算 {left:.0f}min，未入窗口")

    def describe(self) -> str:
        return f"距结算不足 {self.minutes:.0f} 分钟"


class CallableOpportunity(Opportunity):
    """代码钩子 —— 声明式不够用时接一个 callable。

    约定签名 ``(ctx: WatchContext) -> OpportunityHit``。
    ❗返回值必须是 :class:`OpportunityHit`；返回 bool 会被拒绝 ——
    因为 bool 只有两态，会把 unknown 挤没。
    """

    kind = "callable"

    def __init__(
        self,
        fn: Callable[[WatchContext], OpportunityHit],
        describe: str = "",
    ) -> None:
        if not callable(fn):
            raise TypeError(f"钩子不是可调用对象：{fn!r}")
        self._fn = fn
        self._describe = describe or f"自定义钩子 {getattr(fn, '__name__', '?')}"

    def check(self, ctx: WatchContext) -> OpportunityHit:
        out = self._fn(ctx)
        if not isinstance(out, OpportunityHit):
            raise TypeError(
                f"钩子必须返回 OpportunityHit（三态），收到 {type(out).__name__}"
            )
        return out

    def describe(self) -> str:
        return self._describe


BUILTIN_KINDS: Dict[str, Callable[..., Opportunity]] = {
    PriceDeviation.kind: lambda **kw: PriceDeviation(**kw),
    EnvironmentUpgrade.kind: lambda **kw: EnvironmentUpgrade(**kw),
    ManasWindow.kind: lambda **kw: ManasWindow(**kw),
    DeadlineWindow.kind: lambda **kw: DeadlineWindow(**kw),
}


def register_opportunity_kind(
    kind: str, factory: Callable[..., Opportunity]
) -> None:
    """注册一个自定义机会类型。

    留给「不想改内核的接入方」用：主题的机会（叙事升温、供应链险下降）
    不该为了多一个判据就去动 watch 包。
    ❗同名覆盖是被允许的，但会记一条 WARNING —— 静默覆写会让「为什么据
    行为变了」变成查不到的事。
    """
    name = str(kind or "").strip()
    if not name:
        raise UnknownOpportunityKind("机会类型名不能为空")
    if not callable(factory):
        raise TypeError(f"工厂不是可调用对象：{factory!r}")
    if name in BUILTIN_KINDS:
        log.warning("[Opportunity] 机会类型 %s 被覆盖注册", name)
    BUILTIN_KINDS[name] = factory


def build_opportunity(spec: Mapping[str, Any]) -> Opportunity:
    """从声明式配置造一个机会判据。

    ``{"kind": "price_deviation", "pct": 1.2, "direction": "below"}``
    """
    if isinstance(spec, Opportunity):  # 允许直接传实例，混着写时不用分心
        return spec
    if callable(spec) and not isinstance(spec, Mapping):
        return CallableOpportunity(spec)
    if not isinstance(spec, Mapping):
        raise UnknownOpportunityKind(f"机会配置不是 dict：{type(spec).__name__}")

    kind = str(spec.get("kind") or "").strip()
    if not kind:
        raise UnknownOpportunityKind(f"机会配置缺 kind：{dict(spec)!r}")
    factory = BUILTIN_KINDS.get(kind)
    if factory is None:
        raise UnknownOpportunityKind(
            f"未知机会类型 {kind!r}；内置只有 {sorted(BUILTIN_KINDS)}"
        )
    params = {k: v for k, v in spec.items() if k != "kind"}
    try:
        return factory(**params)
    except TypeError as e:
        raise UnknownOpportunityKind(f"机会 {kind} 参数不对：{e}") from e
