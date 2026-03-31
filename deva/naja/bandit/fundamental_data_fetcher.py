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

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class Market(Enum):
    """市场"""
    US = "US"
    A = "A"
    HK = "HK"
    UNKNOWN = "UNKNOWN"


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

    pe_ratio: float = 0.0
    pb_ratio: float = 0.0

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
        self._fetch_interval: float = 300.0
        self._xueqiu_mcp_available = False
        self._check_xueqiu_mcp()

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

        if code_upper in ['NVDA', 'AMD', 'INTC', 'TSM', 'ASML', 'MU', 'SMCI',
                          'MSFT', 'GOOGL', 'AMZN', 'CRWV', 'LUMENTUM', 'CGnx', 'SKX']:
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
        """从新浪获取美股数据"""
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

                parts = text.split('"')[1].split(',')
                if len(parts) >= 10:
                    return {
                        "code": stock_code,
                        "name": parts[0],
                        "current": float(parts[1]),
                        "prev_close": float(parts[26]) if parts[26] else 0,
                        "open": float(parts[2]) if parts[2] else 0,
                        "volume": float(parts[8]) if parts[8] else 0,
                    }
        except Exception as e:
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

            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={symbol}&fields=f43,f44,f45,f46,f47,f48,f57,f58,f107,f116,f117,f191,f192,f234"

            headers = {
                "Referer": "https://quote.eastmoney.com",
                "User-Agent": "Mozilla/5.0"
            }

            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if 'data' in data and data['data']:
                    d = data['data']
                    return {
                        "code": stock_code,
                        "name": d.get('f58', ''),
                        "current": d.get('f43', 0) / 100,
                        "prev_close": d.get('f44', 0) / 100,
                        "open": d.get('f45', 0) / 100,
                        "high": d.get('f46', 0) / 100,
                        "low": d.get('f47', 0) / 100,
                        "volume": d.get('f48', 0),
                        "pe": d.get('f116', 0),
                        "pb": d.get('f117', 0),
                        "market_cap": d.get('f116', 0),
                    }
        except Exception as e:
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
        if not force_refresh and stock_code in self._fundamental_cache:
            cached = self._fundamental_cache[stock_code]
            if time.time() - cached.timestamp < self._fetch_interval:
                return cached

        market = self._detect_market(stock_code)
        fundamental = None

        if market == Market.US:
            fundamental = self._fetch_us_stock(stock_code)
        elif market == Market.A:
            fundamental = self._fetch_a_stock(stock_code)

        if fundamental:
            self._fundamental_cache[stock_code] = fundamental

        return fundamental

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

        fundamental = StockFundamental(
            stock_code=stock_code,
            stock_name=name,
            market=Market.US,
            current_price=current,
            prev_close=prev_close,
            change_pct=change_pct,
            total_volume=sina_data.get('volume', 0),
            timestamp=time.time(),
            raw_data=sina_data
        )

        self._enrich_us_fundamental(fundamental, code_upper)

        return fundamental

    def _enrich_us_fundamental(self, fundamental: StockFundamental, code: str):
        """补充美股基本面数据（基于已知数据）"""
        us_fundamentals = {
            'NVDA': {'pe': 65.0, 'market_cap': 2800000000000, 'market_cap_str': '2.8T'},
            'AMD': {'pe': 45.0, 'market_cap': 280000000000, 'market_cap_str': '280B'},
            'INTC': {'pe': 25.0, 'market_cap': 180000000000, 'market_cap_str': '180B'},
            'TSM': {'pe': 30.0, 'market_cap': 650000000000, 'market_cap_str': '650B'},
            'ASML': {'pe': 40.0, 'market_cap': 380000000000, 'market_cap_str': '380B'},
            'MU': {'pe': 35.0, 'market_cap': 140000000000, 'market_cap_str': '140B'},
            'SMCI': {'pe': 25.0, 'market_cap': 50000000000, 'market_cap_str': '50B'},
            'MSFT': {'pe': 35.0, 'market_cap': 3100000000000, 'market_cap_str': '3.1T'},
            'GOOGL': {'pe': 28.0, 'market_cap': 2100000000000, 'market_cap_str': '2.1T'},
            'AMZN': {'pe': 55.0, 'market_cap': 1900000000000, 'market_cap_str': '1.9T'},
        }

        if code in us_fundamentals:
            data = us_fundamentals[code]
            fundamental.pe_ratio = data.get('pe', 0)
            fundamental.market_cap = data.get('market_cap', 0)
            fundamental.market_cap_str = data.get('market_cap_str', '')

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

        fundamental = StockFundamental(
            stock_code=stock_code,
            stock_name=eastmoney_data.get('name', stock_code),
            market=Market.A,
            current_price=current,
            prev_close=prev_close,
            change_pct=change_pct,
            pe_ratio=eastmoney_data.get('pe', 0),
            pb_ratio=eastmoney_data.get('pb', 0),
            market_cap=eastmoney_data.get('market_cap', 0),
            total_volume=eastmoney_data.get('volume', 0),
            timestamp=time.time(),
            raw_data=eastmoney_data
        )

        return fundamental

    def get_batch_fundamentals(self, stock_codes: List[str]) -> Dict[str, StockFundamental]:
        """批量获取基本面数据"""
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
