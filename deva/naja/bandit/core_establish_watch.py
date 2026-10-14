"""1 号守望：底仓补仓 —— 「什么时候才值得去问一次决策中心」。

它是 :mod:`.core_establish_gate` 的**上游**，不是替代品：

    轮询 ──▶ 守望（值不值得问？）──▶ 闸门（去问，拿到裁定）──▶ 缩量下单

为什么要有这一层
================
闸门上线后，每轮轮询都会完整问一次决策中心（TTL 内复用缓存）。这有两个代价：

1. 即便结论永远是 ``hold``，也总在跑管线、刷 ``DecisionPlan`` 日志；
2. **「在等」这件事没有被记录** —— 30 秒一次地问，日志看起来跟「随机拒绝」
   没有区别，事后无法回答「今天为什么没建成底仓」。

守望把「问」变成一件**有事才做**的事，并且把「我在等什么」写进状态里。

三个判据
========
``manas_window``（默认）
    **直接向 Manas 要一份读数**，行动门开到 ``act_minimally`` 以上才值得问。
    这是 2026-10-14 的一次修正：此前环境信号读的是
    :meth:`CoreEstablishGate.last_action_type`（问过之后的缓存残渣），
    于是「要不要问」依赖「问的结果」—— 只能靠 bootstrap 加沉默催醒
    两道兜底焊住，否则就是死锁。改成主动读数之后，那两道兜底从
    必需品降级成保险。实现见 :mod:`deva.naja.watch.manas_lens`。

``environment_upgrade``（旧行为，``NAJA_T_ESTABLISH_WATCH_SOURCE=cache``）
    读缓存里的档位，零开销，但只有问过才有值。

``deadline_window``
    距收盘不足 ``NAJA_T_ESTABLISH_DEADLINE_MIN`` 分钟 —— 与闸门里的收盘兜底
    是同一件事，只是提前由守望表达出来。

``liveness``（内建在 :class:`~deva.naja.watch.watch.Watch` 里）
    ❗这条必须有：环境判据依赖 ``action_type``，而 ``action_type`` 得**问过**
    决策中心才有。若首次碰上链路不通，``action_type`` 恒为未知 →
    环境机会永不成立 → 永远不问 → 「闸门接好了但从没放行」的死锁。
        守望层用「沉默超过 ``max_silence_seconds`` 就强制问一次」把这道门焊死 ——
    哪怕 Manas 读数一直看不清，守望也不会变成一具不会说话的尸体。

回滚
====
``NAJA_T_ESTABLISH_WATCH=0`` 回到「每轮都问」的旧行为。
``NAJA_T_ESTABLISH_WATCH_SOURCE=cache`` 把环境信号换回「读缓存残渣」的旧行为。
``CoreEstablishGate`` 自己的 ``NAJA_T_ESTABLISH_GATE=0`` 优先级更高 ——
闸门关了，守望也跟着让路（二者同时关等价于完全无闸门）。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from ..watch import (
    Objective,
    Watch,
    WatchContext,
    WatchRegistry,
    WatchScan,
    WatchState,
)
from .core_establish_gate import CoreEstablishGate
from .core_holdings import CoreHoldingSpec, env_flag

log = logging.getLogger(__name__)

__all__ = ["CoreEstablishWatch", "watch_id_for"]

#: 一个交易日内守望的最长寿命（收盘后重新 declare）。兜底用，正常情况下
#: 由结算点扫描先处理。
DEFAULT_MAX_WAIT_SECONDS = 4 * 3600.0

ENV_ENABLED = "NAJA_T_ESTABLISH_WATCH"
#: 环境机的信号源。
#: ``manas`` = 主动向 Manas 要一份读数（默认，见模块 docstring）；
#: ``cache`` = 读上一问决策心之后在存里的位（2026-10-14 之的行为）。
ENV_SOURCE = "NAJA_T_ESTABLISH_WATCH_SOURCE"
DEFAULT_SOURCE = "manas"


def watch_id_for(code: str) -> str:
    return f"core_establish:{code}"


class CoreEstablishWatch:
    """把「底仓补仓」这一种目标挂到守望台上。

    刻意做成**不直接下单**：它只回答「该不该去问」，真正去问的是
    :class:`~.core_establish_gate.CoreEstablishGate`。两者分开是为了让
    「机会」和「放行」永远不成一件事。
    """

    def __init__(
        self,
        gate: CoreEstablishGate,
        *,
        registry: Optional[WatchRegistry] = None,
        enabled: Optional[bool] = None,
        max_silence: Optional[float] = None,
        lens: Optional[Any] = None,
        source: Optional[str] = None,
    ) -> None:
        self.gate = gate
        self._lens = lens
        self._source = str(
            source or os.environ.get(ENV_SOURCE) or DEFAULT_SOURCE
        ).strip().lower()
        if self._source not in ("manas", "cache"):
            log.warning(
                "[CoreEstablishWatch] %s=%r 认不出来，回退为 %s",
                ENV_SOURCE, source, DEFAULT_SOURCE,
            )
            self._source = self.DEFAULT_SOURCE
        self.registry: WatchRegistry = registry or WatchRegistry()
        self._enabled = (
            env_flag(ENV_ENABLED, True) if enabled is None else bool(enabled)
        )
        self._max_silence = max_silence

    @property
    def enabled(self) -> bool:
        """闸门自身关了的话，守望也一并让路（避免逻辑分裂）。"""
        return self._enabled and bool(getattr(self.gate, "enabled", True))

    @property
    def source(self) -> str:
        return self._source

    @property
    def lens(self):
        """Manas 读数透镜。只有 manas 源才需要；拿不到返回 None 是合法的。"""
        if self._source != "manas":
            return None
        if self._lens is None:
            try:
                from ..watch.manas_lens import ManasLens

                self._lens = ManasLens()
            except Exception as e:  # noqa: BLE001 - 透镜不可用要留痕并降级
                log.error(
                    "[CoreEstablishWatch] Manas 透镜不可用，环境机会将一直判不了: %s",
                    e,
                )
                self._lens = False  # 记个位，免得每轮都重试同样一个失败
        return self._lens or None

    # ------------------------------------------------------------------
    def ensure(
        self,
        spec: CoreHoldingSpec,
        *,
        now: float,
        max_wait_seconds: Optional[float] = None,
    ) -> Optional[Watch]:
        """确保守望已经挂上。幂等：已经有活的就返回它。"""
        if not self.enabled:
            return None
        wid = watch_id_for(spec.code)
        alive = self.registry.get(wid)
        if alive is not None and alive.state != WatchState.SETTLED:
            return alive
        return self.registry.declare(
            Objective(
                id=wid,
                kind="establish_core",
                subject=spec.code,
                market=spec.market,
                max_wait_seconds=max_wait_seconds or DEFAULT_MAX_WAIT_SECONDS,
                note=f"{spec.name} 底仓补到 {spec.alloc_pct:.0f}%",
            ),
            self._opportunities(),
            now=now,
            max_silence_seconds=self._max_silence,
            # bootstrap：拿到第一份基线；
            # max_silence：Manas 读数一直看不清时不至于锁死。
            bootstrap=True,
        )

    def context_for(
        self,
        spec: CoreHoldingSpec,
        *,
        now: float,
        price: Optional[float],
        anchor: Optional[float],
        minutes_to_close: Optional[float],
        extras: Optional[Dict[str, Any]] = None,
    ) -> WatchContext:
        """造一个观测面。

        ``action_type`` 从闸门缓存里廉价（不跑管线）；
        Manas 读数由 :attr:`lens` 主动索取。两者来源不同，不要混为一谈。
        """
        probe = getattr(self.gate, "last_action_type", None)
        action_type = probe(spec.code) if callable(probe) else None
        payload: Dict[str, Any] = dict(extras or {})
        payload.setdefault("manas_reading", self._reading(now))
        return WatchContext(
            now=now,
            price=price,
            anchor=anchor,
            minutes_to_close=minutes_to_close,
            action_type=action_type,
            extras=payload,
        )

    def _opportunities(self) -> List[Dict[str, Any]]:
        """按信号源组装机会判据。

        两个环境判据不共存：``manas_window`` 主动读数，
        ``environment_upgrade`` 读缓存残。输入来源不同，
        放在一起会让「为什么触发」事后查不清。
        """
        deadline = {
            "kind": "deadline_window",
            "minutes": float(getattr(self.gate, "_deadline_min", 30.0)),
        }
        if self._source == "cache":
            return [
                {"kind": "environment_upgrade", "min_action": "act_minimally"},
                deadline,
            ]
        lens = self.lens
        max_age = float(getattr(lens, "max_age_seconds", 600.0) or 600.0)
        return [
            {
                "kind": "manas_window",
                "min_action": "act_minimally",
                "max_age_seconds": max_age,
            },
            deadline,
        ]

    def _reading(self, now: float) -> Optional[Any]:
        """取一份 Manas 读数。拿不到就返回 ``None``（看不清，不等于没机会）。"""
        lens = self.lens
        if lens is None:
            return None
        try:
            return lens.read(now=now)
        except Exception as e:  # noqa: BLE001
            log.warning("[CoreEstablishWatch] 读 Manas 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    def peek(
        self,
        spec: CoreHoldingSpec,
        ctx: WatchContext,
        *,
        now: Optional[float] = None,
    ) -> Tuple[bool, Optional[WatchScan]]:
        """这一步该不该去问决策中心？

        :return: ``(要不要问, 扫描明细)``
        """
        if not self.enabled:
            return True, None  # 守望关闭 → 维持「每轮都问」的旧行为
        watch = self.registry.get(watch_id_for(spec.code))
        if watch is None:
            # 守望开着却没挂上，是接线问题。宁可退回旧行为并记录，也不要
            # 用「永不询问」把底仓卡死 —— 那和线程死掉没法区分。
            log.warning(
                "[CoreEstablishWatch] %s 守望缺失，退回旧行为（每轮都问）",
                spec.code,
            )
            return True, None
        scan = watch.scan(ctx)
        return scan.should_ask, scan

    def mark_asked(self, spec: CoreHoldingSpec, granted: bool, reason: str,
                   *, now: Optional[float] = None) -> None:
        """把「问完了」回写给守望，让它回到等待状态。"""
        watch = self.registry.get(watch_id_for(spec.code))
        if watch is None:
            return
        watch.acknowledge(granted, reason, now=now)

    def settle(self, spec: CoreHoldingSpec, outcome: str, reason: str,
               *, now: Optional[float] = None) -> None:
        """目标达成 / 放弃时显式结算。"""
        watch = self.registry.get(watch_id_for(spec.code))
        if watch is None:
            return
        watch.settle(outcome, reason, now=now)

    # ------------------------------------------------------------------
    def snapshot(self, now: Optional[float] = None) -> Dict[str, Any]:
        return self.registry.snapshot(now)

    def heartbeat(self, now: Optional[float] = None, *,
                  force: bool = False) -> Optional[str]:
        return self.registry.heartbeat(now, force=force)
