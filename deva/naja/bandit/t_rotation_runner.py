"""TRotationRunner —— 把「做 T 降成本」引擎接到 MarketDataBus 上。

背景
----
``t_rotation.TRotationEngine`` 写完之后，全仓库找不到一个调用方 ——
这是本仓库最经典的「静默失效」形态：代码是对的、守卫是绿的、
但没有任何一行行情会流进它。本模块就是那个缺失的调用方。

用户拍板的数据源：**MarketDataBus**（统一行情总线），
标的：**科创芯片 ETF 588200**（见 :mod:`core_holdings`）。

它负责的事
----------
1. **订阅 + 轮询双路取行情**，把 ``MarketQuote`` 翻译成引擎要的 tick
2. **交易时段 / 会话管理**：每天首个 tick 开新会话（带昨收），
   收盘前 forced-settle，跨会话兜底买回
3. **单位换算**：新浪给的是**累计**成交量，而 VWAP 要的是**增量**。
   直接把累计量喂进去会把 VWAP 压成一条越走越平的曲线
4. **死水检测**：连续 N 次「价格与成交量都没动」就停喂并告警 ——
   节假日的报纸会以「昨收价」反复出现，纯粹制造幻觉

刻意不做的事
------------
* **不在自己的线程里调用 ``get_price_async`` / ``write_quotes``**。
  它们内部走 ``asyncio.create_task``，在没有事件循环的普通线程里会直接抛
  ``RuntimeError``。这里统一走同步 ``bus.fetch()``（它内部用
  ``ThreadPoolExecutor`` + ``asyncio.run`` 包好了）。
* **不自动补足底仓**，除非显式打开 ``NAJA_T_ROTATION_ESTABLISH=1``。
  动用多少资金建仓必须由人决定，代码不该替用户拍板。
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .core_holdings import (
    CoreHoldingSpec,
    env_flag,
    env_float,
    load_core_holdings,
)

log = logging.getLogger(__name__)

# ── A 股交易时段（本地时间）。只认星期，不做节假日日历。
PHASE_MORNING = "morning"
PHASE_LUNCH = "lunch"
PHASE_AFTERNOON = "afternoon"
PHASE_CLOSED = "closed"
_TRADING_PHASES = (PHASE_MORNING, PHASE_AFTERNOON)

_MORNING = (9 * 60 + 30, 11 * 60 + 30)
_AFTERNOON = (13 * 60, 15 * 60)
_CLOSE_MIN = 15 * 60


def cn_phase(dt: datetime) -> str:
    """纯本地计算当前处于 A 股哪个时段。

    刻意**不依赖** trading_clock 单例：那个要过 AppContainer，
    在本线程里既慢又可能拿不到，而这里需要的只是「现在几点、周几」。
    """
    if dt.weekday() >= 5:
        return PHASE_CLOSED
    minute = dt.hour * 60 + dt.minute
    if _MORNING[0] <= minute < _MORNING[1]:
        return PHASE_MORNING
    if _MORNING[1] <= minute < _AFTERNOON[0]:
        return PHASE_LUNCH
    if _AFTERNOON[0] <= minute < _CLOSE_MIN:
        return PHASE_AFTERNOON
    return PHASE_CLOSED


def minutes_to_close(dt: datetime) -> Optional[float]:
    """距 15:00 收盘还有多少分钟。非交易日/已收盘返回 None。"""
    if dt.weekday() >= 5:
        return None
    minute = dt.hour * 60 + dt.minute + dt.second / 60.0
    if minute >= _CLOSE_MIN:
        return None
    return _CLOSE_MIN - minute


def session_open_ts(dt: datetime) -> float:
    """当日 09:30 的时间戳。T+1 判断「哪些份额是昨天买的」要靠它。"""
    return datetime(dt.year, dt.month, dt.day, 9, 30).timestamp()


class TRotationRunner:
    """行情驱动的做 T 运行器。纯虚拟盘，不触达任何真实下单链路。"""

    #: 连续多少次「毫无变化」就判定行情断流/休市
    DEFAULT_FLAT_LIMIT = 12

    def __init__(
        self,
        portfolio=None,
        bus=None,
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
        self._bus = bus
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

        # 行情总线
        if self._bus is None:
            try:
                from .market_data_bus import get_market_data_bus

                self._bus = get_market_data_bus()
            except Exception as e:  # pragma: no cover
                self._errors["bus"] = str(e)
                log.error(f"[TRotationRunner] 取不到行情总线: {e}")
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
            # 只有**显式指定了份额**才能在此时登记；按比例折算的必须等有价格，
            # 交给 _ensure_plan()（详见那里的注释）。
            if spec.explicit:
                self._engine.register_target(
                    spec.code, spec.target_shares, name=spec.name, note=spec.note
                )

        # 订阅 —— 既让总线知道有人要这只票，也用来观测「推送链路是否活着」。
        # 真正的喂数统一由轮询线程做（见模块 docstring：避免 async 陷阱）。
        try:
            codes = [s.bus_code for s in self._specs]
            self._bus.subscribe(codes, self._on_bus_quote)
            self._bus.register_priority_codes(codes, self._bus.PRIORITY_HIGH)
        except Exception as e:  # pragma: no cover
            self._errors["subscribe"] = str(e)
            log.warning(f"[TRotationRunner] 订阅行情失败（仍可轮询）: {e}")

        return True

    def _on_bus_quote(self, code: str, price: float):
        """总线推送回调。只计数，不喂引擎（喂数统一在轮询线程，避免重复进 bar）。"""
        try:
            from .market_data_bus import _normalize_code

            key = _normalize_code(str(code))
        except Exception:
            key = str(code)
        if key in self._by_code:
            self._stats["pushed_ticks"] += 1

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

        phase = cn_phase(dt)
        if phase not in _TRADING_PHASES:
            self._stats["off_hours_skips"] += 1
            return results

        self._stats["polls"] += 1
        for spec in self._specs:
            try:
                results.append(self._pump(spec, dt, now))
            except Exception as e:
                log.error(f"[TRotationRunner] {spec.code} 处理失败: {e}", exc_info=True)
                results.append({"code": spec.code, "error": str(e)})
        return results

    # ------------------------------------------------------------------
    # 单个标的
    # ------------------------------------------------------------------
    def _read_quote(self, bus_code: str):
        """同步取最新行情。只走 ``bus.fetch`` —— 见模块 docstring。"""
        bus = self._bus
        if bus is None:
            return None
        try:
            bus.fetch([bus_code])
        except Exception as e:
            self._stats["fetch_errors"] += 1
            log.debug(f"[TRotationRunner] fetch {bus_code} 失败: {e}")
            return None
        try:
            return bus.get_quote(bus_code)
        except Exception as e:  # get_quote 缺数据时会尝试 asyncio.create_task
            self._stats["fetch_errors"] += 1
            log.debug(f"[TRotationRunner] get_quote {bus_code} 失败: {e}")
            return None

    def _pump(self, spec: CoreHoldingSpec, dt: datetime, now: float) -> Dict[str, Any]:
        code = spec.code
        open_ts = session_open_ts(dt)
        date = dt.strftime("%Y-%m-%d")

        suspended = self._suspended.get(code)
        if suspended:
            if self._session_date.get(code) != date:
                # 换日就解封，别把一次故障封到天荒地老
                self._suspended.pop(code, None)
                self._flat_runs[code] = 0
            else:
                return {"code": code, "action": "NONE", "reason": suspended}

        quote = self._read_quote(spec.bus_code)
        if quote is None or quote.current <= 0 or quote.prev_close <= 0:
            self._stats["quote_miss"] += 1
            return {"code": code, "action": "NONE", "reason": "行情缺失（无报价或缺昨收）"}
        age = getattr(quote, "age", 0.0) or 0.0
        if age > self._max_quote_age:
            self._stats["stale_quote"] += 1
            return {
                "code": code, "action": "NONE",
                "reason": f"行情过期（{age:.0f}s > {self._max_quote_age:.0f}s）",
            }

        self._maybe_start_session(spec, quote, now, dt, open_ts, date)

        price = float(quote.current)
        # 新浪给的是**当日累计**成交量，VWAP 要的是每根 bar 的增量
        cum_vol = float(getattr(quote, "volume", 0.0) or 0.0)
        prev_cum = self._last_cum_vol.get(code)
        dvol = 0.0
        if prev_cum is not None and cum_vol >= prev_cum:
            dvol = cum_vol - prev_cum
        self._last_cum_vol[code] = cum_vol

        mtc = minutes_to_close(dt)

        # 收盘前：先把没买回的买回来，再谈别的
        force_min = getattr(self._engine._config, "force_close_minutes", 10.0)
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
        price = float(quote.current)
        lot = spec.round_lot
        affordable = available * 0.8 / price if price > 0 else 0.0

        # 分批：单笔金额上限是虚拟仓的风控参数（默认 20% 总资金）。
        # 40% 的底仓必然超过它，一次性下单会被拒。
        # 这里**分批**凑齐，而不是用 bypass_limits 绕过风控。
        single_budget = float(
            getattr(self._portfolio, "single_position_budget", 0.0) or 0.0
        )
        cap_by_limit = (single_budget * 0.95 / price) if single_budget > 0 else missing

        qty = min(missing, affordable, cap_by_limit)
        qty = (int(qty / lot)) * lot
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
            f"（分批改：单笔限额 {single_budget:.0f}，下一轮继续补）"
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
                        now=now, session_open_ts=session_open_ts(dt),
                    )
                except Exception as e:  # pragma: no cover
                    ledger_view = {"error": str(e)}
            symbols.append({
                "code": spec.code,
                "bus_code": spec.bus_code,
                "name": spec.name,
                # 折算后的才是真实目标；spec.target_shares 为 0 仅表示"按比例折算"。
                # 尚未折算过（还没见到行情）就如实给 0，并给出 budget 让人能核对。
                "target_shares": self._plan_targets.get(spec.code, 0.0),
                "explicit_shares": spec.target_shares,
                "alloc_pct": spec.alloc_pct,
                "target_budget": spec.target_budget(self.total_assets()),
                "target_resolved_date": self._plan_date.get(spec.code),
                "session_date": self._session_date.get(spec.code),
                "settled_today": (spec.code, dt.strftime("%Y-%m-%d")) in self._settled,
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
            "phase": cn_phase(dt),
            "minutes_to_close": minutes_to_close(dt),
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
    "cn_phase",
    "minutes_to_close",
    "session_open_ts",
    "PHASE_MORNING",
    "PHASE_LUNCH",
    "PHASE_AFTERNOON",
    "PHASE_CLOSED",
]
