"""把**富途模拟账户**包装成做 T 引擎认得的「组合」对象。

为什么需要这一层
----------------
做 T 引擎（:mod:`t_rotation`）与底仓账本（:mod:`core_position`）从头到尾只认
一个 duck-type 组合接口，四个方法：

    get_summary() / get_all_positions(status) / open_position(...) / reduce_position(...)

此前这个位置上一律是 VirtualPortfolio（内存里的假账本）。于是出现两套账：
富途模拟仓里真的有腾讯 300 股，而做 T 引擎眼里持仓是 0 —— **份额守恒校验
看不见真实底仓**，倒 T 一卖出就是凭空造出来的份额。

本模块把富途模拟账户伪装成那个接口，让「真金白银（模拟金）的持仓」直接
进入做 T 的守恒账本。

三条刻意的设计取舍
------------------
1. **持仓真值一律以富途为准，本地不做加减**。
   虚拟盘是内存态，``open_position`` 后立刻就能读到新份额。富途侧下单与
   成交之间有间隔，本地自加会把「还没成交」记成「已经持有」，份额守恒
   这种铁律一旦靠估算就守不住。所以每次 ``open/reduce`` 之后**重新拉一次
   持仓**确认；拉不到就返回 ``None``，让引擎那句 🚨 买回失败 响亮地喊出来，
   而不是悄悄记一笔假账。

2. **T+1 用富途的 ``can_sell_qty``，不用自己推算建仓时间**。
   账本判断「哪些份额是昨天留下来的」靠 ``entry_time < 今日开盘``，而富途
   的持仓接口**根本没有建仓时间字段**。硬造一个时间戳必然错。改用
   ``can_sell_qty``：它已经把 A 股 T+1（当日买入不可卖）算进去了，是权威值。
   本模块把它挂成持仓的 ``sellable_qty``，由账本在计算可卖额度时取
   ``min(quantity, sellable_qty)``（见 :mod:`core_position` 的改动）。
   ❗ ``entry_time`` 仍然要给（引擎与账本都读它），这里给 0（= 很久以前，
   判成"昨夜传承"）。**真正的 T+1 约束由 sellable_qty 兜住**，不靠它。

3. **各市场独立本币记账**（用户 2026-10-14 拍板：不做汇率换算）。
   一个 :class:`FutuSimPortfolio` 只绑一个市场、一个账户、一种币种。
   HKD 账户的 20 万与 USD 账户的 3 万不需要也没意义加总。

刻意不做的事
------------
* **不碰真实环境**。账户只从 ``TrdEnv.SIMULATE`` 的同步目标里选。
* **不缓存账户**。每次下单重新解析 —— 用户可能在 APP 里换主账户。
* **不实现止盈止损**。引擎本来就把做 T 双腿的止损推到 ±95%，
  真实成交价由富途撮合，不需要本地模拟。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .execution import strip_market_prefix

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 11111

#: 各市场账户的本币（用于日志与对账，不做换算）
MARKET_CURRENCY = {"CN": "CNY", "HK": "HKD", "US": "USD"}

#: 代码里可能出现的市场记号。用来区分前缀式（``US.QQQ``）与后缀式（``NVDA.US``）
_MARKET_TOKENS = frozenset({"US", "HK", "CN", "SH", "SZ", "JP", "SG", "AU", "CA"})


def _num(value: Any, default: float = 0.0) -> float:
    """把富途返回值转成 float。富途大量字段用字符串 ``"N/A"`` 表示不适用。"""
    try:
        if value is None:
            return default
        text = str(value).strip()
        if not text or text.upper() in ("N/A", "NAN", "NONE", ""):
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def bare_code(full: str) -> str:
    """富途持仓代码 → 做 T 用的裸码：``HK.00700`` → ``00700``。

    ❗这一步不能省，也不能只用 :func:`~execution.strip_market_prefix`：
    那个函数**只**剥无点前缀（``sh600487``），带点的（``HK.00700``）按约定
    由调用方先 ``partition``。富途持仓接口返回的一律是带点形式，
    直接丢给它 → 剥不掉 → 持仓代码是 ``HK.00700``，而标的配置里是
    ``00700``，账本两边一对，**一只票都匹配不上**，表现为「底仓 0 份」
    （实测：港股明明持有腾讯 300 股，账本读到持有 0）。
    """
    text = str(full or "").strip()
    if "." in text:
        head, _sep, tail = text.partition(".")
        if tail:
            # ❗后缀式（``NVDA.US``）市场在**后半段**，若一律取后半段会把
            # 一只票读成市场名 "US"。富途持仓接口只给前缀式，但调用方
            # 手里拿的可能是任何一种写法，这里必须两边都认。
            if tail.upper() in _MARKET_TOKENS:
                return strip_market_prefix(head)
            return strip_market_prefix(tail)
    return strip_market_prefix(text)


@dataclass
class FutuSimPosition:
    """一条富途模拟仓持仓，字段对齐 :class:`~virtual_portfolio.VirtualPosition`。

    多出来的 ``sellable_qty`` / ``market`` / ``currency`` 是富途侧才有、
    虚拟盘没有的信息。账本会**优先**读 ``sellable_qty`` 作为 T+1 上限。
    """

    position_id: str
    stock_code: str
    stock_name: str
    quantity: float
    entry_price: float
    current_price: float
    #: 富途 ``can_sell_qty``：已扣除 T+1 冻结的真实可卖数量
    sellable_qty: float
    market: str = ""
    currency: str = ""
    strategy_id: str = ""
    strategy_name: str = ""
    #: 见模块 docstring 第 2 条：富途没有建仓时间，这里恒为 0（判成"昨夜传承"）
    entry_time: float = 0.0
    last_update_time: float = field(default_factory=time.time)
    status: str = "OPEN"
    stop_loss: float = 0.0
    take_profit: float = 0.0
    exit_price: float = 0.0
    exit_time: float = 0.0
    close_reason: str = ""
    market_time: float = 0.0
    signal_confidence: float = 0.5

    @property
    def return_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100

    @property
    def profit_loss(self) -> float:
        return (self.current_price - self.entry_price) * self.quantity

    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity

    @property
    def price(self) -> float:
        """兼容旧接口：price 表示当前价格。"""
        return self.current_price

    @property
    def amount(self) -> float:
        """兼容旧接口：amount 表示当前市值。"""
        return self.market_value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "quantity": self.quantity,
            "sellable_qty": self.sellable_qty,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "market": self.market,
            "currency": self.currency,
            "market_value": self.market_value,
            "profit_loss": self.profit_loss,
            "status": self.status,
        }


class FutuSimPortfolio:
    """一个富途模拟账户，伪装成做 T 引擎要的组合对象。"""

    def __init__(
        self,
        market: str,
        backend=None,
        strategy_id: str = "t_rotation",
        strategy_name: str = "做T",
    ):
        self.market = str(market or "").strip().upper()
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self._backend = backend
        #: position_id -> (market, 裸代码)。reduce_position 只拿到 id，
        #: 而下单需要市场与代码 —— 富途的 position_id 本身不含这些信息。
        self._index: Dict[str, Tuple[str, str]] = {}
        #: 由引擎在每一轮做 T 前注入（见 TRotationEngine._set_leg_tag）。
        #: 虚拟盘没有这个概念，用 hasattr 探测，缺失即忽略。
        self._slot_tag: Optional[str] = None
        self._last_error: Optional[str] = None
        #: 持仓缓存。账本算一次 ``carried_in`` / ``sellable_today`` / ``current_shares``
        #: 会各调一次 ``get_all_positions``，做 T 每秒轮询 → 富途接口每秒被打十几次。
        #: 富途有明确的频率限制（超了会拒），所以缓存一小会儿。
        #: ❗下单后必须立刻失效 —— 缓存里留着旧份额，份额守恒就成了摆设。
        self._cache_ttl = 2.0
        self._cache_ts = 0.0
        self._cache_rows: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # 轮次标签（幂等槽位）
    # ------------------------------------------------------------------
    def set_slot_tag(self, tag: Optional[str]) -> None:
        """设置下一次下单用的幂等标签。

        做 T 一天要跑好几轮，而幂等槽位默认是「日期+市场+标的+方向」——
        不传 tag 的话一天只能各买一次卖一次，**第二轮起全被静默挡掉**。
        传 round_id 后：同一轮重复提交仍被挡（防重放），不同轮各自成槽。
        """
        self._slot_tag = tag

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    # ------------------------------------------------------------------
    # 依赖
    # ------------------------------------------------------------------
    def _get_backend(self):
        if self._backend is not None:
            return self._backend
        from .execution import FutuSimBackend

        self._backend = FutuSimBackend()
        return self._backend

    def _account(self) -> Optional[Dict[str, Any]]:
        backend = self._get_backend()
        try:
            return backend._resolve_account(self.market)
        except Exception as e:  # pragma: no cover
            self._last_error = f"解析模拟账户失败: {e}"
            log.warning("[FutuSimPortfolio] %s", self._last_error)
            return None

    # ------------------------------------------------------------------
    # 持仓读取
    # ------------------------------------------------------------------
    def invalidate(self) -> None:
        """丢弃持仓缓存。下单后必须调用，否则读到的是成交前的旧份额。"""
        self._cache_ts = 0.0
        self._cache_rows = None

    def _fetch_rows(self) -> Optional[List[Dict[str, Any]]]:
        """带缓存的持仓读取。**真实查询在 :meth:`_query_rows`**。

        拆开是为了让「缓存是否生效 / 下单后是否失效」能被独立验证 ——
        守卫里替换 :meth:`_query_rows` 就能数真实调用次数。
        """
        if (
            self._cache_rows is not None
            and (time.time() - self._cache_ts) < self._cache_ttl
        ):
            return self._cache_rows
        rows = self._query_rows()
        if rows is not None:
            self._cache_rows = rows
            self._cache_ts = time.time()
        return rows

    def _query_rows(self) -> Optional[List[Dict[str, Any]]]:
        """真的去富途拉一次持仓。失败返回 None（不是空列表 —— 见下）。"""
        account = self._account()
        if account is None:
            return None
        try:
            from futu import OpenSecTradeContext, RET_OK, SecurityFirm, TrdEnv

            from .execution import trd_market

            firm = getattr(
                SecurityFirm, account.get("firm") or "", SecurityFirm.FUTUSECURITIES
            )
            ctx = OpenSecTradeContext(
                filter_trdmarket=trd_market(self.market), host=HOST, port=PORT,
                security_firm=firm,
            )
            try:
                ret, data = ctx.position_list_query(
                    trd_env=TrdEnv.SIMULATE, acc_id=account["acc_id"],
                )
            finally:
                ctx.close()
            if ret != RET_OK or data is None:
                self._last_error = f"持仓查询失败: {data}"
                log.warning("[FutuSimPortfolio] %s", self._last_error)
                return None
            return [row.to_dict() for _, row in data.iterrows()]
        except Exception as e:
            self._last_error = f"持仓查询异常: {e}"
            log.warning("[FutuSimPortfolio] %s", self._last_error)
            return None

    def get_all_positions(self, status: Optional[str] = None) -> List[FutuSimPosition]:
        """列出持仓。``status="OPEN"`` 是引擎与账本的固定调用方式。

        ❗查不到账户/查询失败时返回**空列表**，这与「账户里确实没有持仓」
        在调用方眼里是同一个形状 —— 典型的「合法的空」。所以失败原因必须
        落到 :attr:`last_error`，并由上层的健康检查把它暴露出来。
        """
        rows = self._fetch_rows()
        if rows is None:
            return []

        out: List[FutuSimPosition] = []
        self._index = {}
        for row in rows:
            full = str(row.get("code") or "")
            code = bare_code(full)
            if not code:
                continue
            qty = _num(row.get("qty"))
            if qty <= 0:
                # 已清仓的行富途仍会返回（qty=0），不能当成持仓
                continue
            pid = str(row.get("position_id") or f"{self.market}_{code}")
            self._index[pid] = (self.market, code)
            out.append(
                FutuSimPosition(
                    position_id=pid,
                    stock_code=code,
                    stock_name=str(row.get("stock_name") or code),
                    quantity=qty,
                    entry_price=_num(row.get("cost_price"), _num(row.get("nominal_price"))),
                    current_price=_num(row.get("nominal_price"), _num(row.get("cost_price"))),
                    sellable_qty=_num(row.get("can_sell_qty")),
                    market=self.market,
                    currency=str(row.get("currency") or MARKET_CURRENCY.get(self.market, "")),
                    strategy_id=self.strategy_id,
                    strategy_name=self.strategy_name,
                    last_update_time=time.time(),
                )
            )
        if status and status.upper() != "OPEN":
            return []
        return out

    def get_position(self, position_id: str) -> Optional[FutuSimPosition]:
        for p in self.get_all_positions(status="OPEN"):
            if p.position_id == position_id:
                return p
        return None

    def get_positions_by_stock(self, stock_code: str) -> List[FutuSimPosition]:
        want = bare_code(str(stock_code))
        return [
            p for p in self.get_all_positions(status="OPEN") if p.stock_code == want
        ]

    # ------------------------------------------------------------------
    # 资金
    # ------------------------------------------------------------------
    def get_summary(self) -> Dict[str, Any]:
        """组合摘要。字段名与 VirtualPortfolio.get_summary() 严格对齐。

        ⚠️ 单位是该账户的**本币**（HKD/USD/CNY），不做汇率换算。
        """
        positions = self.get_all_positions(status="OPEN")
        market_val = sum(p.market_value for p in positions)
        total_cost = sum(p.entry_price * p.quantity for p in positions)
        pnl = sum(p.profit_loss for p in positions)

        total_assets = 0.0
        cash = 0.0
        account = self._account()
        if account is not None:
            try:
                from futu import OpenSecTradeContext, RET_OK, SecurityFirm, TrdEnv

                from .execution import trd_market

                firm = getattr(
                    SecurityFirm, account.get("firm") or "", SecurityFirm.FUTUSECURITIES
                )
                ctx = OpenSecTradeContext(
                    filter_trdmarket=trd_market(self.market), host=HOST, port=PORT,
                    security_firm=firm,
                )
                try:
                    ret, data = ctx.accinfo_query(
                        trd_env=TrdEnv.SIMULATE, acc_id=account["acc_id"],
                    )
                finally:
                    ctx.close()
                if ret == RET_OK and data is not None and len(data):
                    row = data.iloc[0].to_dict()
                    total_assets = _num(row.get("total_assets"))
                    cash = _num(row.get("cash"))
                    if total_assets <= 0:
                        # 个别账户类型不给 total_assets，退回现金+市值
                        total_assets = cash + market_val
                else:
                    self._last_error = f"资金查询失败: {data}"
            except Exception as e:
                self._last_error = f"资金查询异常: {e}"
                log.warning("[FutuSimPortfolio] %s", self._last_error)
                total_assets = cash + market_val
        else:
            total_assets = cash + market_val

        return {
            "total_value": market_val,
            "total_capital": total_assets,
            "used_capital": market_val,
            "available_capital": cash,
            "position_count": len(positions),
            "total_return": (pnl / total_cost * 100) if total_cost > 0 else 0.0,
            "total_profit_loss": pnl,
            # 富途侧独有：币种与市场，便于日志/UI 区分三个仓
            "currency": MARKET_CURRENCY.get(self.market, ""),
            "market": self.market,
            "error": self._last_error,
        }

    # ------------------------------------------------------------------
    # 开仓 / 减仓
    # ------------------------------------------------------------------
    def open_position(
        self,
        strategy_id: str,
        strategy_name: str,
        stock_code: str,
        stock_name: str,
        price: float,
        quantity: float = 0.0,
        amount: float = 0.0,
        stop_loss_pct: float = -5.0,
        take_profit_pct: float = 10.0,
        market_time: float = 0.0,
        signal_confidence: float = 0.5,
        bypass_limits: bool = False,
        **_ignored: Any,
    ) -> Optional[FutuSimPosition]:
        """真实下一笔买单到模拟账户。

        ❗``bypass_limits`` 在这里**不是**"绕过风控"的意思。虚拟盘用它跳过
        仓位上限（回购义务必须成交）；富途侧的仓位上限就是账户里的钱，
        绕不过去。这里它只影响日志措辞 —— 买不回来就是买不回来。
        """
        from types import SimpleNamespace

        code = bare_code(str(stock_code))
        backend = self._get_backend()
        signal = SimpleNamespace(
            stock_code=code, raw_data={"market": self.market}
        )
        qty = float(quantity or 0.0)
        amt = float(amount or 0.0)
        if qty <= 0 and amt <= 0:
            self._last_error = f"{code} 开仓股数与金额都无效"
            log.error("[FutuSimPortfolio] %s", self._last_error)
            return None
        if qty <= 0:
            amt_for_call = amt
        else:
            # 引擎已经按手数取整好了，直接按股数下；amount 仅用于流水记账
            amt_for_call = amt if amt > 0 else qty * float(price or 0.0)

        outcome = backend.submit(
            signal=signal,
            plan=None,
            side="buy",
            price=float(price or 0.0),
            amount=amt_for_call,
            quantity=qty if qty > 0 else None,
            slot_tag=self._slot_tag,
        )
        if not outcome.ok or outcome.skipped:
            self._last_error = f"{code} 买入未成交: {outcome.reason}"
            log.error(
                "[FutuSimPortfolio] ❌ %s 买入失败（%s）", code, outcome.reason
            )
            return None

        return self._reload(code)

    def reduce_position(
        self,
        position_id: str,
        quantity: float,
        exit_price: float,
        reason: str = "REDUCE",
    ) -> Optional[FutuSimPosition]:
        """真实下一笔卖单。

        ❗卖出的是**底仓**，卖飞了要用真金白银买回来。所以：
        1. 先按 ``position_id`` 反查市场与代码（查不到就重新拉一次）；
        2. 卖量不得超过 ``sellable_qty``（T+1 冻结的部分卖了会被拒单）；
        3. 成交后重新拉取，拉不到原持仓就返回 None —— 让调用方知道没卖成。
        """
        from types import SimpleNamespace

        target = self._index.get(str(position_id))
        if target is None:
            self.get_all_positions(status="OPEN")
            target = self._index.get(str(position_id))
        if target is None:
            self._last_error = f"position_id {position_id} 不在当前持仓中"
            log.error("[FutuSimPortfolio] %s", self._last_error)
            return None
        market, code = target

        qty = float(quantity or 0.0)
        if qty <= 0:
            self._last_error = f"{code} 卖出数量非法（{quantity}）"
            return None

        # ② T+1 闸门：只卖真实可卖的部分
        existing = self.get_positions_by_stock(code)
        avail = min((p.sellable_qty for p in existing), default=0.0) if existing else 0.0
        if existing and qty > avail:
            log.warning(
                "[FutuSimPortfolio] %s 计划卖 %.0f 股，超过可卖 %.0f 股，按可卖量下调",
                code, qty, avail,
            )
            qty = avail
        if qty <= 0:
            self._last_error = (
                f"{code} 无可卖份额（can_sell_qty=0，多半是当日买入受 T+1 限制）"
            )
            log.error("[FutuSimPortfolio] ❌ %s", self._last_error)
            return None

        backend = self._get_backend()
        signal = SimpleNamespace(stock_code=code, raw_data={"market": market})
        outcome = backend.submit(
            signal=signal,
            plan=None,
            side="sell",
            price=float(exit_price or 0.0),
            amount=qty * float(exit_price or 0.0),
            quantity=qty,
            slot_tag=self._slot_tag,
        )
        if not outcome.ok or outcome.skipped:
            self._last_error = f"{code} 卖出未成交: {outcome.reason}"
            log.error(
                "[FutuSimPortfolio] ❌ %s 卖出失败（%s）—— 底仓可能已被卖出且未买回！",
                code, outcome.reason,
            )
            return None

        log.info(
            "[FutuSimPortfolio] 卖出 %s %.0f 股 @ %g（%s）",
            code, qty, exit_price, reason,
        )
        # 卖光了富途就不返回这条持仓了，那是成功不是失败
        return self._reload(code, allow_missing=True)

    def _reload(
        self, code: str, *, allow_missing: bool = False,
    ) -> Optional[FutuSimPosition]:
        """下单后重新拉持仓确认。拉不到返回 None（不本地估算）。

        模拟盘撮合几乎瞬间完成，但**不做确认**就等于把「下单成功」当成
        「持仓变了」。份额守恒这条铁律上不能有任何估算。

        ``allow_missing``：卖出场景专用。**全部卖光**时富途不再返回这条
        持仓，那是**成功**而不是失败。不区分的话会把"清仓"误报成"没成交"。
        """
        for attempt in range(3):
            self.invalidate()  # 缓存里是成交前的旧份额，必须丢掉再查
            positions = self.get_positions_by_stock(code)
            if positions:
                return positions[0]
            if allow_missing:
                return None
            if attempt < 2:
                time.sleep(0.4)
        self._last_error = (
            f"{code} 已报单但持仓未出现（可能未成交），不记入账本"
        )
        log.warning("[FutuSimPortfolio] %s", self._last_error)
        return None

    # ------------------------------------------------------------------
    # 只读诊断
    # ------------------------------------------------------------------
    def describe(self) -> Dict[str, Any]:
        summary = self.get_summary()
        account = self._account()
        return {
            "market": self.market,
            "account": account and {
                "name": account.get("name"),
                "acc_id": account.get("acc_id"),
            },
            "currency": summary.get("currency"),
            "total_assets": summary.get("total_capital"),
            "cash": summary.get("available_capital"),
            "positions": [p.to_dict() for p in self.get_all_positions(status="OPEN")],
            "error": self._last_error,
        }


def build_sim_portfolios(
    markets: Optional[List[str]] = None, backend=None,
) -> Dict[str, FutuSimPortfolio]:
    """按市场各建一份组合。做 T 的 runner 用它取代单一虚拟盘。"""
    wanted = [str(m).upper() for m in (markets or ["CN", "HK", "US"])]
    return {m: FutuSimPortfolio(m, backend=backend) for m in wanted}
