"""富途统一行情源 —— A 股 / 港股 / 美股三市场实时快照适配层。

为什么要有这个模块
------------------
做 T 引擎的行情原本走 :mod:`market_data_bus`（新浪）。实测下来它撑不住三市场，
两处都是**静默失效**——数据到了、链路绿着、结果却是空的：

* **港股 00700**：总线里**根本没有 hk 分支**。``_do_fetch_async`` 只有
  ``sh/sz``（A 股）与 ``gb_``（美股）两路，港股代码取回来永远是 ``{}``。
* **美股 QQQ**：新浪明明返回了实时价（``gb_qqq`` 743.10，与富途 743.095 一致，
  时间戳同为 03:22:24），但 ``_parse_response`` **只解析
  ``_get_us_stock_codes()`` 里的代码**（= BlockDictionary 活跃美股池，
  启动日志 ``美股Block=15``，全是股票，**ETF 不在池里**）→ 判空丢弃，
  只留一条 warning。同测 ``gb_spy`` 同样为空，``gb_nvda`` / ``gb_aapl`` 正常。

用户拍板（2026-10-14）：**统一走富途行情**。富途侧三市场都有实时快照
（实测 588200 / 00700 / QQQ 均能取到 ``last_price`` 与 ``prev_close_price``）。

它负责的事
----------
1. **代码换算**：裸码 / 无点前缀（``sh588200``）/ 带点（``US.QQQ``）统一归一，
   再拼成富途 ``MARKET.CODE``。换算不出来**返回错误而不是猜**。
2. **批量取快照**：一次 ``get_market_snapshot`` 取完，减少 OpenD 往返。
3. **把富途字段翻译成做 T 要的口径**：``current`` / ``prev_close`` /
   ``volume``（当日**累计**量，增量由调用方自己差分）/ ``high`` / ``low`` /
   ``lot_size`` / ``price_spread``。

刻意不做的事
------------
* **不做缓存**。行情的时效性是调用方（做 T 运行器）的职责：它已经有
  ``max_quote_age`` 与死水检测。这里再叠一层缓存只会让"过期"更难被发现。
* **不复用长连接**。``OpenQuoteContext`` 每次新建并关闭，与
  :meth:`execution.FutuSimBackend._query_security` 的既有写法保持一致
  （OpenD 对并发连接数有限制，长连接泄漏的代价远高于建连开销）。
* **不猜市场**。``market`` 传不进来且代码形态说不出话时，返回错误。
  「随便挑一个市场」在富途侧表现为 200 返回但字段缺失，看起来像"这票没数据"。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

#: 与 :mod:`execution` 保持一致，避免两处端口漂移
HOST = "127.0.0.1"
PORT = 11111


@dataclass
class FutuQuote:
    """一份富途快照，翻译成本项目做 T / 行情消费方的口径。"""

    code: str                  # 归一化裸码，如 "588200" / "00700" / "QQQ"
    market: str                # CN / HK / US
    futu_code: str = ""        # 实际查询用的富途代码，如 "SH.588200"
    name: str = ""
    current: float = 0.0
    prev_close: float = 0.0
    open_price: float = 0.0
    high: float = 0.0
    low: float = 0.0
    #: 当日**累计**成交量。VWAP 需要的是每根 bar 的**增量**，
    #: 差分由调用方负责（见 ``t_rotation_runner`` 的 ``_last_cum_vol``）。
    volume: float = 0.0
    turnover: float = 0.0
    lot_size: float = 0.0
    price_spread: float = 0.0
    update_time: str = ""
    ok: bool = False
    error: str = ""
    fetch_time: float = field(default_factory=time.time)

    @property
    def age(self) -> float:
        """取回后经过的秒数。供调用方判过期。"""
        return time.time() - self.fetch_time

    @property
    def amplitude_pct(self) -> float:
        """当日振幅（%）。做 T 的"死水"闸门要的就是它。"""
        if self.prev_close <= 0:
            return 0.0
        return (self.high - self.low) / self.prev_close * 100

    def to_dict(self) -> Dict[str, object]:
        return {
            "code": self.code,
            "market": self.market,
            "futu_code": self.futu_code,
            "name": self.name,
            "current": self.current,
            "prev_close": self.prev_close,
            "open_price": self.open_price,
            "high": self.high,
            "low": self.low,
            "volume": self.volume,
            "turnover": self.turnover,
            "lot_size": self.lot_size,
            "price_spread": self.price_spread,
            "update_time": self.update_time,
            "ok": self.ok,
            "error": self.error,
            "age": round(self.age, 1),
            "amplitude_pct": round(self.amplitude_pct, 3),
        }


def _f(value: object) -> float:
    """快照字段 → float。富途缺字段时给的是空串 / None，一律当 0。"""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def resolve(code: str, market: Optional[str] = None) -> Tuple[str, str, str]:
    """把请求代码解析成 ``(市场, 富途代码, 裸码)``。

    Returns:
        失败时市场为空串、富途代码为空串，第三个值是**失败原因** ——
        调用方必须据此跳过，不能拿空串当"随便哪个市场"。
    """
    from .execution import futu_code as _futu_code
    from .execution import infer_market

    mkt = str(market or "").strip().upper()
    if not mkt:
        mkt, note = infer_market(code)
        if not mkt:
            return "", "", note

    full = _futu_code(mkt, code)
    if not full:
        return "", "", f"{code} 换算不出富途代码（市场 {mkt}）"

    bare = full.partition(".")[2]
    return mkt, full, bare


class FutuQuoteSource:
    """富途行情源。线程安全：每次调用独立建连。"""

    def __init__(self, host: str = HOST, port: int = PORT):
        self._host = host
        self._port = port

    # ------------------------------------------------------------------
    # 取数
    # ------------------------------------------------------------------
    def fetch(
        self, requests: Sequence[Tuple[str, Optional[str]]],
    ) -> Dict[str, FutuQuote]:
        """批量取快照。

        Args:
            requests: ``(代码, 市场)`` 序列；市场传 ``None`` 时按代码形态推断。

        Returns:
            **原始代码 → FutuQuote**。失败的条目也在里面，但 ``ok=False``
            并带 ``error`` —— 失踪的标的比错误的标的好排查得多。
        """
        out: Dict[str, FutuQuote] = {}
        resolved: Dict[str, Tuple[str, str, str]] = {}

        for code, market in requests:
            key = str(code)
            mkt, full, third = resolve(key, market)
            if not mkt:
                out[key] = FutuQuote(
                    code=key, market="", ok=False, error=third,
                )
                log.warning("[FutuQuote] %s 无法定位市场: %s", key, third)
                continue
            resolved[key] = (mkt, full, third)

        if not resolved:
            return out

        # 同一裸码可能以不同写法出现（"sh588200" 与 "588200"），按富途代码去重
        by_full: Dict[str, List[str]] = {}
        for key, (_, full, _) in resolved.items():
            by_full.setdefault(full, []).append(key)

        try:
            from futu import OpenQuoteContext, RET_OK

            ctx = OpenQuoteContext(host=self._host, port=self._port)
            try:
                ret, data = ctx.get_market_snapshot(list(by_full.keys()))
            finally:
                ctx.close()
        except Exception as e:  # pragma: no cover - OpenD 不可用
            why = f"连接富途行情失败: {e}"
            log.error("[FutuQuote] %s", why)
            for key, (mkt, full, bare) in resolved.items():
                out[key] = FutuQuote(
                    code=bare, market=mkt, futu_code=full, ok=False, error=why,
                )
            return out

        if ret != RET_OK or data is None or len(data) == 0:
            why = f"get_market_snapshot 失败: {str(data)[:160]}"
            log.warning("[FutuQuote] %s", why)
            for key, (mkt, full, bare) in resolved.items():
                out[key] = FutuQuote(
                    code=bare, market=mkt, futu_code=full, ok=False, error=why,
                )
            return out

        rows = {}
        for _, row in data.iterrows():
            rows[str(row.get("code", ""))] = row

        for full, keys in by_full.items():
            row = rows.get(full)
            for key in keys:
                mkt, _, bare = resolved[key]
                if row is None:
                    out[key] = FutuQuote(
                        code=bare, market=mkt, futu_code=full, ok=False,
                        error=f"快照中缺少 {full}（代码是否存在？）",
                    )
                    log.warning("[FutuQuote] %s 未出现在快照结果中", full)
                    continue
                out[key] = self._to_quote(row, bare, mkt, full)

        return out

    def get(self, code: str, market: Optional[str] = None) -> Optional[FutuQuote]:
        """取单个标的。取不到（连不上 / 无此标的）返回 ``None``。"""
        return self.fetch([(code, market)]).get(str(code))

    # ------------------------------------------------------------------
    # 翻译
    # ------------------------------------------------------------------
    @staticmethod
    def _to_quote(row, bare: str, market: str, full: str) -> FutuQuote:
        current = _f(row.get("last_price"))
        prev_close = _f(row.get("prev_close_price"))

        q = FutuQuote(
            code=bare,
            market=market,
            futu_code=full,
            name=str(row.get("name", "") or ""),
            current=current,
            prev_close=prev_close,
            open_price=_f(row.get("open_price")),
            high=_f(row.get("high_price")),
            low=_f(row.get("low_price")),
            volume=_f(row.get("volume")),
            turnover=_f(row.get("turnover")),
            lot_size=_f(row.get("lot_size")),
            price_spread=_f(row.get("price_spread")),
            update_time=str(row.get("update_time", "") or ""),
        )

        # ❗缺"昨收"比缺"现价"更致命：做 T 所有百分比都以昨收为锚，
        # 没有基准时判据会退化成瞎猜。这里直接判失败，交给调用方跳过。
        if current <= 0:
            q.error = f"{full} 无有效最新价（停牌或代码不存在）"
            log.warning("[FutuQuote] %s", q.error)
            return q
        if prev_close <= 0:
            q.error = f"{full} 无有效昨收，百分比基准缺失"
            log.warning("[FutuQuote] %s", q.error)
            return q

        q.ok = True
        return q


def get_futu_quote_source() -> FutuQuoteSource:
    """进程内共享实例。"""
    global _SOURCE
    if _SOURCE is None:
        _SOURCE = FutuQuoteSource()
    return _SOURCE


_SOURCE: Optional[FutuQuoteSource] = None


__all__ = [
    "FutuQuote",
    "FutuQuoteSource",
    "get_futu_quote_source",
    "resolve",
]
