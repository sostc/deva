"""守望台的唤醒器 —— 把「世界变了」直接接到守望的求值上。

为什么要有这一层
----------------
守望是**执念**：它不主动打扰世界，世界变了它才醒。但系统里原本没有任何
东西会叫它 —— 守望台只能自己每 60 秒伸手问一遍（定时腿），于是：

* 闭市后照样转，而闭市的现价是一份不动的快照，判据本身是假的；
* Manas 档位变了它不知道，只能等到下一轮轮询撞上；
* 开盘那一刻它正好在两次轮询之间，最该被问的时刻反而没被问。

本模块做的是**订阅**：Manas 档位变化 / 交易时钟的时段切换一发生，立刻
叫醒相关的守望去求值。

❗三条硬纪律（每一条都是踩出来的）
----------------------------------
1. **事件腿不能替掉定时腿，只能补在它旁边。**
   纯事件驱动下「没有事件」与「链路断了」长得一模一样 —— 订阅没挂上、
   总线挂了、生产者没人调，守望都会**永远安静且不报错**。这正是守望系统
   当初要加「600 秒沉默催醒 + bootstrap」的原因。所以定时腿是**观测设施**，
   不是没改造干净的残留。本模块只负责让事件腿**更早**叫醒守望。

2. **每一次求值都要记 ``wake_reason``。**
   否则事后无法回答「这个守望三天没问过，是没机会还是链路断了」。
   这是静默失效唯一的入口，必须留。

3. **订阅失败必须透出，回调绝不向外抛。**
   订阅挂在别人的发布链上，回调里抛异常会打断发布者；而订阅失败如果
   只 debug 一行，通道坏了会完全隐形 —— 那就是「合法的空比异常更危险」。

节流
----
盘中行情/事件可能很密，逐条求值会把「固定成本」换成「按波动计费」。
所以两次求值之间有最小间隔；窗口内到达的唤醒**合并而非丢弃**（记进
``pending``，由定时腿 ``flush()`` 补做）—— 事件可以延后，不能消失。

回滚开关：``NAJA_WATCH_AWAKENER=0``。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

log = logging.getLogger(__name__)

ENV_ENABLED = "NAJA_WATCH_AWAKENER"
ENV_MIN_INTERVAL = "NAJA_WATCH_WAKE_MIN_INTERVAL"
ENV_QUIET_SEC = "NAJA_WATCH_QUIET_SEC"
ENV_EXPECT_GRACE = "NAJA_WATCH_EXPECT_GRACE"

#: 两次被唤醒求值之间的最小间隔（秒）。窗口内到达的唤醒会被合并。
DEFAULT_MIN_INTERVAL = 10.0
#: 事件腿安静多久算可疑（秒）。超过就说明「可能没人叫得醒守望了」。
DEFAULT_QUIET_SEC = 1800.0
#: 时钟已经预告了「下一次相位切换大概什么时候」，允许它迟到多久仍不算异常（秒）。
#: ❗这个宽限是必要的：时钟只在**相位切换**时发信号，而相位本身是稀疏的
#: （CN 收盘到次日开盘 18 小时、美股盘后到盘前 5.5 小时都没有切换）。
#: 没有它，「夜间天然安静」会每小时被判成「链路断了」。
DEFAULT_EXPECT_GRACE = 300.0
#: 单个「预期下一次信号」的上限（秒）。时钟给的 seconds_until_next 若是异常
#: 值或结构漂移，截断到这里 —— 否则一个离谱的数字会把沉默判定永久压住，
#: 那就从「假警报」变成了「真的断了没人知道」。
MAX_EXPECT_HORIZON = 24 * 3600.0

# -- wake_reason 的取值 -------------------------------------------------
#: Manas 行动档位变化（唯一的认知侧唤醒源）
WAKE_MANAS = "manas"
#: 交易时钟的时段切换（开盘 / 午休 / 收盘）
WAKE_CLOCK = "clock"
#: 定时腿补做（把合并掉的唤醒做掉）
WAKE_TIMER = "timer"
#: 手工 / 测试触发
WAKE_MANUAL = "manual"

#: 交易时钟里**值得**叫醒守望的时段。closed 不必叫（叫了也会被闸门挡）。
CLOCK_WAKE_PHASES = ("trading", "call_auction", "pre_market", "post_market")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return default
    return val if val >= 0 else default


def _env_on(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


class WatchAwakener:
    """订阅「世界的变化」，叫醒守望台去求值。

    :param desk: 守望台（需要有 ``poll(now=..., wake_reason=..., markets=...)``）。
    :param min_interval: 两次求值的最小间隔，默认 10 秒；0 表示不去抖。
    :param quiet_sec: 事件腿安静多久算可疑，默认 1800 秒。
    :param clock: 时间函数，仅测试注入用。
    """

    def __init__(
        self,
        desk: Any,
        *,
        min_interval: Optional[float] = None,
        quiet_sec: Optional[float] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._desk = desk
        self._min_interval = (
            float(min_interval)
            if min_interval is not None
            else _env_float(ENV_MIN_INTERVAL, DEFAULT_MIN_INTERVAL)
        )
        self._quiet_sec = (
            float(quiet_sec)
            if quiet_sec is not None
            else _env_float(ENV_QUIET_SEC, DEFAULT_QUIET_SEC)
        )
        self._expect_grace = _env_float(ENV_EXPECT_GRACE, DEFAULT_EXPECT_GRACE)
        self._clock: Callable[[], float] = clock or time.time
        self._lock = threading.RLock()

        # -- 订阅状态 -----------------------------------------------------
        self.attached: Dict[str, bool] = {"manas": False, "clock": False}
        #: 有没有真的尝试挂过。❗没挂过 ≠ 挂失败 —— 混在一起会让从未启动
        #: 的唤醒器报「事件源全挂了」，那是假警报。
        self.attach_attempted = False
        #: ❗订阅失败的原因必须留下来：挂着 False 却不说为什么，等于静默失效
        self.attach_errors: Dict[str, str] = {}
        #: 回调里抛过的异常次数（回调绝不能打断发布者，但不能因此不问）
        self.callback_errors = 0
        self.callback_error_reason = ""
        #: 时钟事件缺 phase 的次数（结构漂移的早期信号）
        self.clock_phase_unknown = 0

        # -- 链路活性（❗「没变化」与「通道断了」必须分得开） ---------------
        #: 最近一次**收到信号**的时刻，含被相位过滤掉的 closed/lunch。
        #: 它证明的是「订阅还在、时钟还在发」，与「值不值得唤醒」无关 ——
        #: 只看 last_wake_at 会把「夜间没有可唤醒的相位」误判成链路断了。
        self.last_signal_at: Optional[float] = None
        self.last_signal_detail: str = ""
        #: 各市场「预期下一次信号最晚何时到」，由时钟信号自带的
        #: seconds_until_next 推导；逾期仍未收到才是最可疑的信号。
        self._market_expect: Dict[str, float] = {}

        # -- 唤醒与求值 ---------------------------------------------------
        self.wake_counts: Dict[str, int] = {}
        self.pending: List[str] = []
        self.evals = 0
        self.throttled = 0
        self.last_wake_at: Optional[float] = None
        self.last_wake_reason: str = ""
        self.last_wake_detail: str = ""
        self.last_eval_at: Optional[float] = None
        self.last_eval_tickets: int = 0
        self._recent: deque = deque(maxlen=50)
        #: 事件腿求值产生的票，等定时腿来取走统计。
        #: ❗没有这一步，事件腿开出的票会**不计入统计** —— 页面上看到
        #: 「问过 0 次」，实际问过，属于典型的「显示另一套数」。
        self._undrained: List[Any] = []

    # ------------------------------------------------------------------
    # 订阅
    # ------------------------------------------------------------------
    def enabled(self) -> bool:
        return _env_on(ENV_ENABLED, True)

    def attach(self) -> Dict[str, bool]:
        """挂上所有事件源。单个源挂不上**只跳过它**，不影响别的源。

        ❗返回值要被检查：两个都 False 就意味着守望只剩下定时腿在撑着，
        那必须喊出来（见 :meth:`health_line`）。
        """
        self.attach_attempted = True
        self._attach_manas()
        self._attach_clock()
        ok = [k for k, v in self.attached.items() if v]
        if ok:
            log.info("[WatchAwakener] 已订阅: %s", "、".join(ok))
            # ❗bootstrap：服务启动时是 **Manas 先 compute 完、唤醒器才挂上**，
            # 那第一次档位变化发生在订阅之前，守望收不到 —— 等下一轮定时腿
            # 才补上，事件腿就白挂了。挂上后主动醒一次，把基线补回来。
            # 同一时刻把「下一次信号预期何时到」也补上：不然刚挂上就要干等
            # quiet_sec 才敢说没事，夜间隔几小时的那种天然安静会被误报。
            self._arm_expect_from_clock()
            self.wake(WAKE_MANAS, detail="bootstrap")
        else:
            log.warning(
                "[WatchAwakener] 一个事件源都没挂上（%s）—— 守望只剩定时腿，"
                "事件驱动其实没生效",
                self.attach_errors or "未知原因",
            )
        return dict(self.attached)

    def _attach_manas(self) -> bool:
        try:
            from deva.naja.events import CognitiveEventType, get_event_bus

            bus = get_event_bus()
            bus.subscribe(
                "WatchAwakener",
                self._on_manas_event,
                event_types=[CognitiveEventType.MANAS_STATE_CHANGED],
            )
            self.attached["manas"] = True
            return True
        except Exception as e:  # noqa: BLE001
            self.attach_errors["manas"] = f"{type(e).__name__}: {e}"
            log.warning(
                "[WatchAwakener] 订阅 MANAS_STATE_CHANGED 失败，守望台将"
                "收不到档位变化: %s", e, exc_info=True,
            )
            return False

    def _attach_clock(self) -> bool:
        try:
            from deva.naja.radar.trading_clock import TRADING_CLOCK_STREAM

            TRADING_CLOCK_STREAM.sink(self._on_clock_event)
            self.attached["clock"] = True
            return True
        except Exception as e:  # noqa: BLE001
            self.attach_errors["clock"] = f"{type(e).__name__}: {e}"
            log.warning(
                "[WatchAwakener] 订阅交易时钟流失败，守望台将收不到开收盘: %s",
                e, exc_info=True,
            )
            return False

    # ------------------------------------------------------------------
    # 链路活性
    # ------------------------------------------------------------------
    def _note_signal(self, detail: str, now: Optional[float] = None) -> float:
        """记下「链路活着」的证据：**收到信号本身**就有信息量。

        ❗closed/lunch 的相位切换虽然不值得唤醒守望（叫了也会被闸门挡），
        但它同样证明「订阅还在、时钟还在发」。把它当噪音丢掉，就再也分不出
        「真的没变化」和「通道断了」—— 而那正是本模块存在的理由。
        """
        t = float(now if now is not None else self._clock())
        with self._lock:
            self.last_signal_at = t
            self.last_signal_detail = detail
        return t

    def _arm_expect(self, market: Optional[str], secs: Any, now: float) -> None:
        """由时钟信号里的 ``seconds_until_next`` 推出「下一次信号最晚何时到」。

        取各市场里**最近**的那个：任一市场的相位切换都会发信号，所以最近
        的一次就是链路下一个可验证的时刻。
        """
        try:
            horizon = float(secs)
        except (TypeError, ValueError):
            return
        if horizon <= 0:
            return
        with self._lock:
            self._market_expect[str(market or "?")] = now + min(
                horizon, MAX_EXPECT_HORIZON
            )

    def _arm_expect_from_clock(self) -> None:
        """挂载时问时钟一次：下一次相位切换大概什么时候。问不到就算了。

        失败**不许外抛**（挂载路径不能被它拖垮），也不许静默改判定 ——
        问不到就是 expect_by() 返回 None，退回按安静时长判定。
        """
        now = self._clock()
        try:
            from deva.naja.radar.trading_clock import TradingClock

            clock = TradingClock()
        except Exception:  # noqa: BLE001
            return
        for mk, fn in (("CN", "get_cn_signal"), ("US", "get_us_signal")):
            try:
                sig = getattr(clock, fn)()
            except Exception:  # noqa: BLE001
                continue
            if isinstance(sig, dict):
                self._arm_expect(mk, sig.get("seconds_until_next"), now)

    def expect_by(self) -> Optional[float]:
        """预期下一次事件信号最晚到达的时刻；没有依据时返回 None。"""
        with self._lock:
            vals = [v for v in self._market_expect.values() if v is not None]
        return min(vals) if vals else None

    def _last_activity(self) -> Optional[float]:
        """链路最后一次有动静的时刻：收到信号或被唤醒，取较晚的那个。"""
        cands = [
            x for x in (self.last_signal_at, self.last_wake_at) if x is not None
        ]
        return max(cands) if cands else None

    # ------------------------------------------------------------------
    # 事件回调（绝不向外抛）
    # ------------------------------------------------------------------
    def _on_manas_event(self, event: Any) -> None:
        try:
            data = getattr(event, "data", None) or {}
            cur = data.get("action_type")
            prev = data.get("prev_action_type")
            self._note_signal(f"manas:{prev or '（无）'}→{cur}")
            # ❗档位是组合级的，不针对某个市场 → 全量求值
            self.wake(WAKE_MANAS, detail=f"{prev or '（无）'}→{cur}")
        except Exception as e:  # noqa: BLE001
            self._note_callback_error(e)

    def _on_clock_event(self, event: Any) -> None:
        try:
            data = event if isinstance(event, dict) else {}
            market = data.get("market")
            phase = data.get("phase")
            # ❗先记活性、再过滤：closed/lunch 不值得唤醒，但它证明通道还活着。
            t = self._note_signal(f"{market}:{phase}")
            self._arm_expect(market, data.get("seconds_until_next"), t)
            if phase and phase not in CLOCK_WAKE_PHASES:
                # closed 不必叫醒：叫了也会被闭市闸门挡下，只是白跑一趟
                return
            if not phase:
                # ❗事件里没有 phase 时**不能假装它是 trading**。认不出来就
                # 记一笔并照常唤醒（宁可多叫一次，不要漏掉开盘），但必须
                # 留下痕迹 —— 否则时钟事件结构一变，这里会静默退化成
                # 「每次时钟事件都把全部守望吵一遍」。
                self.clock_phase_unknown += 1
                log.warning(
                    "[WatchAwakener] 交易时钟事件缺 phase（第 %d 次，"
                    "market=%s）—— 照常唤醒，但请检查时钟事件结构",
                    self.clock_phase_unknown, market,
                )
            self.wake(WAKE_CLOCK, market=market, detail=f"{market}:{phase}")
        except Exception as e:  # noqa: BLE001
            self._note_callback_error(e)

    def _note_callback_error(self, e: Exception) -> None:
        self.callback_errors += 1
        self.callback_error_reason = f"{type(e).__name__}: {e}"
        log.warning(
            "[WatchAwakener] 事件回调出错（第 %d 次），这次唤醒作废: %s",
            self.callback_errors, e, exc_info=True,
        )

    # ------------------------------------------------------------------
    # 唤醒
    # ------------------------------------------------------------------
    def wake(
        self,
        reason: str,
        *,
        market: Optional[str] = None,
        detail: str = "",
        now: Optional[float] = None,
    ) -> bool:
        """叫醒守望。返回**是否真的求值了**（False = 被节流合并）。

        ❗被节流不是丢弃：reason 会记进 ``pending``，由 :meth:`flush` 补做。
        """
        t = float(now if now is not None else self._clock())
        markets: Optional[Set[str]] = {market} if market else None
        with self._lock:
            self.wake_counts[reason] = self.wake_counts.get(reason, 0) + 1
            self.last_wake_at = t
            self.last_wake_reason = reason
            self.last_wake_detail = detail
            self._recent.append(
                {"ts": t, "reason": reason, "market": market, "detail": detail}
            )
            if self._too_soon(t):
                self.throttled += 1
                if reason not in self.pending:
                    self.pending.append(reason)
                return False
            return self._evaluate(t, [reason], markets)

    def flush(self, now: Optional[float] = None) -> bool:
        """定时腿每轮调一次：把合并掉的唤醒做掉。

        ❗这是「事件不丢」的保证 —— 节流只是延后，不是取消。
        """
        t = float(now if now is not None else self._clock())
        with self._lock:
            if not self.pending:
                return False
            if self._too_soon(t):
                return False
            reasons = list(self.pending)
            return self._evaluate(t, reasons, None)

    def _too_soon(self, t: float) -> bool:
        if self._min_interval <= 0 or self.last_eval_at is None:
            return False
        return (t - self.last_eval_at) < self._min_interval

    def _evaluate(
        self,
        t: float,
        reasons: Sequence[str],
        markets: Optional[Set[str]],
    ) -> bool:
        merged = "+".join(reasons) or WAKE_MANUAL
        try:
            tickets = self._desk.poll(now=t, wake_reason=merged, markets=markets)
        except TypeError:
            # ❗兼容没有 markets 参数的旧 desk：宁可全量求值，也不要因为
            # 签名不匹配把唤醒吞掉（吞掉 = 事件腿静默失效）
            try:
                tickets = self._desk.poll(now=t, wake_reason=merged)
            except Exception as e:  # noqa: BLE001
                self._note_callback_error(e)
                return False
        except Exception as e:  # noqa: BLE001
            self._note_callback_error(e)
            return False
        tickets = list(tickets or [])
        self.evals += 1
        self.last_eval_at = t
        self.last_eval_tickets = len(tickets)
        self._undrained.extend(tickets)
        self.pending = []
        # ❗「被叫醒了」必须看得见：否则事件腿到底有没有在起作用，只能
        # 靠猜。省掉的问询要留痕，被事件叫醒同样要留痕。
        log.info(
            "[WatchAwakener] 被 %s 叫醒 → 求值完成（%d 张票，本次唤醒来源 %s）",
            merged, len(tickets), ",".join(reasons),
        )
        return True

    def drain_tickets(self) -> List[Any]:
        """取走（并清空）事件腿求值产生的票，交给定时腿统一统计。"""
        with self._lock:
            out = list(self._undrained)
            self._undrained = []
        return out

    # ------------------------------------------------------------------
    # 自证
    # ------------------------------------------------------------------
    def quiet_seconds(self, now: Optional[float] = None) -> Optional[float]:
        """距**上一次链路有动静**过去了多久（收到信号或被唤醒都算）。

        只看事件腿，不含定时腿的 ``flush``。用「收到信号」而非「被唤醒」作
        基准：夜间那些被相位过滤掉的时钟切换同样是链路活着的证据。

        None = 一次都没有过（可能刚启动，也可能通道压根没通）。
        """
        ref = self._last_activity()
        if ref is None:
            return None
        t = float(now if now is not None else self._clock())
        return max(0.0, t - ref)

    def quiet_suspicious(self, now: Optional[float] = None) -> bool:
        """事件腿是不是安静得太久了。

        ❗这条判断的存在意义：把「真的没变化」和「通道断了没人叫」区分开。
        只看「没被叫醒」这两种情况长得一样，必须把沉默时长变成可观测量。
        """
        if not any(self.attached.values()):
            return False  # 压根没订阅 → 由 attach 的 WARNING 负责喊
        t = float(now if now is not None else self._clock())
        # ❗时钟已经预告了下一次相位切换的大致时刻，在那之前安静是**预期内**的：
        # CN 收盘到次日开盘、美股盘后到盘前本就是几小时没有可唤醒的变化。
        # 只有它逾期还没来，才说明「链路断了」而不是「今天没事发生」。
        exp = self.expect_by()
        if exp is not None and t <= exp + self._expect_grace:
            return False
        q = self.quiet_seconds(t)
        if q is None:
            return False
        return q > self._quiet_sec

    def health_line(self, now: Optional[float] = None) -> Optional[str]:
        """一句人话的自证。没异常时返回 None（❗不要制造噪音）。

        ❗「假警报比不报警更伤」：只有真的可疑才说话。
        """
        problems: List[str] = []
        if self.attach_attempted and not any(self.attached.values()):
            problems.append(
                f"事件源一个都没挂上（{self.attach_errors or '未知原因'}）"
            )
        elif self.quiet_suspicious(now):
            # ❗文案里**不放递增的量**（秒数/分钟数）：调用方靠「整行变了才喊」
            # 去抖，嵌一个每轮都在变的数字等于没有去抖 —— 曾经因此每小时刷
            # 45~60 条同一件事。精确值走 status()/quiet_seconds()，那里不怕重复。
            problems.append(
                f"事件腿已沉默（安静超过阈值 {int(self._quiet_sec)}s，"
                "且时钟预告的下一次相位切换也已逾期）"
            )
        if self.callback_errors:
            problems.append(
                f"回调出错 {self.callback_errors} 次"
                f"（最近：{self.callback_error_reason}）"
            )
        if not problems:
            return None
        return "守望唤醒器：" + "；".join(problems)

    def status(self, now: Optional[float] = None) -> Dict[str, Any]:
        t = float(now if now is not None else self._clock())
        return {
            "attached": dict(self.attached),
            "attach_attempted": self.attach_attempted,
            "attach_errors": dict(self.attach_errors),
            "clock_phase_unknown": self.clock_phase_unknown,
            "min_interval": self._min_interval,
            "quiet_sec": self._quiet_sec,
            "wake_counts": dict(self.wake_counts),
            "pending": list(self.pending),
            "evals": self.evals,
            "throttled": self.throttled,
            "callback_errors": self.callback_errors,
            "last_wake_reason": self.last_wake_reason,
            "last_wake_detail": self.last_wake_detail,
            "last_wake_at": self.last_wake_at,
            "last_eval_at": self.last_eval_at,
            "last_eval_tickets": self.last_eval_tickets,
            "last_signal_at": self.last_signal_at,
            "last_signal_detail": self.last_signal_detail,
            "expect_by": self.expect_by(),
            "expect_in": (self.expect_by() - t) if self.expect_by() else None,
            "quiet_sec_now": self.quiet_seconds(t),
            "quiet_suspicious": self.quiet_suspicious(t),
        }

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = list(self._recent)
        if limit and limit > 0:
            rows = rows[-int(limit):]
        return list(reversed(rows))


_AWAKENER: Optional[WatchAwakener] = None
_AWAKENER_LOCK = threading.Lock()


def get_watch_awakener(desk: Any = None) -> Optional[WatchAwakener]:
    """取（或建）全局唤醒器。``NAJA_WATCH_AWAKENER=0`` 时返回 None。"""
    global _AWAKENER
    if not _env_on(ENV_ENABLED, True):
        return None
    with _AWAKENER_LOCK:
        if _AWAKENER is None:
            if desk is None:
                from deva.naja.bandit.intent_runner import get_intent_runner

                desk = get_intent_runner().desk
            _AWAKENER = WatchAwakener(desk)
        return _AWAKENER


def reset_watch_awakener() -> None:
    """仅测试用：清掉全局单例。"""
    global _AWAKENER
    with _AWAKENER_LOCK:
        _AWAKENER = None
