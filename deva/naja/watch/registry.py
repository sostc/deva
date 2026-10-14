"""守望台（WatchRegistry）—— 所有守望的登记表与扫描器。

它不做的事
==========
❗**不写任何生产数据**：不落盘、不碰账本、不改 ``CorePositionLedger``。
守望是纯粹的**运行期视图** —— 这既是为了避免 `DictionaryMetadata`
那类「构造即落盘」的事故，也是因为它的价值就是在进程内存里回答
「我现在在等什么」。重启后重新 declare 即可，不需要持久化。

❗**不下单**：只有 :meth:`scan` 会告诉你「该去问一次了」，去不去、批不批准，
都在决策中心。

自证心跳
========
做 T 那条线踩过一次：**会自动交易的后台任务必须周期性自报**，否则分不清
「在跑但没机会」和「线程已经死了」。守望台沿用同一套：默认 600 秒必报一次，
且带上每个守望的「在等什么 / 等多久了 / 最近判据」。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .objective import Objective, WatchContext
from .opportunity import Opportunity, build_opportunity
from .watch import Settlement, Watch, WatchScan, WatchState

log = logging.getLogger(__name__)

__all__ = ["WatchRegistry"]

_HEARTBEAT_ENV = "NAJA_WATCH_HEARTBEAT_SEC"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def allow_opportunities(specs: Sequence[Any]) -> List[Opportunity]:
    """把「声明式配置 / callable / Opportunity 实例」的混合列表统一成判据。"""
    return [build_opportunity(s) for s in specs]


class WatchRegistry:
    """守望台。

    :param heartbeat_sec: 自证心跳间隔，默认 600 秒（对齐做 T 的做法）。
        设为 0 表示不自动心跳。
    """

    def __init__(self, *, heartbeat_sec: Optional[float] = None) -> None:
        self._watches: Dict[str, Watch] = {}
        self._beat_sec = (
            _env_float(_HEARTBEAT_ENV, 600.0)
            if heartbeat_sec is None
            else float(heartbeat_sec)
        )
        self._last_beat: Optional[float] = None
        self._beats: int = 0

    # ------------------------------------------------------------------
    # 登记
    # ------------------------------------------------------------------
    def declare(
        self,
        objective: Objective,
        opportunities: Sequence[Any],
        *,
        mode: str = "any",
        max_wait_seconds: Optional[float] = None,
        max_silence_seconds: Optional[float] = None,
        bootstrap: bool = False,
        recurring: bool = False,
        standing: bool = False,
        now: Optional[float] = None,
    ) -> Watch:
        """挂一个守望上去。同 id 会覆盖（视为重新瞄准）。

        :param recurring: 循环守望。**到期**结算成 ``reviewed`` 之后由
            :meth:`renew` 自动挂上下一期（长期配置意图专用）。
        :param standing: 常驻守望。**抓到机会并问过一次**就结算成
            ``reached``，随后立刻重挂继续等下一次（做 T 专用）。
            ❗与 ``recurring`` 互斥 —— 一个按时间续、一个按机会续。
        """
        watch = Watch(
            objective=objective,
            opportunities=allow_opportunities(opportunities),
            mode=mode,
            armed_at=now if now is not None else time.time(),
            max_wait_seconds=max_wait_seconds,
            max_silence_seconds=max_silence_seconds,
            bootstrap=bootstrap,
            recurring=recurring,
            standing=standing,
        )
        self._watches[watch.watch_id] = watch
        log.info(
            "[WatchRegistry] 挂上守望 %s（%s）等待 ≡ %s，结算点 %.0fs 后",
            watch.watch_id, objective.describe(), watch.waiting_for(),
            float(watch.max_wait_seconds or 0.0),
        )
        return watch

    def get(self, watch_id: str) -> Optional[Watch]:
        return self._watches.get(watch_id)

    def remove(self, watch_id: str, reason: str = "") -> Optional[Watch]:
        watch = self._watches.pop(watch_id, None)
        if watch is not None:
            watch.settle(Settlement.ABANDONED, reason or "被移除")
        return watch

    def clear(self) -> None:
        self._watches.clear()

    def watches(self) -> List[Watch]:
        return list(self._watches.values())

    def __len__(self) -> int:
        return len(self._watches)

    def __contains__(self, watch_id: object) -> bool:
        return watch_id in self._watches

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def scan(
        self,
        contexts: Mapping[str, WatchContext],
        now: Optional[float] = None,
    ) -> List[WatchScan]:
        """扫所有未结算的守望。

        :param contexts: ``watch_id -> WatchContext``。
            ❗**查不到观测面的守望传进去的是 ``None``**，那会记成 unknown
            而不是「没机会」—— 一次行情取数失败不能伪装成策略在观望。
        """
        t = now if now is not None else time.time()
        out: List[WatchScan] = []
        for watch in self._watches.values():
            out.append(watch.scan(contexts.get(watch.watch_id), now=t))
        del t
        return out

    def due(
        self,
        now: Optional[float] = None,
        *,
        settle: bool = False,
    ) -> List[Watch]:
        """找出已经过了结算点却还没结算的守望。

        :param settle: True 时顺手结算它们。
            ❗过期必须**显式记录** —— 无声消失和从没遇到过机会是两种完全不同的事。

        ❗循环守望**不能结算成 expired**：到期对它而言不是「没等到」，
        而是「这一期看过了」（``reviewed``）。若一律判成 expired，
        长期持仓在每一期结束时都会假装自己失败一次 ——
        页面上看到的将是连续的红字，而实际上一切正常。
        """
        t = now if now is not None else time.time()
        out = [w for w in self._watches.values() if w.is_overdue(t)]
        if settle:
            for w in out:
                if w.recurring:
                    w.settle(
                        Settlement.REVIEWED,
                        f"第 {w.cycles + 1} 期结束：扫 {w.scans} 次 / "
                        f"问过 {w.asked} 次（放行 {w.granted_count} · "
                        f"未批准 {w.denied_count} · 没人问 "
                        f"{w.unanswered_count}）",
                        now=t,
                    )
                    log.info(
                        "[WatchRegistry] 循环守望 %s 第 %d 期结束：%s",
                        w.watch_id, w.cycles + 1, w.settlement_reason,
                    )
                elif w.standing:
                    # ❗常驻守望到期是「这期没轮到我」，不是失败 ——
                    # 它马上会被 renew 重新挂起，继续等下一次机会。
                    w.settle(
                        Settlement.EXPIRED,
                        f"第 {w.cycles + 1} 期结束：这期没等到机会"
                        f"（扫 {w.scans} 次 / 问过 {w.asked} 次）",
                        now=t,
                    )
                    log.info(
                        "[WatchRegistry] 常驻守望 %s 第 %d 期结束（没等到机会）",
                        w.watch_id, w.cycles + 1,
                    )
                else:
                    w.settle(
                        Settlement.EXPIRED,
                        f"等 {w.age(t) / 60:.0f} 分钟未成交，到期结算",
                        now=t,
                    )
                    log.info(
                        "[WatchRegistry] 守望过期结算 %s：%s",
                        w.watch_id, w.settlement_reason,
                    )
        return out

    def renew(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """把已结算的**循环 / 常驻**守望挂上下一期。

        ❗与 :meth:`due` 的分工：``due`` 负责判定「这一期结束了」，
        本方法负责决定「还要继续」。拆成两步才能表达「最后一期」——
        合成一步的话，撤下（``remove`` → ``abandoned``）就没法区分了：
        看起来都像「到期」，但一个是继续、一个是终止。

        ★两类守望的续期条件**不一样**，别合并成一个判断：

        * ``recurring``（长期配置自己）：只有 ``reviewed`` 才续。
          它是「到点回头看一眼」，所以**只有到期才产生新一期**；
          中途撤下（abandoned）就停在那里。
        * ``standing``（做 T）：``abandoned`` 之外**全都续**。
          它是「一直在等下一次机会」，所以不管是抓到了（reached）
          还是这期没轮到（expired），都要立刻重新挂起来继续等。
          ❗把两类合并成「非 abandoned 就续」会让长期配置在**被撤下的
          当月**就复活；合并成「只续 reviewed」会让做 T 抓到一次机会后
          就再也不等了 —— 两个方向都是错的。

        :return: 本期归档列表（每个元素是一期的统计快照）
        """
        t = now if now is not None else time.time()
        out: List[Dict[str, Any]] = []
        for w in self._watches.values():
            if w.state != WatchState.SETTLED:
                continue
            if w.standing:
                if w.settlement == Settlement.ABANDONED:
                    # 撤下是真终止 —— 常驻守望也必须能被真正停掉
                    continue
                out.append(w.arm(t, reason="常驻续期（继续等下一次机会）"))
                log.info(
                    "[WatchRegistry] 常驻守望 %s 已重挂第 %d 期（上期 %s）",
                    w.watch_id, w.cycles, w.settlement.value if w.settlement else "",
                )
            elif w.recurring:
                if w.settlement != Settlement.REVIEWED:
                    # 被人工撤下（abandoned）或其他终态 —— 不续期，停在这里
                    continue
                out.append(w.arm(t, reason="周期性续期"))
        return out

    def pending_asks(self, scans: Sequence[WatchScan]) -> List[WatchScan]:
        """从扫描结果里挑出「值得去问一次」的那些。"""
        return [s for s in scans if s.should_ask]

    # ------------------------------------------------------------------
    # 可观测
    # ------------------------------------------------------------------
    def snapshot(self, now: Optional[float] = None) -> Dict[str, Any]:
        """给 UI / 心跳的快照。两份数据都用 :meth:`Watch.to_row` 产出，避免口径分裂。"""
        t = now if now is not None else time.time()
        rows = [w.to_row(t) for w in self._watches.values()]
        return {
            "now": t,
            "total": len(rows),
            "armed": sum(1 for r in rows if r["state"] == WatchState.ARMED.value),
            "triggered": sum(
                1 for r in rows if r["state"] == WatchState.TRIGGERED.value
            ),
            "settled": sum(1 for r in rows if r["state"] == WatchState.SETTLED.value),
            "unknown": sum(1 for r in rows if r["unknown_scans"] > 0),
            "watches": rows,
        }

    def heartbeat(
        self,
        now: Optional[float] = None,
        *,
        force: bool = False,
    ) -> Optional[str]:
        """周期性自报。到点返回一行文本并打 INFO；没到点返回 ``None``。

        ❗第一次调用必报：否则在一个「守望从没机会」的日子里，日志会干净得
        跟线程死掉一模一样。
        """
        t = now if now is not None else time.time()
        if self._beat_sec <= 0 and not force:
            return None
        if (
            not force
            and self._last_beat is not None
            and (t - self._last_beat) < self._beat_sec
        ):
            return None

        self._last_beat = t
        self._beats += 1
        snap = self.snapshot(t)
        lines = [
            f"💓 守望台 共 {snap['total']} 个："
            f"{snap['armed']} 在等 / {snap['triggered']} 待问 / "
            f"{snap['settled']} 已结算 / {snap['unknown']} 曾有判据看不清"
        ]
        for row in snap["watches"]:
            if row["state"] == WatchState.SETTLED.value:
                continue
            lines.append(
                f"   · {row['id']}（{row['note']}）等={row['waiting_for']} "
                f"已等 {row['age_sec'] / 60:.0f}min 剩 {row['remaining_sec'] / 60:.0f}min "
                f"最近={row['last_reason'] or '（尚未有判据）'}"
            )
        text = "\n".join(lines)
        log.info("[WatchRegistry] %s", text)
        return text

    # ------------------------------------------------------------------
    # 便捷构造：给「只有一个观测源」的调用方省一层
    # ------------------------------------------------------------------
    def scan_one(
        self,
        watch_id: str,
        ctx: Optional[WatchContext],
        now: Optional[float] = None,
    ) -> Optional[WatchScan]:
        watch = self._watches.get(watch_id)
        return None if watch is None else watch.scan(ctx, now=now)

    def context_builder(
        self,
        fn: Callable[[Watch], Optional[WatchContext]],
    ) -> Callable[[Optional[float]], List[WatchScan]]:
        """把「按守望造观测面」的函数包成一次完整扫描。

        ``fn`` 返回 ``None`` 表示该守望本轮没拿到观测 → 记 unknown。
        """

        def _run(now: Optional[float] = None) -> List[WatchScan]:
            t = now if now is not None else time.time()
            return [w.scan(fn(w), now=t) for w in self._watches.values()]

        return _run
