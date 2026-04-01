"""
Global Market API - 全球市场数据异步API

从新浪获取全球市场数据，支持：
- 股指期货：纳指(hf_NQ)、标普500(hf_ES)、道琼斯(hf_YM)
- 商品期货：黄金(hf_GC)、白银(hf_SI)、原油(hf_CL)、天然气(hf_NG)
- 美股个股：gb_nvda、gb_aapl、gb_tsla等（小写，gb_前缀）

用法:
    api = GlobalMarketAPI()
    data = await api.fetch_all()
    print(data["hf_NQ"])     # 纳指期货
    print(data["gb_nvda"])  # 英伟达

    # 只获取美股
    us_data = await api.fetch_us_stocks()
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import aiohttp

log = logging.getLogger(__name__)

SINA_BASE_URL = "https://hq.sinajs.cn/list={codes}"
SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

FUTURES_CODES = {
    "hf_NQ": "nasdaq100",
    "hf_ES": "sp500",
    "hf_YM": "dowjones",
    "hf_GC": "gold",
    "hf_SI": "silver",
    "hf_CL": "crude_oil",
    "hf_NG": "natural_gas",
}

US_STOCK_CODES = {
    # Mega Cap Tech
    "gb_aapl": "aapl",
    "gb_msft": "msft",
    "gb_goog": "goog",
    "gb_googl": "googl",
    "gb_amzn": "amzn",
    "gb_meta": "meta",
    "gb_nvda": "nvda",
    "gb_tsla": "tsla",

    # Semiconductor
    "gb_amd": "amd",
    "gb_intc": "intc",
    "gb_nxpi": "nxpi",
    "gb_qcom": "qcom",
    "gb_mu": "mu",
    "gb_lam": "lam",
    "gb_amat": "amat",
    "gb_asml": "asml",
    "gb_tsm": "tsm",

    # Internet & E-commerce
    "gb_pypl": "pypl",
    "gb_shop": "shop",
    "gb_snap": "snap",
    "gb_pins": "pins",
    "gb_twlo": "twlo",
    "gb_roku": "roku",
    "gb_dbx": "dbx",
    "gb_spot": "spot",

    # Finance
    "gb_jpm": "jpm",
    "gb_bac": "bac",
    "gb_wfc": "wfc",
    "gb_ms": "ms",
    "gb_c": "c",
    "gb_v": "v",
    "gb_ma": "ma",

    # China Stocks (ADRs)
    "gb_baba": "baba",
    "gb_bidu": "bidu",
    "gb_nio": "nio",
    "gb_xpev": "xpev",
    "gb_li": "li",
    "gb_jd": "jd",
    "gb_pdd": "pdd",

    # Others
    "gb_nke": "nke",
    "gb_dis": "dis",
    "gb_mcd": "mcd",
    "gb_hum": "hum",
    "gb_unh": "unh",
    "gb_pfe": "pfe",

    # Crypto
    "gb_mstr": "mstr",
    "gb_coin": "coin",
    "gb_mara": "mara",
    "gb_riot": "riot",

    # Cloud & Security
    "gb_crwd": "crwd",
    "gb_okta": "okta",
    "gb_zs": "zs",
    "gb_net": "net",
    "gb_ddog": "ddog",
    "gb_snow": "snow",

    # Streaming & Gaming
    "gb_nflx": "nflx",
    "gb_ea": "ea",
    "gb_atvi": "atvi",

    # AI & Robotics
    "gb_pltr": "pltr",

    # EV & Energy
    "gb_f": "f",
    "gb_gm": "gm",
    "gb_rivn": "rivn",
    "gb_lucid": "lucid",
    "gb_wrld": "wrld",
    "gb_crwc": "crwv",
}

US_STOCK_SECTORS = {
    "aapl": "科技",
    "msft": "科技",
    "goog": "科技",
    "googl": "科技",
    "amzn": "电商",
    "meta": "科技",
    "nvda": "半导体",
    "tsla": "新能源车",
    "amd": "半导体",
    "intc": "半导体",
    "nxpi": "半导体",
    "qcom": "半导体",
    "mu": "半导体",
    "lam": "半导体",
    "amat": "半导体",
    "asml": "半导体",
    "tsm": "半导体",
    "pypl": "金融科技",
    "shop": "电商",
    "snap": "社交",
    "pins": "社交媒体",
    "twlo": "通信",
    "roku": "流媒体",
    "dbx": "云计算",
    "spot": "音乐",
    "jpm": "金融",
    "bac": "金融",
    "wfc": "金融",
    "ms": "金融",
    "c": "金融",
    "v": "支付",
    "ma": "支付",
    "baba": "电商",
    "bidu": "科技",
    "nio": "新能源车",
    "xpev": "新能源车",
    "li": "新能源车",
    "jd": "电商",
    "pdd": "电商",
    "nke": "消费",
    "dis": "娱乐",
    "mcd": "消费",
    "hum": "医疗",
    "unh": "医疗",
    "pfe": "医疗",
    "mstr": "加密",
    "coin": "加密",
    "mara": "加密",
    "riot": "加密",
    "crwd": "安全",
    "okta": "安全",
    "zs": "安全",
    "net": "安全",
    "ddog": "云",
    "snow": "云",
    "nflx": "流媒体",
    "ea": "游戏",
    "atvi": "游戏",
    "pltr": "AI",
    "f": "新能源车",
    "gm": "新能源车",
    "rivn": "新能源车",
    "lucid": "新能源车",
    "wrld": "游戏",
    "crwc": "游戏",
}

US_SECTOR_LIST = [
    "科技", "半导体", "电商", "新能源车", "金融", "金融科技",
    "支付", "社交", "社交媒体", "通信", "流媒体", "云计算",
    "安全", "云", "游戏", "AI", "医疗", "消费", "娱乐", "加密"
]

ALL_CODES = {**FUTURES_CODES, **US_STOCK_CODES}
MARKET_ID_TO_CODE = {v: k for k, v in ALL_CODES.items()}


@dataclass
class MarketData:
    """市场数据"""
    code: str
    market_id: str
    name: str
    current: float
    open: float
    high: float
    low: float
    prev_close: float
    change: float
    change_pct: float
    volume: int
    update_time: str
    update_date: str
    timestamp: float


class GlobalMarketAPI:
    """全球市场异步API"""

    def __init__(self, codes: Optional[List[str]] = None):
        self.codes = codes or list(ALL_CODES.keys())
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=20, limit_per_host=10),
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    def _parse_futures_line(self, line: str) -> Optional[MarketData]:
        """解析期货数据行"""
        try:
            prefix, data = line.split('="')
            code = prefix.split("_")[-1]
            data = data.rstrip('"')
            if not data:
                return None
            fields = data.split(",")
            if len(fields) < 15:
                return None

            current = float(fields[0]) if fields[0] else 0
            open_price = float(fields[2]) if fields[2] else 0
            prev_close = float(fields[3]) if fields[3] else 0
            high = float(fields[4]) if fields[4] else 0
            low = float(fields[5]) if fields[5] else 0
            update_time = fields[6] if len(fields) > 6 else ""
            volume = int(fields[9]) if len(fields) > 9 and fields[9].isdigit() else 0
            update_date = fields[12] if len(fields) > 12 else ""
            name = fields[13] if len(fields) > 13 else code

            change = current - prev_close if current and prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            return MarketData(
                code=code,
                market_id=FUTURES_CODES.get(f"hf_{code}", code),
                name=name,
                current=current,
                open=open_price,
                high=high,
                low=low,
                prev_close=prev_close,
                change=change,
                change_pct=change_pct,
                volume=volume,
                update_time=update_time,
                update_date=update_date,
                timestamp=datetime.now().timestamp(),
            )
        except Exception:
            return None

    def _parse_us_stock_line(self, line: str) -> Optional[MarketData]:
        """解析美股数据行"""
        try:
            prefix, data = line.split('="')
            code = prefix.split("_")[-1]
            data = data.rstrip('"')
            if not data:
                return None
            fields = data.split(",")
            if len(fields) < 30:
                return None

            name = fields[0]
            current = float(fields[1]) if fields[1] else 0
            change_pct = float(fields[2]) if fields[2] else 0
            update_date_time = fields[3] if len(fields) > 3 else ""
            change = float(fields[4]) if fields[4] else 0
            open_price = float(fields[5]) if fields[5] else 0
            high = float(fields[6]) if len(fields) > 6 and fields[6] else 0
            low = fields[7] if len(fields) > 7 else ""
            low = float(low) if low and low.replace('.', '').replace('-', '').isdigit() else 0
            volume = int(fields[10]) if len(fields) > 10 and fields[10].isdigit() else 0
            prev_close = float(fields[26]) if len(fields) > 26 and fields[26] else current - change

            update_time = update_date_time.split(" ")[1] if " " in update_date_time else update_date_time
            update_date = update_date_time.split(" ")[0] if " " in update_date_time else ""

            return MarketData(
                code=code,
                market_id=US_STOCK_CODES.get(f"gb_{code}", code),
                name=name,
                current=current,
                open=open_price,
                high=high,
                low=low,
                prev_close=prev_close,
                change=change,
                change_pct=change_pct,
                volume=volume,
                update_time=update_time,
                update_date=update_date,
                timestamp=datetime.now().timestamp(),
            )
        except Exception as e:
            log.debug(f"解析美股失败: {line[:50]}... error: {e}")
            return None

    def _parse_response(self, text: str, codes: List[str]) -> Dict[str, MarketData]:
        """解析响应"""
        result = {}
        futures_codes = set(FUTURES_CODES.keys())
        us_codes = set(US_STOCK_CODES.keys())

        for line in text.strip().split("\n"):
            if not line or '="' not in line:
                continue
            try:
                prefix = line.split('="')[0]
                code_part = prefix.split("_")[-1]
                full_code = prefix.split("hq_str_")[-1] if "hq_str_" in prefix else f"hf_{code_part}"

                if full_code in futures_codes:
                    parsed = self._parse_futures_line(line)
                    if parsed:
                        result[code_part] = parsed
                elif full_code in us_codes:
                    parsed = self._parse_us_stock_line(line)
                    if parsed:
                        result[code_part] = parsed
            except Exception:
                continue
        return result

    async def fetch(self, codes: Optional[List[str]] = None) -> Dict[str, MarketData]:
        """获取市场数据"""
        codes_to_fetch = codes or self.codes
        if not codes_to_fetch:
            return {}

        try:
            session = await self._get_session()
            codes_str = ",".join(codes_to_fetch)
            url = SINA_BASE_URL.format(codes=codes_str)

            async with session.get(url, headers=SINA_HEADERS) as resp:
                if resp.status != 200:
                    log.warning(f"获取市场数据失败: HTTP {resp.status}")
                    return {}
                text = await resp.text()
                return self._parse_response(text, codes_to_fetch)
        except Exception as e:
            log.error(f"获取市场数据异常: {e}")
            return {}
        finally:
            await self.close()

    async def fetch_futures(self) -> Dict[str, MarketData]:
        """获取期货数据"""
        return await self.fetch(list(FUTURES_CODES.keys()))

    async def fetch_us_stocks(self) -> Dict[str, MarketData]:
        """获取美股数据"""
        return await self.fetch(list(US_STOCK_CODES.keys()))

    async def fetch_all(self) -> Dict[str, MarketData]:
        """获取所有市场数据"""
        return await self.fetch(self.codes)

    async def get_market_data(self, market_id: str) -> Optional[MarketData]:
        """获取特定市场数据"""
        code = MARKET_ID_TO_CODE.get(market_id)
        if not code:
            return None
        data = await self.fetch([code])
        return data.get(code.split("_")[-1])

    def to_dict(self, data: Dict[str, MarketData]) -> Dict[str, Dict[str, Any]]:
        """转换为字典格式"""
        return {
            code: {
                "code": md.code,
                "market_id": md.market_id,
                "name": md.name,
                "current": md.current,
                "open": md.open,
                "high": md.high,
                "low": md.low,
                "prev_close": md.prev_close,
                "change": md.change,
                "change_pct": md.change_pct,
                "volume": md.volume,
                "update_time": md.update_time,
                "update_date": md.update_date,
                "timestamp": md.timestamp,
            }
            for code, md in data.items()
        }

    async def close(self):
        """关闭会话"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


_global_api: Optional[GlobalMarketAPI] = None


def get_global_market_api() -> GlobalMarketAPI:
    """获取全局API实例"""
    global _global_api
    if _global_api is None:
        _global_api = GlobalMarketAPI()
    return _global_api


async def fetch_global_market_data() -> Dict[str, MarketData]:
    """便捷函数：获取全球市场数据"""
    api = get_global_market_api()
    return await api.fetch_all()


if __name__ == "__main__":
    async def test():
        async with GlobalMarketAPI() as api:
            print("=== 获取期货数据 ===")
            futures = await api.fetch_futures()
            for code, md in futures.items():
                print(f"{md.name}: {md.current} ({md.change_pct:+.2f}%)")

            print("\n=== 获取美股数据 ===")
            us_stocks = await api.fetch_us_stocks()
            for code, md in us_stocks.items():
                print(f"{md.name}: ${md.current} ({md.change_pct:+.2f}%)")

    asyncio.run(test())