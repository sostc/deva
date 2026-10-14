"""守望（Watch）—— 把一个目标挂到一组机会上，然后休眠。

生命周期
========
    ARMED ──机会成立──▶ TRIGGERED ──去问决策中心──▶ 执行 / 被否 ──▶ 回 ARMED
      │                                                              ▲
      └────────────── 结算点到了（达成 / 过期 / 放弃）──▶ SETTLED ────┘（不可复活）

❗``TRIGGERED`` 的语义要念准：它表示**「值得去问一次」**，不是「已经批准」。
批准权在决策中心手里，守望从来不自己下单。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Union

from .objective import Objective, WatchContext
from .opportunity import Opportunity, OpportunityHit

log = logging.getLogger(__name__)

__all__ = [
    "WatchState",
    "Settlement",
    "WatchScan",
    "Watch",
    "ASK_LOG_MAXLEN",
    "ask_verdict_text",
]

#: 每个守望留多少条问询记录。够回看「最近为什么没买」，又不至于无限膨胀。
ASK_LOG_MAXLEN = 30


def ask_verdict_text(granted: Optional[bool]) -> str:
    """把三态结论翻成人话。

    ❗``None``（没人去问）必须跟 ``False``（问了但没批）**分开写**：
    这两个都表现为「没有成交」，但前者是链路断了、后者是决策在观望，
    混在一起就会把「票没人消费」这种静默失效伪装成「策略在等」。
    """
    if granted is None:
        return "没人去问"
    return "放行" if granted else "未批准"


class WatchState(str, Enum):
    ARMED = "armed"          # 挂着，还在等
    TRIGGERED = "triggered"  # 机会成立，值得去问一次
    SETTLED = "settled"      # 已结算，终态


class Settlement(str, Enum):
    REACHED = "reached"      # 目标达成了
    EXPIRED = "expired"      # 到点没达成 —— 必须显式记录，不是无声消失
    ABANDONED = "abandoned"  # 主动放弃（换策略、撤单、人工介入）


@dataclass
class WatchScan:
    """一次扫描的结果。**调用方主要看两个字段**。"""

    watch_id: str
    state: WatchState
    #: 要不要去问决策中心（机会成立了）
    should_ask: bool
    #: 本轮有没有判据「看不清」。❗True 时即使没触发也必须被上层看见
    unknown: bool = False
    #: 成立的机会类型
    fired_kinds: List[str] = field(default_factory=list)
    #: 所有判据的一句话理由，供心跳 / UI 展示
    reasons: List[str] = field(default_factory=list)

    def why(self) -> str:
        return "；".join(self.reasons) if self.reasons else "（无判据）"


@dataclass
class Watch:
    """一个挂起的守望。

    :param opportunities: 机会判据列表
    :param mode: ``"any"`` 任一成立即值得问一次；``"all"`` 要求全部成立
    :param max_wait_seconds: 覆盖目标上的值；两者都没有会抛
        :class:`~deva.naja.watch.objective.MissingSettlementPoint`
    """

    objective: Objective
    opportunities: Sequence[Opportunity] = field(default_factory=tuple)
    mode: str = "any"
    armed_at: float = field(default_factory=time.time)
    max_wait_seconds: Optional[float] = None
    #: ❗活性保证：超过这么久没任何机会成立，就强制托一次。
    #: 没有这条会退化成本仓库最痛的那种死锁 ——「闸门接好了，但从没放行过」。
    #: 典型场景：环境机会要读 ``action_type``，而 ``action_type`` 得问了决策中心
    #: 才有；若一直问不到，守望就永远安静。沉默既可能是耐心，也可能是死了。
    max_silence_seconds: Optional[float] = None
    #: **首次扫描就要去问一次**。
    #:
    #: ❗默认False 是有意的：多数守望（价格类）首次就该安静，
    #: 无条件催问会让「还没到时候」的第一轮被白白浪费掉。
    #: 但**环境类判据必须开** —— 它的输入 ``action_type`` 只有问过才存在，
    #: 不 bootstrap 就是「永远拿不到第一份 → 永远 unknown → 再也不问」的死锁。
    bootstrap: bool = False

    def __post_init__(self) -> None:
        if not self.opportunities:
            raise ValueError(f"守望 {self.objective.id} 没有挂任何机会判据")
        if str(self.mode) not in ("any", "all"):
            raise ValueError(f"mode 只支持 any/all，收到 {self.mode!r}")
        wait = self.max_wait_seconds or self.objective.max_wait_seconds
        if wait is None or float(wait) <= 0:
            # Objective 构造时已查过一次；这里是给「覆盖值」兜底
            from .objective import MissingSettlementPoint

            raise MissingSettlementPoint(f"守望 {self.objective.id} 没有结算点")
        self.max_wait_seconds = float(wait)
        self.objective.max_wait_seconds = self.max_wait_seconds

        # -- 运行期记账 -------------------------------------------------
        self.state: WatchState = WatchState.ARMED
        self.scans: int = 0
        self.fires: int = 0
        self.unknown_scans: int = 0
        self.last_scan_at: Optional[float] = None
        self.last_reason: str = ""
        self.last_state_change_at: float = self.armed_at
        self.settlement: Optional[Settlement] = None
        self.settlement_reason: str = ""
        self.settled_at: Optional[float] = None
        #: 上一次「值得问」的时刻，用来度量沉默多久了
        self.last_prod_at: float = self.armed_at
        self._bootstrapped: bool = False
        self.prods: int = 0

        # -- 执行记录 ---------------------------------------------------
        #: ❗「守望在等」这件事看不见就等于没发生：UI 要回答「这个想法问过
        #: 几次、每次决策中心怎么说的」，所以问询必须留痕。
        self.ask_log: deque = deque(maxlen=ASK_LOG_MAXLEN)
        self.asked: int = 0
        self.granted_count: int = 0
        self.denied_count: int = 0
        self.unanswered_count: int = 0
        self.last_ask_at: Optional[float] = None
        self.last_granted: Optional[bool] = None
        self.max_silence_seconds = (
            600.0
            if self.max_silence_seconds is None
            else max(0.0, float(self.max_silence_seconds))
        )

    # ------------------------------------------------------------------
    @property
    def watch_id(self) -> str:
        return self.objective.id

    @property
    def deadline(self) -> float:
        return self.armed_at + float(self.max_wait_seconds or 0.0)

    def remaining(self, now: Optional[float] = None) -> float:
        """距结算还剩多少秒。负数 = 已超时待结算。"""
        return self.deadline - (now if now is not None else time.time())

    def age(self, now: Optional[float] = None) -> float:
        t = now if now is not None else time.time()
        return t - self.armed_at

    def is_overdue(self, now: Optional[float] = None) -> bool:
        return self.state != WatchState.SETTLED and self.remaining(now) <= 0

    # ------------------------------------------------------------------
    def scan(
        self,
        ctx: Optional[WatchContext],
        now: Optional[float] = None,
    ) -> WatchScan:
        """扫一轮。

        :param ctx: 观测面。``None`` = **这一轮压根没取到观测** ——
            那是 unknown，不是「没机会」。
        :param now: 本轮时刻。❗显式传进来，不要在这里猜时钟：
            ``ctx`` 缺失时若退回真实墙上时钟，会跟 armed_at（可能是测试用例的
            逻辑时钟）混算出一个巨大的沉默时长，活性兜底立刻被误触。
            「买了 HD 图的时间」和「守望诞生的时间」必须是同一把尺子。
        """
        self.scans += 1
        now = (
            now if now is not None
            else (ctx.now if ctx is not None else time.time())
        )
        self.last_scan_at = now

        if self.state == WatchState.SETTLED:
            return WatchScan(
                self.watch_id, self.state, False,
                reasons=[f"已结算（{self.settlement}）"],
            )

        hits: List[OpportunityHit] = []
        reasons: List[str] = []
        unknown = False

        if ctx is None:
            unknown = True
            for op in self.opportunities:
                hits.append(OpportunityHit.unclear("本轮没有观测面"))
                reasons.append(f"{op.kind}: 无观测")
        else:
            for op in self.opportunities:
                hit = op.check(ctx)
                hits.append(hit)
                reasons.append(f"{op.kind}: {hit.reason or ('成立' if hit.fired else '未成立')}")
                if hit.unknown:
                    unknown = True

        fired = [h.fired for h in hits]
        decided = all(fired) if self.mode == "all" else any(fired)
        # ❗unknown 参与但未成立时**不许放行**：看不清就是看不清
        if decided and unknown and self.mode == "all":
            decided = False

        if unknown:
            self.unknown_scans += 1

        # -- 活性兜底：bootstrap 或沉默太久就强制托一次 ------------------
        silence = now - self.last_prod_at
        need_seed = self.bootstrap and not self._bootstrapped
        if (
            not decided
            and self.max_silence_seconds > 0
            and (need_seed or silence >= self.max_silence_seconds)
        ):
            self._bootstrapped = True
            decided = True
            self.prods += 1
            reasons.append(
                "liveness: 首次需要建立基线，先问一次"
                if need_seed
                else f"liveness: 沉默 {silence:.0f}s 已达上限 "
                     f"{self.max_silence_seconds:.0f}s，强制再问一次"
            )

        if decided:
            self.fires += 1
            self.last_prod_at = now
            natural = [r for r in reasons if not r.startswith("liveness:")]
            if natural:
                self.last_reason = "；".join(natural)[:300]
            self._to(WatchState.TRIGGERED, now)
        elif self.state == WatchState.TRIGGERED:
            self._to(WatchState.ARMED, now)

        kinds = [
            op.kind for op, h in zip(self.opportunities, hits) if h.fired
        ]
        return WatchScan(
            watch_id=self.watch_id,
            state=self.state,
            should_ask=decided,
            unknown=unknown,
            fired_kinds=kinds,
            reasons=reasons,
        )

    def acknowledge(self, granted: bool, reason: str = "",
                    now: Optional[float] = None) -> None:
        """把「问完了」这件事回写给守望。

        ``granted=False`` 不是失败，是**继续等**；守望回到 ARMED。
        """
        t = now if now is not None else time.time()
        self.last_reason = reason
        self._to(WatchState.ARMED if not granted else WatchState.TRIGGERED, t)

    def record_ask(
        self,
        granted: Optional[bool],
        reason: str = "",
        now: Optional[float] = None,
        fired_kinds: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """记一次「去问了，结果是这样」。

        :param granted: ``True`` 放行 / ``False`` 问了但没批 / ``None`` **没人去问**。
            ❗三态：``None`` 是链路断了（没接执行器、或执行器没给结论），
            跟「问过、决策中心说再等等」是两回事。合成两态的话，UI 上就分不清
            「守望在耐心等」和「票开出去没人领」—— 后者是本仓库头号病理。
        """
        t = now if now is not None else time.time()
        verdict = None if granted is None else bool(granted)
        entry = {
            "ts": round(t, 3),
            "time": datetime.fromtimestamp(t).strftime("%m-%d %H:%M:%S"),
            "granted": verdict,
            "verdict": ask_verdict_text(verdict),
            "reason": str(reason or ""),
            "fired": list(fired_kinds or ()),
        }
        self.ask_log.append(entry)
        self.last_ask_at = t
        self.last_granted = verdict
        self.asked += 1
        if verdict is None:
            self.unanswered_count += 1
        elif verdict:
            self.granted_count += 1
        else:
            self.denied_count += 1
        return entry

    def ask_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """最近若干条问询记录（新的在前）。"""
        rows = list(self.ask_log)
        if limit and limit > 0:
            rows = rows[-int(limit):]
        return list(reversed(rows))

    def settle(
        self,
        outcome: Union[Settlement, str],
        reason: str = "",
        now: Optional[float] = None,
    ) -> None:
        """结算。终态，不可复活。"""
        t = now if now is not None else time.time()
        if isinstance(outcome, str):
            outcome = Settlement(outcome)
        self.settlement = outcome
        self.settlement_reason = reason
        self.settled_at = t
        self._to(WatchState.SETTLED, t)

    def _to(self, state: WatchState, now: float) -> None:
        if state != self.state:
            self.state = state
            self.last_state_change_at = now

    # ------------------------------------------------------------------
    def waiting_for(self) -> str:
        """给 UI / 心跳用的一句话：「我在等什么」。"""
        return "；".join(op.describe() for op in self.opportunities)

    def to_row(self, now: Optional[float] = None) -> Dict[str, Any]:
        """一行快照。**UI 与心跳都从这里取**，避免两边口径不一致。"""
        t = now if now is not None else time.time()
        return {
            "id": self.watch_id,
            "kind": self.objective.kind,
            "subject": self.objective.subject,
            "market": self.objective.market,
            "state": self.state.value,
            "note": self.objective.describe(),
            "waiting_for": self.waiting_for(),
            "age_sec": round(self.age(t), 1),
            "remaining_sec": round(self.remaining(t), 1),
            "scans": self.scans,
            "fires": self.fires,
            "prods": self.prods,
            "silence_sec": round(t - self.last_prod_at, 1),
            "unknown_scans": self.unknown_scans,
            "last_reason": self.last_reason,
            # -- 执行记录：问过几次、放行/被否/没人问各多少 --
            "asked": self.asked,
            "granted_count": self.granted_count,
            "denied_count": self.denied_count,
            "unanswered_count": self.unanswered_count,
            "last_ask_at": self.last_ask_at,
            "last_granted": self.last_granted,
            "last_ask_age_sec": (
                None if self.last_ask_at is None else round(t - self.last_ask_at, 1)
            ),
            "settlement": self.settlement.value if self.settlement else "",
            "settlement_reason": self.settlement_reason,
            "recent_asks": self.ask_history(5),
        }
