"""执行后端 —— 把 ``DecisionPlan`` 真正变成一笔单。

为什么要这个模块
----------------
链路此前**止步于虚拟仓**：全仓 ``place_order`` 调用数为 **0**，
``DecisionPlan`` 只进 UI 与 LLM 叙事，永远不下单 —— 也就是
"判断 → 决策" 有、 "决策 → 动手" 没有。本模块把"执行"抽成一个
**可切换的后端**，让同一个 ``DecisionPlan`` 既能落进虚拟仓，
也能真的报到富途**模拟账户**（``TrdEnv.SIMULATE``）。

后端选择（``NAJA_EXEC_BACKEND``）
--------------------------------
* ``virtual``（**默认**）—— 写 ``VirtualPortfolio``，与改造前行为一致。
* ``futu_sim`` —— 调 ``place_order`` 报到富途模拟账户。

默认**必须**是 ``virtual``：换后端等于换掉"下单写到哪里"，不能让
"装了新代码"就自动开始报单。要动手就显式设环境变量，回滚同一处。

模拟报单的四道闸（缺一不可）
----------------------------
1. **市场白名单**（``NAJA_FUTU_SIM_MARKETS``，默认 ``HK``）。
   目前 OpenD 只开了**港股**股票/期权模拟账户，没有美股模拟账户 ——
   不设白名单就会拿美股信号去撞一个不存在的账户。
2. **市场必须可判定**。信号里的 ``stock_code`` 是裸代码（``06666`` /
   ``nvda``），**6 位数字既是港股也可能是 A 股**（``000001`` 两边都成立）。
   判不出来就**如实跳过并说明原因**，绝不猜 —— 猜错市场等于把单下到
   另一个盘口去。
3. **每手股数必须实查**。港股每手 20 ~ 10000 股不等（实测
   ``HK.06666``=500、``HK.00100``=20），下单必须是**整手整数**；
   虚拟仓侧 ``qty`` 是小数（如 ``14378.145``），照搬必被拒单。
4. **幂等**。信号可能被多条链路各推进一次（WakeSync 补作业 / 轮询 +
   流式订阅并存），而``_on_new_signal`` 的"已有持仓就跳过"检查查的是
   **虚拟仓** —— 走模拟后端时虚拟仓并不更新，那道检查完全失效，
   同一个信号会被反复下单。故按 ``(日期, 市场, 标的, 方向)``
   用 ``O_CREAT|O_EXCL`` 做**原子认领**；失败要**归还**，否则一次
   网络抖动就把该标的当天唯一的报单机会吃掉了。
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 11111

# ---------------------------------------------------------------- 环境开关

ENV_BACKEND = "NAJA_EXEC_BACKEND"
ENV_SIM_MARKETS = "NAJA_FUTU_SIM_MARKETS"

BACKEND_VIRTUAL = "virtual"
BACKEND_FUTU_SIM = "futu_sim"
BACKENDS = (BACKEND_VIRTUAL, BACKEND_FUTU_SIM)

# 目前 OpenD 上真实存在的模拟账户只有港股（STOCK + OPTION），故默认只放行 HK。
DEFAULT_SIM_MARKETS = "HK"


def selected_backend_name() -> str:
    """读出本次要用的执行后端名。**认不出的一律回落 ``virtual``**。"""
    raw = (os.environ.get(ENV_BACKEND) or "").strip().lower()
    if raw in BACKENDS:
        return raw
    if raw:
        log.warning("[Execution] 未知的执行后端 %r，回落 %s", raw, BACKEND_VIRTUAL)
    return BACKEND_VIRTUAL


def futu_sim_enabled() -> bool:
    return selected_backend_name() == BACKEND_FUTU_SIM


def sim_markets() -> frozenset:
    """模拟报单放行的市场白名单（大写）。"""
    raw = os.environ.get(ENV_SIM_MARKETS)
    text = DEFAULT_SIM_MARKETS if raw is None else raw
    return frozenset(m.strip().upper() for m in text.split(",") if m.strip())


# ---------------------------------------------------------------- 路径

def order_dir() -> Path:
    """模拟单的落盘目录（认领槽位 + 流水）。"""
    return Path(os.path.expanduser("~/.naja/futu_sim_orders"))


def _claim_dir() -> Path:
    return order_dir() / "claimed"


def _journal_path() -> Path:
    return order_dir() / "orders.jsonl"


# ---------------------------------------------------------------- 市场判定

# 裸数字代码 → 市场。**只认长度明确的两种**，其余一律判不出来：
# 港股代码是 5 位（``06666``、``00100``），A 股是 6 位（``000001``）。
# 中间地带（如 4 位、7 位）没有可靠依据，宁可跳过。
_NUMERIC_MARKET: Dict[int, str] = {5: "HK", 6: "CN"}


def infer_market(code: str, raw_data: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """判定一个标的属于哪个市场。

    Returns:
        ``(市场大写, 依据说明)``。判不出来时市场为空串，依据是原因 ——
        调用方必须据此**跳过**，不能拿空串当"随便哪个市场"。
    """
    text = str(code or "").strip()
    if not text:
        return "", "代码为空"

    if "." in text:
        prefix, _, rest = text.partition(".")
        if prefix.strip() and rest.strip():
            return prefix.strip().upper(), f"代码前缀（{text}）"

    for key in ("market", "sec_market", "trd_market", "exchange"):
        value = (raw_data or {}).get(key)
        if value:
            return str(value).strip().upper(), f"信号字段 {key}"

    if text.isdigit():
        market = _NUMERIC_MARKET.get(len(text))
        if market:
            return market, f"{len(text)} 位数字代码"
        return "", f"数字代码位数 {len(text)} 无法判定市场（港股 5 位 / A 股 6 位）"

    # 字母代码：港股也有字母代码但极罕见，不猜；美股是主流。
    return "", f"裸字母代码 {text!r} 无法判定市场（请带 HK./US. 前缀）"


def futu_code(market: str, code: str) -> str:
    """把裸代码拼成富途要求的 ``MARKET.CODE``。

    港股代码必须**补零到 5 位**（``6666`` → ``HK.06666``），否则查不到标的。
    """
    bare = str(code or "").strip().upper()
    if "." in bare:
        bare = bare.partition(".")[2]
    if market.upper() == "HK" and bare.isdigit():
        return f"HK.{bare.lstrip('0').zfill(5) or '00000'}"
    return f"{market.upper()}.{bare}"


# ---------------------------------------------------------------- 数量折算

def floor_to_lot(amount: float, price: float, lot_size: int) -> int:
    """把"能花多少钱"折算成**整手**股数（向下取整）。

    虚拟仓的 ``qty`` 允许小数，模拟报单要求整手整数倍 —— 这是两边
    语义最容易错的地方，故单独成函数并配守卫。
    """
    if price <= 0 or lot_size <= 0 or amount <= 0:
        return 0
    return int(amount // (price * float(lot_size))) * int(lot_size)


# ---------------------------------------------------------------- 幂等槽位

def order_slot_key(market: str, code: str, side: str, *, day: Optional[str] = None) -> str:
    """一个标的在一个交易日内的报单槽位键。"""
    stamp = day or time.strftime("%Y%m%d")
    return f"{stamp}_{market.upper()}_{str(code).strip().lower()}_{side.lower()}"


def claim_order_slot(key: str) -> bool:
    """原子认领槽位。已被认领返回 ``False``（表示这一单不该再下）。

    用 ``O_CREAT|O_EXCL``：并发下只有一个调用方能创建成功，不靠"先查后写"。
    """
    path = _claim_dir() / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as fh:
        json.dump({"claimed_at": time.time(), "pid": os.getpid()}, fh)
    return True


def release_order_slot(key: str) -> None:
    """归还槽位。**报单失败必须归还** —— 否则这个标的当天再也下不出单。"""
    try:
        (_claim_dir() / f"{key}.json").unlink()
    except FileNotFoundError:
        pass
    except OSError as e:  # pragma: no cover - 权限等罕见情况
        log.warning("[Execution] 归还报单槽位失败 %s: %s", key, e)


def slot_taken(key: str) -> bool:
    """只读判断槽位是否已被认领（查询用，不产生副作用）。"""
    return (_claim_dir() / f"{key}.json").exists()


def append_journal(record: Dict[str, Any]) -> None:
    """把一次执行结果追加到流水（审计与守卫用；失败不影响交易主流程）。"""
    try:
        path = _journal_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as e:  # pragma: no cover
        log.debug("[Execution] 写执行流水失败: %s", e)


def read_journal(limit: int = 100) -> List[Dict[str, Any]]:
    """读最近的执行流水（新→旧）。"""
    path = _journal_path()
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return list(reversed(out))[:limit]


# ---------------------------------------------------------------- 结果契约

@dataclass
class ExecutionOutcome:
    """一次执行的结果。

    ``ok`` 与 ``skipped`` 是**两个独立维度**，不许合并成一个布尔：
    "跳过"是链路完好、只是这道闸没放行（要有原因）；"失败"是链路坏了。
    把跳过报成失败会制造假警报，把失败报成跳过会把故障埋成"长期正常"。
    """

    backend: str
    symbol: str = ""
    side: str = "buy"
    ok: bool = False
    skipped: bool = False
    quantity: float = 0.0
    price: float = 0.0
    amount: float = 0.0
    position_id: str = ""
    order_id: str = ""
    reason: str = ""
    detail: str = ""
    position: Any = None

    @property
    def acted(self) -> bool:
        """是否真的动了手（下单成功）。"""
        return bool(self.ok) and not self.skipped

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "symbol": self.symbol,
            "side": self.side,
            "ok": self.ok,
            "skipped": self.skipped,
            "quantity": self.quantity,
            "price": self.price,
            "amount": self.amount,
            "position_id": self.position_id,
            "order_id": self.order_id,
            "reason": self.reason,
            "detail": self.detail,
            "ts": time.time(),
        }

    def describe(self) -> str:
        if self.skipped:
            return f"⏭ 跳过（{self.reason}）"
        if not self.ok:
            return f"❌ 失败（{self.reason or self.detail}）"
        return (f"✅ {self.symbol} {self.side} {self.quantity:g} @ {self.price:g}"
                + (f" 单号 {self.order_id}" if self.order_id else ""))


# ---------------------------------------------------------------- 后端基类

class ExecutionBackend:
    """执行后端接口。"""

    name = "base"

    def submit(
        self,
        *,
        signal: Any,
        plan: Optional[Dict[str, Any]],
        side: str,
        price: float,
        amount: float,
        stop_loss_pct: float = -5.0,
        take_profit_pct: float = 10.0,
    ) -> ExecutionOutcome:
        raise NotImplementedError


# ---------------------------------------------------------------- 虚拟仓后端

class VirtualPortfolioBackend(ExecutionBackend):
    """默认后端：写 ``VirtualPortfolio``（改造前的老行为）。"""

    name = BACKEND_VIRTUAL

    def __init__(self, portfolio):
        self._portfolio = portfolio

    def submit(
        self,
        *,
        signal: Any,
        plan: Optional[Dict[str, Any]],
        side: str,
        price: float,
        amount: float,
        stop_loss_pct: float = -5.0,
        take_profit_pct: float = 10.0,
    ) -> ExecutionOutcome:
        outcome = ExecutionOutcome(
            backend=self.name, symbol=signal.stock_code, side=side, price=price, amount=amount,
        )
        if self._portfolio is None:
            outcome.reason = "VirtualPortfolio 不可用"
            return outcome
        try:
            position = self._portfolio.open_position(
                strategy_id=signal.strategy_id,
                strategy_name=signal.strategy_name,
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                price=price,
                amount=amount,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                market_time=getattr(signal, "market_time", 0.0),
                signal_confidence=getattr(signal, "confidence", 0.5),
            )
        except Exception as e:
            log.error("[Execution] 虚拟开仓异常: %s", e, exc_info=True)
            outcome.reason = f"虚拟开仓异常: {e}"
            return outcome

        if position is None:
            outcome.reason = "虚拟开仓被拒（价格无效 / 仓位超限）"
            return outcome

        outcome.ok = True
        outcome.position = position
        outcome.position_id = position.position_id
        outcome.quantity = position.quantity
        outcome.amount = position.quantity * position.entry_price
        return outcome


# ---------------------------------------------------------------- 富途模拟后端

class FutuSimBackend(ExecutionBackend):
    """把单报到**富途模拟账户**（``TrdEnv.SIMULATE``）。

    只做**买入**：虚拟仓同样只支持做多，平仓/减仓仍归虚拟仓侧的
    止盈止损逻辑，本后端不越界。
    """

    name = BACKEND_FUTU_SIM

    def __init__(self, markets: Optional[Sequence[str]] = None, syncer=None):
        self.markets = frozenset(m.upper() for m in (markets if markets is not None else sim_markets()))
        self._syncer = syncer

    # ---------------------------------------------------- 依赖

    def _get_syncer(self):
        if self._syncer is not None:
            return self._syncer
        from .futu_portfolio_syncer import FutuPortfolioSyncer
        self._syncer = FutuPortfolioSyncer(trd_env="SIMULATE")
        return self._syncer

    def _resolve_account(self, market: str) -> Optional[Dict[str, Any]]:
        """找出该市场的模拟账户。**取不到就返回 None**，不猜、不回落。"""
        try:
            targets, _, _ = self._get_syncer().get_sync_targets()
        except Exception as e:
            log.warning("[Execution] 枚举模拟账户失败: %s", e)
            return None
        for target in targets:
            if market in (target.get("market_auth") or []):
                return target
        return None

    def _query_lot_size(self, market: str, code: str) -> int:
        """实查每手股数。查不到返回 0（调用方跳过）。"""
        try:
            from futu import OpenQuoteContext, RET_OK, Market, SecurityType

            ctx = OpenQuoteContext(host=HOST, port=PORT)
            try:
                ret, data = ctx.get_stock_basicinfo(
                    _market_enum(market), SecurityType.STOCK, [futu_code(market, code)],
                )
            finally:
                ctx.close()
            if ret != RET_OK or data is None or len(data) == 0:
                log.warning("[Execution] 每手股数查询失败 %s: %s", code, str(data)[:120])
                return 0
            return int(data.iloc[0].get("lot_size", 0) or 0)
        except Exception as e:
            log.warning("[Execution] 每手股数查询异常 %s: %s", code, e)
            return 0

    # ---------------------------------------------------- 主流程

    def submit(
        self,
        *,
        signal: Any,
        plan: Optional[Dict[str, Any]],
        side: str,
        price: float,
        amount: float,
        stop_loss_pct: float = -5.0,
        take_profit_pct: float = 10.0,
    ) -> ExecutionOutcome:
        code = str(signal.stock_code)
        outcome = ExecutionOutcome(
            backend=self.name, symbol=code, side=side, price=price, amount=amount,
        )

        def skip(reason: str) -> ExecutionOutcome:
            outcome.skipped = True
            outcome.reason = reason
            log.info("[Execution] ⏭ 模拟报单跳过 %s: %s", code, reason)
            append_journal(outcome.to_dict())
            return outcome

        def fail(reason: str) -> ExecutionOutcome:
            outcome.ok = False
            outcome.reason = reason
            log.error("[Execution] ❌ 模拟报单失败 %s: %s", code, reason)
            append_journal(outcome.to_dict())
            return outcome

        if side != "buy":
            return skip(f"模拟后端只支持买入（收到 {side}）")
        if price <= 0:
            return skip(f"价格无效（{price}）")
        if amount <= 0:
            return skip(f"金额无效（{amount}）")

        market, why = infer_market(code, getattr(signal, "raw_data", None))
        if not market:
            return skip(why)
        if market not in self.markets:
            return skip(f"市场 {market} 不在模拟报单白名单 {sorted(self.markets)} 内")

        target = self._resolve_account(market)
        if target is None:
            return skip(f"未找到 {market} 市场的富途模拟账户（模拟账户是否已开通？）")

        lot_size = self._query_lot_size(market, code)
        if lot_size <= 0:
            return skip(f"取不到 {code} 的每手股数，拒绝凭猜报单")

        quantity = floor_to_lot(amount, price, lot_size)
        if quantity <= 0:
            return skip(f"金额 {amount:.0f} 买不起一手（每手 {lot_size} 股 @ {price:g}）")
        outcome.quantity = float(quantity)

        key = order_slot_key(market, code, side)
        if not claim_order_slot(key):
            return skip(f"该标的今日已报过单（幂等槽位 {key} 已占用）")

        try:
            order_id = self._place(market, code, quantity, price, target)
        except Exception as e:
            release_order_slot(key)
            return fail(f"下单异常: {e}")

        if not order_id:
            # 报单没成功 → 归还槽位，别把当天唯一的机会吃掉
            release_order_slot(key)
            return fail("place_order 未返回有效单号")

        outcome.ok = True
        outcome.order_id = order_id
        outcome.position_id = order_id
        outcome.amount = quantity * price
        outcome.detail = f"模拟账户 {target['name']}（acc_id={target['acc_id']}）"
        log.info("[Execution] ✅ 模拟报单成功 %s %s股 @ %s 单号=%s", code, quantity, price, order_id)
        append_journal(outcome.to_dict())
        return outcome

    def _place(
        self, market: str, code: str, quantity: int, price: float, target: Dict[str, Any],
    ) -> str:
        """真正调 ``place_order``。成功返回单号，失败返回空串。"""
        from futu import (
            OpenSecTradeContext, OrderType, RET_OK, SecurityFirm, TrdEnv, TrdSide,
        )

        firm = getattr(SecurityFirm, target.get("firm") or "", SecurityFirm.FUTUSECURITIES)
        ctx = OpenSecTradeContext(host=HOST, port=PORT, security_firm=firm)
        try:
            ret, data = ctx.place_order(
                price=price,
                qty=quantity,
                code=futu_code(market, code),
                trd_side=TrdSide.BUY,
                order_type=OrderType.NORMAL,
                trd_env=TrdEnv.SIMULATE,
                acc_id=target["acc_id"],
            )
        finally:
            ctx.close()

        if ret != RET_OK:
            log.error("[Execution] place_order 失败: %s", str(data)[:200])
            return ""
        try:
            return str(data.iloc[0].get("order_id", ""))
        except Exception:
            return str(data)[:60]


def _market_enum(market: str):
    from futu import Market
    return getattr(Market, market.upper(), Market.HK)


# ---------------------------------------------------------------- 装配

def resolve_backend(
    name: Optional[str] = None, *, portfolio=None, syncer=None,
) -> ExecutionBackend:
    """按配置装配执行后端。未知名字回落虚拟仓后端。"""
    chosen = (name or selected_backend_name()).strip().lower()
    if chosen == BACKEND_FUTU_SIM:
        return FutuSimBackend(syncer=syncer)
    return VirtualPortfolioBackend(portfolio)


__all__ = [
    "BACKENDS",
    "BACKEND_FUTU_SIM",
    "BACKEND_VIRTUAL",
    "ENV_BACKEND",
    "ENV_SIM_MARKETS",
    "ExecutionBackend",
    "ExecutionOutcome",
    "FutuSimBackend",
    "VirtualPortfolioBackend",
    "append_journal",
    "claim_order_slot",
    "floor_to_lot",
    "futu_code",
    "futu_sim_enabled",
    "infer_market",
    "order_slot_key",
    "read_journal",
    "release_order_slot",
    "resolve_backend",
    "selected_backend_name",
    "sim_markets",
    "slot_taken",
]
