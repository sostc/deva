"""虚拟仓价格供给器 —— 给 ``VirtualPortfolio`` 里的持仓定期喂真实行情。

## 为什么需要这个模块

在此之前，虚拟仓的现价**没有任何人更新**：

- ``VirtualPortfolio.update_price()`` 只有两个调用方（``adaptive_cycle`` /
  ``tuner``），而 ``adaptive_cycle`` 是**懒单例** —— 没人碰到它就永远不会
  跑，于是它内部的 ``update_price`` 也就永远不会被调用；
- 真实券商账户看起来是活的，那其实靠 ``futu_portfolio_syncer`` 每 5 分钟
  直接覆盖 ``current_price``，跟虚拟仓没有关系；
- 行情总线 ``MarketDataBus`` 的 ``subscribe()`` **全仓无人调用**。

结果就是「孤儿持仓」：``虚拟测试`` 账户里的持仓现价永远停在开仓那一刻。
实测 NVDA 那条记了 **entry=450.0 / current=450.0**（开仓价当现价，一年没动），
而同期真实价格已经 217。更糟的是**止损永不触发** —— ``update_price`` 里那段
``current_price <= stop_loss`` 的判定从来没被执行过，所有止损位都是摆设。

## 第二层孤儿：本地记账账户

补上虚拟仓之后，同一形状的问题在 ``PortfolioManager`` 里还剩一层：
``account_type == "us"`` 的本地记账账户（Spark / Cutie / 「手动」）既不归
``FutuPortfolioSyncer``（那管 ``account_type == "futu"`` 的券商镜像），也没人
喂价。实测「手动」账户的现价停在一周前，UI 却照样把它算进当前市值。

所以本模块现在**同时喂两套**：

- ``VirtualPortfolio``（「虚拟测试」）—— 带止损止盈，价格会触发平仓；
- ``PortfolioManager`` 的本地记账账户 —— 无止损，只更新市值/浮盈。

券商同步账户（``futu``）**故意不碰**：它们的现价必须与券商 App 一致，
用行情快照覆盖会让人以为对账出错；港股本来也不在本总线路由内。

## 设计取舍

1. **主动拉取而非订阅总线**
   ``MarketDataBus.subscribe(codes, cb)`` 要求**预先给出代码列表**，而持仓
   是动态的：建仓、平仓、换标的之后代码集合就变了。预先订阅必然漏掉新标的。
   这里改成每轮从组合里现取 OPEN 持仓的代码，再 ``bus.fetch()`` 批量查。

2. **取不到的价格绝不写回**
   ``bus.fetch()`` 对取不到的代码返回 ``0.0``。直接写进 ``current_price``
   会把持仓市值清零、浮亏变成 -100%，还会**立刻击穿任何止损**（0 <= stop_loss）。
   所以只接受 ``price > 0``，取不到就记进 ``unpriced`` 并在诊断里透出。

3. **落库节流**
   ``update_price`` 只改内存不落库；不落库的话重启后现价又回到旧快照。
   但每个 tick 都 ``_save_positions()`` 太重，这里按 ``save_interval`` 节流。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


#: 哨兵：区分「调用方没传 manager（按需懒加载）」与「显式传 None（禁用）」。
#: ❗守卫必须能显式禁用 —— 否则构造一个 feed 就会真初始化 PortfolioManager
#: 去读生产库，守卫自证就成了污染源。
_AUTO = object()


class PortfolioPriceFeed:
    """周期性把行情喂给虚拟仓。

    Args:
        portfolio: ``VirtualPortfolio`` 实例；``None`` 时由调用方用 ``SR`` 注入。
        bus: ``MarketDataBus`` 实例；``None`` 时用单例。
        interval: 拉取间隔（秒）。默认 30s —— 比总线 5s tick 慢，但虚拟仓
            只关心止损止盈级别的变动，30s 足够，也免得把新浪接口打爆。
        save_interval: 落库间隔（秒）。
    """

    def __init__(
        self,
        portfolio: Any = None,
        bus: Any = None,
        interval: Optional[float] = None,
        save_interval: Optional[float] = None,
        manager: Any = _AUTO,
    ):
        self._portfolio = portfolio
        self._bus = bus
        self._manager = None if manager is _AUTO else manager
        self._auto_manager = manager is _AUTO
        self._interval = interval if interval is not None else _env_float(
            "NAJA_PORTFOLIO_PRICE_INTERVAL", 30.0
        )
        self._save_interval = save_interval if save_interval is not None else 60.0

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_save = 0.0

        # ── 诊断字段（UI / 守卫直接读）────────────────────────────────
        self.tick_count = 0
        self.error_count = 0
        self.last_tick_ts = 0.0
        self.last_error = ""
        self.last_prices: Dict[str, float] = {}
        #: 上一轮「有持仓但取不到价」的代码 → 原因
        self.unpriced: Dict[str, str] = {}
        self.closed_this_tick: int = 0
        #: 上一轮本地记账账户的更新结果 {账户名: 条数}
        self.local_updated: Dict[str, int] = {}

    # ── 装配 ────────────────────────────────────────────────────────────

    @property
    def portfolio(self):
        if self._portfolio is None:
            from deva.naja.register import SR
            self._portfolio = SR("virtual_portfolio")
        return self._portfolio

    @property
    def bus(self):
        if self._bus is None:
            from .market_data_bus import get_market_data_bus
            self._bus = get_market_data_bus()
        return self._bus

    @property
    def manager(self):
        """``PortfolioManager``（多账户）。取不到时返回 ``None`` 而不是抛。

        ❗多账户是**第二层孤儿**：``VirtualPortfolio`` 只管「虚拟测试」一个
        账户，Spark / Cutie / 「手动」这三个本地记账账户的持仓既不归富途同步器
        （那是 ``account_type="futu"`` 的券商镜像），也没有任何人喂价 ——
        实测「手动」账户的现价停在一周前，UI 上照样显示成当前市值。
        """
        if self._manager is None and self._auto_manager:
            try:
                from .portfolio_manager import get_portfolio_manager
                self._manager = get_portfolio_manager()
            except Exception as e:  # noqa: BLE001
                self.last_error = f"PortfolioManager 不可用：{type(e).__name__}: {e}"
                log.warning("[PortfolioPriceFeed] %s", self.last_error)
                return None
        return self._manager

    # ── 生命周期 ────────────────────────────────────────────────────────

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """启动后台守护线程。重复调用是幂等的。"""
        if self.alive:
            return True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="naja-portfolio-price-feed", daemon=True
        )
        self._thread.start()
        log.info(
            "[PortfolioPriceFeed] 已启动：每 %.0fs 刷新虚拟仓 + 本地记账账户现价（落库每 %.0fs）",
            self._interval, self._save_interval,
        )
        return True

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.refresh_once()
            except Exception as e:  # noqa: BLE001
                self.error_count += 1
                self.last_error = f"{type(e).__name__}: {e}"
                log.warning("[PortfolioPriceFeed] 刷新失败: %s", self.last_error)
            self._stop.wait(self._interval)

    # ── 核心 ────────────────────────────────────────────────────────────

    def open_codes(self) -> List[str]:
        """``VirtualPortfolio``（「虚拟测试」账户）里 OPEN 持仓的代码集合。

        去重、保留原始大小写交给总线归一。
        """
        vp = self.portfolio
        positions = getattr(vp, "_positions", {}) or {}
        seen: Dict[str, str] = {}
        for pos in positions.values():
            if getattr(pos, "status", "") != "OPEN":
                continue
            code = str(getattr(pos, "stock_code", "") or "").strip()
            if code:
                seen.setdefault(code.lower(), code)
        return list(seen.values())

    def local_account_codes(self) -> List[str]:
        """本地记账账户（``account_type != "futu"``）里 OPEN 持仓的代码集合。

        ❗**必须排除券商账户**：FutuHK / MoomooUS / FutuSim* 的现价由
        ``FutuPortfolioSyncer`` 写，用行情快照覆盖会让账户数字与券商 App
        对不上（港股那些总线根本取不到，覆盖也只会是 0.0）。
        """
        pm = self.manager
        if pm is None:
            return []
        getter = getattr(pm, "get_local_accounts", None)
        if not callable(getter):
            self.last_error = "PortfolioManager 缺少 get_local_accounts（版本不匹配）"
            log.warning("[PortfolioPriceFeed] %s", self.last_error)
            return []
        try:
            accounts = getter() or {}
        except Exception as e:  # noqa: BLE001
            self.last_error = f"get_local_accounts 失败：{type(e).__name__}: {e}"
            log.warning("[PortfolioPriceFeed] %s", self.last_error)
            return []

        seen: Dict[str, str] = {}
        for name, portfolio in accounts.items():
            try:
                opened = portfolio.get_open_positions() or []
            except Exception as e:  # noqa: BLE001 —— 单账户坏了不拖垮其它账户
                log.warning("[PortfolioPriceFeed] 账户 %s 读持仓失败: %s", name, e)
                continue
            for pos in opened:
                code = str(getattr(pos, "stock_code", "") or "").strip()
                if code:
                    seen.setdefault(code.lower(), code)
        return list(seen.values())

    def refresh_once(self) -> Dict[str, Any]:
        """跑一轮：取价 → 喂持仓 → 按需落库。返回本轮诊断。"""
        vp = self.portfolio
        vp_codes = self.open_codes()
        local_codes = self.local_account_codes()

        # 两套持仓可能持同一只票（如 588200 同时在「虚拟测试」和 FutuSimCN），
        # 合并成一次 fetch，避免对同一批代码发两轮请求。
        merged: Dict[str, str] = {}
        for code in vp_codes + local_codes:
            merged.setdefault(code.lower(), code)
        codes = list(merged.values())

        self.tick_count += 1
        self.last_tick_ts = time.time()

        if not codes:
            self.last_prices = {}
            self.unpriced = {}
            self.local_updated = {}
            return {"codes": 0, "priced": 0, "updated": 0, "local_updated": {},
                    "note": "无 OPEN 持仓"}

        try:
            prices = self.bus.fetch(codes) or {}
        except Exception as e:  # noqa: BLE001
            self.error_count += 1
            self.last_error = f"{type(e).__name__}: {e}"
            self.unpriced = {c: f"总线异常：{type(e).__name__}" for c in codes}
            raise

        priced: Dict[str, float] = {}
        unpriced: Dict[str, str] = {}
        for code in codes:
            price = float(prices.get(code) or 0.0)
            # ❗0.0 = 取不到，绝不能写回（会清零市值并击穿所有止损）
            if price > 0:
                priced[code] = price
            else:
                unpriced[code] = "行情源返回 0（无此路由或非交易时段）"

        self.last_prices = priced
        self.unpriced = unpriced

        # ① 虚拟仓：只喂自己那批代码（local 账户的代码不归它管）
        vp_set = {c.lower() for c in vp_codes}
        updated = 0
        closed_total = 0
        update_failures: Dict[str, str] = {}
        for code, price in priced.items():
            if code.lower() not in vp_set:
                continue
            try:
                closed = vp.update_price(code, price) or []
            except Exception as e:  # noqa: BLE001
                self.error_count += 1
                self.last_error = f"update_price({code}) {type(e).__name__}: {e}"
                update_failures[code] = f"{type(e).__name__}: {e}"
                continue
            updated += 1
            if closed:
                closed_total += len(closed)
                for pos in closed:
                    log.warning(
                        "[PortfolioPriceFeed] 补上迟到的平仓：%s(%s) 成本 %.3f → 现价 %.3f "
                        "收益 %.2f%% 原因 %s（这条持仓此前没有价格源，止损判定从未执行过）",
                        getattr(pos, "stock_name", ""), getattr(pos, "stock_code", ""),
                        getattr(pos, "entry_price", 0.0), price,
                        getattr(pos, "return_pct", 0.0), getattr(pos, "close_reason", ""),
                    )

        # ② 本地记账账户（Spark / Cutie / 手动）：与虚拟仓并列的第二层孤儿
        local_updated: Dict[str, int] = {}
        local_set = {c.lower() for c in local_codes}
        local_prices = {c: p for c, p in priced.items() if c.lower() in local_set}
        if local_prices:
            pm = self.manager
            updater = getattr(pm, "update_local_prices", None) if pm is not None else None
            if callable(updater):
                try:
                    local_updated = updater(local_prices) or {}
                except Exception as e:  # noqa: BLE001
                    self.error_count += 1
                    self.last_error = f"update_local_prices {type(e).__name__}: {e}"
                    log.warning("[PortfolioPriceFeed] 本地账户喂价失败: %s", e)
            elif pm is not None:
                self.last_error = "PortfolioManager 缺少 update_local_prices（版本不匹配）"
                log.warning("[PortfolioPriceFeed] %s", self.last_error)

        self.local_updated = local_updated
        self.closed_this_tick = closed_total
        self._maybe_save(vp)

        if unpriced and not priced:
            # 全取不到：这一轮等于没干活，必须留痕（否则又变成"看着在跑"）
            log.warning(
                "[PortfolioPriceFeed] 本轮 %d 只持仓全部取不到价格，现价未被更新：%s",
                len(codes), "、".join(f"{c}({r})" for c, r in list(unpriced.items())[:5]),
            )

        return {
            "codes": len(codes),
            "priced": len(priced),
            "updated": updated,
            "closed": closed_total,
            "local_updated": dict(local_updated),
            "unpriced": dict(unpriced),
            "update_failures": update_failures,
        }

    def _maybe_save(self, vp: Any) -> None:
        now = time.time()
        if now - self._last_save < self._save_interval:
            return
        self._last_save = now
        flush = getattr(vp, "flush", None)
        try:
            if callable(flush):
                flush()
            else:  # 兼容老接口
                vp._save_positions()  # noqa: SLF001
        except Exception as e:  # noqa: BLE001
            self.error_count += 1
            self.last_error = f"落库失败 {type(e).__name__}: {e}"
            log.warning("[PortfolioPriceFeed] 持仓落库失败: %s", e)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "alive": self.alive,
            "interval": self._interval,
            "tick_count": self.tick_count,
            "error_count": self.error_count,
            "last_tick_ts": self.last_tick_ts,
            "last_error": self.last_error,
            "priced_codes": len(self.last_prices),
            "unpriced_codes": len(self.unpriced),
            "unpriced": dict(self.unpriced),
            "local_updated": dict(self.local_updated),
            "local_account_names": self._local_account_names(),
        }

    def _local_account_names(self) -> List[str]:
        pm = self.manager
        getter = getattr(pm, "get_local_accounts", None) if pm is not None else None
        if not callable(getter):
            return []
        try:
            return sorted((getter() or {}).keys())
        except Exception:  # noqa: BLE001 —— 诊断字段不许抛
            return []


_feed: Optional[PortfolioPriceFeed] = None
_feed_lock = threading.Lock()


def get_portfolio_price_feed(portfolio: Any = None) -> PortfolioPriceFeed:
    """进程内单例。❗状态型对象只许单例，直接构造会造出两份各写各的。"""
    global _feed
    with _feed_lock:
        if _feed is None:
            _feed = PortfolioPriceFeed(portfolio=portfolio)
        elif portfolio is not None and _feed._portfolio is None:  # noqa: SLF001
            _feed._portfolio = portfolio  # noqa: SLF001
        return _feed
