"""IntentRunner —— 让「我想买英伟达」这种人工意向真的一直有人盯着。

为什么要有第四条运行器
======================
做 T 那条线（``TRotationRunner``）解决的是「已经持有的底仓怎么降成本」，
它对「还没买、想买但不知道什么时候下手」这件事一无所知 ——
2026-10-14 用户问的就是这个缺口：「这个想买入的想法应该进入守望台」。

本运行器只做三件事，别的都不做：

1. **按节拍 poll 守望台**（默认 60 秒一轮）；
2. **机会成立时去问决策中心**，把结论写进日志与守望状态；
3. **周期性自报**（默认 15 分钟一行心跳），让「在等」这件事看得见。

❗它**不下单**。批了只是「拿到一张可以执行的许可」，
真要落单还需要另一道显式的授权，那条线还没接。

自报为什么是必需的
==================
会自动交易的后台任务必须周期性自报，否则分不清「在跑但没机会」和
「线程已经死了」—— 这是做 T 那条线已经得出的结论。

环境变量
========
``NAJA_INTENT_WATCH_ENABLED``   ``0`` 关闭（默认开）
``NAJA_INTENT_POLL_SECONDS``    轮询秒数，默认 60
``NAJA_INTENT_HEARTBEAT_SEC``   心跳秒数，默认 900
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from ..watch import BuyIntent, Intent, SellIntent, WatchDesk, WatchScan
from .core_holdings import env_flag, env_float

log = logging.getLogger(__name__)

__all__ = [
    "IntentRunner", "get_intent_runner", "decision_center_asker",
    "intent_file_path", "load_intents",
]

DEFAULT_POLL_SECONDS = 60.0
DEFAULT_HEARTBEAT_SEC = 900.0

#: 声明式意向清单。守望是**纯内存**的，另一个进程里登记不会飞进服务进程，
#: 所以「我想买英伟达」这句话要落到一个服务启动时读得到的地方。
ENV_INTENT_FILE = "NAJA_INTENT_FILE"
DEFAULT_INTENT_FILE = "~/.naja/intents.json"

_runner: Optional["IntentRunner"] = None
_runner_lock = threading.Lock()


# ---------------------------------------------------------------- 询问器

def decision_center_asker(objective: Any, ctx: Any, _scan: WatchScan):
    """默认的询问器：把提问交给决策中心，**批了才谈执行**。

    复用 :func:`~.core_establish_gate.ask_decision_center` 而不是另写一份：
    那条路径自带 :class:`DecisionPlan` 留痕（写穿日志），
    事后能查到「这一笔当时为什么放行 / 被否」。另写一份等于绕过留痕。
    """
    from .core_establish_gate import VerdictUnavailable, ask_decision_center

    price = float(getattr(ctx, "price", 0.0) or 0.0)
    side = str(objective.params.get("side") or "buy").upper()
    spec = SimpleNamespace(
        code=objective.subject,
        bus_code=_bus_code(objective.subject, objective.market),
        name=objective.params.get("name") or objective.subject,
    )
    try:
        raw = ask_decision_center(spec, price)
    except VerdictUnavailable as e:
        # ❗「不清楚」与「已否决」是两码事，理由里必须写出来
        return False, f"决策中心不可用：{e}"
    except Exception as e:  # noqa: BLE001
        return False, f"问决策中心抛异常：{type(e).__name__}: {e}"

    plan = raw.get("plan") or {}
    action_type = str(raw.get("action_type") or plan.get("action_type") or "hold")
    size_hint = float(plan.get("size_hint") or 0.0)
    approved = bool(raw.get("approved"))
    detail = (
        f"档位={action_type} size_hint={size_hint:.2f} "
        f"置信度={raw.get('final_confidence')}"
    )
    if approved and size_hint > 0:
        return True, f"决策中心放行（{detail}）"
    reason = str(plan.get("gate_reason") or "")
    if not approved and reason:
        return False, f"{reason}（{detail}）"
    if approved and size_hint <= 0:
        return False, f"决策中心批准但没给额度（{detail}）—— 常见于 hold 档"
    return False, f"决策中心未予批准（{detail}）"


def _bus_code(code: str, market: str) -> str:
    """总线 bus 代码。决策中心把 code 当作带前缀的标准化代码处理，
    喂裸码会被当成另一个标的。"""
    text = str(code or "").strip()
    if text.startswith(("sh", "sz", "bj", "gb_", "hk")):
        return text
    try:
        from .market_data_bus import format_exchange_code

        return format_exchange_code(text)
    except Exception as e:  # noqa: BLE001
        log.debug("[IntentRunner] 推断 %s 的总线代码失败: %s", text, e)
        return text


def intent_file_path() -> Path:
    """意向清单路径。"""
    raw = (os.environ.get(ENV_INTENT_FILE) or "").strip()
    return Path(raw).expanduser() if raw else Path(DEFAULT_INTENT_FILE).expanduser()


def load_intents(path=None) -> List[Intent]:
    """读声明式意向清单。

    单条坏了**只跳过那一条并喊出来**，不影响其余：一份清单里有一条填错市场，
    不该让另外几条「想买」也跟着消失（静默失效家族的标准形态）。

    文件不存在是「合法的空」：返回空列表，不报错。
    """
    p = Path(path).expanduser() if path is not None else intent_file_path()
    if not p.exists():
        log.debug("[IntentRunner] 意向清单 %s 不存在（合法的空）", p)
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("[IntentRunner] 意向清单 %s 读不出来：%s:%s",
                    p, type(e).__name__, e)
        return []

    rows = data if isinstance(data, list) else (data.get("intents") or [])
    if not isinstance(rows, list):
        log.warning("[IntentRunner] 意向清单 %s 的顶层不是列表，整份跳过", p)
        return []

    out: List[Intent] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            log.warning("[IntentRunner] 意向清单第 %d 条不是对象，跳过", i + 1)
            continue
        try:
            side = str(row.get("side") or "buy").strip().lower()
            factory = SellIntent if side in ("sell", "trim") else BuyIntent
            out.append(factory(
                str(row.get("code") or "").strip(),
                str(row.get("market") or "").strip(),
                max_wait_seconds=float(row.get("max_wait_seconds") or 0.0),
                name=str(row.get("name") or ""),
                budget=(float(row["budget"]) if row.get("budget") else None),
                note=str(row.get("note") or ""),
                rationale=str(row.get("rationale") or ""),
                min_action=str(row.get("min_action") or "act_minimally"),
                reading_max_age=float(row.get("reading_max_age") or 600.0),
            ))
        except Exception as e:  # noqa: BLE001 - 单条坏了只跳过这一条
            log.warning("[IntentRunner] 意向清单第 %d 条（%s）不可用：%s:%s",
                        i + 1, row.get("code"), type(e).__name__, e)
    return out


class IntentRunner:
    """意向守望的常驻驱动。

    :param desk: 守望台桌面；不传就自己造一个（默认询问器）。
    :param asker: 决策执行器；默认用 :func:`decision_center_asker`。
    """

    ENV_ENABLED = "NAJA_INTENT_WATCH_ENABLED"
    ENV_POLL = "NAJA_INTENT_POLL_SECONDS"
    ENV_HEARTBEAT = "NAJA_INTENT_HEARTBEAT_SEC"

    def __init__(
        self,
        desk: Optional[WatchDesk] = None,
        *,
        asker: Optional[Callable[..., Any]] = None,
        enabled: Optional[bool] = None,
        poll_seconds: Optional[float] = None,
        heartbeat_sec: Optional[float] = None,
    ) -> None:
        self._desk = desk
        self._asker = asker
        self._enabled = env_flag(self.ENV_ENABLED, True) if enabled is None else bool(enabled)
        self._poll_seconds = (
            env_float(self.ENV_POLL, DEFAULT_POLL_SECONDS)
            if poll_seconds is None
            else float(poll_seconds)
        )
        self._beat_sec = (
            env_float(self.ENV_HEARTBEAT, DEFAULT_HEARTBEAT_SEC)
            if heartbeat_sec is None
            else float(heartbeat_sec)
        )
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._desk_lock = threading.Lock()
        self._errors: Dict[str, str] = {}
        self.stats: Dict[str, int] = {
            "polls": 0,
            "tickets": 0,
            "granted": 0,
            "denied": 0,
            "unanswered": 0,
        }

    # ----------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    @property
    def desk(self) -> WatchDesk:
        """取桌面，没有就现场装一个。要不要跑起来交给 start()。"""
        with self._desk_lock:
            if self._desk is None:
                self._desk = WatchDesk(
                    asker=self._asker or decision_center_asker,
                    heartbeat_sec=self._beat_sec,
                )
            elif self._asker is not None and self._desk.asker is None:
                # ❗外部注入的桌面可能没接执行器。运行器自己的执行器必须补上去，
                # 否则「接了执行器」这件事被静默丢掉 —— 票照样开、照样没人消费，
                # 日志里只留下一句「没接执行器」，而代码明明接了。
                self._desk.asker = self._asker
        return self._desk

    # ----------------------------------------------------------------
    def seed(self, path=None) -> int:
        """读声明式清单并挂上守望台，返回成功挂上去的条数。"""
        n = 0
        for intent in load_intents(path):
            try:
                self.declare(intent)
                n += 1
            except Exception as e:  # noqa: BLE001
                log.warning("[IntentRunner] 意向 %s 没挂上去：%s:%s",
                            intent.describe(), type(e).__name__, e)
        return n

    def declare(self, intent: Intent) -> str:
        """登记一个意向。运行器还没启动也能调用（start 之后会一起扫描）。"""
        watch = self.desk.declare_intent(intent)
        log.info(
            "[IntentRunner] 意向已进入守望台：%s（%s），最多等 %.0f 小时",
            watch.watch_id, intent.describe(),
            float(intent.max_wait_seconds or 0.0) / 3600.0,
        )
        return watch.watch_id

    def start(self) -> bool:
        if not self._enabled:
            log.info("[IntentRunner] NAJA_INTENT_WATCH_ENABLED=0，未启动")
            return False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            try:
                self.desk  # 触发现场装配，失败要在这里炸而不是在线程里
            except Exception as e:  # noqa: BLE001
                self._errors["desk"] = str(e)
                log.error(f"[IntentRunner] 守望台桌面装配失败，运行器不启动: {e}",
                          exc_info=True)
                return False
            seeded = self.seed()
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop, name="intent-watch", daemon=True
            )
            self._thread.start()
            log.info(
                "[IntentRunner] 已启动：轮询 %.0fs，心跳 %.0fs，当前 %d 个守望"
                "（其中 %d 个来自声明式清单 %s）",
                self._poll_seconds, self._beat_sec, len(self.desk.registry),
                seeded, intent_file_path(),
            )
            return True

    def stop(self, timeout: float = 3.0) -> bool:
        self._stop.set()
        th = self._thread
        if th is not None and th.is_alive():
            th.join(timeout)
        return not (th is not None and th.is_alive())

    # ----------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        out = self.desk.snapshot()
        out.update({"running": self.running, "stats": dict(self.stats),
                    "errors": dict(self._errors)})
        return out

    def tick(self, now: Optional[float] = None) -> List[Any]:
        """跑一轮。与心跳分离是为了便于测试与手工推动。"""
        t = now if now is not None else time.time()
        self.stats["polls"] += 1
        tickets = self.desk.poll(t)
        for tk in tickets:
            self.stats["tickets"] += 1
            if tk.unanswered:
                self.stats["unanswered"] += 1
                continue
            if tk.granted:
                self.stats["granted"] += 1
                log.info(
                    "[IntentRunner] 🚦 %s 机会成立且决策中心放行：%s（%s）",
                    tk.watch_id, tk.objective.describe(), tk.reason,
                )
            else:
                self.stats["denied"] += 1
                log.info(
                    "[IntentRunner] ⏳ %s 机会成立但决策中心未予批准：%s",
                    tk.watch_id, tk.reason,
                )
        # ❗心跳文本必须落日志：registry 那一行只报守望台，
        # Manas 镜头「看过几次 / 看不清几次」和「几张票没人消费」只在桌面这一行里。
        beat = self.desk.heartbeat(t)
        if beat:
            log.info("[IntentRunner] %s", beat)
        return tickets

    # ----------------------------------------------------------------
    def _run_loop(self) -> None:
        while not self._stop.wait(self._poll_seconds):
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                # 轮询线程里的 except 必须把堆栈留下，否则故障会被吞掉
                log.error(f"[IntentRunner] 本轮扫描失败: {e}", exc_info=True)
        log.info("[IntentRunner] 轮询线程已退出")


def get_intent_runner() -> IntentRunner:
    """进程内单例。容器启动时用它 start()。"""
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = IntentRunner()
        return _runner
