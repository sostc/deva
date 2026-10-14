"""TRotationRunner —— 把「做 T 降成本」引擎接到 MarketDataBus 上。

背景
----
``t_rotation.TRotationEngine`` 写完之后，全仓库找不到一个调用方 ——
这是本仓库最经典的「静默失效」形态：代码是对的、守卫是绿的、
但没有任何一行行情会流进它。本模块就是那个缺失的调用方。

用户拍板的数据源（2026-10-14 更新）：**富途统一行情**（:mod:`futu_quote_source`）。
标的见 :mod:`core_holdings`：A 股 588200 科创芯片ETF / 美股 QQQ / 港股 00700。

❗为什么不再走 MarketDataBus（新浪）
--------------------------------
实测两处**静默失效**，数据到了、链路绿着、结果却是空的：

* **港股**：总线里根本没有 ``hk`` 分支，``hk00700`` 取回来永远是 ``{}``。
* **美股**：新浪明明返回了实时价（``gb_qqq`` 743.10，与富途 743.095 一致），
  但 ``_parse_response`` 只解析 BlockDictionary 活跃美股池里的代码
  （启动日志「美股Block=15」，全是股票，**ETF 不在池里**）→ 判空丢弃。

它负责的事
----------
1. **轮询取行情**，把 ``FutuQuote`` 翻译成引擎要的 tick
2. **交易时段 / 会话管理**：**按市场各自判断**（见 :mod:`market_session`）——
   每天首个 tick 开新会话（带昨收），收盘前 forced-settle，跨会话兜底买回
3. **单位换算**：富途给的是**累计**成交量，而 VWAP 要的是**增量**。
   直接把累计量喂进去会把 VWAP 压成一条越走越平的曲线
4. **死水检测**：连续 N 次「价格与成交量都没动」就停喂并告警 ——
   节假日的报价会以「昨收价」反复出现，纯粹制造幻觉

刻意不做的事
------------
* **不做节假日日历**。休市日的报价会被死水检测拦下，比维护一份会过期的日历可靠。
* **不自动补足底仓**，除非显式打开 ``NAJA_T_ROTATION_ESTABLISH=1``。
  动用多少资金建仓必须由人决定，代码不该替用户拍板。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from .core_holdings import (
    CoreHoldingSpec,
    env_flag,
    env_float,
    load_core_holdings,
)
from .core_establish_gate import CoreEstablishGate
from .core_establish_watch import CoreEstablishWatch
from .market_session import (
    is_trading,
    market_phase,
    minutes_to_close,
    session_date,
    session_open_ts,
)
from .t_rotation import TRotationConfig

log = logging.getLogger(__name__)


class TRotationRunner:
    """行情驱动的做 T 运行器。纯虚拟盘，不触达任何真实下单链路。"""

    #: 连续多少次「毫无变化」就判定行情断流/休市
    DEFAULT_FLAT_LIMIT = 12

    #: 连续多少轮「分批补底仓但份额零增长」才算真的卡住。
    #: 底仓规模（默认 40% 总资产）本来就超过单笔上限（默认 20%），
    #: **分批是设计意图，不是故障** —— 前几轮没补满属正常，
    #: 只有一直原地踏步才值得占 ERROR 通道喊人。
    DEFAULT_STALL_LIMIT = 3

    def __init__(
        self,
        portfolio=None,
        quotes=None,
        engine=None,
        ledger=None,
        specs: Optional[List[CoreHoldingSpec]] = None,
        poll_seconds: Optional[float] = None,
        establish_missing: Optional[bool] = None,
        flat_poll_limit: Optional[int] = None,
        clock: Optional[Callable[[], float]] = None,
        max_quote_age: Optional[float] = None,
        on_sim: Optional[bool] = None,
        portfolios: Optional[Dict[str, Any]] = None,
        stall_limit: Optional[int] = None,
        establish_gate=None,
        establish_watch=None,
    ):
        self._specs = list(specs) if specs else load_core_holdings()
        self._by_code: Dict[str, CoreHoldingSpec] = {s.code: s for s in self._specs}

        self._poll_seconds = float(
            poll_seconds if poll_seconds is not None
            else env_float("NAJA_T_ROTATION_POLL_SECONDS", 30.0)
        )
        self._max_quote_age = float(
            max_quote_age if max_quote_age is not None
            else max(60.0, self._poll_seconds * 2.5)
        )
        self._establish = (
            establish_missing if establish_missing is not None
            # 默认开：用户已给出「40% 仓位」这个数字，
            # 此前「动用多少资金由人拍板、代码不擅自下场」的前提不再成立。
            # 想让系统只观察不建仓，置 NAJA_T_ROTATION_ESTABLISH=0。
            else env_flag("NAJA_T_ROTATION_ESTABLISH", True)
        )
        self._flat_limit = int(flat_poll_limit or self.DEFAULT_FLAT_LIMIT)
        # 底仓要分好几批才补得满，中间几轮"没补满"是计划的一部分；
        # 只有连续这么多轮一分钱也没买进去，才按真故障处理。
        self._stall_limit = int(
            stall_limit if stall_limit is not None
            else env_float("NAJA_T_ROTATION_STALL_LIMIT", self.DEFAULT_STALL_LIMIT)
        )

        # ❗真仓开关：默认 **关**。关着的时候一切照旧走虚拟盘，
        # 装了新代码不代表可以自动开始往模拟账户报单 —— 要真下单必须
        # 显式置 NAJA_T_ROTATION_ON_SIM=1。
        self._on_sim = (
            on_sim if on_sim is not None
            else env_flag("NAJA_T_ROTATION_ON_SIM", False)
        )

        self._clock = clock or time.time
        self._portfolio = portfolio
        self._quotes = quotes
        self._engine = engine
        self._ledger = ledger
        #: 按市场各持一份组合 / 引擎。三个模拟仓是三个**独立账户**，
        #: 各记各的本币 —— 共用一个组合对象等于把港元、美元、人民币混着算。
        self._portfolios: Dict[str, Any] = {}
        self._engines: Dict[str, Any] = {}

        # 补仓闸门：**下单前必须先问决策中心**。背景见 core_establish_gate 模块
        # 文档 —— 没有它的时候，逆风行情反而是买入触发器
        #（target 的定义本身会让「越跌 → 目标份额越大 → 接着买」）。
        # 留 None 是为了让守卫能注入假裁定，离线验证闸门的三条分支。
        self._gate = establish_gate if establish_gate is not None \
            else CoreEstablishGate()
        # 「等待机会」的一等公民：守望只回答「这一步值不值得去问」，
        # 真正去问的仍是 self._gate。两者分开，就是为了不让「机会」和
        # 「放行」变成同一件事 —— 背景见 core_establish_watch 模块文档。
        if not hasattr(self, "_establish_watch"):
            self._establish_watch: Any = (
                establish_watch
                if establish_watch is not None
                else CoreEstablishWatch(self._gate)
            )
        # 闸门拦截的按天去重键。被 Manas 否掉是**常态**（不是故障），
        # 30 秒一条就会把 INFO 刷成噪音；真正该喊的是 source=unavailable。
        self._gate_noted: Dict[str, str] = {}

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

        self._session_date: Dict[str, str] = {}
        self._settled: set = set()
        # 每份计划当天折算出来的目标份额。 **必须按天锁定**：
        # 目标份额若随 tick 价格漂移，份额守恒的基准就跟着漂，
        # 守恒校验会变成「拿一把会伸缩的尺子量自己」。
        self._plan_targets: Dict[str, float] = {}
        self._plan_date: Dict[str, str] = {}
        # 真的卡住的额度冲突才告警，按天去重，别把日志刷满
        self._budget_warned: Dict[str, str] = {}
        # 在飞单提示的按天去重键。这类是**持续状态**而不是瞬时事件：
        # 一笔挂单可能挂几分钟，30 秒一条就把日志淹了。
        # 「到底有没有下单」在订单流水和心跳里另有记录，不靠这条提示。
        self._inflight_noted: Dict[str, str] = {}
        # 分批补底仓的进度追踪：(交易日, 上一轮持有份额, 连续零增长轮数)
        self._fill_progress: Dict[str, tuple] = {}
        # 当天已成交的分批笔数，仅用于日志可读性：(交易日, 笔数)
        self._fill_batches: Dict[str, tuple] = {}
        self._last_price: Dict[str, float] = {}
        self._last_cum_vol: Dict[str, float] = {}
        self._flat_runs: Dict[str, int] = {}
        self._suspended: Dict[str, str] = {}
        self._last_diag: Dict[str, Dict[str, Any]] = {}
        self._errors: Dict[str, str] = {}

        self._stats: Dict[str, int] = {
            "polls": 0,
            "ticks": 0,
            "duplicates": 0,
            "quote_miss": 0,
            "stale_quote": 0,
            "off_hours_skips": 0,
            "settlements": 0,
            "cross_session_buyback": 0,
            "actions": 0,
            "pushed_ticks": 0,
            "fetch_errors": 0,
            # 被大环境闸门拦下 / 闸门链路不可用。两个数区分得开很重要：
            # 前者是策略在观望，后者是故障 —— 混起来看会以为一切正常。
            "gate_blocked": 0,
            "gate_unavailable": 0,
            # 守望认为「还不值得去问」—— 与 gate_blocked 区分开：
            # 前者是压根没走到决策中心，后者是走到被否了。
            "watch_waiting": 0,
        }

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @property
    def specs(self) -> List[CoreHoldingSpec]:
        return list(self._specs)

    @property
    def enabled(self) -> bool:
        return env_flag("NAJA_T_ROTATION_ENABLED", True)

    def start(self) -> bool:
        """启动后台轮询。幂等；被禁用或依赖缺失时返回 False 并留下原因。"""
        if not self.enabled:
            log.info("[TRotationRunner] NAJA_T_ROTATION_ENABLED=0，未启动")
            return False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            if not self._bootstrap():
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop, name="t-rotation", daemon=True
            )
            self._thread.start()
            names = ", ".join(f"{s.name}({s.bus_code})" for s in self._specs)
            log.info(
                f"[TRotationRunner] 已启动：{names}"
                f"（轮询 {self._poll_seconds:.0f}s，"
                f"自动建仓={'开' if self._establish else '关'}）"
            )
            return True

    def stop(self, timeout: float = 3.0) -> bool:
        self._stop.set()
        th = self._thread
        if th is not None and th.is_alive():
            th.join(timeout)
        return not (th is not None and th.is_alive())

    @property
    def running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    # ------------------------------------------------------------------
    # 按市场路由
    # ------------------------------------------------------------------
    def _pf(self, market: str):
        """该市场用的组合。真仓模式下是富途模拟账户，否则是虚拟盘。"""
        return self._portfolios.get(market) or self._portfolio

    def _eng(self, market: str):
        """该市场用的做 T 引擎。与 :meth:`_pf` 一一对应。"""
        return self._engines.get(market) or self._engine

    # ------------------------------------------------------------------
    # 依赖装配
    # ------------------------------------------------------------------
    def _bootstrap(self) -> bool:
        # 组合 —— 走 SR 单例，和 UI/其它策略共用同一个虚拟盘
        if self._portfolio is None:
            try:
                from deva.naja.register import SR

                self._portfolio = SR("virtual_portfolio")
            except Exception as e:  # pragma: no cover - 依赖环境
                self._errors["portfolio"] = str(e)
                log.error(f"[TRotationRunner] 取不到虚拟盘，运行器不启动: {e}")
                return False
        if self._portfolio is None:
            self._errors["portfolio"] = "virtual_portfolio 为 None"
            log.error("[TRotationRunner] 虚拟盘为 None，运行器不启动")
            return False

        # 行情源 —— 富途（三市场统一实时）。见模块 docstring：新浪链路
        # 在港股/美股 ETF 上是静默失效的，不能再当数据源用。
        if self._quotes is None:
            try:
                from .futu_quote_source import get_futu_quote_source

                self._quotes = get_futu_quote_source()
            except Exception as e:  # pragma: no cover
                self._errors["quotes"] = str(e)
                log.error(f"[TRotationRunner] 取不到富途行情源: {e}")
                return False

        # 账本 + 引擎
        if self._ledger is None:
            from .core_position import get_core_position_ledger

            self._ledger = get_core_position_ledger()
        if self._engine is None:
            from .t_rotation import TRotationEngine

            self._engine = TRotationEngine(
                portfolio=self._portfolio, ledger=self._ledger
            )

        # ── 真仓模式：按市场各建一份富途模拟组合 + 一台引擎 ──
        # 三个模拟仓是三个独立账户、三种本币，共用一个组合对象等于把
        # 港元/美元/人民币混着算（用户拍板：各市场独立本币记账）。
        if self._on_sim:
            from .t_rotation import TRotationEngine

            for market in sorted({s.market for s in self._specs if s.market}):
                pf = self._portfolios.get(market)
                if pf is None:
                    try:
                        from .futu_sim_portfolio import FutuSimPortfolio

                        pf = FutuSimPortfolio(market)
                        self._portfolios[market] = pf
                    except Exception as e:  # pragma: no cover
                        self._errors[f"sim_portfolio_{market}"] = str(e)
                        log.error(
                            f"[TRotationRunner] {market} 模拟组合装配失败，"
                            f"该市场回退虚拟盘: {e}"
                        )
                        continue
                if market not in self._engines:
                    self._engines[market] = TRotationEngine(
                        portfolio=pf, ledger=self._ledger
                    )
            if self._portfolios:
                log.info(
                    "[TRotationRunner] 真仓模式开启，已接管市场 %s",
                    sorted(self._portfolios),
                )
            else:
                self._errors["sim_portfolio"] = "真仓模式已开启但一个模拟组合都没建成"
                log.error(
                    "[TRotationRunner] ❌ 真仓模式已开启但没有任何模拟组合可用，"
                    "全部标的将回退虚拟盘（不会真的下单）"
                )

        for spec in self._specs:
            # ❗每个标的挂上**它自己市场**的参数档：判据按波动尺度标定，
            # 拿 A 股那套去套 QQQ 会永不触发（实测 QQQ 振幅 0.72% < 闸门 1.0%）。
            prof = spec.profile
            self._eng(spec.market).set_symbol_profile(
                spec.code,
                thresholds=prof.thresholds,
                config=replace(
                    # ❗从**市场档**取，而不是裸 TRotationConfig()：
                    # 了结/买回的回撤容忍度必须与当日振幅同量级，
                    # 三市场共用 0.3% 会让 QQQ 几乎无法自然买回
                    prof.config,
                    max_round_amount=prof.max_round_amount,
                    round_lot=spec.round_lot,
                    # 最少做**一手**：A股/港股 100 份，美股 1 股。
                    # 沿用 100 会让美股「一手」变成 7 万多美元。
                    min_round_shares=spec.round_lot,
                ),
                round_lot=spec.round_lot,
            )
            # 只有**显式指定了份额**才能在此时登记；按比例折算的必须等有价格，
            # 交给 _ensure_plan()（详见那里的注释）。
            if spec.explicit:
                self._eng(spec.market).register_target(
                    spec.code, spec.target_shares, name=spec.name, note=spec.note
                )

        return True

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def _run_loop(self):
        while not self._stop.is_set():
            try:
                self.poll()
            except Exception as e:  # 循环里绝不让异常冒出去把线程打死
                log.error(f"[TRotationRunner] poll 异常: {e}", exc_info=True)
                self._stats["fetch_errors"] += 1
            self._stop.wait(self._poll_seconds)

    def poll(self) -> List[Dict[str, Any]]:
        """拉一次行情并驱动引擎。对测试与手动结算同样可用。"""
        if self._engine is None and not self._bootstrap():
            return []
        now = self._clock()
        dt = datetime.fromtimestamp(now)
        results: List[Dict[str, Any]] = []

        self._stats["polls"] += 1
        for spec in self._specs:
            # ❗时段必须**按市场各自判断**：三个市场的开盘时间互不重叠
            # （A股 09:30–15:00 / 港股 09:30–16:00 / 美股 21:30–04:00 北京时间）。
            # 写死成 A 股时段的话，美股一整场都不会被喂一根 tick。
            if not is_trading(spec.market, dt):
                self._stats["off_hours_skips"] += 1
                continue
            try:
                results.append(self._pump(spec, dt, now))
            except Exception as e:
                log.error(f"[TRotationRunner] {spec.code} 处理失败: {e}", exc_info=True)
                results.append({"code": spec.code, "error": str(e)})
        self._heartbeat(dt)
        return results

    # ------------------------------------------------------------------
    # 心跳
    # ------------------------------------------------------------------
    # 每多少次轮询自报一次。30s × 20 = 10 分钟。
    HEARTBEAT_EVERY = 20

    def _heartbeat(self, dt: datetime) -> None:
        """周期性自报「我活着、我看到了什么、我为什么没动手」。

        ❗**静默的后台任务等于没有后台任务**。真仓模式下做 T 会自己报单，
        而 ``poll()`` 正常路径**一行日志都不打** —— 于是「在跑但没机会」
        与「线程已经死了」在日志上完全无法区分：页面数字停在最后一次的值，
        看起来就是「今天没行情」。这类「合法的空」比报错危险得多。
        所以必须定期把**增量**说出来，让人能一眼判断链路是不是活的。
        """
        n = self._stats["polls"]
        # 第一次轮询必报（相当于启动自检），之后按间隔报。
        # 否则「重启后到底有没有真正跑起来」要等 10 分钟才知道。
        if n != 1 and n % self.HEARTBEAT_EVERY != 0:
            return

        mode = "真仓(模拟账户)" if self._on_sim else "虚拟盘"
        parts = [
            f"💓 心跳 轮询={n}",
            f"行情 缺失={self._stats['quote_miss']} 错误={self._stats['fetch_errors']}",
            f"tick={self._stats['ticks']} 动作={self._stats['actions']}",
            f"休市跳过={self._stats['off_hours_skips']}",
            f"模式={mode}",
        ]
        lines = ["[TRotationRunner] " + " | ".join(parts)]

        for spec in self._specs:
            if not is_trading(spec.market, dt):
                lines.append(f"    · {spec.code}({spec.market}) 休市，未取数")
                continue
            mtc = minutes_to_close(spec.market, dt)
            try:
                held = self._ledger.effective_shares(
                    spec.code, self._pf(spec.market),
                    now=self._clock(),
                    session_open_ts=session_open_ts(spec.market, dt),
                )
            except Exception as e:  # 心跳绝不能把轮询拖死
                held = float("nan")
                lines.append(f"    · {spec.code} 读持仓失败: {e}")
            target = self._plan_targets.get(spec.code)
            tgt = f"/目标{target:.0f}" if target else ""
            diag = self._last_diag.get(spec.code) or {}
            why = (
                diag.get("reason")
                or diag.get("action")
                or ("已喂 tick" if self._last_diag.get(spec.code) else "尚未取到行情")
            )
            lines.append(
                f"    · {spec.code}({spec.market}) 盘中 距收盘={mtc:.0f}min "
                f"持有={held:.0f}{tgt} 最近={why}"
            )
        log.info("\n".join(lines))

    # ------------------------------------------------------------------
    # 单个标的
    # ------------------------------------------------------------------
    def _read_quote(self, spec: CoreHoldingSpec):
        """同步取最新行情（富途）。连不上/无此标的返回 None。"""
        src = self._quotes
        if src is None:
            return None
        try:
            quote = src.get(spec.code, spec.market)
        except Exception as e:
            self._stats["fetch_errors"] += 1
            log.debug(f"[TRotationRunner] 取 {spec.code} 行情失败: {e}")
            return None
        if quote is None or not quote.ok:
            self._stats["fetch_errors"] += 1
            log.debug(
                f"[TRotationRunner] {spec.code} 行情不可用: "
                f"{getattr(quote, 'error', '无返回')}"
            )
            return None
        return quote

    def _pump(self, spec: CoreHoldingSpec, dt: datetime, now: float) -> Dict[str, Any]:
        code = spec.code
        market = spec.market
        # ❗会话锚点用**市场自己的交易日**：北京时间周三 03:35 属于美东周二
        # 那个交易日。用北京日期会让美股在 04:00 和 21:30 各开一次会话，
        # 昨收基准被重置两次，日内序列直接废掉。
        open_ts = session_open_ts(market, dt)
        date = session_date(market, dt)

        suspended = self._suspended.get(code)
        if suspended:
            if self._session_date.get(code) != date:
                # 换日就解封，别把一次故障封到天荒地老
                self._suspended.pop(code, None)
                self._flat_runs[code] = 0
            else:
                return {"code": code, "action": "NONE", "reason": suspended}

        quote = self._read_quote(spec)
        if quote is None or quote.current <= 0 or quote.prev_close <= 0:
            self._stats["quote_miss"] += 1
            return {
                "code": code, "action": "NONE", "market": market,
                "reason": "行情缺失（无报价或缺昨收）",
            }
        age = getattr(quote, "age", 0.0) or 0.0
        if age > self._max_quote_age:
            self._stats["stale_quote"] += 1
            return {
                "code": code, "action": "NONE",
                "reason": f"行情过期（{age:.0f}s > {self._max_quote_age:.0f}s）",
            }

        self._maybe_start_session(spec, quote, now, dt, open_ts, date)

        price = float(quote.current)
        # 富途给的也是**当日累计**成交量，VWAP 要的是每根 bar 的增量
        cum_vol = float(getattr(quote, "volume", 0.0) or 0.0)
        prev_cum = self._last_cum_vol.get(code)
        dvol = 0.0
        if prev_cum is not None and cum_vol >= prev_cum:
            dvol = cum_vol - prev_cum
        self._last_cum_vol[code] = cum_vol

        mtc = minutes_to_close(market, dt)

        # 收盘前：先把没买回的买回来，再谈别的
        force_min = self._eng(spec.market).config_for(code).force_close_minutes
        if mtc is not None and mtc <= force_min:
            if (code, date) in self._settled:
                return {"code": code, "action": "NONE", "reason": "当日已结算"}
            report = self._eng(spec.market).settle_before_close(
                code, price, now=now, session_open_ts=open_ts
            )
            self._settled.add((code, date))
            self._stats["settlements"] += 1
            diag = {
                "code": code, "action": "SETTLE",
                "reason": f"距收盘 {mtc:.0f} 分钟，执行收盘结算",
                "settlement": report,
            }
            self._last_diag[code] = diag
            return diag

        # 底仓**每轮**都查，不能只在换日那一轮做：
        #   ① 一次性买到位会撞虚拟仓的单笔限额（默认 20%），必须分批；
        #   ② 底仓若因任何原因出现缺口，就该当天补回来。
        # 位置刻意放在「价量无变化 → 跳过」之前 ——
        # 横盘时价格不动，若放在后面，分批就永远补不到第二笔。
        self._maybe_establish_core(spec, quote, now, open_ts, date)

        # 价格与成交量都没动 → 没有新信息，不值得占一根 bar
        if self._last_price.get(code) == price and dvol <= 0:
            runs = self._flat_runs.get(code, 0) + 1
            self._flat_runs[code] = runs
            self._stats["duplicates"] += 1
            if runs >= self._flat_limit:
                self._suspended[code] = (
                    f"连续 {runs} 次行情无变化，疑似休市或数据源断流，"
                    f"已停止喂数至下一个交易日"
                )
                log.warning(f"[TRotationRunner] ⚠️ {spec.name}({code}) {self._suspended[code]}")
            return {"code": code, "action": "NONE", "reason": "价格与成交量均无变化"}

        self._flat_runs[code] = 0
        self._last_price[code] = price

        diag = self._eng(spec.market).on_tick(
            code,
            price,
            timestamp=now,
            volume=dvol,
            minutes_to_close=mtc,
            session_open_ts=open_ts,
        )
        self._last_diag[code] = diag
        self._stats["ticks"] += 1
        if diag.get("action") not in (None, "NONE", ""):
            self._stats["actions"] += 1
            log.info(
                f"[TRotationRunner] {spec.name}({code}) → {diag.get('action')}: "
                f"{diag.get('reason', '')}"
            )
        return diag

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 目标份额折算（每个交易日只做一次）
    # ------------------------------------------------------------------
    def total_assets(self, market: Optional[str] = None) -> float:
        """折算底仓用的分母 = 组合总资金（不是可用资金）。

        刻意不用 available：那玩意会被其它策略的临时持仓挤来挤去，
        底仓规模不该跟着别人的仓位抖。

        ❗``market``：真仓模式下每个市场是**独立账户、独立本币**，
        折算必须用该市场自己的总资产 —— 拿人民币总资产去折 QQQ 的份数，
        单位都不对。
        """
        try:
            summary = self._pf(market).get_summary() or {}
        except Exception as e:  # pragma: no cover
            log.debug(f"[TRotationRunner] 读组合摘要失败: {e}")
            return 0.0
        val = float(summary.get("total_capital", 0.0) or 0.0)
        if val <= 0:
            val = float(summary.get("available_capital", 0.0) or 0.0)
        return val

    def _ensure_plan(
        self, spec: CoreHoldingSpec, price: float, date: str, carried: float = 0.0
    ) -> float:
        """算出并**锁定**本交易日的目标份额。

        为什么必须锁死
        --------------
        目标份额 = 总资产 × alloc_pct ÷ 现价。价格每 tick 都在动，
        若每次都重算，登记在账本里的 plan 就会漂；而计划份额正是
        「份额守恒」的基准 —— 用一把会伸缩的尺子量自己，校验形同虚设。

        所以：一天只在**见到首份有效行情时**折算一次，
        其余时间一律读缓存。
        """
        cached = self._plan_targets.get(spec.code)
        if cached is not None and self._plan_date.get(spec.code) == date:
            return cached

        # ❗必须带 market：真仓模式下三个市场是**三个独立账户、三种本位币**。
        #   漏掉参数会退化到 self._portfolio（虚拟盘兜底），于是折出的是
        #   「虚拟盘人民币总资产 ÷ 港股价格」这种跨币种跨账户的量纲 ——
        #   而且日志那句「📐 …总资产 X×40%÷P」读的是**带 market 的版本**，
        #   展示的数字与真正用来算的数不是同一个，看日志排查会被带偏
        #   （2026-10-14 实测：登记 405600 份，那是按虚拟盘 100 万折的；
        #    按 CN 账户 998981 折应为 405200）。
        target = spec.resolve_target_shares(self.total_assets(spec.market), price)
        if target <= 0:
            # 折算不出来（价格缺失 / 资金为 0）就沿用昨天的，
            # 绝不把计划悄悄砍成 0 —— 那等于无声地放弃长期持有。
            if cached:
                log.debug(
                    f"[TRotationRunner] {spec.code} 本次折算失败，沿用昨日计划 {cached:.0f} 份"
                )
                return cached
            log.warning(f"[TRotationRunner] {spec.code} 无法折算目标份额（价格/资金缺失）")
            return 0.0

        # 只增不减：价格上涨会让同一比例折出更少的份额，
        # 若照单收录，等于事后宣布「你的底仓超配了」→ 可用卖出额度被压缩。
        # 长期持有的份额只能被人为下调（改 env），不能被行情悄悄削掉。
        if cached and cached > target:
            log.info(
                f"[TRotationRunner] {spec.name} 折算目标 {target:.0f} 份 < 已登记 "
                f"{cached:.0f} 份（价格上涨所致），按「只增不减」保留较大值"
            )
            target = cached

        self._eng(spec.market).register_target(
            spec.code, target, name=spec.name,
            note=f"{spec.note}｜目标约占总资产 {spec.alloc_pct:g}%",
        )
        self._plan_targets[spec.code] = target
        self._plan_date[spec.code] = date
        log.info(
            f"[TRotationRunner] 📐 {spec.name}({spec.code}) 今日目标 {target:.0f} 份"
            f"（{spec.market} 总资产 {self.total_assets(spec.market):.0f} "
            f"× {spec.alloc_pct:g}% ÷ {price:.3f}）"
        )
        return target

    def _maybe_start_session(
        self, spec: CoreHoldingSpec, quote, now: float,
        dt: datetime, open_ts: float, date: str,
    ):
        code = spec.code
        if self._session_date.get(code) == date:
            return

        # ① 跨会话兜底：昨天（或上次进程）没买回来的，开盘第一件事就是买回来。
        #    这是「保证长期持有」在重启/提前退出场景下唯一的兑现点。
        outstanding = list(self._ledger.outstanding(code))
        if outstanding:
            qty = sum(ob.quantity for ob in outstanding)
            report = self._eng(spec.market).settle_before_close(
                code, float(quote.current), now=now, session_open_ts=open_ts
            )
            self._stats["cross_session_buyback"] += 1
            log.warning(
                f"[TRotationRunner] 🚨 跨会话回购 {spec.name}({code}): "
                f"待补 {qty:.0f} 份 → {report.get('forced_buyback', 0):.0f} 份已买回"
            )

        # ② 开新会话（重置日内序列 + 设定昨收基准）
        self._eng(spec.market).start_session(
            code, float(quote.prev_close), name=spec.name, session_open_ts=open_ts
        )
        self._session_date[code] = date
        self._settled = {k for k in self._settled if k[0] != code}
        self._last_price.pop(code, None)
        self._last_cum_vol.pop(code, None)
        self._flat_runs[code] = 0

        # ③ 开完新会话就登记今日目标（一次性），供下面补给使用
        self._ensure_plan(spec, float(quote.current), date)

    def _maybe_establish_core(
        self, spec: CoreHoldingSpec, quote, now: float, open_ts: float, date: str
    ):
        """底仓不足时补足。

        规模来自 ``CoreHoldingSpec.resolve_target_shares``
        （总资产 × ``alloc_pct`` ÷ 现价），这是用户拍板过的数字，
        所以默认会真的下场买；不想让它自动建仓就把
        ``NAJA_T_ROTATION_ESTABLISH`` 置为 0。
        """
        # 先折算/锁定目标份额：计划都没有的话，下面算不出"缺多少"
        target = self._ensure_plan(spec, float(quote.current), date)
        if target <= 0:
            return

        # ⚠️ 缺口必须按**份额守恒口径**算，不能用 carried_in_shares。
        #
        # carried_in_shares 是 T+1 口径，**刻意排除当日新建的仓位**
        # （当日买入不可卖）。用它当"已持有多少"，当天刚买的第一笔
        # 就凭空消失，下一轮再算还是缺这么多 → 反复补 Buy，
        # 实测能把 40 万份的目标买到 76 万份，一路买到资金耗尽。
        #
        # effective_shares = 真实 OPEN 持仓 + 未履行回购义务，
        # 与 _verify_conservation 用的是同一把尺子。
        carried = self._ledger.effective_shares(spec.code, self._pf(spec.market))
        missing = target - carried
        if missing <= spec.round_lot:
            # 底仓到位 —— 顺手销掉分批账，下次再出现缺口时重新计数
            self._reset_fill_tracking(spec)
            return

        if not self._establish:
            log.warning(
                f"[TRotationRunner] ⚠️ {spec.name}({spec.code}) 底仓未到位："
                f"持有 {carried:.0f} / 目标 {target:.0f}，"
                f"缺 {missing:.0f} 份。NAJA_T_ROTATION_ESTABLISH=0，"
                f"只观察不建仓（倒 T 必须靠昨夜传承的底仓）"
            )
            return

        pf = self._pf(spec.market)

        # ❗在飞单闸门（2026-10-14 富途模拟仓首航实跑踩到的）
        #
        # 报单到成交之间有真实的时间差（实测 SH.588200 用了 4 秒），而下面
        # 三件事凑起来会咬人：
        #   · FutuSimPortfolio._reload 只等 0.8 秒就判定「持仓未出现」
        #   · 幂等槽位按**分钟**分槽（core_{日期}_{分钟}）
        #   · 这里每 30 秒轮询一次
        # 只要成交慢一点、跨过分钟边界，下一轮 carried 仍读到 0，
        # 于是拿着全额 missing 再报一单 —— **双倍仓位**。
        #
        # 所以判据不能是「等多久」或「记在内存里」（进程一重启就没了），
        # 而是问券商：**那张单还在不在飞**。这是唯一站得住的外生真相。
        inflight, blind_reason = self._probe_inflight(spec, pf)
        if inflight is None:
            # 查不到 ≠ 没有。看不清路面就别踩油门。
            self._note_inflight_blind(spec, blind_reason, date)
            return
        if inflight:
            self._note_inflight_wait(spec, inflight, carried, target, date)
            return

        # ❗守望层：这一步值不值得去问。
        #
        # 顺序刻意放在在飞单闸门之后 —— 有单在飞时连问都不必问。
        # 守望不改变「谁有权放行」，只是把「每 30 秒必问一次」变成
        # 「有事才问」，同时把「我在等什么」落成可观测的状态。
        # 三个判据见 core_establish_watch 模块文档，其中 liveness 那条
        # 是防死锁的：环境判据依赖 action_type，而 action_type 得问过才有。
        mtc = minutes_to_close(spec.market, datetime.fromtimestamp(now))
        self._establish_watch.ensure(spec, now=now)
        watch_ctx = self._establish_watch.context_for(
            spec,
            now=now,
            price=float(quote.current),
            anchor=float(getattr(quote, "prev_close", 0.0) or 0.0) or None,
            minutes_to_close=mtc,
        )
        ask, wscan = self._establish_watch.peek(spec, watch_ctx, now=now)
        if not ask:
            self._note_watch_wait(spec, wscan, carried, target, date)
            return

        # ❗大环境闸门（2026-10-14）：补仓必须先过决策中心。
        #
        # 在飞单闸门守的是「别重复报单」，这里守的是「别在逆风里加码」。
        # 两件事不一样，两个闸门都要有 —— 只有前者的话，标的越跌就买得越多
        #（target = 总资产 × 40% ÷ 现价，分母变小所以份额变大）。
        verdict = self._gate.evaluate(spec, float(quote.current), mtc)
        self._establish_watch.mark_asked(
            spec, bool(verdict.allowed), verdict.reason, now=now
        )
        if not verdict.allowed:
            self._note_gate_block(spec, verdict, date)
            return

        summary = pf.get_summary() or {}
        available = float(summary.get("available_capital", 0.0) or 0.0)
        used = float(summary.get("used_capital", 0.0) or 0.0)
        price = float(quote.current)
        lot = spec.round_lot
        affordable = available * 0.8 / price if price > 0 else 0.0

        # 分批：单笔金额上限是虚拟仓的风控参数（默认 20% 总资金）。
        # 40% 的底仓必然超过它，一次性下单会被拒。
        # 这里**分批**凑齐，而不是用 bypass_limits 绕过风控。
        #
        # 双上限都要看（实测踩到过）：
        #   单笔上限 max_position_pct —— 一次买太多会被拒
        #   总额度上限 max_total_pct  —— 其它策略已占用的部分要从这份额度里扣。
        #      真实账户上就撞了：已有持仓占 41 万，总上限 80 万，
        #      留给 40 万底仓只剩 39 万 —— 只看单笔的话，最后一笔会被拒，
        #      表现为「建仓失败」的 error 每 30 秒刷一条。
        single_budget = float(
            getattr(pf, "single_position_budget", 0.0) or 0.0
        )
        cap_by_single = (single_budget * 0.95 / price) if single_budget > 0 else missing

        total_budget = float(
            getattr(pf, "category_position_budget", 0.0) or 0.0
        )
        if total_budget > 0:
            headroom = max(0.0, total_budget - used)
            cap_by_total = headroom / price if price > 0 else 0.0
        else:
            # ❗富途模拟仓**没有**虚拟盘的额度属性（total_budget=0）。
            # 不能沿用上面的 else 分支（那里把"份额"当"金额"再除一次价格，
            # 量纲错得离谱 → qty 趋近 0 → 永远建不出底仓）。
            # 模拟仓的额度就是账户里的钱。
            headroom = available
            cap_by_total = affordable

        qty = min(missing, affordable, cap_by_single, cap_by_total)
        qty = (int(qty / lot)) * lot

        # 定量折算：决策中心给的是 0~1 的仓位乘子（decision.sizing 单一口径）。
        # 逆风少买而不是不打折扣地全买 —— 「等待时机」落在数量上，
        # 而不是归零（乘子算出来 0 就永远不建仓，等于换个姿势死锁）。
        # ❗地板是 1 手：乘子再小也要有进展，否则闸门放行了却什么都不做。
        hint = float(getattr(verdict, "size_hint", 0.0) or 0.0)
        if 0.0 < hint < 1.0:
            wanted = (int(missing * hint / lot)) * lot
            qty = min(qty, max(lot, wanted))

        # 本轮买不满目标 → 分批。这一步**不是故障**，而是设计意图。
        #
        # ❗历史教训（2026-10-14）：这里原本只要 "本轮买不满" 就发 ERROR
        # 并写「需要人工介入」—— 结果首批就说"缺 21 万份"，60 秒后系统
        # 自己分三批补满了。中间态被当成终态报，会把能自愈的分批伪装成
        # 必须处理的故障，还因为它按天去重，看上去像是一直没解决。
        #
        # 判据改成「有没有进展」：份额在涨 = 分批正常，静默；
        # 连续多轮份额一动不动 = 真的卡住（资金耗尽/额度见顶/下单被拒），
        # 这时才升 ERROR 并按天去重。
        if qty + lot <= missing:
            self._note_fill_round(
                spec, target=target, carried=carried, missing=missing, qty=qty,
                price=price, date=date, headroom=headroom,
                total_budget=total_budget, used=used, available=available,
                affordable=affordable,
            )
        else:
            # 本轮就能补满 —— 把分批账销掉，别把旧计数带进下一次缺口
            self._reset_fill_tracking(spec)

        if qty < lot:
            log.warning(
                f"[TRotationRunner] 资金/限额不足以补足 {spec.name} 底仓"
                f"（可用 {available:.0f}，单笔上限 {single_budget:.0f}，"
                f"需买 {missing:.0f} 份）"
            )
            return

        # 分批建仓也要各占各的槽位（按分钟分槽）：默认槽位是
        # 「日期+市场+标的+方向」，一天只能买一次 —— 底仓要分好几批才凑得齐
        # 40%，第二批起会被静默挡掉。虚拟盘没有 set_slot_tag，探测后跳过。
        setter = getattr(pf, "set_slot_tag", None)
        if callable(setter):
            setter(f"core_{date}_{int(now // 60)}")

        pos = pf.open_position(
            strategy_id="core_position",
            strategy_name="长期底仓",
            stock_code=spec.code,
            stock_name=spec.name,
            price=price,
            quantity=qty,
            stop_loss_pct=-95.0,
            take_profit_pct=995.0,
        )
        if pos is None:
            # ❗这里**不能**再说「建仓失败 / 可能撞仓位限额」。
            #
            # 下单前刚确认过没有在飞单，且 open_position 里 ok=False 会提前
            # return —— 走到这里说明**单已经报出去了**，只是 _reload 的等待
            # 窗口（0.8s）比真实撮合（实测 4s）短，还没看到持仓而已。
            #
            # 把它记成 ERROR 还顺手猜一个错的病因，是典型的假警报：
            # 真出额度问题时，日志里混着这类"没事却喊疼"的记录，真信号会被
            # 稀释；而看到它的人先去查仓位限额，查的方向就是错的。
            # （同一类病：见上面「本轮买不满就报 ERROR」那段批注。）
            log.info(
                f"[TRotationRunner] 🕐 {spec.name}({spec.code}) 已报单 "
                f"{qty:.0f} 份 @{price:.3f}，等待成交确认"
                f"（下一轮核对 —— 有单在飞时不会重复建仓）"
            )
            return

        batch_note = ""
        if qty < missing:
            batch_no = self._bump_fill_batch(spec, date)
            total_batches = self._expected_batches(missing, qty, lot)
            batch_note = (
                f"（分批 {batch_no}/{total_batches}：受单笔限额 "
                f"{single_budget:,.0f} / 可用额度 {headroom:,.0f} 限制，"
                f"下一轮继续补）"
            )
        log.info(
            f"[TRotationRunner] 🏦 补足底仓 {spec.name}({spec.code}) "
            f"{qty:.0f} 份 @{price:.3f}，"
            f"累计 {carried + qty:.0f}/{target:.0f}（T+1，今日不可卖）{batch_note}"
        )

    # ------------------------------------------------------------------
    # 在飞单闸门（建仓幂等的判据）
    # ------------------------------------------------------------------
    def _probe_inflight(
        self, spec: CoreHoldingSpec, pf: Any,
    ) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """问组合："这个标的现在有没有还没了结的买单？"

        返回 ``(orders, blind_reason)``：

        * ``([], "")``      —— 确认没有 → 放行
        * ``([...], "")``   —— 确认在飞 → 跳过，等它落地
        * ``(None, "...")`` —— **查不到**（接口失败 / 账户解析不出来）。
          调用方必须当成"我不知道"，**绝不**能当成"没有" ——
          把 None 当 [] 用，等于宣称"接口失联 = 可以放心下单"。

        虚拟盘没有 :meth:`in_flight_buy_orders`（下单即成交，不存在中间态），
        探测不到就走 ``([], "")`` 放行 —— 这是 duck-type 的**刻意兼容**，
        不是降级，虚拟盘的行为与本次改动前完全一致。
        """
        probe = getattr(pf, "in_flight_buy_orders", None)
        if not callable(probe):
            return [], ""
        try:
            orders = probe(spec.code)
        except Exception as e:
            # 适配器自己没兜住的异常，在这里同样不能当成"没有在飞单"
            return None, f"查询异常: {e}"
        if orders is None:
            reason = str(getattr(pf, "last_error", "") or "").strip()
            return None, reason or "接口未返回结果"
        return list(orders), ""

    def _note_inflight_wait(
        self, spec: CoreHoldingSpec, orders: List[Dict[str, Any]],
        carried: float, target: float, date: str,
    ) -> None:
        """有单在飞。这不是故障，按天去重地提示一次就够。"""
        if self._inflight_noted.get(spec.code) == f"{date}|wait":
            return
        self._inflight_noted[spec.code] = f"{date}|wait"
        first = orders[0] if orders else {}
        log.info(
            f"[TRotationRunner] ⏳ {spec.name}({spec.code}) 有 "
            f"{len(orders)} 笔买单在飞（首笔单号 {first.get('order_id')}，"
            f"状态 {first.get('order_status')}）持有 {carried:.0f} / "
            f"目标 {target:.0f} —— 等它落地再决定补不补"
        )

    def _note_inflight_blind(
        self, spec: CoreHoldingSpec, reason: str, date: str,
    ) -> None:
        """查不到订单状态。看不清路面不能当路面是空的。"""
        if self._inflight_noted.get(spec.code) == f"{date}|blind":
            return
        self._inflight_noted[spec.code] = f"{date}|blind"
        log.warning(
            f"[TRotationRunner] ⚠️ {spec.name}({spec.code}) 查不到在飞订单"
            f"（{reason}）—— **查不到不等于没有**，本轮不建仓以免重复报单"
        )

    def _note_watch_wait(
        self,
        spec: CoreHoldingSpec,
        wscan: Any,
        carried: float,
        target: float,
        date: str,
    ) -> None:
        """守望认为「还不值得去问」。

        ❗这是**策略在等待**，不是故障，所以用 INFO 并按天去重 ——
        但守望在它自己的心跳里仍会周期性自报，防止「在跑但没机会」与
        「线程已死」混淆。
        """
        self._stats["watch_waiting"] += 1
        reason = str(getattr(wscan, "why", lambda: "")() or "（无判据）")
        unknown = bool(getattr(wscan, "unknown", False))
        # unknown 时不参与去重：判据看不清这件事必须每轮可见
        if unknown:
            log.info(
                f"[TRotationRunner] 🌫️ {spec.name}({spec.code}) 判据看不清，"
                f"本轮不问 —— {reason}"
            )
            return
        key = f"{date}|waiting"
        if self._gate_noted.get(f"watch:{spec.code}") == key:
            return
        self._gate_noted[f"watch:{spec.code}"] = key
        log.info(
            f"[TRotationRunner] 🕰️ {spec.name}({spec.code}) 等待机会，本轮不问 —— "
            f"持有 {carried:.0f} / 目标 {target:.0f}；{reason}"
        )

    def _note_gate_block(
        self, spec: CoreHoldingSpec, verdict: Any, date: str,
    ) -> None:
        """补仓被决策中心拦下。

        ❗两种"不许买"必须分开喊：

        * ``source="decision_center"`` = Manas 没放行，**符合预期**，INFO + 按天去重；
        * ``source="unavailable"`` = 决策中心取不到结论，这是**链路故障**，
          必须 WARNING 且每轮都喊 —— 否则它会伪装成"行情不好所以没买"，
          闸门故障与策略观望长得一模一样，正是本仓库头号病理。
        """
        src = str(getattr(verdict, "source", "") or "")
        reason = str(getattr(verdict, "reason", "") or "（无理由）")
        if src == "unavailable":
            self._stats["gate_unavailable"] += 1
            log.warning(
                f"[TRotationRunner] 🚧 {spec.name}({spec.code}) {reason} —— "
                f"看不到大环境判断时不冒险下单"
            )
            return

        self._stats["gate_blocked"] += 1
        key = f"{date}|{src}"
        if self._gate_noted.get(spec.code) == key:
            return
        self._gate_noted[spec.code] = key
        log.info(
            f"[TRotationRunner] 🌤️ {spec.name}({spec.code}) 等待时机，本轮不补仓 —— "
            f"{reason}"
        )

    # ------------------------------------------------------------------
    # 分批补底仓的进度记账
    # ------------------------------------------------------------------
    def _reset_fill_tracking(self, spec: CoreHoldingSpec) -> None:
        """底仓到位（或本轮即可到位）→ 销掉分批账。"""
        self._fill_progress.pop(spec.code, None)
        self._fill_batches.pop(spec.code, None)
        self._budget_warned.pop(spec.code, None)

    def _bump_fill_batch(self, spec: CoreHoldingSpec, date: str) -> int:
        """记一笔成功的分批，返回它是今天的第几批。"""
        last_date, n = self._fill_batches.get(spec.code, (None, 0))
        if last_date != date:
            n = 0
        n += 1
        self._fill_batches[spec.code] = (date, n)
        return n

    @staticmethod
    def _expected_batches(missing: float, qty: float, lot: float) -> int:
        """按本轮的规模粗估总共要分几批（只用于日志，不参与决策）。"""
        if qty <= 0:
            return 1
        return max(1, int(missing / max(qty, lot) + 0.999))

    def _note_fill_round(
        self, spec: CoreHoldingSpec, *, target: float, carried: float,
        missing: float, qty: float, price: float, date: str, headroom: float,
        total_budget: float, used: float, available: float, affordable: float,
    ) -> None:
        """本轮补不满时的记账：有进展就沉默，连续原地踏步才升级成 ERROR。

        分批是设计意图（40% 底仓必然超过 20% 单笔上限），所以**默认不说**；
        只有「名额是该给它的，但连续 N 轮一分也买不进去」才值得占 ERROR
        通道。判据是份额有没有涨，而不是本轮有没有买满。
        """
        prev_date, prev_shares, prev_rounds = self._fill_progress.get(
            spec.code, (None, None, 0)
        )
        if prev_date != date or prev_shares is None:
            # 当天第一轮：还没得比，先立个基准，不急着喊
            self._fill_progress[spec.code] = (date, carried, 0)
            return

        progressed = carried > prev_shares + spec.round_lot / 2
        rounds = 0 if progressed else prev_rounds + 1
        self._fill_progress[spec.code] = (date, carried, rounds)

        if rounds < self._stall_limit:
            return

        # 真的卡住了 —— 每天只说一次，否则 30 秒一条会把真故障淹掉
        if self._budget_warned.get(spec.code) == date:
            return
        self._budget_warned[spec.code] = date

        if headroom < missing * price * 0.999:
            why = (
                f"总持仓额度只剩 {headroom:,.0f} 元"
                f"（上限 {total_budget:,.0f}，其它策略已占用 {used:,.0f}）"
            )
        elif affordable < missing:
            why = f"可用资金不足：{available:,.0f} 元"
        else:
            why = "单笔/总额度限制"
        log.error(
            f"[TRotationRunner] 🚨 {spec.name}({spec.code}) 底仓卡住："
            f"连续 {rounds} 轮份额零增长（持有 {carried:.0f}/目标 {target:.0f}，"
            f"仍缺 {missing:.0f} 份，本轮只买得起 {qty:.0f} 份）—— {why}。"
            f"需要人工介入：清理无用持仓，或调整虚拟仓的总持仓上限。"
        )

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        now = self._clock()
        dt = datetime.fromtimestamp(now)
        symbols = []
        for spec in self._specs:
            diag = self._last_diag.get(spec.code, {})
            ledger_view = {}
            if self._ledger is not None:
                try:
                    ledger_view = self._ledger.get_summary(
                        spec.code, self._pf(spec.market),
                        now=now, session_open_ts=session_open_ts(spec.market, dt),
                    )
                except Exception as e:  # pragma: no cover
                    ledger_view = {"error": str(e)}
            symbols.append({
                "code": spec.code,
                "bus_code": spec.bus_code,
                "name": spec.name,
                "market": spec.market,
                "currency": spec.currency,
                # 折算后的才是真实目标；spec.target_shares 为 0 仅表示"按比例折算"。
                # 尚未折算过（还没见到行情）就如实给 0，并给出 budget 让人能核对。
                "target_shares": self._plan_targets.get(spec.code, 0.0),
                "explicit_shares": spec.target_shares,
                "alloc_pct": spec.alloc_pct,
                "target_budget": spec.target_budget(self.total_assets(spec.market)),
                "target_resolved_date": self._plan_date.get(spec.code),
                # 「真的卡住了」才会打上日期（分批进行中是不打的）
                "budget_warned": self._budget_warned.get(spec.code),
                # 分批进行到第几没有进展了 —— 0 表示上一轮有进展
                "fill_stalled_rounds": self._fill_progress.get(
                    spec.code, (None, None, 0)
                )[2],
                "fill_batches": self._fill_batches.get(spec.code, (None, 0))[1],
                "held_shares": (
                    None if self._ledger is None else
                    self._ledger.effective_shares(spec.code, self._pf(spec.market))
                ),
                "session_date": self._session_date.get(spec.code),
                "settled_today": (
                    spec.code, session_date(spec.market, dt)
                ) in self._settled,
                "last_price": self._last_price.get(spec.code, 0.0),
                "suspended": self._suspended.get(spec.code, ""),
                "last_diag": diag,
                "engine": ledger_view,
            })
        return {
            "enabled": self.enabled,
            "running": self.running,
            "establish_enabled": self._establish,
            "total_assets": self.total_assets(),
            "alloc_pct": self._specs[0].alloc_pct if self._specs else 0.0,
            "poll_seconds": self._poll_seconds,
            # ❗是否真的在往富途模拟仓下单 —— 这个开关必须一眼可见。
            # 「UI 显示在做 T 但实际全在虚拟盘」是静默失效里最伤的一种。
            "on_sim": self._on_sim,
            "sim_markets": sorted(self._portfolios),
            # 三个市场时段不同，这里**逐市场**给出，不再只有一个 A 股 phase
            "phases": {
                spec.code: {
                    "market": spec.market,
                    "phase": market_phase(spec.market, dt),
                    "minutes_to_close": minutes_to_close(spec.market, dt),
                    "session_date": session_date(spec.market, dt),
                }
                for spec in self._specs
            },
            "now": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
            "errors": dict(self._errors),
            "stats": dict(self._stats),
            "symbols": symbols,
        }


_runner: Optional[TRotationRunner] = None
_runner_lock = threading.Lock()


def get_t_rotation_runner() -> TRotationRunner:
    """获取全局做 T 运行器（进程内单例）。"""
    global _runner
    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = TRotationRunner()
    return _runner


__all__ = [
    "TRotationRunner",
    "get_t_rotation_runner",
]
