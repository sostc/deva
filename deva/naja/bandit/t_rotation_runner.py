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
from typing import Any, Callable, Dict, List, Optional

from .core_holdings import (
    CoreHoldingSpec,
    env_flag,
    env_float,
    load_core_holdings,
)
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

        self._clock = clock or time.time
        self._portfolio = portfolio
        self._quotes = quotes
        self._engine = engine
        self._ledger = ledger

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
        # 额度不足属于配置冲突，按天去重告警，别把日志刷满
        self._budget_warned: Dict[str, str] = {}
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

        for spec in self._specs:
            # ❗每个标的挂上**它自己市场**的参数档：判据按波动尺度标定，
            # 拿 A 股那套去套 QQQ 会永不触发（实测 QQQ 振幅 0.72% < 闸门 1.0%）。
            prof = spec.profile
            self._engine.set_symbol_profile(
                spec.code,
                thresholds=prof.thresholds,
                config=replace(
                    TRotationConfig(),
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
                self._engine.register_target(
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
        return results

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
        force_min = self._engine.config_for(code).force_close_minutes
        if mtc is not None and mtc <= force_min:
            if (code, date) in self._settled:
                return {"code": code, "action": "NONE", "reason": "当日已结算"}
            report = self._engine.settle_before_close(
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

        diag = self._engine.on_tick(
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
    def total_assets(self) -> float:
        """折算底仓用的分母 = 组合总资金（不是可用资金）。

        刻意不用 available：那玩意会被其它策略的临时持仓挤来挤去，
        底仓规模不该跟着别人的仓位抖。
        """
        try:
            summary = self._portfolio.get_summary() or {}
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

        target = spec.resolve_target_shares(self.total_assets(), price)
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

        self._engine.register_target(
            spec.code, target, name=spec.name,
            note=f"{spec.note}｜目标约占总资产 {spec.alloc_pct:g}%",
        )
        self._plan_targets[spec.code] = target
        self._plan_date[spec.code] = date
        log.info(
            f"[TRotationRunner] 📐 {spec.name}({spec.code}) 今日目标 {target:.0f} 份"
            f"（总资产 {self.total_assets():.0f} × {spec.alloc_pct:g}% ÷ {price:.3f}）"
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
            report = self._engine.settle_before_close(
                code, float(quote.current), now=now, session_open_ts=open_ts
            )
            self._stats["cross_session_buyback"] += 1
            log.warning(
                f"[TRotationRunner] 🚨 跨会话回购 {spec.name}({code}): "
                f"待补 {qty:.0f} 份 → {report.get('forced_buyback', 0):.0f} 份已买回"
            )

        # ② 开新会话（重置日内序列 + 设定昨收基准）
        self._engine.start_session(
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
        carried = self._ledger.effective_shares(spec.code, self._portfolio)
        missing = target - carried
        if missing <= spec.round_lot:
            return

        if not self._establish:
            log.warning(
                f"[TRotationRunner] ⚠️ {spec.name}({spec.code}) 底仓未到位："
                f"持有 {carried:.0f} / 目标 {target:.0f}，"
                f"缺 {missing:.0f} 份。NAJA_T_ROTATION_ESTABLISH=0，"
                f"只观察不建仓（倒 T 必须靠昨夜传承的底仓）"
            )
            return

        summary = self._portfolio.get_summary() or {}
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
            getattr(self._portfolio, "single_position_budget", 0.0) or 0.0
        )
        cap_by_single = (single_budget * 0.95 / price) if single_budget > 0 else missing

        total_budget = float(
            getattr(self._portfolio, "category_position_budget", 0.0) or 0.0
        )
        headroom = max(0.0, total_budget - used) if total_budget > 0 else missing
        cap_by_total = headroom / price if price > 0 else 0.0

        qty = min(missing, affordable, cap_by_single, cap_by_total)
        qty = (int(qty / lot)) * lot

        # 额度不够把目标买满，是**配置冲突**，不是行情问题 ——
        # 每天只在首次识别时说一次，否则每 30 秒一条 error 会把真故障淹掉。
        if qty + lot <= missing and self._budget_warned.get(spec.code) != date:
            self._budget_warned[spec.code] = date
            if headroom < (missing - carried * 0) * price * 0.999 and headroom <= missing * price:
                why = (
                    f"总持仓额度只剩 {headroom:,.0f} 元"
                    f"（上限 {total_budget:,.0f}，其它策略已占用 {used:,.0f}）"
                )
            else:
                why = (
                    f"可用资金不足：{available:,.0f} 元"
                    if affordable < missing else "单笔/总额度限制"
                )
            log.error(
                f"[TRotationRunner] 🚨 {spec.name}({spec.code}) 底仓受额度限制，"
                f"本轮只能补 {qty:.0f} 份、仍缺 {missing - qty:.0f} 份 —— {why}。"
                f"需要人工介入：清理无用持仓，或调整虚拟仓的总持仓上限。"
            )

        if qty < lot:
            log.warning(
                f"[TRotationRunner] 资金/限额不足以补足 {spec.name} 底仓"
                f"（可用 {available:.0f}，单笔上限 {single_budget:.0f}，"
                f"需买 {missing:.0f} 份）"
            )
            return

        pos = self._portfolio.open_position(
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
            log.error(
                f"[TRotationRunner] 底仓建仓失败 {spec.name}({spec.code}) "
                f"{qty:.0f} 份（可能撞仓位限额）"
            )
            return

        batch_note = (
            f"（分批：受单笔限额 {single_budget:,.0f} / 可用额度 {headroom:,.0f} 限制，"
            f"下一轮继续补）"
            if qty < missing else ""
        )
        log.info(
            f"[TRotationRunner] 🏦 补足底仓 {spec.name}({spec.code}) "
            f"{qty:.0f} 份 @{price:.3f}，"
            f"累计 {carried + qty:.0f}/{target:.0f}（T+1，今日不可卖）{batch_note}"
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
                        spec.code, self._portfolio,
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
                "target_budget": spec.target_budget(self.total_assets()),
                "target_resolved_date": self._plan_date.get(spec.code),
                # 额度不够买满目标时，这里要能回答「为什么差这么多」
                "budget_warned": self._budget_warned.get(spec.code),
                "held_shares": (
                    None if self._ledger is None else
                    self._ledger.effective_shares(spec.code, self._portfolio)
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
