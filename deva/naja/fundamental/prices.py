"""日线收盘价：统一走富途 OpenD。

为什么不用第三方 PE 接口
------------------------
现成的 PE/PB 历史接口很多（乐咕、雪球…），但口径不可控：有的用静态 PE，
有的用扣非，有的在送转后不复权。既然估值分位要用于**决策**，就必须能
回答「这条 PE 是用哪天的价格、哪期的 EPS、什么口径算出来的」。自己算
只有一个代价：多写几十行。

``autype=NONE`` 是关键：PE 用的是**当时的真实价格**，不能用前复权价。
前复权把历史价格按分红送转往下压，会让历史 PE 系统性偏低，分位整体失真。
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

import atexit

#: (futu_code, [(YYYY-MM-DD, close)])
PriceSeries = List[Tuple[str, float]]

_context = None
_context_lock = threading.Lock()
_last_error: Optional[str] = None


def to_futu_code(symbol: str) -> Optional[str]:
    """Naja 内部代码 → 富途代码。

    ``nvda`` → ``US.NVDA`` / ``000001`` → ``SZ.000001`` / ``588200`` → ``SH.588200``
    """
    s = str(symbol).strip()
    if not s:
        return None
    if "." in s and s.split(".")[0].upper() in ("US", "SH", "SZ", "HK"):
        return s.upper()
    if s[:1].isalpha():
        return f"US.{s.upper()}"
    code = s.lower().removeprefix("sh").removeprefix("sz")
    if not code.isdigit():
        return None
    # 6/9 开头、5 开头的场内基金 → 上交所；其余（0/1/2/3）→ 深交所
    if code[0] in ("6", "9", "5"):
        return f"SH.{code}"
    return f"SZ.{code}"


def _get_context():
    global _context, _last_error
    with _context_lock:
        if _context is not None:
            return _context
        try:
            import futu as ft

            _context = ft.OpenQuoteContext(host="127.0.0.1", port=11111)
            _last_error = None
        except Exception as e:  # pragma: no cover - 环境相关
            _last_error = f"{type(e).__name__}: {e}"
            log.warning("[Valuation] 连接富途 OpenD 失败: %s", e)
            _context = None
        return _context


def reset_context() -> None:
    """测试用：丢弃缓存的连接。"""
    global _context
    with _context_lock:
        try:
            if _context is not None:
                _context.close()
        except Exception:
            pass
        _context = None


@atexit.register
def _shutdown() -> None:
    """进程退出时关掉 OpenD 连接，否则解释器会卡在 socket 上（脚本表现为超时）。"""
    try:
        reset_context()
    except Exception:
        pass


def daily_closes(symbol: str, years: int = 5, today: Optional[date] = None) -> PriceSeries:
    """取日线收盘价（不复权）。失败返回空列表，**不抛异常**。"""
    code = to_futu_code(symbol)
    if not code:
        return []
    ctx = _get_context()
    if ctx is None:
        return []
    today = today or date.today()
    start = (today - timedelta(days=int(years * 365.25) + 10)).isoformat()
    try:
        import futu as ft

        ret, df, _key = ctx.request_history_kline(
            code,
            start=start,
            end=today.isoformat(),
            ktype=ft.KLType.K_DAY,
            autype=ft.AuType.NONE,
            max_count=max(300, int(years * 260)),
        )
    except Exception as e:
        log.warning("[Valuation] %s 日线拉取异常: %s", code, e)
        return []
    try:
        import futu as ft

        if ret != ft.RET_OK or df is None or len(df) == 0:
            log.debug("[Valuation] %s 日线为空: %s", code, df)
            return []
        out: PriceSeries = []
        for _, row in df.iterrows():
            ts = str(row["time_key"])[:10]
            try:
                out.append((ts, float(row["close"])))
            except (TypeError, ValueError):
                continue
        return out
    except Exception as e:  # pragma: no cover
        log.debug("[Valuation] %s 日线解析失败: %s", symbol, e)
        return []


def snapshot_shares(symbol: str) -> Optional[float]:
    """实时总股本（仅用于兜底，历史股本变化无法回溯）。"""
    ctx = _get_context()
    code = to_futu_code(symbol)
    if ctx is None or not code:
        return None
    try:
        ret, df = ctx.get_market_snapshot([code])
        if ret == 0 and len(df):
            shares = float(df.iloc[0].get("issued_shares") or 0)
            return shares or None
    except Exception:
        return None
    return None
