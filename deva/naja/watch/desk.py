"""守望台桌面（WatchDesk）—— 让守望真正被周期性问一次的那层。

内核与桌面的分工
================
``watch`` 内核（目标 / 守望 / 守望台）回答「值不值得问」，
本模块回答「谁来问、按什么节拍问、问完的结果去哪了」。少了这一层，
守望就是一堆漂亮的对象但没人驱动 —— 本仓库最常犯的毛病。

桌面只做三件事
==============
1. 造观测面：每个守望只看自己的那片世界（价格、锚、距收盘、Manas 读数）。
   观测面造不出来就传 ``None``，那会被记成 unknown，而不是「没机会」。
2. 驱动扫描：该不该问由 ``Watch.scan`` 判断，桌面不掺和。
3. 盯着消费：票开出来必须有人去问一次，没人接就喊。

与 :mod:`deva.naja.watch` 内核相同的三条纪律
============================================
* 桌面不下单：它只负责把票交出去，批不批在决策中心。
* 桌面不落盘：守望是运行期数据，重启后重新登记即可。
* 票没人消费必须喊：记 WARNING，而不是静默丢掉。

最后一条正是 2026-10-14 那次事故留下的教训 ——「UI 写好了、链路没接」。
一个一直在开票却从没有人领取的守望，和一条死掉的线程长得一模一样。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .allocation import Allocation, declare_allocation
from .intent import Intent, clamp_confidence, declare_intent
from .manas_lens import ManasLens, ManasReading
from .objective import Objective, WatchContext
from .registry import WatchRegistry
from .watch import Watch, WatchScan, WatchState, ask_verdict_text

log = logging.getLogger(__name__)

__all__ = ["DeskTicket", "WatchDesk", "TICKET_LOG_MAXLEN"]

#: 全局开票流水留多少条。这是「守望台到底在干什么」的唯一物证。
TICKET_LOG_MAXLEN = 200

#: 观测面工厂：``(守望, 本轮时刻) -> 观测面``。返回 None = 本轮没拿到观测。
Observer = Callable[[Watch, float], Optional[WatchContext]]

#: 决策执行器：``(目标, 观测面, 扫描结果) -> 放行与否 / 理由``。
Asker = Callable[[Objective, Optional[WatchContext], WatchScan], Any]


@dataclass(frozen=True)
class DeskTicket:
    """本次 poll 开出的一张票：「这个守望认为该去问一次了」。"""

    watch_id: str
    objective: Objective
    scan: WatchScan
    context: Optional[WatchContext]
    #: True = 决策中心放行；False = 被否或问询失败；None = **没人去问**
    granted: Optional[bool] = None
    reason: str = ""

    @property
    def unanswered(self) -> bool:
        """True = 这张票没人领。把「守望开了票但执行器没接」喊出来。"""
        return self.granted is None


def _normalize_verdict(res: Any) -> Tuple[bool, str]:
    """把执行器的返回值统一成 ``(放行与否, 理由)``。

    ❗认不出来的形态一律按**否决**处理并在理由里写明，
    绝不让一个奇怪的返回值被当成 True —— 那是另一种「静默放行」。
    """
    if res is None:
        return False, "决策执行器没有给出结论"
    if isinstance(res, bool):
        return res, ""
    if isinstance(res, Mapping):
        return bool(res.get("granted")), str(res.get("reason") or "")
    if isinstance(res, (tuple, list)) and len(res) >= 2:
        return bool(res[0]), str(res[1])
    if isinstance(res, (tuple, list)) and len(res) == 1:
        return bool(res[0]), ""
    return False, f"决策执行器返回了认不出的类型：{type(res).__name__}"


class WatchDesk:
    """守望的桌面。

    :param registry: 守望台；不传就自己造一个。
    :param lens: Manas 读数透镜；不传就自己造一个（走全局单例）。
    :param asker: 决策执行器。**不传 = 开票但没人消费**，桌面会为此告警。
    """

    #: 行情超过这么久就不能当成「现价」了；过期传 None（= unknown）。
    DEFAULT_QUOTE_MAX_AGE = 300.0
    #: 缓存缺失时同步补抓的冷却（秒）：既不让轮询线程每轮都去打网络，
    #: 也不会像总线的异步补抓那样在非 asyncio 线程里退化成没人 await 的协程。
    SYNC_FETCH_COOLDOWN = 60.0

    def __init__(
        self,
        registry: Optional[WatchRegistry] = None,
        lens: Optional[ManasLens] = None,
        *,
        quote_fn: Optional[Callable[[str], Any]] = None,
        minutes_to_close_fn: Optional[Callable[[str], Optional[float]]] = None,
        asker: Optional[Asker] = None,
        quote_max_age: Optional[float] = None,
        heartbeat_sec: Optional[float] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        #: ❗心跳间隔必须能一路传进 registry。上一版 IntentRunner 读到了
        #: ``NAJA_INTENT_HEARTBEAT_SEC`` 却没人用它 —— 配置项写了没人读，
        #: 跟「UI 写好了链路没接」是同一种静默失效。
        self.registry: WatchRegistry = registry or WatchRegistry(
            heartbeat_sec=heartbeat_sec
        )
        self.lens: Optional[ManasLens] = ManasLens() if lens is None else lens
        self._quote_fn = quote_fn
        self._mtc_fn = minutes_to_close_fn
        self._asker = asker
        self._quote_max_age = (
            self.DEFAULT_QUOTE_MAX_AGE if quote_max_age is None
            else float(quote_max_age)
        )
        self._clock: Callable[[], float] = clock or time.time

        self._observers: Dict[str, Observer] = {}
        for side in ("buy", "sell", "trim"):
            self._observers[f"{side}_intent"] = self._intent_context
        #: ★长期配置（循环守望）。观测面与意向类相同：行情 + 距收盘 + Manas 读数。
        #: ❗**必须显式登记**：少了这一行，长期配置会因为找不到观测面工厂
        #: 而每轮记成「本轮取不到观测」—— 不触发、不报错、日志里只留一行
        #: 警告，和「这个想法从来没挂上过」长得一模一样。
        self._observers["allocation"] = self._intent_context

        # -- 自证计数 ------------------------------------------------
        self.polls = 0
        self.unknown_scans = 0
        self.consumed = 0
        self.unanswered = 0
        #: 循环守望续期次数。长期持仓的「心跳」—— 一直不涨说明台面卡住了。
        self.renewals = 0
        self._warned_missing: set = set()
        self._warned_no_asker: set = set()
        self._last_sync_fetch: Dict[str, float] = {}
        #: 开票流水（全局，含已撤下的守望留下的痕迹）
        self._ticket_log: deque = deque(maxlen=TICKET_LOG_MAXLEN)

    # ----------------------------------------------------------------
    @property
    def asker(self) -> Optional[Asker]:
        return self._asker

    @asker.setter
    def asker(self, fn: Optional[Asker]) -> None:
        """后接执行器。❗接到之后要清掉「没人消费」的告警记录，
        否则先开出去的那些票会一直顶着旧警告。"""
        self._asker = fn
        self._warned_no_asker.clear()

    def register_observer(self, kind: str, fn: Observer) -> None:
        """给某一类目标挂观测面工厂。做 T 那类自带观测的目标从这里接入。"""
        if not callable(fn):
            raise TypeError(f"观测面工厂不是可调用对象：{fn!r}")
        self._observers[str(kind)] = fn

    def declare_intent(
        self,
        intent: Intent,
        *,
        now: Optional[float] = None,
        max_silence_seconds: Optional[float] = None,
    ) -> Watch:
        """把一个人工意向挂上守望台。"""
        return declare_intent(
            self.registry, intent, now=now,
            max_silence_seconds=max_silence_seconds,
        )

    def declare_allocation(
        self,
        alloc: Allocation,
        *,
        now: Optional[float] = None,
        max_silence_seconds: Optional[float] = None,
        bootstrap: bool = True,
    ) -> Watch:
        """把一份长期配置挂上台。**循环守望**：到期自动续下一期。

        ❗``bootstrap`` 默认开，与一次性意向不同：长期持仓的仓位可能早就够了，
        这时它永远不会触发机会判据 —— 没有 bootstrap 就等于从第一天起完全隐形。
        """
        return declare_allocation(
            self.registry, alloc, now=now,
            max_silence_seconds=max_silence_seconds,
            bootstrap=bootstrap,
        )

    def watches(self) -> Sequence[Watch]:
        return self.registry.watches()

    def settle(self, watch_id: str, outcome: str, reason: str = "") -> None:
        watch = self.registry.get(watch_id)
        if watch is None:
            log.warning("[WatchDesk] 结算目标 %s 不存在（没东西可结算）", watch_id)
            return
        watch.settle(outcome, reason)

    # ----------------------------------------------------------------
    def set_confidence(self, watch_id: str, value: Any) -> float:
        """改一个守望的意愿强度（UI「调力度」走这里）。

        ❗只能改强度，**封顶仍在** :func:`~.intent.clamp_confidence` 手里：
        人在 UI 上拖到 100 也拿不到 1.0 —— 「主动想买 ≠ 放行」这条纪律
        靠的就是这个上限，UI 不能成为绕过它的后门。

        :raises KeyError: 台上没有这个守望。认不出来就抛，不静默返回 0。
        """
        watch = self.registry.get(watch_id)
        if watch is None:
            raise KeyError(f"守望 {watch_id} 不在台上，改不了它的意愿强度")
        conf = clamp_confidence(value)
        params = watch.objective.params
        old = params.get("confidence")
        params["confidence"] = conf
        # 人手改过就必须标成 explicit：审计时「用户拖过」与「系统默认」要分得开
        params["confidence_explicit"] = True
        log.info(
            "[WatchDesk] %s 意愿强度 %.2f → %.2f（人工调整，封顶 %.2f）",
            watch_id,
            float(old) if isinstance(old, (int, float)) else 0.0,
            conf,
            float(clamp_confidence(9.9)),
        )
        return conf

    def ticket_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """最近若干条开票流水（新的在前）。"""
        rows = list(self._ticket_log)
        if limit and limit > 0:
            rows = rows[-int(limit):]
        return list(reversed(rows))

    # ----------------------------------------------------------------
    def poll(self, now: Optional[float] = None) -> List[DeskTicket]:
        """扫一轮，给到期的守望开票。"""
        t = float(now if now is not None else self._clock())
        tickets: List[DeskTicket] = []
        for watch in list(self.registry.watches()):
            if watch.state == WatchState.SETTLED:
                continue
            builder = self._observers.get(watch.objective.kind)
            if builder is None:
                self._note_missing_observer(watch)
                ctx = None
            else:
                try:
                    ctx = builder(watch, t)
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "[WatchDesk] 给 %s 造观测面失败: %s",
                        watch.watch_id, e, exc_info=True,
                    )
                    ctx = None
            scan = watch.scan(ctx, now=t)
            if scan.unknown:
                self.unknown_scans += 1
            if not scan.should_ask:
                continue
            tk = self._consume(watch, ctx, scan, t)
            self._log_ticket(tk, t)
            tickets.append(tk)
        self.polls += 1
        # 到期的守望这一轮就结算，不让它无声消失
        self.registry.due(t, settle=True)
        # ❗循环守望结算成 reviewed 之后**必须有人把它挂回下一期**。
        # 少了这一步，「长期持有」会在第一期结束时变成一具尸体 ——
        # 页面上显示「已结算」，跟「这个想法从没存在过」没有区别。
        # 这正是「配置写好了、链路没接」那一类静默失效的标准形态。
        summaries = self.registry.renew(t)
        for s in summaries:
            self.renewals += 1
            log.info(
                "[WatchDesk] 循环守望已续期 —— 第 %d 期：扫 %d 次 / 问过 %d 次"
                "（放行 %d · 未批准 %d · 没人问 %d）",
                s["cycle"], s["scans"], s["asked"],
                s["granted_count"], s["denied_count"], s["unanswered_count"],
            )
        return tickets

    def heartbeat(self, now: Optional[float] = None, *,
                  force: bool = False) -> Optional[str]:
        t = float(now if now is not None else self._clock())
        text = self.registry.heartbeat(t, force=force)
        if text is not None:
            lens = self.lens
            if lens is not None:
                tail = f" 读数 {lens.reads} 次 / 看不清 {lens.unknown_reads} 次"
                if lens.last_unknown_reason:
                    tail += f"（最近：{lens.last_unknown_reason}）"
                text += "\n   🔭 Manas 镜头：" + tail.strip()
            if self.unanswered:
                text += f"\n   ⚠️ {self.unanswered} 张票没人消费（没接执行器）"
        return text

    def snapshot(self, now: Optional[float] = None) -> Dict[str, Any]:
        t = float(now if now is not None else self._clock())
        out: Dict[str, Any] = self.registry.snapshot(t)
        out.update(
            {
                "polls": self.polls,
                "unknown_scans": self.unknown_scans,
                "consumed": self.consumed,
                "unanswered": self.unanswered,
                "asker_attached": self._asker is not None,
                "tickets_recent": self.ticket_log(20),
                "manas": (
                    {
                        "reads": self.lens.reads,
                        "unknown_reads": self.lens.unknown_reads,
                        "refreshes": self.lens.refreshes,
                        "fail_streak": self.lens.fail_streak,
                        "last_unknown_reason": self.lens.last_unknown_reason,
                    }
                    if self.lens is not None
                    else {}
                ),
            }
        )
        return out

    # ----------------------------------------------------------------
    def _consume(
        self, watch: Watch, ctx: Optional[WatchContext],
        scan: WatchScan, now: float,
    ) -> DeskTicket:
        """票有人领就去问，没人领就喊 —— 绝不静默丢掉。"""
        if self._asker is None:
            self.unanswered += 1
            reason = "没接决策执行器（asker），这张票没人消费"
            if watch.watch_id not in self._warned_no_asker:
                self._warned_no_asker.add(watch.watch_id)
                log.warning(
                    "[WatchDesk] %s 机会成立（%s）—— %s",
                    watch.watch_id, scan.why(), reason,
                )
            watch.record_ask(None, reason, now=now, fired_kinds=scan.fired_kinds)
            watch.acknowledge(False, reason, now=now)
            return DeskTicket(
                watch.watch_id, watch.objective, scan, ctx,
                granted=None, reason=reason,
            )

        try:
            res = self._asker(watch.objective, ctx, scan)
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[WatchDesk] %s 问决策中心时抛异常: %s",
                watch.watch_id, e, exc_info=True,
            )
            res = (False, f"问决策中心失败: {type(e).__name__}: {e}")

        granted, reason = _normalize_verdict(res)
        watch.record_ask(
            granted, reason, now=now, fired_kinds=scan.fired_kinds
        )
        watch.acknowledge(granted, reason, now=now)
        self.consumed += 1
        return DeskTicket(
            watch.watch_id, watch.objective, scan, ctx,
            granted=granted, reason=reason,
        )

    def _log_ticket(self, tk: DeskTicket, now: float) -> None:
        """开票流水。已撤下的守望也会留痕 —— 复盘时要看得到「它曾经问过」。"""
        self._ticket_log.append(
            {
                "ts": round(now, 3),
                "time": datetime.fromtimestamp(now).strftime("%m-%d %H:%M:%S"),
                "watch_id": tk.watch_id,
                "subject": tk.objective.subject,
                "market": tk.objective.market,
                "kind": tk.objective.kind,
                "side": str(tk.objective.params.get("side") or ""),
                "confidence": tk.objective.params.get("confidence"),
                "granted": tk.granted,
                "verdict": ask_verdict_text(tk.granted),
                "fired": list(tk.scan.fired_kinds or ()),
                "reason": tk.reason,
            }
        )

    def _note_missing_observer(self, watch: Watch) -> None:
        if watch.watch_id in self._warned_missing:
            return
        self._warned_missing.add(watch.watch_id)
        log.warning(
            "[WatchDesk] %s（%s）没有观测面工厂，本轮按「取不到观测」记录 —— "
            "不是「机会」",
            watch.watch_id, watch.objective.kind,
        )

    # ----------------------------------------------------------------
    def _intent_context(self, watch: Watch, now: float) -> WatchContext:
        """意向类守望的观测面：行情 + 距收盘时长 + Manas 读数。"""
        obj = watch.objective
        price, anchor = self._price_and_anchor(obj.subject, obj.market)
        return WatchContext(
            now=now,
            price=price,
            anchor=anchor,
            minutes_to_close=self._minutes_to_close(obj.market),
            action_type=None,
            extras={"manas_reading": self._reading(now)},
        )

    def _reading(self, now: float) -> Optional[ManasReading]:
        if self.lens is None:
            return None
        try:
            return self.lens.read(now=now)
        except Exception as e:  # noqa: BLE001
            log.warning("[WatchDesk] 读 Manas 读数失败: %s", e)
            return None

    def _price_and_anchor(
        self, code: str, market: str
    ) -> Tuple[Optional[float], Optional[float]]:
        quote = self._quote(self._bus_code(code, market))
        if quote is None:
            return None, None
        age = getattr(quote, "age", None)
        # 行情过期就传 None（调用方会记成 unknown），而不是拿陈货当现价
        if age is not None and float(age) > self._quote_max_age:
            return None, None
        cur = getattr(quote, "current", None)
        prev = getattr(quote, "prev_close", None)
        price = float(cur) if cur and float(cur) > 0 else None
        anchor = float(prev) if prev and float(prev) > 0 else None
        return price, anchor

    def _quote(self, bus_code: str) -> Any:
        if self._quote_fn is not None:
            try:
                return self._quote_fn(bus_code)
            except Exception as e:  # noqa: BLE001
                log.debug("[WatchDesk] 取行情失败 %s: %s", bus_code, e)
                return None
        try:
            from ..bandit.market_data_bus import get_market_data_bus

            bus = get_market_data_bus()
        except Exception as e:  # noqa: BLE001
            log.debug("[WatchDesk] 行情总线不可用 %s: %s", bus_code, e)
            return None

        try:
            quote = bus.get_quote(bus_code)
        except Exception as e:  # noqa: BLE001
            log.debug("[WatchDesk] 取 %s 行情失败: %s", bus_code, e)
            return None
        if quote is None:
            # ❗缓存缺失时不能就此罢手。总线的异步补抓是在 asyncio 线程里
            # 排的任务，本线程没有跑着的 loop —— create_task 退化成一个没人
            # await 的协程（日志里那条 ``never awaited``），缓存永远填不上，
            # 价格类判据就永远「看不清」。所以这里按冷却自己同步补一次。
            self._sync_fetch(bus, bus_code)
            try:
                quote = bus.get_quote(bus_code)
            except Exception as e:  # noqa: BLE001
                log.debug("[WatchDesk] 补抓后再取 %s 行情失败: %s", bus_code, e)
                return None
        return quote

    def _sync_fetch(self, bus: Any, bus_code: str) -> None:
        """按冷却同步补抓一次。失败只记一次 debug —— 取不到行情的合法结果是
        「本轮没有观测」，不能把轮询线程搞崩。"""
        now = float(self._clock())
        last = float(self._last_sync_fetch.get(bus_code, 0.0))
        if (now - last) < self.SYNC_FETCH_COOLDOWN:
            return
        self._last_sync_fetch[bus_code] = now
        try:
            bus.fetch([bus_code])
        except Exception as e:  # noqa: BLE001
            log.debug("[WatchDesk] 同步补抓 %s 失败: %s", bus_code, e)

    def _minutes_to_close(self, market: str) -> Optional[float]:
        fn = self._mtc_fn
        if fn is None:
            try:
                from ..bandit.market_session import minutes_to_close as fn  # type: ignore
            except Exception as e:  # noqa: BLE001
                log.debug("[WatchDesk] 时段模块不可用: %s", e)
                return None
        try:
            return fn(market)
        except Exception as e:  # noqa: BLE001
            log.debug("[WatchDesk] 算距收盘失败 %s: %s", market, e)
            return None

    @staticmethod
    def _bus_code(code: str, market: str) -> str:
        """归一化代码转行情总线代码。转不出来就用原码 —— 查不到行情的自然结果
        是观测面缺失（unknown），而不是认错标的。"""
        try:
            from ..bandit.market_data_bus import format_exchange_code

            return format_exchange_code(code)
        except Exception as e:  # noqa: BLE001
            log.debug("[WatchDesk] 推断 %s 的总线代码失败: %s", code, e)
            return code
