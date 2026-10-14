"""CorePosition——核心底仓守护与「必须买回」回购义务账本

别名/关键词: 底仓守护、做T回购义务、核心份额、core position、buyback obligation

设计动机
--------
需求原话是这么说的：

    「我们应该长期持有一个半导体指数……中间可以做 T，
      但做完之后一定要买回来，保证我们长期持有。」

这句话可以拆成两条**互不相同的硬约束**：

1. **长期持有不可侵蚀**
   底仓不是为了搏它上涨，而是**买下"随时能做 T 的权利"**——一份期权。
   空仓的人遇到今天这种 6% 振幅的日子只能干看着。所以 target_shares 以内的份额
   **任何时候都不参与卖出**，否则等于把自己的期权卖掉了。

2. **卖出必须买回**
   倒 T（先卖后买）卖出的一瞬间，份额确实少了 N 份。这 N 份必须回来。
   所以它不只是"记账"，而是一笔**待履行的义务**：``OPEN → FULFILLED / EXPIRED``。
   到期没买回要能强制补回——**宁可买贵，也不能让份额流失**。
   这正是用户反复强调的"保证我们长期持有"。

为什么需要「欠着的份额」这个概念
--------------------------------
倒 T 卖出后，真实持仓少了 N 份，但那 N 份**约定要回来**。若不加区分地拿
"当前 OPEN 份额"去算可用轮换额度，同一份配额会被重复卖出，第二轮就开始啃食
核心底仓。因此一切额度都必须建立在：

    carried_in = 今日开盘时手里有的份额
               = (entry_time < session_open 且仍 OPEN 的份额)     # 昨夜传承下来的
               + (今日产生的回购义务份额)                          # 今天卖掉的，约定要回来

注意这里刻意**排除当日新买入的份额**：A股 T+1，当日买入当日不可卖。
这也是为什么必须显式给出 session_open——拿不到就不能假装知道。

缺登记 = 不允许做 T
------------------
``plan`` 不存在或 target<=0 时，``session_quota`` 恒为 0，即一律不允许倒 T。
这是刻意的**保守默认**：宁可错过机会，也不能在没登记意图的标的上偷偷卖出。
项目里"合法的空比异常更危险"这条教训在本模块的对应物就是这个默认值。
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, fields as dc_fields
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

CORE_POSITION_TABLE = "naja_core_position_ledger"

OBLIGATION_OPEN = "OPEN"
OBLIGATION_FULFILLED = "FULFILLED"
OBLIGATION_EXPIRED = "EXPIRED"

#: 调用方给不出收盘时间时的兜底：默认要求 1 小时内买回。
#: 宁短勿长——到期未买回会触发强制补回，短一点更安全。
DEFAULT_FALLBACK_DEADLINE = 3600.0

#: 调用方给不出开盘时间时，用于近似"当日"的滚动窗口。
#: A股一个交易日连盘前约 5.5 小时，取 8 小时偏保守（更少的仓位被判为可卖）。
DEFAULT_SESSION_WINDOW = 8 * 3600.0


@dataclass
class CorePlan:
    """某个标的的长期持有目标份额。"""

    stock_code: str
    stock_name: str = ""
    target_shares: float = 0.0
    enabled: bool = True
    created_time: float = 0.0
    updated_time: float = 0.0
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "target_shares": self.target_shares,
            "enabled": self.enabled,
            "created_time": self.created_time,
            "updated_time": self.updated_time,
            "note": self.note,
        }


@dataclass
class BuybackObligation:
    """一笔「卖出后必须买回」的义务。

    只有倒 T（先卖后买）会产生它。正 T（先买后卖）份额本来就守恒，不需要。
    """

    obligation_id: str
    stock_code: str
    quantity: float
    sell_price: float
    created_time: float
    deadline: float
    session_key: str = ""
    status: str = OBLIGATION_OPEN
    buyback_price: float = 0.0
    fulfilled_time: float = 0.0
    forced: bool = False
    note: str = ""

    @property
    def is_open(self) -> bool:
        return self.status == OBLIGATION_OPEN

    @property
    def realized_edge(self) -> float:
        """这笔倒 T 兑现的差价（金额，正=赚钱=降低持仓成本）。"""
        if self.status != OBLIGATION_FULFILLED or self.quantity <= 0:
            return 0.0
        return (self.sell_price - self.buyback_price) * self.quantity

    @property
    def edge_pct(self) -> float:
        """这笔倒 T 的差价百分比（正=成功高抛低吸）。"""
        if self.status != OBLIGATION_FULFILLED or self.sell_price <= 0:
            return 0.0
        return (self.sell_price - self.buyback_price) / self.sell_price * 100

    def is_overdue(self, now: Optional[float] = None) -> bool:
        if not self.is_open:
            return False
        return (now if now is not None else time.time()) > self.deadline

    def to_dict(self) -> Dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "stock_code": self.stock_code,
            "quantity": self.quantity,
            "sell_price": self.sell_price,
            "created_time": self.created_time,
            "deadline": self.deadline,
            "session_key": self.session_key,
            "status": self.status,
            "buyback_price": self.buyback_price,
            "fulfilled_time": self.fulfilled_time,
            "forced": self.forced,
            "note": self.note,
            "realized_edge": self.realized_edge,
            "edge_pct": self.edge_pct,
            "open": self.is_open,
        }


class CorePositionLedger:
    """核心底仓守护 + 回购义务账本。

    本类**不做任何买卖**，只回答"能不能卖、卖了要还多少、还了没有"。
    真正的下单在 ``t_rotation.TRotationEngine``，它必须拿着本账本的许可才能动手。
    """

    def __init__(
        self,
        table: str = CORE_POSITION_TABLE,
        persist: bool = True,
        fallback_deadline: float = DEFAULT_FALLBACK_DEADLINE,
        session_window: float = DEFAULT_SESSION_WINDOW,
    ):
        self._plans: Dict[str, CorePlan] = {}
        self._obligations: Dict[str, BuybackObligation] = {}
        self._lock = threading.RLock()
        self._persist = persist
        self._fallback_deadline = fallback_deadline
        self._session_window = session_window

        self._db = None
        self._degraded = False
        self._warned_no_session_open = False

        if persist:
            try:
                from deva import NB

                self._db = NB(table)
            except Exception as e:  # pragma: no cover - 依赖环境
                self._degraded = True
                log.warning(
                    f"[CorePosition] 持久化不可用，降级为内存账本: {e}。"
                    f"重启后回购义务会丢失，务必检查依赖。"
                )

        self._load()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def _load(self):
        if self._db is None:
            return
        try:
            data = self._db.get("ledger", {})
            plan_fields = {f.name for f in dc_fields(CorePlan)}
            ob_fields = {f.name for f in dc_fields(BuybackObligation)}

            for code, raw in (data.get("plans") or {}).items():
                if isinstance(raw, dict):
                    self._plans[code] = CorePlan(
                        **{k: v for k, v in raw.items() if k in plan_fields}
                    )
            for oid, raw in (data.get("obligations") or {}).items():
                if isinstance(raw, dict):
                    self._obligations[oid] = BuybackObligation(
                        **{k: v for k, v in raw.items() if k in ob_fields}
                    )
            if self._plans or self._obligations:
                log.info(
                    f"[CorePosition] 已加载 {len(self._plans)} 份底仓计划、"
                    f"{len(self._obligations)} 条回购义务"
                )
        except Exception as e:
            self._degraded = True
            log.error(f"[CorePosition] 加载失败，本次以空账本运行: {e}")

    def _save(self):
        if self._db is None:
            return
        try:
            self._db["ledger"] = {
                "plans": {c: p.to_dict() for c, p in self._plans.items()},
                "obligations": {
                    o: ob.to_dict() for o, ob in self._obligations.items()
                },
            }
        except Exception as e:
            self._degraded = True
            log.error(f"[CorePosition] 保存失败（内存态仍在）: {e}")

    # ------------------------------------------------------------------
    # 交易日会话
    # ------------------------------------------------------------------
    @staticmethod
    def session_key(now: float, session_open_ts: Optional[float] = None) -> str:
        """当日交易会话标识。

        判"是不是同一天"需要交易日历，拿不到就退化成日期字符串 + 近似窗口。
        这里刻意不做"聪明"推断：调用方能给 session_open_ts 就优先用它。
        """
        ts = session_open_ts if session_open_ts else now
        return time.strftime("%Y-%m-%d", time.localtime(ts))

    def resolve_session_open(
        self, now: float, session_open_ts: Optional[float] = None
    ) -> float:
        """确定"当日开盘时刻"，用于 T+1 判断哪些仓位是当日建仓不可卖。

        给不出时降级为 ``now - session_window``，并向调用方明示这是近似值。
        """
        if session_open_ts:
            return session_open_ts
        if not self._warned_no_session_open:
            self._warned_no_session_open = True
            log.warning(
                f"[CorePosition] 未提供 session_open_ts，"
                f"退化为 {self._session_window / 3600:.1f}h 滚动窗口近似判断当日仓位。"
                f"接入时应传入真实开盘时间。"
            )
        return now - self._session_window

    # ------------------------------------------------------------------
    # 底仓计划
    # ------------------------------------------------------------------
    def set_plan(
        self,
        stock_code: str,
        target_shares: float,
        stock_name: str = "",
        note: str = "",
    ) -> CorePlan:
        """登记一份长期持有目标。target_shares<=0 等同于撤销计划。"""
        with self._lock:
            existing = self._plans.get(stock_code)
            now = time.time()
            plan = CorePlan(
                stock_code=stock_code,
                stock_name=stock_name or (existing.stock_name if existing else ""),
                target_shares=max(0.0, float(target_shares)),
                enabled=True,
                created_time=existing.created_time if existing else now,
                updated_time=now,
                note=note,
            )
            self._plans[stock_code] = plan
            self._save()
            log.info(
                f"[CorePosition] 登记底仓计划: {stock_code} "
                f"目标 {plan.target_shares:.0f} 份"
                + (f" ({plan.stock_name})" if plan.stock_name else "")
            )
            return plan

    def remove_plan(self, stock_code: str) -> bool:
        with self._lock:
            existed = self._plans.pop(stock_code, None) is not None
            if existed:
                self._save()
                log.info(f"[CorePosition] 撤销底仓计划: {stock_code}")
            return existed

    def get_plan(self, stock_code: str) -> Optional[CorePlan]:
        return self._plans.get(stock_code)

    def list_plans(self) -> List[CorePlan]:
        return list(self._plans.values())

    # ------------------------------------------------------------------
    # 份额视图
    # ------------------------------------------------------------------
    def _open_positions(self, portfolio, stock_code: str) -> List[Any]:
        if portfolio is None:
            return []
        return [
            p
            for p in portfolio.get_all_positions(status="OPEN")
            if getattr(p, "stock_code", None) == stock_code
        ]

    @staticmethod
    def _sellable_cap(positions) -> Optional[float]:
        """组合给出的**真实可卖上限**（富途 ``can_sell_qty``），虚拟盘为 None。

        为什么要有它
        ------------
        本账本判断"哪些份额能卖"一直靠 ``entry_time < 今日开盘``。虚拟盘里
        每个持仓都有建仓时间，这个判据成立；但**富途的持仓接口根本没有
        建仓时间字段**（:mod:`futu_sim_portfolio` 只能把 entry_time 填成 0，
        一律判成"昨夜传承"）。

        于是 A 股当日买入的份额会被误判成可卖 —— 卖单发出去被富途以 T+1
        为由直接拒单，做 T 的卖腿悬空，而买入腿已经成交，份额凭空多出来。

        ``can_sell_qty`` 是富途自己算好的权威值（已扣 T+1 冻结），用它做
        上限最可靠。虚拟盘没有这个字段 → 返回 None → 行为完全不变。
        """
        vals: List[float] = []
        for p in positions or []:
            raw = getattr(p, "sellable_qty", None)
            if raw is None:
                continue
            try:
                vals.append(max(0.0, float(raw)))
            except (TypeError, ValueError):
                continue
        if not vals:
            return None
        return sum(vals)

    def carried_in_shares(
        self,
        stock_code: str,
        portfolio,
        now: Optional[float] = None,
        session_open_ts: Optional[float] = None,
    ) -> float:
        """今日开盘时手里有的份额（T+1 口径）。

        = 昨夜传承下来的、今天还没被卖掉的部分 + 今天卖掉但约定要买回的部分。

        刻意排除当日新建的仓位：A股 T+1 不允许当日买入当日卖出。
        """
        now = time.time() if now is None else now
        session_open = self.resolve_session_open(now, session_open_ts)
        session_key = self.session_key(now, session_open_ts)

        positions = self._open_positions(portfolio, stock_code)
        inherited = sum(
            float(getattr(p, "quantity", 0.0) or 0.0)
            for p in positions
            if float(getattr(p, "entry_time", 0.0) or 0.0) < session_open
        )
        # ❗真实可卖上限（富途 can_sell_qty）：A 股当日买入的份额在券商眼里
        # 卖不掉，必须在这里扣掉，不能只信 entry_time。见 _sellable_cap。
        cap = self._sellable_cap(positions)
        if cap is not None:
            inherited = min(inherited, cap)
        # 今日卖出但**尚未**买回的份额虽然已从 OPEN 持仓里扣掉，
        # 但它们约定要回来，必须加回来才是"今日开盘时手里有的份额"。
        # ⚠️ 只加 OPEN 状态的义务：已 FULFILLED 的份额已经躺在 OPEN 持仓里了，
        #    再加一遍会凭空翻倍。
        today_ob = sum(
            ob.quantity
            for ob in self._obligations.values()
            if ob.stock_code == stock_code
            and ob.session_key == session_key
            and ob.is_open
        )
        return inherited + today_ob

    def today_sold_shares(
        self,
        stock_code: str,
        now: Optional[float] = None,
        session_open_ts: Optional[float] = None,
    ) -> float:
        """今日累计已用于倒 T 卖出的份额（含已经买回的那些）。

        为什么要含已买回的：买回的份额是**当日买入**，T+1 当日不可再卖。
        不占住这笔额度，同一份配额就会被反复卖出好几轮 —— 而每一轮
        都会短暂地实际减仓，叠加起来足以把核心份额一点点啃掉。
        """
        now = time.time() if now is None else now
        key = self.session_key(now, session_open_ts)
        return sum(
            ob.quantity
            for ob in self._obligations.values()
            if ob.stock_code == stock_code and ob.session_key == key
        )

    def sellable_today_shares(
        self,
        stock_code: str,
        portfolio,
        now: Optional[float] = None,
        session_open_ts: Optional[float] = None,
    ) -> float:
        """今日可卖的份额上限（T+1 口径）：昨夜传承下来的、今天还没卖掉的部分。

        与 :meth:`session_quota` 的区别：这里**不扣核心份额**。
        正 T（先买后卖）的了结腿要走它——因为它同期已经买入等量份额，
        净额守恒，不存在侵蚀底仓的问题，只需要满足 T+1。
        """
        now = time.time() if now is None else now
        session_open = self.resolve_session_open(now, session_open_ts)
        positions = self._open_positions(portfolio, stock_code)
        inherited = sum(
            float(getattr(p, "quantity", 0.0) or 0.0)
            for p in positions
            if float(getattr(p, "entry_time", 0.0) or 0.0) < session_open
        )
        cap = self._sellable_cap(positions)
        if cap is not None:
            inherited = min(inherited, cap)
        return inherited

    def current_shares(self, stock_code: str, portfolio) -> float:
        """当前真实持仓份额（不含尚未买回的义务）。"""
        return sum(
            float(getattr(p, "quantity", 0.0) or 0.0)
            for p in self._open_positions(portfolio, stock_code)
        )

    def effective_shares(self, stock_code: str, portfolio, **kw) -> float:
        """买回全部兑现之后的份额水平（= 真实持仓 + 未履行义务）。"""
        return self.current_shares(stock_code, portfolio) + self.outstanding_qty(
            stock_code
        )

    def core_shares(self, stock_code: str, portfolio=None, **kw) -> float:
        """不可动用的核心份额 = min(当前持有, 目标)。"""
        plan = self._plans.get(stock_code)
        if not plan or not plan.enabled or plan.target_shares <= 0:
            return 0.0
        held = (
            self.current_shares(stock_code, portfolio)
            if portfolio is not None
            else 0.0
        )
        return min(held, plan.target_shares)

    def rotatable_shares(self, stock_code: str, portfolio=None, **kw) -> float:
        """超出目标之上的、理论上可做 T 的份额。

        注意这是**瞬时视图**，用于展示；真正能否卖出要看
        :meth:`session_quota`（含 T+1 与当日已用额度）。
        """
        plan = self._plans.get(stock_code)
        if not plan or not plan.enabled or plan.target_shares <= 0:
            return 0.0
        return max(
            0.0, self.effective_shares(stock_code, portfolio, **kw) - plan.target_shares
        )

    def session_quota(
        self,
        stock_code: str,
        portfolio,
        now: Optional[float] = None,
        session_open_ts: Optional[float] = None,
    ) -> float:
        """今日还能用于倒 T 卖出的剩余额度。

        约束链条：
        1. 没有登记目标 → 0（绝不默认放行）
        2. 减去必须长期持有的 target
        3. 减去**今日已卖出**（含已买回的）——防同一份额被重复卖出。
           这一项不能省：少了它，每一轮都会短暂实际减仓，几轮叠起来
           足以把 target 以内的核心份额啃掉，而单次检查全都合法。
        """
        plan = self._plans.get(stock_code)
        if not plan or not plan.enabled or plan.target_shares <= 0:
            return 0.0

        now = time.time() if now is None else now
        carried = self.carried_in_shares(
            stock_code, portfolio, now=now, session_open_ts=session_open_ts
        )
        sold_today = self.today_sold_shares(
            stock_code, now=now, session_open_ts=session_open_ts
        )
        room = max(0.0, carried - plan.target_shares)
        return max(0.0, room - sold_today)

    def can_sell(
        self,
        stock_code: str,
        quantity: float,
        portfolio,
        now: Optional[float] = None,
        session_open_ts: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """能否卖出 ``quantity`` 份做 T。

        Returns:
            (是否允许, 原因说明) —— 拒绝时必须给出**为什么**，
            调用方好写日志，用户好排查。空原因的拒绝是另一种静默失效。
        """
        if quantity is None or quantity <= 0:
            return False, f"卖出数量非法: {quantity}"

        plan = self._plans.get(stock_code)
        if plan is None:
            return False, f"{stock_code} 未登记核心底仓计划，默认不允许卖出"
        if not plan.enabled:
            return False, f"{stock_code} 的底仓计划已停用"
        if plan.target_shares <= 0:
            return False, f"{stock_code} 目标份额为 0，未设定长期持有额度"

        quota = self.session_quota(
            stock_code, portfolio, now=now, session_open_ts=session_open_ts
        )
        if quota <= 0:
            carried = self.carried_in_shares(
                stock_code, portfolio, now=now, session_open_ts=session_open_ts
            )
            return False, (
                f"{stock_code} 今日无可卖额度：开盘持有 {carried:.0f} 份，"
                f"需长期持有 {plan.target_shares:.0f} 份"
            )
        if quantity > quota + 1e-9:
            return False, (
                f"{stock_code} 请求卖出 {quantity:.0f} 份，"
                f"超出今日可卖额度 {quota:.0f} 份"
                f"（差额将侵蚀底仓）"
            )
        return True, f"允许卖出 {quantity:.0f} 份（今日额度剩 {quota:.0f}）"

    # ------------------------------------------------------------------
    # 回购义务
    # ------------------------------------------------------------------
    def open_obligation(
        self,
        stock_code: str,
        quantity: float,
        sell_price: float,
        deadline: Optional[float] = None,
        now: Optional[float] = None,
        session_open_ts: Optional[float] = None,
        note: str = "",
    ) -> BuybackObligation:
        """卖出即产生回购义务。 quantity 份必须在 deadline 前买回。"""
        now = time.time() if now is None else now
        if deadline is None:
            deadline = now + self._fallback_deadline
        with self._lock:
            ob = BuybackObligation(
                obligation_id=f"bb_{uuid.uuid4().hex[:12]}",
                stock_code=stock_code,
                quantity=float(quantity),
                sell_price=float(sell_price),
                created_time=now,
                deadline=float(deadline),
                session_key=self.session_key(now, session_open_ts),
                status=OBLIGATION_OPEN,
                note=note,
            )
            self._obligations[ob.obligation_id] = ob
            self._save()
            log.warning(
                f"[CorePosition] ⚠️ 产生回购义务: {stock_code} "
                f"{ob.quantity:.0f} 份 @{ob.sell_price:.3f}，"
                f"须在 {time.strftime('%H:%M:%S', time.localtime(ob.deadline))} 前买回"
            )
            return ob

    def outstanding(
        self, stock_code: Optional[str] = None
    ) -> List[BuybackObligation]:
        """未履行的回购义务（按创建时间升序，FIFO 履约）。"""
        obs = [
            ob
            for ob in self._obligations.values()
            if ob.is_open and (stock_code is None or ob.stock_code == stock_code)
        ]
        return sorted(obs, key=lambda o: o.created_time)

    def outstanding_qty(self, stock_code: str) -> float:
        return sum(ob.quantity for ob in self.outstanding(stock_code))

    def fulfill_obligation(
        self,
        obligation_id: str,
        buyback_price: float,
        now: Optional[float] = None,
        quantity: Optional[float] = None,
    ) -> Optional[BuybackObligation]:
        """履行（部分买回则传 quantity，剩余份额仍挂 OPEN）。"""
        now = time.time() if now is None else now
        with self._lock:
            ob = self._obligations.get(obligation_id)
            if ob is None or not ob.is_open:
                return None

            target_qty = ob.quantity if quantity is None else min(
                float(quantity), ob.quantity
            )
            if target_qty <= 0:
                return None

            edge = (ob.sell_price - buyback_price) * target_qty
            if target_qty >= ob.quantity - 1e-9:
                ob.buyback_price = float(buyback_price)
                ob.fulfilled_time = now
                ob.status = OBLIGATION_FULFILLED
                remaining = 0.0
            else:
                # 部分买回：把剩余部分拆成新义务，原义务按已买回口径结清
                remaining = ob.quantity - target_qty
                ratio = target_qty / ob.quantity
                if abs(ratio - 1.0) > 1e-9:
                    leftover = BuybackObligation(
                        obligation_id=f"bb_{uuid.uuid4().hex[:12]}",
                        stock_code=ob.stock_code,
                        quantity=remaining,
                        sell_price=ob.sell_price,
                        created_time=ob.created_time,
                        deadline=ob.deadline,
                        session_key=ob.session_key,
                        status=OBLIGATION_OPEN,
                        note=f"部分买回剩余（原 {obligation_id}）",
                    )
                    self._obligations[leftover.obligation_id] = leftover
                ob.quantity = target_qty
                ob.buyback_price = float(buyback_price)
                ob.fulfilled_time = now
                ob.status = OBLIGATION_FULFILLED

            self._save()
            verb = "买回" if edge >= 0 else "追高买回"
            log.info(
                f"[CorePosition] ✅ 回购已履行: {ob.stock_code} "
                f"{target_qty:.0f} 份 @{buyback_price:.3f}，"
                f"{verb}兑现 {edge:+.2f}"
                + (f"，剩余待买回 {remaining:.0f} 份" if remaining else "")
            )
            return ob

    def mark_expired(self, now: Optional[float] = None) -> List[BuybackObligation]:
        """把超期未买回的义务标为 EXPIRED（供外部触发强制补回）。

        只打标记、**不自动下单**：是否强补由上层决定，但一定会暴露出来。
        """
        now = time.time() if now is None else now
        expired = []
        with self._lock:
            for ob in self._obligations.values():
                if ob.is_open and now > ob.deadline:
                    ob.status = OBLIGATION_EXPIRED
                    expired.append(ob)
            if expired:
                self._save()
        for ob in expired:
            log.error(
                f"[CorePosition] 🚨 回购义务超期未履行: {ob.stock_code} "
                f"{ob.quantity:.0f} 份（卖出价 {ob.sell_price:.3f}），需强制补回"
            )
        return expired

    def mark_forced(self, obligation_id: str, price: float, now: Optional[float] = None):
        """标记某笔义务已被强制补回（价格不利也要买，份额优先）。"""
        now = time.time() if now is None else now
        with self._lock:
            ob = self._obligations.get(obligation_id)
            if ob is None or ob.status == OBLIGATION_FULFILLED:
                return None
            ob.buyback_price = float(price)
            ob.fulfilled_time = now
            ob.status = OBLIGATION_FULFILLED
            ob.forced = True
            self._save()
        log.error(
            f"[CorePosition] 🚨 已强制补回: {ob.stock_code} "
            f"{ob.quantity:.0f} 份 @{price:.3f}（原卖出 @{ob.sell_price:.3f}，"
            f"差价 {(ob.sell_price - price) * ob.quantity:+.2f}）"
        )
        return ob

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def realized_edge_total(self, stock_code: Optional[str] = None) -> float:
        """累计已兑现的做 T 差价（金额）。正值=确实降低了持仓成本。"""
        return sum(
            ob.realized_edge
            for ob in self._obligations.values()
            if ob.status == OBLIGATION_FULFILLED
            and (stock_code is None or ob.stock_code == stock_code)
        )

    def get_stats(self) -> Dict[str, Any]:
        now = time.time()
        open_obs = [o for o in self._obligations.values() if o.is_open]
        return {
            "plans": len(self._plans),
            "obligations_total": len(self._obligations),
            "obligations_open": len(open_obs),
            "obligations_open_qty": sum(o.quantity for o in open_obs),
            "obligations_overdue": sum(1 for o in open_obs if now > o.deadline),
            "realized_edge": sum(o.realized_edge for o in self._obligations.values()),
            "degraded": self._degraded,
            "persisted": self._db is not None,
        }

    def get_summary(self, stock_code: str, portfolio=None, **kw) -> Dict[str, Any]:
        plan = self._plans.get(stock_code)
        carried = self.carried_in_shares(stock_code, portfolio, **kw)
        return {
            "stock_code": stock_code,
            "planned": plan is not None and plan.enabled and plan.target_shares > 0,
            "plan": plan.to_dict() if plan else None,
            "target_shares": plan.target_shares if plan else 0.0,
            "current_shares": self.current_shares(stock_code, portfolio),
            "carried_in_shares": carried,
            "effective_shares": self.effective_shares(stock_code, portfolio, **kw),
            "core_shares": self.core_shares(stock_code, portfolio, **kw),
            "rotatable_shares": self.rotatable_shares(stock_code, portfolio, **kw),
            "session_quota": self.session_quota(stock_code, portfolio, **kw),
            "outstanding_qty": self.outstanding_qty(stock_code),
            "realized_edge": self.realized_edge_total(stock_code),
        }


_ledger: Optional[CorePositionLedger] = None
_ledger_lock = threading.Lock()


def get_core_position_ledger() -> CorePositionLedger:
    """进程内单例。"""
    global _ledger
    if _ledger is None:
        with _ledger_lock:
            if _ledger is None:
                _ledger = CorePositionLedger()
    return _ledger
