"""FundamentalDataFetcher - 供应链基本面数据获取器

从市场获取供应链相关公司的真实基本面数据：
1. 实时价格、涨跌幅
2. 市值
3. PE、PB 等估值指标
4. 营收、利润等财务数据

支持：
- 美股：通过雪球/新浪 API
- A 股：通过雪球 MCP
"""

import os
import time
import logging
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return default


class Market(Enum):
    """市场"""
    US = "US"
    A = "A"
    HK = "HK"
    UNKNOWN = "UNKNOWN"


def _parse_ratio_field(raw: str) -> Optional[float]:
    """解析新浪的比率字段（PE/PB）。

    ❗新浪对**亏损股**返回字符串 ``--``（实测 INTC：EPS=-0.62、PE="--"）。
    这里必须返回 ``None``：

    - 返回 ``0.0`` → 页面上「PE 0」会被读成「白送」，是全场最危险的数；
    - 返回 ``None`` → 调用方走「未采集」分支并写出原因。

    空串 / ``N/A`` / 非数字同样按缺失处理。
    """
    text = (raw or "").strip()
    if not text or text in ("--", "-", "N/A", "null", "None"):
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _fmt_cap(cap: float) -> str:
    """市值 human-readable（5.26T / 650B / 50B）。

    只做展示格式化，**不参与任何计算** —— 计算一律用 ``market_cap`` 原值。
    """
    if cap <= 0:
        return ""
    if cap >= 1e12:
        return f"{cap / 1e12:.2f}T"
    if cap >= 1e9:
        return f"{cap / 1e9:.0f}B"
    if cap >= 1e6:
        return f"{cap / 1e6:.0f}M"
    return f"{cap:.0f}"


@dataclass
class StockFundamental:
    """股票基本面数据"""
    stock_code: str
    stock_name: str
    market: Market

    current_price: float = 0.0
    prev_close: float = 0.0
    change_pct: float = 0.0

    market_cap: float = 0.0
    market_cap_str: str = ""

    #: PE（TTM）。**0.0 只表示「没拿到」**，不是「PE=0」—— 判可信度看
    #: ``pe_source``，不看这个数本身。
    pe_ratio: float = 0.0
    pb_ratio: float = 0.0
    #: PE 的数据来源（``sina`` / ``eastmoney`` / 空串＝没拿到）。
    #: ❗ UI 必须读它来判断 PE 能不能信，不能只看 ``pe_ratio > 0``。
    pe_source: str = ""
    #: PE 拿不到时的原因（如「亏损股无 PE」「源无此标的」）。空串＝正常拿到。
    pe_note: str = ""
    #: 每股收益（TTM）。负值或 0 表示亏损/缺失。
    eps: float = 0.0
    #: 总股本（股）。用于自算市值交叉校验。
    shares: float = 0.0

    revenue: float = 0.0
    revenue_str: str = ""
    profit: float = 0.0
    profit_str: str = ""

    total_volume: float = 0.0
    turnover_rate: float = 0.0

    high_52w: float = 0.0
    low_52w: float = 0.0

    dividend_yield: float = 0.0

    timestamp: float = 0.0

    raw_data: Dict = None

    def __post_init__(self):
        if self.raw_data is None:
            self.raw_data = {}
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def is_valid(self) -> bool:
        """数据是否有效"""
        return self.current_price > 0

    def get_distance_from_52w_high(self) -> float:
        """距离52周高点的跌幅"""
        if self.high_52w <= 0:
            return 0.0
        return (self.current_price - self.high_52w) / self.high_52w * 100

    def get_distance_from_52w_low(self) -> float:
        """距离52周低点的涨幅"""
        if self.low_52w <= 0:
            return 0.0
        return (self.current_price - self.low_52w) / self.low_52w * 100


class FundamentalDataFetcher:
    """
    基本面数据获取器

    从雪球 MCP 或其他 API 获取真实市场数据
    """

    def __init__(self):
        self._price_cache: Dict[str, float] = {}
        self._fundamental_cache: Dict[str, StockFundamental] = {}
        self._last_fetch: float = 0.0
        self._fetch_interval: float = 3600.0
        # ❗负缓存：失败的股票也要记住，否则每次打开页面都重发注定失败的请求
        self._failed_cache: Dict[str, Tuple[float, str]] = {}
        self._failure_interval: float = _env_float("NAJA_FUNDAMENTAL_NEGATIVE_TTL", 300.0)
        self._negative_cache_enabled: bool = _env_flag("NAJA_FUNDAMENTAL_NEGATIVE_CACHE", True)
        self._max_workers: int = _env_int("NAJA_FUNDAMENTAL_MAX_WORKERS", 8)
        # 数据源最近一次的真实错误（给 UI 上屏用，不许只显示「加载中」）
        self._source_errors: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._xueqiu_mcp_available = False
        self._check_xueqiu_mcp()

    def _record_source_error(self, source: str, exc: BaseException) -> None:
        """记住数据源的真实错误原因（网络失败 / 代理拒绝 / 解析失败）。"""
        try:
            with self._lock:
                self._source_errors[source] = f"{type(exc).__name__}: {exc}"[:200]
        except Exception:  # pragma: no cover - 记错误本身绝不能把主流程带崩
            pass

    def _record_failure(self, stock_code: str, reason: str) -> None:
        with self._lock:
            self._failed_cache[stock_code] = (time.time(), reason)

    def get_fetch_diagnostics(self, stock_codes: Optional[List[str]] = None) -> Dict[str, Any]:
        """给 UI 上屏用的抓取诊断：成功几只、失败几只、失败原因是什么。

        ❗ 空必须同时给可信度/来源：页面不能把「数据源不可达」显示成「加载中」。
        """
        with self._lock:
            if stock_codes is None:
                stock_codes = list(self._fundamental_cache.keys()) + list(self._failed_cache.keys())
            failed = {}
            now = time.time()
            for code in stock_codes:
                if code in self._fundamental_cache:
                    continue
                hit = self._failed_cache.get(code)
                if hit:
                    failed[code] = hit[1]
            return {
                "total": len(stock_codes),
                "ok": len([c for c in stock_codes if c in self._fundamental_cache]),
                "failed": failed,
                "failed_count": len(failed),
                "source_errors": dict(self._source_errors),
                "negative_cache_enabled": self._negative_cache_enabled,
                "failure_interval": self._failure_interval,
                "generated_at": now,
            }

    def _check_xueqiu_mcp(self):
        """检查雪球 MCP 是否可用"""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 8000))
            sock.close()
            self._xueqiu_mcp_available = (result == 0)
            if self._xueqiu_mcp_available:
                logger.info("[FundamentalDataFetcher] 雪球 MCP 服务可用")
            else:
                logger.info("[FundamentalDataFetcher] 雪球 MCP 服务不可用，将使用备用方案")
        except Exception as e:
            logger.warning(f"[FundamentalDataFetcher] 检查雪球 MCP 失败: {e}")
            self._xueqiu_mcp_available = False

    def _detect_market(self, stock_code: str) -> Market:
        """识别市场"""
        code_upper = stock_code.upper()

        if stock_code.isdigit():
            if len(stock_code) == 6:
                if stock_code.startswith('6'):
                    return Market.A
                elif stock_code.startswith(('0', '3')):
                    return Market.A
                else:
                    return Market.A

        us_suffixes = ['.US', '-US', 'US:']
        for suffix in us_suffixes:
            if suffix in code_upper:
                return Market.US

        # ❗白名单**只能当快速通道，不能当唯一判据**（2026-10-20 实测）：
        # 白名单里只有 14 个老代码，ALAB / AVGO / CRDO / ANET / PLTR / MRVL
        # 这些后加的标的全不在里面 → 被判 UNKNOWN → 抓取直接返回 None，
        # 页面上显示成「—」且不写原因。"结构性增长"监控池里一半的股票
        # 拿不到任何行情，根因就是这一行。
        if code_upper in ['NVDA', 'AMD', 'INTC', 'TSM', 'ASML', 'MU', 'SMCI',
                          'MSFT', 'GOOGL', 'AMZN', 'CRWV', 'LUMENTUM', 'CGnx', 'SKX']:
            return Market.US

        # 形态判定：纯 ASCII 字母（1-5 位）＝美股 ticker。
        # ❗必须在数字/前缀分支之后，且**只对纯字母生效**：
        # A 股是 6 位数字、港股是 5 位数字，走不到这里；``SH.600487`` 这类
        # 带点前缀的也不会被误判（含 '.' 就不是 isalpha 的纯字母串）。
        # 上限 5 位是为了避免把 'UNKNOWN' 这种非代码串当美股。
        if stock_code.isascii() and stock_code.isalpha() and 1 <= len(stock_code) <= 5:
            return Market.US

        return Market.UNKNOWN

    async def fetch_from_xueqiu_mcp(self, stock_code: str) -> Optional[Dict]:
        """从雪球 MCP 获取数据"""
        if not self._xueqiu_mcp_available:
            return None

        try:
            import aiohttp
            url = f"http://localhost:8000/quote_detail?stock_code={stock_code}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data
        except Exception as e:
            logger.debug(f"[FundamentalDataFetcher] 雪球 MCP 获取 {stock_code} 失败: {e}")

        return None

    def fetch_from_sina(self, stock_code: str) -> Optional[Dict]:
        """从新浪获取美股数据（含真实 PE / EPS / 市值）。

        ❗字段索引是**单一真源**，改之前先实测（2026-10-20 用 15 只美股逐个核对）：

            idx 内容
            0   名称（GBK）          8/9  52 周高/低
            1   现价                10   成交量
            2   涨跌幅(%)           12   总市值
            4   涨跌额              13   EPS(TTM)
            5   开盘                14   PE(TTM)  ← 亏损股是 "--" 不是 0
            6/7 最高/最低           19   总股本
                                    26   昨收

        实测自洽：NVDA 218.28 / EPS 6.57 = PE 33.22 ✅；总股本 24.1B × 218.28
        = 市值 5.26T ✅。

        ❗**PE 可能是 ``--``**（亏损股，实测 INTC 的 EPS=-0.62、PE="--"）。
        必须解析成 ``None`` —— 解析成 0 会把「巨亏」显示成「PE 0 = 白送」。
        """
        try:
            import requests

            if self._detect_market(stock_code) == Market.US:
                symbol = f"gb_{stock_code.lower()}"
            else:
                symbol = stock_code

            url = f"https://hq.sinajs.cn/list={symbol}"
            headers = {
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0"
            }

            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                text = resp.text
                if '=""' in text:
                    return None

                quoted_parts = text.split('"')
                if len(quoted_parts) >= 2:
                    parts = quoted_parts[1].split(',')

                    def _f(idx: int) -> float:
                        """取浮点字段，取不到/非数字一律 0（数值字段的既有语义）。"""
                        if idx >= len(parts):
                            return 0.0
                        raw = (parts[idx] or "").strip()
                        try:
                            return float(raw)
                        except (TypeError, ValueError):
                            return 0.0

                    if len(parts) >= 10:
                        return {
                            "code": stock_code,
                            "name": parts[0],
                            "current": _f(1),
                            "prev_close": _f(26),
                            "open": _f(5),
                            "volume": _f(10),
                            "high_52w": _f(8),
                            "low_52w": _f(9),
                            "market_cap": _f(12),
                            "eps": _f(13),
                            "pe": _parse_ratio_field(parts[14] if len(parts) > 14 else ""),
                            "shares": _f(19),
                        }
        except Exception as e:
            self._record_source_error("sina", e)
            logger.debug(f"[FundamentalDataFetcher] 新浪获取 {stock_code} 失败: {e}")

        return None

    def fetch_from_eastmoney_a(self, stock_code: str) -> Optional[Dict]:
        """从东方财富获取 A 股数据"""
        try:
            import requests

            if stock_code.startswith('6'):
                symbol = f"1.{stock_code}"
            else:
                symbol = f"0.{stock_code}"

            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={symbol}&fields=f43,f44,f45,f46,f47,f48,f57,f58,f9,f23,f116,f117,f162,f163,f164,f167"

            headers = {
                "Referer": "https://quote.eastmoney.com",
                "User-Agent": "Mozilla/5.0"
            }

            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if 'data' in data and data['data']:
                    d = data['data']
                    # PE: 优先动态市盈率(f9/f162)，其次TTM(f163)
                    pe = d.get('f9') or d.get('f162') or d.get('f163') or 0
                    # PB: 优先 f23，其次 f164/f167
                    pb = d.get('f23') or d.get('f164') or d.get('f167') or 0
                    return {
                        "code": stock_code,
                        "name": d.get('f58', ''),
                        "current": d.get('f43', 0) / 100,
                        "prev_close": d.get('f44', 0) / 100,
                        "open": d.get('f45', 0) / 100,
                        "high": d.get('f46', 0) / 100,
                        "low": d.get('f47', 0) / 100,
                        "volume": d.get('f48', 0),
                        "pe": pe,
                        "pb": pb,
                        "market_cap": d.get('f116', 0),
                    }
        except Exception as e:
            self._record_source_error("eastmoney", e)
            logger.debug(f"[FundamentalDataFetcher] 东方财富获取 {stock_code} 失败: {e}")

        return None

    def get_fundamental(self, stock_code: str, force_refresh: bool = False) -> Optional[StockFundamental]:
        """
        获取股票基本面数据

        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新

        Returns:
            StockFundamental 或 None
        """
        if not force_refresh:
            with self._lock:
                cached = self._fundamental_cache.get(stock_code)
            if cached is not None and time.time() - cached.timestamp < self._fetch_interval:
                return cached

            # ❗负缓存命中：这只股票刚才就失败了，TTL 内不再打网络。
            # 没有这一层时，27 只拿不到的 A 股每次打开页面都会重发一遍请求（实测 ~2.5s）。
            if self._negative_cache_enabled:
                with self._lock:
                    failed = self._failed_cache.get(stock_code)
                if failed is not None and time.time() - failed[0] < self._failure_interval:
                    return None

        market = self._detect_market(stock_code)
        if market == Market.UNKNOWN:
            self._record_failure(stock_code, f"无法识别市场（{stock_code} 不在美股白名单也非 A 股代码）")
            return None

        if market == Market.US:
            fundamental = self._fetch_us_stock(stock_code)
            source = "sina"
        else:
            fundamental = self._fetch_a_stock(stock_code)
            source = "eastmoney"

        if fundamental:
            with self._lock:
                self._fundamental_cache[stock_code] = fundamental
                self._failed_cache.pop(stock_code, None)
                # ❗抓到就清掉这个源的旧错误：否则一次历史失败会一直挂在诊断里，
                # 把「这只票没数据」显示成「源不可达」。
                self._source_errors.pop(source, None)
            return fundamental

        reason = self._source_errors.get(source)
        if reason:
            self._record_failure(stock_code, f"{source} 不可达：{reason}")
        else:
            # 源是通的，只是这只票没数据 —— 不能谎报成「不可达」
            self._record_failure(stock_code, f"{source} 无此标的数据")
        logger.debug("[FundamentalDataFetcher] %s 抓取失败，已记负缓存 %ss：%s",
                     stock_code, self._failure_interval, reason or "无数据")
        return None

    def _fetch_us_stock(self, stock_code: str) -> Optional[StockFundamental]:
        """获取美股数据"""
        sina_data = self.fetch_from_sina(stock_code)

        if not sina_data:
            return None

        code_upper = stock_code.upper()
        name = code_upper

        name_map = {
            'NVDA': '英伟达', 'AMD': '超威半导体', 'INTC': '英特尔',
            'TSM': '台积电', 'ASML': 'ASML', 'MU': '美光科技',
            'SMCI': '超微电脑', 'MSFT': '微软', 'GOOGL': '谷歌',
            'AMZN': '亚马逊', 'CRWV': 'CoreWeave', 'LUMENTUM': 'Lumentum',
            'CGnx': 'Cognex', 'SKX': 'SK海力士'
        }
        name = name_map.get(code_upper, code_upper)

        current = sina_data.get('current', 0)
        prev_close = sina_data.get('prev_close', 0)
        change_pct = 0.0
        if prev_close > 0:
            change_pct = (current - prev_close) / prev_close * 100

        pe = sina_data.get('pe')
        eps = float(sina_data.get('eps') or 0.0)
        cap = float(sina_data.get('market_cap') or 0.0)

        # ❗PE 缺失必须说清是「亏损」还是「源没给」——两者对用户的含义完全不同：
        # 亏损股（EPS<=0）是**这家公司现在不赚钱**，不是我们抓不到。
        if pe is not None and pe > 0:
            pe_source = "sina"
            pe_note = ""
        elif eps <= 0:
            pe_source = ""
            pe_note = "亏损股无 PE（EPS≤0）"
        else:
            pe_source = ""
            pe_note = "sina 未返回该标的 PE"

        fundamental = StockFundamental(
            stock_code=stock_code,
            stock_name=name,
            market=Market.US,
            current_price=current,
            prev_close=prev_close,
            change_pct=change_pct,
            pe_ratio=float(pe) if pe is not None else 0.0,
            pe_source=pe_source,
            pe_note=pe_note,
            eps=eps,
            shares=float(sina_data.get('shares') or 0.0),
            market_cap=cap,
            market_cap_str=_fmt_cap(cap),
            high_52w=float(sina_data.get('high_52w') or 0.0),
            low_52w=float(sina_data.get('low_52w') or 0.0),
            total_volume=sina_data.get('volume', 0),
            timestamp=time.time(),
            raw_data=sina_data
        )

        return fundamental

    def _fetch_a_stock(self, stock_code: str) -> Optional[StockFundamental]:
        """获取 A 股数据"""
        eastmoney_data = self.fetch_from_eastmoney_a(stock_code)

        if not eastmoney_data:
            return None

        current = eastmoney_data.get('current', 0)
        prev_close = eastmoney_data.get('prev_close', 0)
        change_pct = 0.0
        if prev_close > 0:
            change_pct = (current - prev_close) / prev_close * 100

        pe = float(eastmoney_data.get('pe') or 0.0)
        fundamental = StockFundamental(
            stock_code=stock_code,
            stock_name=eastmoney_data.get('name', stock_code),
            market=Market.A,
            current_price=current,
            prev_close=prev_close,
            change_pct=change_pct,
            pe_ratio=pe,
            pe_source="eastmoney" if pe > 0 else "",
            pe_note="" if pe > 0 else "eastmoney 未返回该标的 PE",
            pb_ratio=eastmoney_data.get('pb', 0),
            market_cap=eastmoney_data.get('market_cap', 0),
            market_cap_str=_fmt_cap(float(eastmoney_data.get('market_cap') or 0.0)),
            total_volume=eastmoney_data.get('volume', 0),
            timestamp=time.time(),
            raw_data=eastmoney_data
        )

        return fundamental

    def get_batch_fundamentals(self, stock_codes: List[str]) -> Dict[str, StockFundamental]:
        """批量获取基本面数据（并发）。

        ❗原来是纯串行：39 只股票 = 39 次串行 HTTP，实测首次 4.3s。
        并发后墙钟时间由最慢的那一个决定，而不是全部之和。
        """
        if not stock_codes:
            return {}

        if len(stock_codes) == 1 or self._max_workers <= 1:
            return self._get_batch_sequential(stock_codes)

        try:
            with ThreadPoolExecutor(max_workers=min(self._max_workers, len(stock_codes))) as pool:
                raw = list(pool.map(self.get_fundamental, stock_codes))
        except Exception as e:  # 并发框架本身出问题不该让页面白屏，退回串行
            logger.warning("[FundamentalDataFetcher] 并发抓取失败，退回串行: %s", e)
            return self._get_batch_sequential(stock_codes)

        return {code: f for code, f in zip(stock_codes, raw) if f}

    def _get_batch_sequential(self, stock_codes: List[str]) -> Dict[str, StockFundamental]:
        """串行兜底（并发不可用 / 只有一只票时走这里）。"""
        results = {}
        for code in stock_codes:
            fundamental = self.get_fundamental(code)
            if fundamental:
                results[code] = fundamental
        return results

    def get_supply_chain_fundamentals(self) -> Dict[str, StockFundamental]:
        """获取供应链所有股票的基本面数据"""
        from deva.naja.bandit import get_supply_chain_graph

        graph = get_supply_chain_graph()
        if not graph:
            return {}

        stock_codes = []
        for node in graph._nodes.values():
            if node.type.value == "company" and node.stock_code:
                stock_codes.append(node.stock_code)

        return self.get_batch_fundamentals(stock_codes)


_fundamental_fetcher: Optional[FundamentalDataFetcher] = None


def get_fundamental_data_fetcher() -> FundamentalDataFetcher:
    """获取基本面数据获取器（单例）"""
    global _fundamental_fetcher
    if _fundamental_fetcher is None:
        _fundamental_fetcher = FundamentalDataFetcher()
    return _fundamental_fetcher
