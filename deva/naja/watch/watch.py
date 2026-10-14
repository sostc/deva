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

from .clock import MarketClock
from .objective import Objective, WatchContext
from .opportunity import Opportunity, OpportunityHit

log = logging.getLogger(__name__)

__all__ = [
    "WatchState",
    "Settlement",
    "WatchScan",
    "Watch",
    "ASK_LOG_MAXLEN",
    "CYCLE_LOG_MAXLEN",
    "ask_verdict_text",
]

#: 每个守望留多少条问询记录。够回看「最近为什么没买」，又不至于无限膨胀。
ASK_LOG_MAXLEN = 30

#: 循环守望留多少期归档。一期一条，够回看「这个长期持仓最近几周干了什么」。
CYCLE_LOG_MAXLEN = 20


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
    #: ★ 循环守望专用：**这一期看过了**，不是失败也不是达成。
    #: 只有 :attr:`Watch.recurring` 的守望才会走到这里 —— 长期持有的
    #: 语义就是「没有完成态」，但每一期都得有个终点（见类 docstring）。
    REVIEWED = "reviewed"


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
    #: ★循环守望：**到期不是终点，而是「这一期看过了」**。
    #:
    #: 用户原话（2026-10-14）：「希望长期来说持有科创 ETF 腾讯 qqq」。
    #: 这类意愿和「我想买英伟达」不是一回事 ——
    #:     * 买英伟达是**机会型**：等一个进场点，买到了就完成，守望消失
    #:     * 长期持有是**状态型**：买了不算完，跌了要回补、做 T 卖飞了要买回
    #: 但守望系统有一条硬纪律：**不准有无限期的守望**（没有结算点的守望
    #: 和死掉的线程长得一样）。循环守望就是这两者的和解办法 ——
    #: 把「永远」切成**一串有终点的周期**：每期到点结算成 ``reviewed``，
    #: 然后由 :meth:`WatchRegistry.renew` 自动挂上下一期。
    #: 于是纪律没破（每期都有终点），长期也表达了（整体不结束），
    #: 而且每一期都留痕 —— 事后能回答「这周它等了什么、问过几次」。
    recurring: bool = False
    #: ★★常驻守望：**问过一次就立刻重挂，永远在等下一次机会**。
    #:
    #: 用户原话（2026-10-14）：「这个做 t 的守望应该是持续一直存在的，
    #: 一直在等待机会来买卖」。
    #:
    #: 它和 :attr:`recurring` 回答的是**两个不同的问题**，不能混：
    #:     * ``recurring`` 是**时间到了就续**（定期回头看一眼）——
    #:       长期配置自己：不管有没有机会，一周期满就记「这期看过了」
    #:     * ``standing`` 是**抓到机会就续**（一直等下一次）——
    #:       做 T：这期抓到一个价差机会、问过决策中心了，下一期立刻继续等
    #:
    #: ❗结算语义也不同：常驻守望到期是「这期没轮到我」（``expired``，
    #: 不是失败）；被问过一次是「这期抓到了」（``reached``）。两者都会
    #: 重挂，唯独人工撤下（``abandoned``）不重挂 ——
    #: 撤下必须是**真终止**，否则它只是个视觉动作。
    standing: bool = False
    #: ★市场时钟：**闭市时时钟停走**（``watch/clock.py``）。
    #:
    #: 守望的窗口量的是「等多久才算白等」，而这个数只在开盘时有意义。
    #: 做 T 守望一期 30 分钟，若半夜挂上，墙上时钟半小时后到期 —— 那半小时
    #: 市场根本没开，「这期没轮到我」是一次纯记账的白记，而且开盘那一刻它
    #: 正好刚过期，最该问到的开盘波动反而漏了。
    #:
    #: ``None`` = 用墙上时钟（**原行为**，也是所有既有用例的口径）。
    #: ❗认不出的市场由时钟自己退回墙上差，守望不猜 —— 把「市场不认识」
    #: 当「市场关着」会让一个拼错 market 的守望永远安静。
    clock: Optional[MarketClock] = None

    def __post_init__(self) -> None:
        if self.recurring and self.standing:
            # 一个是「到期续」、一个是「抓到就续」，同时为真时续期时机无法判定
            raise ValueError(
                f"守望 {self.objective.id} 不能既是循环（recurring）又是常驻"
                "（standing）—— 两者的续期时机冲突，只能选一个"
            )
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

        # -- 循环守望记账 -----------------------------------------------
        #: 已完成的期数。第 1 期从 ``armed_at`` 开始算，每次续期 +1。
        self.cycles: int = 0
        #: 每期归档。看「这个长期持仓最近几周都干了什么」靠它。
        self.cycle_log: deque = deque(maxlen=CYCLE_LOG_MAXLEN)
        #: ❗「本期」与「累计」必须分开：UI 要能同时回答
        #: 「这一期问过几次」和「这个长期持仓总共问过几次」。
        #: ``scans`` / ``fires`` / ``asked`` 等是**本期**；下面是累计。
        self.total_scans: int = 0
        self.total_fires: int = 0
        self.total_asked: int = 0
        self.total_granted: int = 0
        self.total_denied: int = 0
        self.total_unanswered: int = 0

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
        # -- 「这一轮故意没问」的留痕 ------------------------------------
        #: ❗省掉的问询必须留痕。闭市不问是**决定**，链路没取到是**故障**，
        #: 两者若都表现为「这一轮没问」，页面上就再也分不清了 —— 那正是
        #: 静默失效家族的标准形态。所以跳过要计数、要带原因、要显示。
        self.skipped_closed: int = 0
        self.total_skipped: int = 0
        self.last_skip_reason: str = ""
        self.last_skip_at: Optional[float] = None
        self.max_silence_seconds = (
            600.0
            if self.max_silence_seconds is None
            else max(0.0, float(self.max_silence_seconds))
        )

    # ------------------------------------------------------------------
    @property
    def watch_id(self) -> str:
        return self.objective.id

    # -- 时间：一律走「算数的时间」，有市场时钟就按在场时间 ------------
    def _elapsed(self, t0: float, t1: float) -> float:
        """``t0 → t1`` 之间**算数**的秒数。

        有市场时钟时是**在场秒数**（闭市/午休/周末不算），没有就是墙上差。
        ❗所有时间量都必须过这个方法 —— 直接拿 ``now - armed_at`` 会在闭市
        期间照走，把窗口悄悄耗光。
        """
        if self.clock is None:
            return max(0.0, float(t1) - float(t0))
        return self.clock.elapsed(self.objective.market, t0, t1)

    def _wall_at(self, t0: float, seconds: float) -> float:
        """从 ``t0`` 起、算数时间走过 ``seconds`` 秒之后的**墙上时刻**。"""
        if self.clock is None:
            return float(t0) + float(seconds)
        return self.clock.wall_at(self.objective.market, t0, seconds)

    @property
    def market_clock_on(self) -> bool:
        return self.clock is not None

    @property
    def deadline(self) -> float:
        """到期的**墙上时刻**。在场时钟下它可能是次日开盘后某刻。

        ❗不要拿 ``deadline - now`` 当剩余时间 —— 中间隔着闭市，那段不算数。
        剩余时间一律用 :meth:`remaining`。
        """
        return self._wall_at(self.armed_at, float(self.max_wait_seconds or 0.0))

    def remaining(self, now: Optional[float] = None) -> float:
        """距结算还剩多少**算数秒**。负数 = 已超时待结算。"""
        t = now if now is not None else time.time()
        return float(self.max_wait_seconds or 0.0) - self._elapsed(self.armed_at, t)

    def age(self, now: Optional[float] = None) -> float:
        t = now if now is not None else time.time()
        return self._elapsed(self.armed_at, t)

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
        self.total_scans += 1
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
        # ❗沉默按**在场时间**算：闭市干等不算沉默，开盘那一刻才该被催。
        silence = self._elapsed(self.last_prod_at, now)
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
            self.total_fires += 1
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

    def acknowledge(self, granted: Optional[bool], reason: str = "",
                    now: Optional[float] = None) -> None:
        """把「问完了」这件事回写给守望。

        ``granted=False`` 不是失败，是**继续等**；守望回到 ARMED。

        ★常驻守望（:attr:`standing`）在这里**立刻结算**：对它而言
        「问过一次」本身就是这一期的终点 —— 抓到了机会、去问了、有结论了，
        下一期重新开始等。所以这里结算成 ``reached``，等 :meth:`arm` 重挂。

        ❗``granted=None``（**没人去问**）绝不能走到这一步：那是链路断了，
        把它记成「这期抓到了」是假成功 —— 守望必须继续挂着等。
        """
        t = now if now is not None else time.time()
        self.last_reason = reason
        self._to(WatchState.ARMED if not granted else WatchState.TRIGGERED, t)
        if self.standing and granted is not None:
            self.settle(
                Settlement.REACHED,
                f"第 {self.cycles + 1} 期抓到机会并问过决策中心"
                f"（{'放行' if granted else '未批准'}）",
                now=t,
            )

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
        self.total_asked += 1
        if verdict is None:
            self.unanswered_count += 1
            self.total_unanswered += 1
        elif verdict:
            self.granted_count += 1
            self.total_granted += 1
        else:
            self.denied_count += 1
            self.total_denied += 1
        return entry

    def arm(self, now: Optional[float] = None, reason: str = "") -> Dict[str, Any]:
        """给**循环 / 常驻**守望挂上下一期。只有这两类能用。

        ❗为什么结算和续期要分成两步：``settle`` 是事实（这一期结束了），
        ``arm`` 是决定（还要继续）。合成一步的话，「最后一期」就没法表达了 ——
        UI 上永远看不到「已经停了」，只能看到一个又一期的循环。

        上一期的统计会被**归档**而不是丢弃：长期持仓最值钱的信息恰恰是
        「这几期它都在等什么、问过几次、被否了几次」。
        """
        if not (self.recurring or self.standing):
            raise ValueError(
                f"守望 {self.watch_id} 既不是循环（recurring）也不是常驻"
                "（standing），不能续期 —— 一次性守望到期就该结束，"
                "重新挂请用 declare()"
            )
        t = now if now is not None else time.time()
        summary = {
            "cycle": max(1, self.cycles),
            "armed_at": round(self.armed_at, 3),
            "settled_at": (
                round(self.settled_at, 3) if self.settled_at is not None else None
            ),
            "outcome": self.settlement.value if self.settlement else "",
            "reason": self.settlement_reason or reason,
            "scans": self.scans,
            "fires": self.fires,
            "asked": self.asked,
            "granted_count": self.granted_count,
            "denied_count": self.denied_count,
            "unanswered_count": self.unanswered_count,
        }
        self.cycle_log.append(summary)
        self.cycles += 1
        self.state = WatchState.ARMED
        self.armed_at = t
        self.last_prod_at = t
        self.last_state_change_at = t
        self.settlement = None
        self.settlement_reason = ""
        self.settled_at = None
        self._bootstrapped = False
        # 本期计数归零（累计计数 total_* 保持不动）
        self.scans = 0
        self.fires = 0
        self.unknown_scans = 0
        self.prods = 0
        self.asked = 0
        self.granted_count = 0
        self.denied_count = 0
        self.unanswered_count = 0
        # 本期「故意没问」的计数归零（累计 total_skipped 保持不动）
        self.skipped_closed = 0
        self.last_skip_reason = ""
        self.last_skip_at = None
        log.info(
            "[Watch] %s 进入第 %d 期（%s）",
            self.watch_id, self.cycles, reason or "周期性续期",
        )
        return summary

    def cycle_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """最近若干期的归档（新的在前）。"""
        rows = list(self.cycle_log)
        if limit and limit > 0:
            rows = rows[-int(limit):]
        return list(reversed(rows))

    def note_skip(self, reason: str, now: Optional[float] = None) -> None:
        """记一次「这一轮**故意**没问」。

        ❗闭市不问是决定，链路没取到是故障。两者都表现为「这一轮没问」，
        只有**带原因的计数**能把它们分开：看见「已收盘，距开盘 9h12min」
        就知道是有意跳过，看见计数不动而行情也取不到，才是链路断了。
        """
        self.skipped_closed += 1
        self.total_skipped += 1
        self.last_skip_reason = str(reason or "")
        self.last_skip_at = now if now is not None else time.time()

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
            "silence_sec": round(self._elapsed(self.last_prod_at, t), 1),
            "unknown_scans": self.unknown_scans,
            "last_reason": self.last_reason,
            # -- 时间与市场状态：为什么这一轮可能根本没问 --
            "market_clock": bool(self.clock is not None),
            "skipped_closed": self.skipped_closed,
            "last_skip_reason": self.last_skip_reason,
            "last_skip_at": self.last_skip_at,
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
            # -- 循环 / 常驻守望：这两类的时间维度 --
            "recurring": bool(self.recurring),
            "standing": bool(self.standing),
            "cycles": self.cycles,
            "total_scans": self.total_scans,
            "total_fires": self.total_fires,
            "total_asked": self.total_asked,
            "total_granted": self.total_granted,
            "total_denied": self.total_denied,
            "total_unanswered": self.total_unanswered,
            "recent_cycles": self.cycle_history(3),
        }
