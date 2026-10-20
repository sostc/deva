"""MarketDataBus - 行情数据服务总线

全局行情数据共享层，提供：
1. 统一行情缓存（内存 + NB持久化）
2. Single-flight 请求合并（避免同一时刻多次拉取相同股票）
3. TTL + Stale 策略（缓存优先，异步回源）
4. Stream Hub 多播（一次获取，多方消费）
5. 优先级调度（HOLDINGS > MEDIUM > LOW）

设计原则：
- Source Agnostic：不绑定任何特定数据源
- 实时交易优先，接受异步获取
- 一次获取，多方复用
- 统一 code 格式：外部接口统一带 sh/sz/gb_ 前缀，内部 normalize 存储

用法:
    bus = get_market_data_bus()

    # 获取价格（同步阻塞，最多等3秒）
    price = bus.get_price("nvda")

    # 获取价格（异步，缓存无数据立即返回0）
    price = bus.get_price_async("nvda")

    # 订阅价格变化
    bus.subscribe(["nvda", "aapl"], lambda code, price: print(f"{code}: {price}"))

    # 主动获取（触发回源）
    prices = bus.fetch(["nvda", "aapl"])

    # 注册高优先级（持仓股，TTL=5s）
    bus.register_priority_codes(["nvda", "aapl"], "HIGH")
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading

# ❗本总线自己就写明「不绑定任何特定数据源」，所以它**不在 DatasourceManager 的
# 注册体系内**，首页数据源卡原先永远看不到它。这里挂探针，让每一次真实回源
# 都自动上报成败 —— 首页「数据源」卡的口径来自 FleetRegistry，不靠人记得登记。
from deva.naja.infra.observability.fleet_registry import KIND_DATASOURCE, probe
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from deva import NB, NS

if TYPE_CHECKING:
    # 仅用于 `from_market_data(md: "MarketData")` 的注解；
    # 运行时不需要（该入口只读属性，不依赖类型本身）。
    from deva.naja.market_hotspot.data import MarketData

log = logging.getLogger(__name__)

MARKET_DATA_BUS_TABLE = "naja_market_data_bus"
MARKET_DATA_HUB_STREAM = "market_data_hub"
MARKET_QUOTE_VERSION = 1


def _normalize_code(code: str) -> str:
    """去掉 sh/sz/gb_ 前缀，用于内部存储和 API 查询

    A股格式: sh600519, sz000001 (无下划线)
    美股格式: gb_nvda, gb_aapl (有下划线)

    ⚠️ 统一转小写。本函数的返回值同时充当**缓存键**和**去重键**，而上游符号来源
    大小写不一（portfolio 传 ``NVDA``、有些地方传 ``gb_NVDA``）。此前不做大小写
    归一，导致 ``get_quote("NVDA")`` 永远查不到以 ``nvda`` 存储的缓存 —— 永久未命中，
    每次调用都回落新浪拉取，且拼出的 ``gb_NVDA`` 被新浪判为空，形成每分钟一轮的
    WARNING。A股代码是纯数字/带数字前缀，转小写无副作用。
    """
    c = code.strip()
    lower = c.lower()
    if lower.startswith("gb_"):
        return lower[3:]
    if lower.startswith(("sh", "sz", "bj")):
        return c[2:]
    return lower


def format_exchange_code(code: str) -> str:
    """还原带前缀的 code，用于外部 API 查询。

    规则（按交易所真实号段）：
        沪市 ``sh``：6xxxxx（主板/科创板股票）+ **5xxxxx（基金/ETF，
            含 58xxxx 科创板 ETF、588xxx 科创板指数 ETF）** + 9xxxxx（B 股）
        深市 ``sz``：0xxxxx/3xxxxx（主板/创业板）+ 1xxxxx（基金/ETF）+ 2xxxxx（B 股）

    ⚠️ 曾经这里只写 ``code.startswith("6") → sh``，**其余一律 sz** ——
    于是所有沪市 ETF（510300 / 512480 / **588200**）和基金都被编成 sz，
    新浪返回空行，整个 A 股拉取链路静默返回 ``{}``。
    报错信息还被 ``log.debug`` 吞掉，表现为「取不到行情」而不是「代码错了」。
    """
    if code[:3].lower() == "gb_":
        # 新浪美股代码必须小写，gb_NVDA 会返回空串
        return f"gb_{code[3:].lower()}"
    if code[:2].lower() in ("sh", "sz", "bj"):
        return code[:2].lower() + code[2:]
    if len(code) == 6 and code.isdigit():
        if code[0] in ("5", "6", "9"):
            return f"sh{code}"
        return f"sz{code}"
    # 裸美股符号（NVDA / nvda）走到这里，统一小写，便于上层拼 gb_ 前缀
    return code.lower()


def _format_code(code: str) -> str:
    """内部别名，保留给既有调用方。"""
    return format_exchange_code(code)


def looks_like_us_symbol(code: str) -> bool:
    """裸字母股票代码（1~5 位）＝ 美股。

    ❗曾经这里靠一个 **10 只的白名单**（nvda/aapl/tsla/…）决定谁走美股分支，
    白名单外的美股（``alab`` / ``crwv`` / ``skuu`` …）两个分支都不进，被丢进
    ``unrouted`` —— 行情抓不到，持仓现价永远停在开仓价。而白名单看起来"工作
    正常"，因为最常看的那几只恰好在里面。

    A 股（6 位数字）与港股（5 位数字）都是纯数字，``isalpha()`` 天然排除，
    所以这个判据不会误伤。
    """
    c = (code or "").strip()
    if c[:3].lower() == "gb_":
        c = c[3:]
    return c.isalpha() and 1 <= len(c) <= 5


@dataclass
class MarketQuote:
    code: str
    name: str
    current: float
    prev_close: float
    change: float
    change_pct: float
    volume: int
    high: float
    low: float
    open_price: float = 0.0
    amount: float = 0.0
    market: str = "UNKNOWN"
    timestamp: float = 0.0
    fetch_time: float = field(default_factory=time.time)
    is_stale: bool = False
    _version: int = MARKET_QUOTE_VERSION

    @property
    def age(self) -> float:
        return time.time() - self.fetch_time

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "current": self.current,
            "prev_close": self.prev_close,
            "change": self.change,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "high": self.high,
            "low": self.low,
            "open_price": self.open_price,
            "amount": self.amount,
            "market": self.market,
            "timestamp": self.timestamp,
            "fetch_time": self.fetch_time,
            "is_stale": self.is_stale,
            "_version": self._version,
        }

    @classmethod
    def from_market_data(cls, md: "MarketData", market: str = "US") -> "MarketQuote":
        code = _normalize_code(getattr(md, "market_id", None) or getattr(md, "code", ""))
        return cls(
            code=code,
            name=getattr(md, "name", code),
            current=getattr(md, "current", 0.0),
            prev_close=getattr(md, "prev_close", 0.0),
            change=getattr(md, "change", 0.0),
            change_pct=getattr(md, "change_pct", 0.0),
            volume=getattr(md, "volume", 0),
            high=getattr(md, "high", 0.0),
            low=getattr(md, "low", 0.0),
            open_price=getattr(md, "open_price", getattr(md, "open", 0.0)),
            amount=getattr(md, "amount", 0.0),
            market=market,
            timestamp=getattr(md, "timestamp", time.time()),
            fetch_time=time.time(),
            is_stale=False,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "MarketQuote":
        return cls(
            code=data.get("code", ""),
            name=data.get("name", ""),
            current=data.get("current", 0.0),
            prev_close=data.get("prev_close", 0.0),
            change=data.get("change", 0.0),
            change_pct=data.get("change_pct", 0.0),
            volume=data.get("volume", 0),
            high=data.get("high", 0.0),
            low=data.get("low", 0.0),
            open_price=data.get("open_price", 0.0),
            amount=data.get("amount", 0.0),
            market=data.get("market", "UNKNOWN"),
            timestamp=data.get("timestamp", 0.0),
            fetch_time=data.get("fetch_time", time.time()),
            is_stale=data.get("is_stale", False),
        )

_EMPTY_QUOTE = MarketQuote(
    code="", name="", current=0.0, prev_close=0.0,
    change=0.0, change_pct=0.0, volume=0, high=0.0, low=0.0,
    market="", timestamp=0.0, fetch_time=0.0, is_stale=True
)


@dataclass
class PendingRequest:
    codes: Set[str]
    _future: Optional[asyncio.Future] = field(default=None, init=False)
    _future_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    created_at: float = field(default_factory=time.time)

    @property
    def future(self) -> asyncio.Future:
        with self._future_lock:
            if self._future is None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                self._future = asyncio.Future()
        return self._future

    def resolve(self, result: Dict[str, "MarketQuote"]):
        if self.future.done():
            return
        try:
            self.future.set_result(result)
        except Exception:
            pass

    def reject(self, exc: Exception):
        if self.future.done():
            return
        try:
            self.future.set_exception(exc)
        except Exception:
            pass


class MarketDataBus:
    DEFAULT_TTL = 10.0
    STALE_TTL = 30.0
    FORCE_FETCH_THRESHOLD = 60.0
    SINGLE_FLIGHT_WINDOW = 0.05

    PRIORITY_HIGH = "HIGH"
    PRIORITY_MEDIUM = "MEDIUM"
    PRIORITY_LOW = "LOW"

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._cache: Dict[str, MarketQuote] = {}
        self._lock_cache = threading.RLock()

        self._priority_codes: Dict[str, List[str]] = {
            self.PRIORITY_HIGH: [],
            self.PRIORITY_MEDIUM: [],
            self.PRIORITY_LOW: [],
        }
        self._lock_priority = threading.RLock()

        self._pending: Dict[frozenset, PendingRequest] = {}
        self._lock_pending = threading.Lock()

        self._subscribers: List[Callable[[str, float], None]] = []
        self._lock_subscribers = threading.Lock()

        self._stream = NS(
            MARKET_DATA_HUB_STREAM,
            cache_max_len=100,
            cache_max_age_seconds=300,
        )

        self._db = NB(MARKET_DATA_BUS_TABLE)

        self._fetch_in_progress: Set[str] = set()
        self._lock_fetch = threading.Lock()
        # 已经喊过「总线不覆盖这个代码」的集合（同一只票只喊一次，别刷屏）
        self._unrouted_warned: Set[str] = set()

        self._initialized = True

        log.info("[MarketDataBus] 行情数据服务总线已初始化")

    def _warn_unrouted(self, codes: List[str]) -> None:
        """把「总线没有这条路由」显式喊出来（每只票只喊一次）。

        ❗这类沉默是危险的：调用方拿到 0.0 会当成「行情还没来」，
        于是一直等、一直不报警，而真相是**这条链路根本不支持这个市场**。
        """
        fresh = [c for c in codes if c not in self._unrouted_warned]
        if not fresh:
            return
        self._unrouted_warned.update(fresh)
        log.warning(
            "[MarketDataBus] 这些代码没有对应的行情路由，总线取不到（不是网络失败）：%s。"
            "A 股需 sh/sz 前缀（5/6/9 开头为沪市）、美股走 gb_ 前缀；"
            "港股（5 位数字）当前不由本总线覆盖，现价请以 futu_portfolio_syncer 同步值为准。",
            "、".join(fresh),
        )

    def get_price(self, code: str, timeout: float = 3.0) -> float:
        quote = self.get_quote(code)
        if quote and quote.current > 0:
            return quote.current
        return 0.0

    def get_price_async(self, code: str) -> float:
        normalized = _normalize_code(code)
        quote = self._get_cached_quote(normalized)
        if quote and quote.current > 0:
            if quote.age > self.STALE_TTL:
                self._trigger_async_fetch([code])
            return quote.current

        self._trigger_async_fetch([code])
        return 0.0

    def get_quote(self, code: str, allow_stale: bool = True) -> Optional[MarketQuote]:
        normalized = _normalize_code(code)
        quote = self._get_cached_quote(normalized)
        if not quote:
            self._trigger_async_fetch([code])
            return None

        if not allow_stale and quote.age > self.STALE_TTL:
            self._trigger_async_fetch([code])
            return None

        if quote.age > self.STALE_TTL:
            self._trigger_async_fetch([code])

        return quote

    def get_prices(self, codes: List[str]) -> Dict[str, float]:
        result = {}
        stale_codes = []

        with self._lock_cache:
            for code in codes:
                normalized = _normalize_code(code)
                quote = self._cache.get(normalized)
                if quote and quote.current > 0:
                    result[code] = quote.current
                    if quote.age > self.STALE_TTL:
                        stale_codes.append(code)
                else:
                    stale_codes.append(code)

        if stale_codes:
            self._trigger_async_fetch(stale_codes)

        return result

    def subscribe(self, codes: List[str], callback: Callable[[str, float], None]):
        filtered_stream = self._stream
        for code in codes:
            c = code
            filtered_stream = filtered_stream.filter(lambda q, _c=c: q.get("code") == _c)

        with self._lock_subscribers:
            self._subscribers.append(callback)

        filtered_stream.sink(lambda q: callback(q.get("code"), q.get("current", 0)))
        log.debug(f"[MarketDataBus] 订阅行情: {codes}")

    def unsubscribe(self, callback: Callable):
        with self._lock_subscribers:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def fetch(self, codes: List[str], force: bool = False) -> Dict[str, float]:
        if not codes:
            return {}

        normalized_set = {_normalize_code(c) for c in codes}
        key = frozenset(normalized_set)

        pending_req = None
        with self._lock_pending:
            if key in self._pending:
                existing = self._pending[key]
                elapsed = time.time() - existing.created_at
                if elapsed < self.SINGLE_FLIGHT_WINDOW:
                    try:
                        result = existing.future.result(timeout=max(0.1, 3.0 - elapsed))
                        if result:
                            return {code: result.get(code, _EMPTY_QUOTE).current for code in codes}
                    except Exception:
                        pass
            pending_req = PendingRequest(normalized_set)
            self._pending[key] = pending_req

        try:
            quotes = self._do_fetch_sync(codes) or {}
            pending_req.resolve(quotes)
            self._update_cache_from_quotes(quotes)

            code_to_normalized = {code: _normalize_code(code) for code in codes}

            def _pick_price(code: str) -> float:
                """按「裸码 → 带交易所前缀」逐级兜底取值。

                ❗A 股分支历史上把 quote 存在 ``sh588200`` 这类**带前缀** key 上，
                而调用方拿的是 ``588200`` —— 只查一个 key 就永远 miss。这里做
                多形态兜底，避免同类映射错误再把整条链路静默归零。
                """
                for key in (code, code_to_normalized[code], _format_code(code)):
                    quote = quotes.get(key)
                    if quote is not None and getattr(quote, "current", 0) > 0:
                        return quote.current
                return 0.0

            result = {code: _pick_price(code) for code in codes}
            self._emit_to_subscribers_from_quotes(quotes)
            return result
        except Exception as e:
            if pending_req:
                pending_req.reject(e)
            raise
        finally:
            if pending_req:
                with self._lock_pending:
                    self._pending.pop(key, None)

    def prefetch(self, codes: List[str]):
        self._trigger_async_fetch(codes)

    def register_priority_codes(self, codes: List[str], level: str):
        if level not in (self.PRIORITY_HIGH, self.PRIORITY_MEDIUM, self.PRIORITY_LOW):
            return

        with self._lock_priority:
            for code in codes:
                for lvl in (self.PRIORITY_HIGH, self.PRIORITY_MEDIUM, self.PRIORITY_LOW):
                    if code in self._priority_codes[lvl]:
                        self._priority_codes[lvl].remove(code)
            self._priority_codes[level].extend(codes)

        log.debug(f"[MarketDataBus] 注册优先级 {level}: {codes}")

    def write_quotes(self, quotes: Dict[str, MarketQuote]):
        self._update_cache_from_quotes(quotes)
        self._emit_to_subscribers_from_quotes(quotes)

    def _get_cached_quote(self, normalized_code: str) -> Optional[MarketQuote]:
        with self._lock_cache:
            return self._cache.get(normalized_code)

    def _update_cache_from_quotes(self, quotes: Dict[str, MarketQuote]):
        now = time.time()
        with self._lock_cache:
            for code, quote in quotes.items():
                normalized = _normalize_code(code)
                quote.fetch_time = now
                quote.is_stale = False
                self._cache[normalized] = quote
        self._persist_quotes_to_db(quotes)

    def _persist_quotes_to_db(self, quotes: Dict[str, MarketQuote]):
        try:
            # 原先逐条 self._db.upsert(...)（每条一次提交），上千只票就是上千次写。
            # 聚合为单次 bulk_update，显著降低提交/写放大开销。
            payload = {_normalize_code(code): quote.to_dict() for code, quote in quotes.items()}
            if payload:
                self._db.bulk_update(payload)
        except Exception as e:
            log.debug(f"[MarketDataBus] 持久化行情失败: {e}")

    def _trigger_async_fetch(self, codes: List[str]):
        if not codes:
            return

        with self._lock_fetch:
            new_codes = [c for c in codes if _normalize_code(c) not in self._fetch_in_progress]
            if not new_codes:
                return
            for c in new_codes:
                self._fetch_in_progress.add(_normalize_code(c))

        asyncio.create_task(self._fetch_async(new_codes))

    async def _fetch_async(self, codes: List[str]):
        try:
            await self._do_fetch_async(codes)
        finally:
            with self._lock_fetch:
                for c in codes:
                    self._fetch_in_progress.discard(_normalize_code(c))

    async def _do_fetch_async(self, codes: List[str]):
        await asyncio.sleep(0)

        # Normalize and re-format codes to ensure proper prefixes for external APIs
        normalized_codes = {_normalize_code(c) for c in codes}
        formatted_codes = [_format_code(c) for c in normalized_codes]
        a股_codes = [c for c in formatted_codes if c.startswith(("sh", "sz", "bj"))]
        # ❗判据是「裸字母 1~5 位」而不是 10 只白名单：白名单外的美股（alab /
        # crwv / skuu …）曾被静默丢进 unrouted，持仓现价永远停在开仓价。
        美股_codes = [
            c for c in formatted_codes
            if c.startswith("gb_") or looks_like_us_symbol(c)
        ]

        # ❗没被任何分支接住的代码必须喊出来。
        #
        # 港股（``06666`` / ``00700``，5 位数字）在这里**两个列表都不进**：
        # ``_format_code`` 原样返回，既不以 sh/sz 开头、也不在美股白名单里。
        # 结果是它被静默丢弃，调用方只看到 current=0.0，看起来像「行情没到」。
        # 港股现价目前由 ``futu_portfolio_syncer`` 同步维护，不靠这条总线 ——
        # 但必须让「总线不覆盖港股」这件事可见，而不是伪装成取数失败。
        routed = set(a股_codes) | set(美股_codes)
        unrouted = sorted(c for c in formatted_codes if c not in routed)
        if unrouted:
            self._warn_unrouted(unrouted)

        quotes: Dict[str, MarketQuote] = {}

        if 美股_codes:
            try:
                from deva.naja.market_hotspot.data.global_market_futures import GlobalMarketAPI, MARKET_ID_TO_CODE
                sina_codes = []
                for code in 美股_codes:
                    if code.startswith("gb_"):
                        sina_codes.append(code)
                    else:
                        # 新浪美股代码必须小写
                        sina_codes.append(f"gb_{code.lower()}")

                async with GlobalMarketAPI() as api:
                    data = await api.fetch(sina_codes)
                    for sina_code, md in data.items():
                        if hasattr(md, "current"):
                            normalized = md.code
                            quotes[normalized] = MarketQuote.from_market_data(md, market="US")
                        elif isinstance(md, dict):
                            normalized = MARKET_ID_TO_CODE.get(sina_code, sina_code.replace("gb_", ""))
                            quotes[normalized] = MarketQuote(
                                code=normalized,
                                name=md.get("name", normalized),
                                current=md.get("current", 0),
                                prev_close=md.get("prev_close", 0),
                                change=md.get("change", 0),
                                change_pct=md.get("change_pct", 0),
                                volume=md.get("volume", 0),
                                high=md.get("high", 0),
                                low=md.get("low", 0),
                                open_price=md.get("open_price", md.get("open", 0.0)),
                                amount=md.get("amount", 0.0),
                                market="US",
                                timestamp=md.get("timestamp", time.time()),
                                fetch_time=time.time(),
                                is_stale=False,
                            )
            except Exception as e:
                log.debug(f"[MarketDataBus] 美股获取失败: {e}")

        if a股_codes:
            try:
                a股_quotes = await self._fetch_ashare(a股_codes)
                quotes.update(a股_quotes)
            except Exception as e:
                log.debug(f"[MarketDataBus] A股获取失败: {e}")

        if quotes:
            self._update_cache_from_quotes(quotes)
            self._emit_to_subscribers_from_quotes(quotes)

        return quotes

    def _do_fetch_sync(self, normalized_codes: Set[str]) -> Dict[str, MarketQuote]:
        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self._do_fetch_async(list(normalized_codes)))
                return future.result()
        except RuntimeError:
            return asyncio.run(self._do_fetch_async(list(normalized_codes)))

    @probe(KIND_DATASOURCE, "ds:sina_ashare", "新浪A股行情（行情总线）", cadence="按需/批量")
    async def _fetch_ashare(self, codes: List[str]) -> Dict[str, MarketQuote]:
        try:
            import aiohttp
            codes_dedup = list(dict.fromkeys(codes))
            url = f"https://hq.sinajs.cn/list={','.join(codes_dedup)}"
            headers = {
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        return self._parse_ashare_response(text, codes_dedup)
        except Exception as e:
            log.debug(f"[MarketDataBus] A股HTTP获取失败: {e}")
        return {}

    def _parse_ashare_response(self, text: str, requested_codes: List[str]) -> Dict[str, MarketQuote]:
        quotes = {}
        now = time.time()
        requested_set = set(requested_codes)
        lines = text.strip().split("\n")
        for line in lines:
            if not line or '="' not in line:
                continue
            try:
                prefix, data = line.split('="')
                raw_code = prefix.split("_")[-1]
                data = data.rstrip('"')
                if not data or len(data.split(",")) < 10:
                    continue

                if raw_code not in requested_set:
                    continue

                original = raw_code
                normalized = _normalize_code(original)
                fields = data.split(",")
                market = "SH" if original.startswith("sh") else "SZ" if original.startswith("sz") else "UNKNOWN"

                prev_close = float(fields[2])
                current = float(fields[3])
                change = current - prev_close
                change_pct = (change / prev_close * 100) if prev_close > 0 else 0

                # ❗key 必须用**裸码**（normalized），与美股分支保持一致。
                #
                # 曾经这里写 ``quotes[original] = ...``（即 ``sh588200``），而
                # ``fetch()`` 是拿「调用方传进来的原始 code（``588200``）」和
                # 「它的归一形式（``588200``）」去查 —— 两个都命中不了带前缀的
                # key，于是 A 股/ETF **行情明明抓到了 3 条，却被映射成 0.0**。
                #
                # 后果：所有 A 股持仓的现价永远停在开仓价，止损止盈形同虚设，
                # 而 log.debug 里只看得到「取不到行情」。实测 sh588200=0.92、
                # sz000001=11.44 都在返回体里，就是取不出来。
                q = MarketQuote(
                    code=original,
                    name=fields[0],
                    current=current,
                    prev_close=prev_close,
                    change=change,
                    change_pct=change_pct,
                    volume=int(fields[8]) if fields[8].isdigit() else 0,
                    high=float(fields[4]) if fields[4] else current,
                    low=float(fields[5]) if fields[5] else current,
                    open_price=float(fields[1]) if fields[1] else current,
                    amount=float(fields[9]) if len(fields) > 9 and fields[9].replace('.', '', 1).isdigit() else 0.0,
                    market=market,
                    timestamp=now,
                    fetch_time=now,
                    is_stale=False,
                )
                quotes[normalized] = q
                # 双 key：normalized 供 ``fetch()`` 查，original 供既有调用方兼容
                quotes.setdefault(original, q)
            except (ValueError, IndexError):
                continue
        return quotes

    def _emit_to_subscribers_from_quotes(self, quotes: Dict[str, MarketQuote]):
        if not quotes:
            return
        with self._lock_subscribers:
            for callback in self._subscribers:
                try:
                    for code, quote in quotes.items():
                        callback(quote.code, quote.current)
                except Exception as e:
                    log.debug(f"[MarketDataBus] 推送失败: {e}")

        for code, quote in quotes.items():
            self._stream.emit(quote.to_dict())

    def get_stats(self) -> dict:
        with self._lock_cache:
            total = len(self._cache)
            stale = sum(1 for q in self._cache.values() if q.is_stale or q.age > self.STALE_TTL)

        with self._lock_pending:
            pending_count = len(self._pending)

        with self._lock_fetch:
            fetching_count = len(self._fetch_in_progress)

        return {
            "cached_codes": total,
            "stale_codes": stale,
            "pending_requests": pending_count,
            "fetching_codes": fetching_count,
            "subscribers": len(self._subscribers),
            "priority_high": len(self._priority_codes[self.PRIORITY_HIGH]),
            "priority_medium": len(self._priority_codes[self.PRIORITY_MEDIUM]),
            "priority_low": len(self._priority_codes[self.PRIORITY_LOW]),
        }


def get_market_data_bus() -> MarketDataBus:
    """获取 MarketDataBus 单例（已使用 __new__ 单例模式）"""
    return MarketDataBus()
