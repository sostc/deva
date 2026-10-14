"""Manas 读数透镜 —— 机会的**发源地**。

用户的一段话（2026-10-14）
=========================

    「我想买入英伟达，但可能现在价格高或者怎么样，我决定不了什么时候买入，
     但是呢我确实是想买入 —— 这个时候这个想买入的想法应该进入守望台。
     然后呢等待一个机会来买入，那这个机会是怎么出现的呢？它因为我们现在
     系统是会去看新闻啊，看市场的行情的这个计算啊，就是有很多种数据，
     最后会汇聚到 Manas 决策中心这里来嘛，其实机会应该是在这里出现的。」

工程上，这句话落成三个决定。

决定一：机会的输入必须是 Manas 自己的输出，不是「结论的残渣」
------------------------------------------------------------
1 号守望（``core_establish_watch``）原先读的是
:meth:`CoreEstablishGate.last_action_type` —— 那是**上一次问过决策中心之后
缓存里剩下的东西**。于是「要不要问」依赖「问的结果」：想拿到档位就得先问，
不问就永远拿不到档位。这条循环只能靠 bootstrap（首次必问）加
``max_silence_seconds``（沉默多久强制再问）两道兜底焊住，否则就是
「闸门接好了，但从没放行过」那种死锁。

换成直接向 Manas 读数之后，这两道兜底从**必需品**降级为**保险**：
档位是主动读来的，不是省下来的。

决定二：读数必须廉价
--------------------
机会判定发生在轮询里（做 T 是 30 秒一轮），而
``TradingCenter.process_strategy_signal`` 会带着 FP 洞察、
:class:`DecisionPlan` 留痕一起跑 —— 那是**放行**要走的路，
不能拿来当**机会**的探针，守望要省的就是这条路。

Manas 自己的 ``compute()`` 带 1 秒缓存且只依赖 stdlib，所以本透镜默认
先读现成的输出（``get_state()["last_output"]``，几乎零开销），
**只有读数确实过期了**才按冷却节流地触发一次计算。

决定三：新鲜度必须自证 —— 没有时间戳的读数一律算「看不清」
----------------------------------------------------------
``ManasReading.stamped`` 为 False 时，:class:`ManasWindow` 会返回
``OpportunityHit.unclear``。这不是保守过头：拿一份**不知道什么时候算的**
档位当「现在有机会」，比干脆说不知道糟糕得多 ——
记忆里那条「假新鲜比异常更毒」说的就是这件事。

三态在这里的表现
================
:meth:`ManasLens.read` 返回 ``None`` 等于 **看不清**（没启用 / 算不出来 /
没时间戳 / 抛异常）。消费方（``ManasWindow``）必须把它翻译成
``unknown``，**绝不能当成「没机会」**。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Optional, Tuple

log = logging.getLogger(__name__)

__all__ = ["ManasReading", "ManasLens", "ACTION_LADDER"]

#: 行动档位，由弱到强。
#: 刻意写成裸字符串而不导入 Manas 的枚举：守望层不该因为上游换了个
#: 枚举实现就多背一个依赖，也不该在 Manas 不可用时连 import 都失败。
ACTION_LADDER = ("hold", "act_minimally", "act_carefully", "act_fully")

#: 读数 dict 里可能出现的时间戳键（按优先级）。
_TS_KEYS = ("timestamp", "taken_at", "computed_at", "time")


# ---------------------------------------------------------------- 读数


@dataclass(frozen=True)
class ManasReading:
    """一次 Manas 读数。**带得上时间戳才算数**。"""

    action_type: Optional[str]
    manas_score: Optional[float] = None
    regime_score: Optional[float] = None
    timing_score: Optional[float] = None
    #: Manas 自己的行动门叙述（为什么不让你动）
    gate_reason: str = ""
    #: 这份输出是在什么时候算出来的（epoch 秒）
    taken_at: float = 0.0
    #: True = 时间戳可信。False 时消费方必须按「看不清」处理
    stamped: bool = False
    #: 来源标记，写进日志便于事后追责（``state`` / ``compute`` / ``injected``）
    source: str = ""

    def age(self, now: float) -> float:
        return max(0.0, float(now) - float(self.taken_at))

    def ladder_index(self) -> Optional[int]:
        """在 :data:`ACTION_LADDER` 里的序号。认不出来返回 ``None``（不当 0 用）。"""
        if not self.action_type:
            return None
        try:
            return ACTION_LADDER.index(self.action_type)
        except ValueError:
            return None

    def describe(self) -> str:
        score = "--" if self.manas_score is None else f"{self.manas_score:.3f}"
        regime = "--" if self.regime_score is None else f"{self.regime_score:.3f}"
        return (
            f"档位={self.action_type or '--'} manas={score} regime={regime} "
            f"来源={self.source or '?'}"
        )


# ---------------------------------------------------------------- 透镜


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _norm_action(raw: Any) -> Optional[str]:
    """把各种形态的 ``action_type`` 归一化成小写裸名。

    三种都要认，因为这条链上至少见过这么多写法：

    * ``ActionType.HOLD``（枚举实例）→ 取 ``.value``
    * ``"hold"``                     → 原样
    * ``"ActionType.HOLD"``          → py3.11+ 的 ``str(Enum)`` 就是这个形态，
      必须剥掉类名前缀，否则整套判据恒为「认不出来的档位」。
    """
    if raw is None:
        return None
    val = raw.value if isinstance(raw, Enum) else raw
    text = str(val or "").strip()
    if not text:
        return None
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.lower() or None


def _num(raw: Mapping[str, Any], key: str) -> Optional[float]:
    """取值。``None`` 表示**上游没给**，不能用 0.0 顶替 ——
    那会把「Manas 没给分」伪装成「Manas 打了 0 分」。"""
    if key not in raw:
        return None
    try:
        return float(raw[key])
    except (TypeError, ValueError):
        return None


def _coerce_ts(raw: Any) -> Optional[float]:
    """把可能的时间戳转成 epoch 秒。毫秒戳（13 位）也认 ——
    认错了会让一份刚算出来的读数看上去是 1970 年算的。"""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val > 1e11:
        val /= 1000.0
    return val if val > 0 else None


class ManasLens:
    """向 Manas 要一份**廉价**读数。

    :param provider: 注入源（``() -> Optional[dict]``）。守卫与测试用它
        在没有 Manas 进程的环境里离线验证逻辑；不注入就走全局单例。
    :param max_age_seconds: 读数超过这么久就算过期，默认 600 秒。
    :param refresh_seconds: 主动重新计算的冷却时间，默认 60 秒 ——
        防止「轮询每 30 秒就拖着整个引擎跑一遍」。
    """

    ENV_MAX_AGE = "NAJA_WATCH_MANAS_MAX_AGE"
    ENV_REFRESH = "NAJA_WATCH_MANAS_REFRESH_SEC"

    DEFAULT_MAX_AGE = 600.0
    DEFAULT_REFRESH = 60.0
    #: 主动计算超过这个秒数就告警：它跑在轮询线程里。
    SLOW_REFRESH_SECONDS = 2.0

    def __init__(
        self,
        provider: Optional[Callable[[], Optional[Mapping[str, Any]]]] = None,
        *,
        max_age_seconds: Optional[float] = None,
        refresh_seconds: Optional[float] = None,
        allow_refresh: bool = True,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._provider = provider
        self._max_age = (
            _env_float(self.ENV_MAX_AGE, self.DEFAULT_MAX_AGE)
            if max_age_seconds is None
            else float(max_age_seconds)
        )
        self._refresh = (
            _env_float(self.ENV_REFRESH, self.DEFAULT_REFRESH)
            if refresh_seconds is None
            else float(refresh_seconds)
        )
        self._allow_refresh = bool(allow_refresh)
        self._clock: Callable[[], float] = clock or time.time
        # 轮询线程与手工调用会并发，read() 必须串行
        self._lock = threading.Lock()
        self._last_refresh_try = 0.0

        # -- 自证计数器（给心跳 / 排障看） ----------------------------
        self.reads = 0
        self.unknown_reads = 0
        self.refreshes = 0
        self.fail_streak = 0
        self.last_unknown_reason = ""

    # ----------------------------------------------------------------
    @property
    def max_age_seconds(self) -> float:
        return self._max_age

    def read(self, now: Optional[float] = None) -> Optional[ManasReading]:
        """取一份读数。返回 ``None`` 等于**看不清**（不是「没有机会」）。"""
        t = float(now if now is not None else self._clock())
        with self._lock:
            self.reads += 1
            try:
                raw, source = self._pull(t)
            except Exception as e:  # noqa: BLE001 - 上游挂了也要稳住轮询线程
                return self._unknown(f"读 Manas 时抛异常：{type(e).__name__}: {e}")
            if raw is None:
                return self._unknown("Manas 没有可用输出（未启用 / 还没算过）")

            reading, why = self._parse(raw, source)
            if reading is None:
                return self._unknown(why or "Manas 输出无法解析")
            self.fail_streak = 0
            return reading

    # ----------------------------------------------------------------
    def _unknown(self, reason: str) -> None:
        """记一次「看不清」。

        必须可见：连着看不清却不喊，跟「Manas 一直很安静」长得一模一样 ——
        这正是本仓库头号病理（静默失效家族）的标准形态。
        """
        self.unknown_reads += 1
        self.fail_streak += 1
        self.last_unknown_reason = reason
        if self.fail_streak == 1 or self.fail_streak % 10 == 0:
            log.warning(
                "[ManasLens] 连续第 %d 次拿不到可读的 Manas 读数：%s "
                "（机会判据按「看不清」处理，不会假装没机会）",
                self.fail_streak, reason,
            )

    def _manager(self) -> Any:
        """取全局 Manas 管理器。取不到返回 ``None``（看不清的合法来源之一）。"""
        try:
            from ..attention.kernel.manas_manager import get_manas_manager
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"ManasManager 不可导入: {e}") from e
        return get_manas_manager()

    def _pull(self, now: float) -> Tuple[Optional[Mapping[str, Any]], str]:
        """拿到原始输出 dict 与来源标记。"""
        if self._provider is not None:
            return self._provider(), "injected"

        manager = self._manager()
        if manager is None:
            return None, ""
        enabled = getattr(manager, "is_enabled", None)
        if callable(enabled) and not bool(enabled()):
            return None, "disabled"

        raw, taken = self._state_of(manager)
        if self._too_old(taken, now) and self._allow_refresh:
            self._maybe_refresh(manager, now)
            raw, taken = self._state_of(manager)
        if raw is None:
            return None, ""
        return self._with_ts(raw, taken), "state"

    def _state_of(
        self, manager: Any
    ) -> Tuple[Optional[Mapping[str, Any]], Optional[float]]:
        try:
            state = manager.get_state() or {}
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"get_state 失败: {e}") from e
        raw = state.get("last_output")
        # ManasManager.get_state() 不吐计算时刻，而**没有时刻的读数不能自称
        # 新鲜**（假新鲜比异常更毒），所以宁可读这个私有属性。
        taken = _coerce_ts(getattr(manager, "_last_compute_time", None))
        if not isinstance(raw, Mapping):
            return None, taken
        if taken is None:
            for key in _TS_KEYS:
                taken = _coerce_ts(raw.get(key))
                if taken is not None:
                    break
        return raw, taken

    def _too_old(self, taken: Optional[float], now: float) -> bool:
        if taken is None:
            return True
        return (now - taken) > self._max_age

    def _maybe_refresh(self, manager: Any, now: float) -> None:
        """按冷却主动算一次。既不唐突，也不会每轮都拖着引擎跑。"""
        if (now - self._last_refresh_try) < self._refresh:
            return
        self._last_refresh_try = now
        started = time.monotonic()
        try:
            manager.compute()
            self.refreshes += 1
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"compute 失败: {e}") from e
        finally:
            elapsed = time.monotonic() - started
            if elapsed > self.SLOW_REFRESH_SECONDS:
                log.warning(
                    "[ManasLens] 主动刷新 Manas 耗时 %.1fs，同步阻塞了轮询线程 —— "
                    "请调大 %s（当前 %.0fs）",
                    elapsed, self.ENV_REFRESH, self._refresh,
                )

    def _with_ts(
        self, raw: Mapping[str, Any], taken: Optional[float]
    ) -> Mapping[str, Any]:
        """把外部取到的时刻塞回 dict，交给统一的解析逻辑。"""
        if taken is None:
            return raw
        out = dict(raw)
        out.setdefault("__taken_at", float(taken))
        return out

    def _parse(
        self, raw: Mapping[str, Any], source: str
    ) -> Tuple[Optional[ManasReading], str]:
        action = _norm_action(raw.get("action_type"))
        if action is None:
            return None, "Manas 输出里没有 action_type（拿不到档位）"

        taken = _coerce_ts(raw.get("__taken_at"))
        if taken is None:
            for key in _TS_KEYS:
                taken = _coerce_ts(raw.get(key))
                if taken is not None:
                    break
        if taken is None:
            # 不知道这份输出是什么时候算的 —— 按看不清处理
            return None, "Manas 输出没有可信时刻（不敢冒充新鲜读数）"

        return (
            ManasReading(
                action_type=action,
                manas_score=_num(raw, "manas_score"),
                regime_score=_num(raw, "regime_score"),
                timing_score=_num(raw, "timing_score"),
                gate_reason=str(raw.get("action_gate_reason") or ""),
                taken_at=taken,
                stamped=True,
                source=source,
            ),
            "",
        )
