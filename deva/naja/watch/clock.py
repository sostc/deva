"""守望用的**市场时钟**：闭市时时钟停走。

为什么守望不能直接用墙上时钟
----------------------------
守望的窗口（一期多久、沉默多久催醒一次）量的是「等多久才算白等」，而这个
问题的答案**只在开盘时才有意义**：

* 做 T 守望一期 30 分钟。若半夜 02:00 挂上，墙上时钟到 02:30 就到期了 ——
  那半小时里市场根本没开，「这期没轮到我」是一次**纯属记账的白记**。
  更糟的是开盘那一刻它正好在冷却或刚过期，最该被问到的开盘波动反而漏了。
* 收盘到次日开盘之间那 18 小时，守望什么都没等到，却照样走完 N 期。

所以守望的时间一律按**所属市场的在场时间**计：闭市、午休、周末时钟停走。
「一期 30 分钟」= 30 分钟真的能交易的时间。

❗认不出市场的处理
------------------
``MarketClock`` 所有查询都可能返回 ``None``，语义是**这个市场我不认识**，
❗不是「它现在关着」。两者的后果完全相反：

* 关着 → 这一轮不问（省一次基于停摆价格的假问询）
* 不认识 → **退回墙上时钟、照常问**

把「不认识」当成「关着」，一个 market 字段拼错的守望会**永远安静**——
这正是本仓库最痛的那种失效：不报错，只是再也没人问它。

刻意不做的事
------------
* 不做节假日日历（与 :mod:`~deva.naja.bandit.market_session` 一致）：假日会
  按正常开盘时刻醒来一次，由上游的死水检测拦下，比维护会过期的日历可靠。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable, Optional, Tuple

log = logging.getLogger(__name__)


def _as_dt(ts: Optional[float]) -> datetime:
    return datetime.fromtimestamp(ts) if ts is not None else datetime.now()


class MarketClock:
    """守望的市场时钟。纯函数薄封装，不持有任何状态、不碰单例。

    :param session: 时段模块，默认 ``deva.naja.bandit.market_session``。
        注入口是为了让守卫与用例能塞一个假时钟进去。
    :param warmup_seconds: 开盘后这么久之内**先不问**。刚开盘的价是跳的、
        昨收基准也可能没刷新，拿它判「涨过头」容易误报。默认 0 = 不暖机。
    """

    def __init__(
        self,
        session: Optional[Any] = None,
        warmup_seconds: float = 0.0,
    ) -> None:
        self._ms = session
        self.warmup_seconds = max(0.0, float(warmup_seconds))

    # ------------------------------------------------------------------
    @property
    def ms(self) -> Any:
        """时段模块（懒加载，避免 import 期就把 bandit 拉起来）。"""
        if self._ms is None:
            from ..bandit import market_session  # type: ignore

            self._ms = market_session
        return self._ms

    def known(self, market: str) -> bool:
        """这个市场我认识吗。不认识一律按「用墙上时钟、照常问」处理。"""
        try:
            return str(market or "").strip().upper() in self.ms.MARKET_SESSIONS
        except Exception:  # noqa: BLE001 - 时段模块坏了就当不认识
            return False

    def is_open(self, market: str, now: Optional[float] = None) -> Optional[bool]:
        """盘中？``None`` = 不认识这个市场（❗不是关着）。"""
        if not self.known(market):
            return None
        try:
            return bool(self.ms.is_trading(market, _as_dt(now)))
        except Exception as e:  # noqa: BLE001
            log.warning("[MarketClock] 判 %s 是否在盘失败: %s", market, e)
            return None

    def seconds_to_open(
        self, market: str, now: Optional[float] = None
    ) -> Optional[float]:
        """距下一次开盘秒数。**盘中 = 0**；不认识市场 = ``None``。"""
        if not self.known(market):
            return None
        try:
            return self.ms.seconds_to_open(market, _as_dt(now))
        except Exception as e:  # noqa: BLE001
            log.warning("[MarketClock] 算 %s 距开盘失败: %s", market, e)
            return None

    def elapsed(self, market: str, t0: float, t1: float) -> float:
        """``[t0, t1]`` 之间该市场在场了多少秒。不认识市场 → 墙上差。"""
        try:
            got = self.ms.market_elapsed_seconds(market, t0, t1)
        except Exception as e:  # noqa: BLE001
            log.warning("[MarketClock] 算 %s 在场时长失败: %s", market, e)
            return max(0.0, float(t1) - float(t0))
        return float(got) if got is not None else max(0.0, float(t1) - float(t0))

    def wall_at(self, market: str, t0: float, seconds: float) -> float:
        """从 ``t0`` 起、在场满 ``seconds`` 秒后的墙上时刻。

        不认识市场 → ``t0 + seconds``（退回墙上时钟）。
        """
        try:
            got = self.ms.market_wall_at(market, t0, seconds)
        except Exception as e:  # noqa: BLE001
            log.warning("[MarketClock] 算 %s 到期时刻失败: %s", market, e)
            return float(t0) + float(seconds)
        if got is None:
            return float(t0) + float(seconds)
        return float(got)

    # ------------------------------------------------------------------
    def ask_ready(
        self, market: str, now: Optional[float] = None
    ) -> Tuple[bool, str]:
        """这一刻**值不值得问**决策中心。

        :returns: ``(可以问吗, 为什么)``。❗不认识市场一律**可以问** ——
            那是个配置问题，不是休市，把配置问题伪装成休市会让它永远安静。
        """
        if not self.known(market):
            return True, ""
        t = now if now is not None else datetime.now().timestamp()
        open_state = self.is_open(market, t)
        if open_state is None:
            return True, ""
        if not open_state:
            left = self.seconds_to_open(market, t)
            return False, f"{market} 已收盘" + (
                f"，距开盘 {_human(left)}" if left else ""
            )
        if self.warmup_seconds > 0:
            # 开盘至今过了多久（用「在场」算，午休不算数）
            try:
                opening = self.ms.next_open_ts(market, _as_dt(t))
            except Exception:  # noqa: BLE001
                opening = None
            if opening is not None and (t - opening) < self.warmup_seconds:
                return False, f"{market} 刚开盘，暖机中"
        return True, ""

    def next_wake_seconds(
        self,
        markets: Iterable[str],
        now: Optional[float] = None,
        cap: Optional[float] = None,
    ) -> Optional[float]:
        """这批市场**下一次值得醒来**是多久以后（秒）。

        * 任一市场正盘中 → ``0``（现在就该醒）
        * 全部休市 → 最近那个开盘的秒数
        * 全都不认识 → ``None``（调用方按自己的固定节拍走）

        :param cap: 上限。❗调用方**必须**传一个不超过心跳间隔的上限 ——
            睡到开盘可能一睡十几个小时，而**长时间不吭声与线程死了在日志上
            长得一模一样**。分片长睡是活性的硬要求，不是优化。
        """
        t = now if now is not None else datetime.now().timestamp()
        best: Optional[float] = None
        for m in markets:
            left = self.seconds_to_open(m, t)
            if left is None:
                continue
            if left <= 0:
                best = 0.0
                break
            best = left if best is None else min(best, left)
        if best is None:
            return None
        if cap is not None:
            best = min(best, float(cap))
        return max(0.0, best)


def _human(seconds: Optional[float]) -> str:
    """把秒数说成人话。``None`` 说「未知」而不是省略 —— 省掉的那个词
    正好是「算不出来」与「马上开盘」的区别。"""
    if seconds is None:
        return "未知"
    s = max(0.0, float(seconds))
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        return f"{s / 60:.0f}min"
    h, m = divmod(int(s) // 60, 60)
    return f"{h}h{m:02d}min"


__all__ = ["MarketClock"]
