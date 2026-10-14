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
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from ..watch import BuyIntent, Intent, SellIntent, WatchDesk, WatchScan
from ..watch.intent import clamp_confidence
from .core_holdings import env_flag, env_float

log = logging.getLogger(__name__)

__all__ = [
    "IntentRunner", "get_intent_runner", "decision_center_asker",
    "intent_file_path", "load_intents",
    "read_intent_rows", "save_intents", "upsert_intent", "remove_intent",
    "intent_row_of",
]

DEFAULT_POLL_SECONDS = 60.0
DEFAULT_HEARTBEAT_SEC = 900.0

#: 意愿强度的全局覆盖。设成 0.5 就等于「人工意向与系统自动补仓无差别」——
#: 这是这条链路的一句话回滚开关。定义在**模块级**而不是类属性：
#: :func:`decision_center_asker` 是模块级函数，拿不到类命名空间。
ENV_INTENT_CONFIDENCE = "NAJA_INTENT_CONFIDENCE"

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
    from ..watch.intent import SIGNAL_TYPE_FOR_SIDE, clamp_confidence
    from .core_establish_gate import VerdictUnavailable, ask_decision_center

    price = float(getattr(ctx, "price", 0.0) or 0.0)
    side = str(objective.params.get("side") or "buy").strip().lower()
    signal_type = (
        str(objective.params.get("signal_type") or "").strip().upper()
        or SIGNAL_TYPE_FOR_SIDE.get(side, "BUY")
    )

    # ❗意愿强度：优先意向自带，其次环境变量（一句话回滚成「无差别」），
    # 最后才是默认。上限由 clamp_confidence 兜住，谁都调不过 0.75。
    raw_conf = objective.params.get("confidence")
    env_conf = os.environ.get(ENV_INTENT_CONFIDENCE)
    if env_conf:
        try:
            raw_conf = float(env_conf)
        except ValueError:
            log.warning("[IntentRunner] 非法 %s=%r，忽略", ENV_INTENT_CONFIDENCE, env_conf)
    confidence = clamp_confidence(raw_conf)

    spec = SimpleNamespace(
        code=objective.subject,
        bus_code=_bus_code(objective.subject, objective.market),
        name=objective.params.get("name") or objective.subject,
        # ❗身份必须可区分：决策中心原先看到的是 core_establish:NVDA，
        # 跟系统自动补底仓的信号长得一模一样 —— 「这是人想买的」这件事
        # 在打分里权重就是 0。留痕时也能一眼分出两条链路。
        strategy_id=f"intent:{side}:{objective.subject}",
        signal_type=signal_type,
        signal_confidence=confidence,
        signal_metadata={
            "intent": True,
            "side": side,
            "market": objective.market,
            "rationale": str(objective.params.get("rationale") or ""),
            "budget": objective.params.get("budget"),
            "confidence": confidence,
            "confidence_source": (
                "env" if env_conf
                else ("intent" if objective.params.get("confidence_explicit") else "default")
            ),
            "watch_id": getattr(objective, "id", ""),
        },
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
                confidence=row.get("confidence"),
            ))
        except Exception as e:  # noqa: BLE001 - 单条坏了只跳过这一条
            log.warning("[IntentRunner] 意向清单第 %d 条（%s）不可用：%s:%s",
                        i + 1, row.get("code"), type(e).__name__, e)
    return out


# ---------------------------------------------------------------- 落盘

def _read_doc(path: Path) -> Any:
    """读清单原文。读不出来返回 ``None``（**不抛**），写回方据此决定怎么办。"""
    if not Path(path).exists():
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("[IntentRunner] 意向清单 %s 读不出来：%s:%s",
                    path, type(e).__name__, e)
        return None


def read_intent_rows(path=None) -> List[Dict[str, Any]]:
    """读清单里的**原始条目**（dict 列表），不做校验。

    与 :func:`load_intents` 的分工：那个把条目变成 :class:`Intent`
    （坏的跳过），这个保留原样 —— UI 要在不改坏条目的前提下改其中一行。
    """
    p = Path(path).expanduser() if path is not None else intent_file_path()
    doc = _read_doc(p)
    if doc is None:
        return []
    rows = doc if isinstance(doc, list) else (doc.get("intents") or [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def save_intents(rows, path=None) -> Path:
    """整份写回。**原子替换**：先写同目录临时文件再 ``os.replace``，
    避免写一半崩掉把清单变成空文件 —— 那等于把所有「想买」一次性抹掉。

    :param rows: 原始条目列表。顶层原本是 ``{"intents": [...]}`` 的会保持原形状。
    """
    p = Path(path).expanduser() if path is not None else intent_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = _read_doc(p)
    body = list(rows)
    payload: Any = body
    if isinstance(doc, dict):
        payload = dict(doc)
        payload["intents"] = body
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, p)
    log.info("[IntentRunner] 意向清单已写回 %s（%d 条）", p, len(body))
    return p


def _row_key(row: Mapping[str, Any]) -> Tuple[str, str, str]:
    return (
        str(row.get("code") or "").strip().upper(),
        str(row.get("market") or "").strip().upper(),
        str(row.get("side") or "buy").strip().lower(),
    )


def intent_row_of(intent: Intent) -> Dict[str, Any]:
    """把意向变回清单里的一行。**只写 load_intents 认得的键**，
    免得存进一堆下次读不懂的字段（幽灵配置的标准长法）。"""
    row: Dict[str, Any] = {
        "code": intent.code,
        "market": intent.market,
        "side": intent.side,
        "max_wait_seconds": float(intent.max_wait_seconds or 0.0),
        "min_action": intent.min_action,
        "reading_max_age": float(intent.reading_max_age),
    }
    if intent.name:
        row["name"] = intent.name
    if intent.budget is not None:
        row["budget"] = float(intent.budget)
    if intent.note:
        row["note"] = intent.note
    if intent.rationale:
        row["rationale"] = intent.rationale
    # ❗只有人手给过/改过的才写进文件：不然「系统默认 0.6」会被固化下来，
    # 以后调默认值时旧清单会反过来把默认值钉死。
    if intent.confidence_explicit:
        row["confidence"] = clamp_confidence(intent.confidence)
    return row


def upsert_intent(intent: Intent, path=None) -> str:
    """新增或更新一条，返回 ``"added"`` / ``"updated"``。

    ❗**先落盘再挂台**的顺序交给调用方；这里只管文件。
    认不出同款（code+market+side）就追加。
    """
    rows = read_intent_rows(path)
    key = _row_key(
        {"code": intent.code, "market": intent.market, "side": intent.side}
    )
    row = intent_row_of(intent)
    for i, old in enumerate(rows):
        if _row_key(old) == key:
            merged = dict(old)
            merged.update(row)
            rows[i] = merged
            save_intents(rows, path)
            return "updated"
    rows.append(row)
    save_intents(rows, path)
    return "added"


def remove_intent(code: str, market: str, side: str = "buy", path=None) -> bool:
    """从清单里删掉一条。找不到返回 ``False``（**不抛**）——
    「本来就没有」和「删失败」对 UI 来说是两件事，但都不是错误。"""
    rows = read_intent_rows(path)
    key = _row_key({"code": code, "market": market, "side": side})
    left = [r for r in rows if _row_key(r) != key]
    if len(left) == len(rows):
        return False
    save_intents(left, path)
    return True


class IntentRunner:
    """意向守望的常驻驱动。

    :param desk: 守望台桌面；不传就自己造一个（默认询问器）。
    :param asker: 决策执行器；默认用 :func:`decision_center_asker`。
    """

    ENV_ENABLED = "NAJA_INTENT_WATCH_ENABLED"
    ENV_POLL = "NAJA_INTENT_POLL_SECONDS"
    ENV_HEARTBEAT = "NAJA_INTENT_HEARTBEAT_SEC"
    #: 意愿强度的全局覆盖（与模块级 :data:`ENV_INTENT_CONFIDENCE` 同源）。
    ENV_INTENT_CONFIDENCE = ENV_INTENT_CONFIDENCE

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
