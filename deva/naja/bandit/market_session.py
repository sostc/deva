"""多市场交易时段 —— 纯函数，不依赖任何单例。

为什么自己写一份而不是复用 ``radar.trading_clock``
------------------------------------------------
那里是一个**带后台线程、会往总线发事件的有状态单例**，而且**没有港股**。
做 T 运行器跑在自己的轮询线程里，过 AppContainer 取单例既慢又可能拿不到
（``t_rotation_runner`` 的模块 docstring 里就写过这个理由）。
这里只需要「现在几点、是否盘中、距收盘多久」，纯函数最合适。

为什么用 zoneinfo 而不是写死时差
--------------------------------
美股开盘是**美东 09:30**，不是「北京时间 21:30」——夏令时（3 月第二个周日至
11 月第一个周日）会整整差一小时。写死 21:30 的话，半年里的
``minutes_to_close`` 会系统性偏差 60 分钟，而它直接决定
「收盘前多久强制买回」和「收盘前多久不新开倒 T」——偏 60 分钟就是
**该买回的时候没买回**，份额守恒在收盘那一刻被打破。

时区一律交给 zoneinfo，本地时间的时段表才是不变的那个东西。

刻意不做的事
------------
* **不做节假日日历**。与既有的 ``cn_phase`` 保持一致：假日的报价会以昨收价
  反复出现，由 ``t_rotation_runner`` 的死水检测（连续 N 次价量不动）拦下，
  比维护一份会过期的日历更可靠。
* **不做半日市 / 临时休市**。同上。
"""

from __future__ import annotations

import logging
from datetime import datetime, time as dtime, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

#: 向前找开盘/累计在场时间时最多翻多少天。
#: 正常一轮只翻 1~2 天；这个上限是防「市场永远不开放」时死循环。
MAX_DAYS = 400

PHASE_MORNING = "morning"
PHASE_AFTERNOON = "afternoon"
PHASE_LUNCH = "lunch"
PHASE_CLOSED = "closed"

#: 处于这些 phase 才算盘中（午休不算）
TRADING_PHASES = (PHASE_MORNING, PHASE_AFTERNOON)

#: 市场 → 时区。**美股必须按美东时间算，否则夏令时会差一小时。**
MARKET_TZ: dict = {
    "CN": "Asia/Shanghai",
    "HK": "Asia/Hong_Kong",
    "US": "America/New_York",
}

#: 市场 → 连续交易时段（**市场本地时间**的 ``(时, 分)``）。
#: 午休拆成两段，距收盘才不会把午休算成"还有时间"。
MARKET_SESSIONS: dict = {
    # A 股：9:30–11:30 / 13:00–15:00
    "CN": (((9, 30), (11, 30)), ((13, 0), (15, 0))),
    # 港股：9:30–12:00 / 13:00–16:00（2023 起收盘延到 16:00）
    "HK": (((9, 30), (12, 0)), ((13, 0), (16, 0))),
    # 美股：9:30–16:00（美东），中间不休息
    "US": (((9, 30), (16, 0)),),
}


def _tz(market: str) -> Optional[ZoneInfo]:
    name = MARKET_TZ.get(str(market or "").strip().upper())
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception as e:  # pragma: no cover - 缺 tzdata
        log.error("[MarketSession] 时区 %s 不可用: %s", name, e)
        return None


def market_local(market: str, dt: datetime) -> Optional[datetime]:
    """把任意时区的时刻换算成**市场本地时间**。换算不了返回 None。"""
    tz = _tz(market)
    if tz is None:
        return None
    if dt.tzinfo is None:
        # 朴素 datetime 按系统本地时区解释（运行器用的就是 fromtimestamp）
        dt = dt.astimezone()
    return dt.astimezone(tz)


def _minutes(clock: Tuple[int, int]) -> int:
    return clock[0] * 60 + clock[1]


def market_phase(market: str, dt: Optional[datetime] = None) -> str:
    """当前处于该市场的哪个时段。认不出市场一律按 ``closed``（保守）。"""
    now = market_local(market, dt or datetime.now())
    if now is None:
        return PHASE_CLOSED
    if now.weekday() >= 5:
        return PHASE_CLOSED

    minute = now.hour * 60 + now.minute
    segments = MARKET_SESSIONS.get(str(market or "").strip().upper())
    if not segments:
        return PHASE_CLOSED

    for i, (start, end) in enumerate(segments):
        s, e = _minutes(start), _minutes(end)
        if s <= minute < e:
            return PHASE_AFTERNOON if i > 0 else PHASE_MORNING

    # 不在任何一段里：可能是午休，也可能是还没开盘 / 已收盘
    first_start = _minutes(segments[0][0])
    last_end = _minutes(segments[-1][1])
    if first_start <= minute < last_end:
        return PHASE_LUNCH
    return PHASE_CLOSED


def is_trading(market: str, dt: Optional[datetime] = None) -> bool:
    return market_phase(market, dt) in TRADING_PHASES


def minutes_to_close(market: str, dt: Optional[datetime] = None) -> Optional[float]:
    """距**当日收盘**还有多少分钟（含午休那段时间）。

    非交易日 / 已收盘 / 认不出市场 → ``None``。调用方拿到 None 时的保守行为
    是「不新开倒 T」，这是刻意的：不知道还有多久，就不要开一腿可能买不回来的仓。
    """
    now = market_local(market, dt or datetime.now())
    if now is None or now.weekday() >= 5:
        return None

    minute = now.hour * 60 + now.minute + now.second / 60.0
    segments = MARKET_SESSIONS.get(str(market or "").strip().upper())
    if not segments:
        return None

    first_start = _minutes(segments[0][0])
    last_end = _minutes(segments[-1][1])
    # ❗未开盘时「距收盘」没有意义（返回 None 让调用方保守跳过），
    # 否则会拿到一个"还有 12 小时"的数字，把强平/强制买回的判断带偏。
    if minute >= last_end or minute < first_start:
        return None

    # 盘中：剩余 = 到本段结束 + 后面所有整段的时长
    for i, (start, end) in enumerate(segments):
        s, e = _minutes(start), _minutes(end)
        if s <= minute < e:
            rest = e - minute
            for j in range(i + 1, len(segments)):
                rest += _minutes(segments[j][1]) - _minutes(segments[j][0])
            return rest

    # 还没开盘或午休：到收盘的总时长
    return float(last_end - minute)


def session_open_dt(market: str, dt: Optional[datetime] = None) -> Optional[datetime]:
    """该市场**当日**开盘时刻（带时区）。用于 T+1 判断「哪些份额是昨天买的」。"""
    now = market_local(market, dt or datetime.now())
    if now is None:
        return None
    segments = MARKET_SESSIONS.get(str(market or "").strip().upper())
    if not segments:
        return None
    h, m = segments[0][0]
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def session_open_ts(market: str, dt: Optional[datetime] = None) -> float:
    """开盘时刻的 POSIX 时间戳。换不出来返回 0（调用方须判 0 而不是当今天用）。"""
    open_dt = session_open_dt(market, dt)
    return open_dt.timestamp() if open_dt is not None else 0.0


def session_date(market: str, dt: Optional[datetime] = None) -> str:
    """**该市场自己的**交易日（``YYYY-MM-DD``）。

    ❗不能用北京日期当美股的交易日：北京时间周三 03:35 属于**美东周二**那个
    交易日。混用的话，美股每天会在 04:00（北京）和 21:30（北京）各开一次会话，
    昨收基准被重置两次，日内序列直接废掉。
    """
    now = market_local(market, dt or datetime.now())
    if now is None:
        return ""
    return now.strftime("%Y-%m-%d")


def _key(market: str) -> str:
    return str(market or "").strip().upper()


def _day_start(market: str, ts: float) -> Optional[datetime]:
    """``ts`` 那天在该市场本地的 00:00。换不出来返回 None。"""
    loc = market_local(market, datetime.fromtimestamp(ts))
    if loc is None:
        return None
    return loc.replace(hour=0, minute=0, second=0, microsecond=0)


def _next_day(day: datetime) -> datetime:
    """次日本地 00:00。❗用 date 相加而不是 timedelta(days=1)：后者在夏令时
    切换日会整整差一小时，累计多天就会把开盘时刻算偏。"""
    return datetime.combine(
        day.date() + timedelta(days=1), dtime(0, 0), tzinfo=day.tzinfo
    )


def _day_segments(market: str, day: datetime) -> List[Tuple[float, float]]:
    """某一天（本地 00:00 的 datetime）所有交易段，换算成 epoch 秒区间。

    ❗周末返回空表。这条是实测抓出来的：漏了它的话「周六 10:00–10:30」
    会被算成**在场 30 分钟**，于是跨周末的窗口时钟白白走了半个钟头 ——
    而且不报错，只是守望的到期时刻悄悄提前。
    """
    if day.weekday() >= 5:
        return []
    segments = MARKET_SESSIONS.get(_key(market))
    if not segments:
        return []
    out: List[Tuple[float, float]] = []
    for (sh, sm), (eh, em) in segments:
        s = day.replace(hour=sh, minute=sm, second=0, microsecond=0)
        e = day.replace(hour=eh, minute=em, second=0, microsecond=0)
        out.append((s.timestamp(), e.timestamp()))
    return out


def market_elapsed_seconds(
    market: str, t0: float, t1: float
) -> Optional[float]:
    """``[t0, t1]`` 之间该市场**在场了多少秒**（闭市、午休、周末不算）。

    ❗认不出市场返回 ``None``，不是 0 —— 0 的真语义是「这一整段它都没开」，
    把它当成"认不出"会让守望的窗口在未知市场下一动不动地停住。
    调用方拿到 ``None`` 的保守行为是**退回墙上时钟**。
    """
    if t1 <= t0:
        return 0.0
    if _key(market) not in MARKET_SESSIONS:
        return None
    day = _day_start(market, t0)
    if day is None:
        return None

    total = 0.0
    for _ in range(MAX_DAYS):
        for s, e in _day_segments(market, day):
            a = max(s, float(t0))
            b = min(e, float(t1))
            if b > a:
                total += b - a
        if day.timestamp() > float(t1):
            break
        day = _next_day(day)
    return total


def market_wall_at(
    market: str, t0: float, seconds: float
) -> Optional[float]:
    """从 ``t0`` 起、该市场**在场满 ``seconds`` 秒**之后的墙上时刻。

    这是 :func:`market_elapsed_seconds` 的反函数，用来算「一期 30 分钟在场
    时间」到底落在哪个墙上时刻（可能跨夜、跨周末）。认不出市场返回 None。
    """
    left = float(seconds)
    if left <= 0:
        return float(t0)
    if _key(market) not in MARKET_SESSIONS:
        return None
    day = _day_start(market, t0)
    if day is None:
        return None

    for _ in range(MAX_DAYS):
        for s, e in _day_segments(market, day):
            a = max(s, float(t0))
            if e <= a:
                continue
            avail = e - a
            if avail >= left:
                return a + left
            left -= avail
        day = _next_day(day)
    # 翻了 MAX_DAYS 天还凑不够在场时间 —— 只可能是配置出了鬼。
    # ❗不静默返回 t0+seconds：那会把「算不出来」伪装成一个正常到期时刻。
    log.warning(
        "[MarketSession] %s 从 %s 起累计 %.0fs 在场时间算不出来",
        market, t0, seconds,
    )
    return None


def next_open_dt(market: str, dt: Optional[datetime] = None) -> Optional[datetime]:
    """该市场**下一次开盘**的时刻（带时区）。

    ❗**正在盘中就返回当前时刻** —— 调用方问的是「还要多久才能问」，
    盘中的答案是 0，而不是"等明天"。周末/休市会一直往后翻到下一个交易日。
    认不出市场返回 ``None``（不是 now —— 那会让它看起来永远开着）。
    """
    if _key(market) not in MARKET_SESSIONS:
        return None
    now = market_local(market, dt or datetime.now())
    if now is None:
        return None

    for _ in range(MAX_DAYS):
        if now.weekday() < 5:
            for (sh, sm), (eh, em) in MARKET_SESSIONS[_key(market)]:
                s = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
                e = now.replace(hour=eh, minute=em, second=0, microsecond=0)
                if s <= now < e:
                    return now
                if now < s:
                    return s
        now = _next_day(now)
    return None


def next_open_ts(market: str, dt: Optional[datetime] = None) -> Optional[float]:
    """下一次开盘的 POSIX 时间戳；认不出市场返回 ``None``。"""
    d = next_open_dt(market, dt)
    return d.timestamp() if d is not None else None


def seconds_to_open(
    market: str, dt: Optional[datetime] = None
) -> Optional[float]:
    """距下一次开盘还有多少秒。**盘中 = 0**。认不出市场返回 ``None``。"""
    ts = next_open_ts(market, dt)
    base = (dt or datetime.now()).timestamp()
    return max(0.0, ts - base) if ts is not None else None


__all__ = [
    "MARKET_SESSIONS",
    "MARKET_TZ",
    "MAX_DAYS",
    "TRADING_PHASES",
    "is_trading",
    "market_elapsed_seconds",
    "market_local",
    "market_phase",
    "market_wall_at",
    "minutes_to_close",
    "next_open_dt",
    "next_open_ts",
    "seconds_to_open",
    "session_date",
    "session_open_dt",
    "session_open_ts",
]
