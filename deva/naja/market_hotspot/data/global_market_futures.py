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


def _get_china_codes() -> set:
    """获取A股代码集合"""
    try:
        from deva.naja.dictionary.blocks import get_block_dictionary
        bd = get_block_dictionary()
        return set(bd.get_all_stocks('CN'))
    except Exception:
        return set()


def _get_us_stock_codes() -> Dict[str, str]:
    """从 BlockDictionary 获取美股代码（Sina格式：gb_nvda）"""
    try:
        from deva.naja.dictionary.blocks import get_block_dictionary
        bd = get_block_dictionary()
        us_codes = bd.get_all_stocks('US')
        result = {}
        for code in us_codes:
            info = bd.get_stock_info(code)
            if info:
                result[f"gb_{code}"] = info.name
        return result
    except Exception as e:
        log.warning(f"[_get_us_stock_codes] 获取失败: {e}, 返回空字典")
        return {}


_DEBUG_MARKET_MODE = None  # 正常模式，可设置为 "a_share", "us", "closed" 模拟不同市场


def set_debug_market_mode(mode: str):
    """设置调试市场模式（仅通过命令行参数显式指定时调用）"""
    global _DEBUG_MARKET_MODE
    _DEBUG_MARKET_MODE = mode
    log.warning(f"[_DEBUG_MARKET_MODE] 已通过命令行参数设置为: {mode}")


def _get_current_market() -> str:
    """获取当前市场状态"""
    if _DEBUG_MARKET_MODE:
        return _DEBUG_MARKET_MODE

    try:
        from deva.naja.register import ensure_trading_clocks
        ensure_trading_clocks()
        from deva.naja.radar.trading_clock import is_trading_time, is_us_trading_time
        if is_us_trading_time():
            return "us"
        if is_trading_time():
            return "a_share"
        return "closed"
    except Exception as e:
        log.debug(f"[_get_current_market] 获取市场状态失败: {e}")
        return "closed"


def get_current_stock_codes() -> Dict[str, str]:
    """获取当前市场的股票代码列表

    根据市场状态返回：
    - 美股交易时间: 返回美股代码 (Sina格式: gb_nvda)
    - A股交易时间: 返回A股代码 (Sina格式: sh600519)
    - 其他时间: 返回空字典
    """
    from deva.naja.dictionary.blocks import get_block_dictionary

    market = _get_current_market()
    bd = get_block_dictionary()

    if market == "us":
        us_codes = bd.get_all_stocks('US')
        return {f"gb_{code}": bd.get_stock_info(code).name for code in us_codes if bd.get_stock_info(code)}
    elif market == "a_share":
        cn_codes = bd.get_all_stocks('CN')
        return {code: bd.get_stock_info(code).name for code in cn_codes if bd.get_stock_info(code)}
    else:
        return {}


from deva.naja.bandit.stock_block_map import US_STOCK_BLOCKS

US_INDUSTRY_MAP = {
    code: info.get("industry_code", "other")
    for code, info in US_STOCK_BLOCKS.items()
}

US_INDUSTRY_LIST = list(dict.fromkeys(info.get("industry_code", "other") for info in US_STOCK_BLOCKS.values()))

ALL_CODES = {**FUTURES_CODES, **US_INDUSTRY_MAP}
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
                timeout=aiohttp.ClientTimeout(total=30),
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
                market_id=US_INDUSTRY_MAP.get(f"gb_{code}", code),
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

    def _parse_china_stock_line(self, line: str, sina_code: str) -> Optional[MarketData]:
        """解析A股数据行

        A股新浪数据格式：
        name,open,close,current,high,low,volume,amount,...
        """
        try:
            prefix, data = line.split('="')
            data = data.rstrip('"')
            if not data:
                return None
            fields = data.split(",")

            # A股至少有：name, open, close, current, high, low, volume, amount
            if len(fields) < 10:
                return None

            name = fields[0]
            open_price = float(fields[1]) if fields[1] else 0
            prev_close = float(fields[2]) if fields[2] else 0
            current = float(fields[3]) if fields[3] else 0
            high = float(fields[4]) if fields[4] else 0
            low = float(fields[5]) if fields[5] else 0
            volume = int(fields[8]) if len(fields) > 8 and fields[8].isdigit() else 0
            amount = float(fields[9]) if len(fields) > 9 and fields[9] else 0

            change = current - prev_close if current and prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            # 提取市场标识
            if sina_code.startswith('sh'):
                market_id = f"SH:{sina_code[2:]}"
            elif sina_code.startswith('sz'):
                market_id = f"SZ:{sina_code[2:]}"
            else:
                market_id = sina_code

            return MarketData(
                code=sina_code,
                market_id=market_id,
                name=name,
                current=current,
                open=open_price,
                high=high,
                low=low,
                prev_close=prev_close,
                change=change,
                change_pct=change_pct,
                volume=volume,
                update_time="",
                update_date="",
                timestamp=datetime.now().timestamp(),
            )
        except Exception as e:
            log.debug(f"解析A股失败: {line[:50]}... error: {e}")
            return None

    def _parse_response(self, text: str, codes: List[str]) -> Dict[str, MarketData]:
        """解析响应"""
        result = {}
        futures_codes = set(FUTURES_CODES.keys())
        us_codes = set(_get_us_stock_codes().keys())
        china_codes = _get_china_codes()

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
                elif full_code in china_codes:
                    # A股解析
                    parsed = self._parse_china_stock_line(line, full_code)
                    if parsed:
                        result[full_code] = parsed
            except Exception:
                continue
        return result

    async def fetch(self, codes: Optional[List[str]] = None, max_retries: int = 3) -> Dict[str, MarketData]:
        """获取市场数据（含指数退避重试 + requests fallback）"""
        codes_to_fetch = codes or self.codes
        if not codes_to_fetch:
            log.debug("获取市场数据跳过: 代码列表为空")
            return {}

        import asyncio
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                session = await self._get_session()
                codes_str = ",".join(codes_to_fetch)
                url = SINA_BASE_URL.format(codes=codes_str)

                async with session.get(url, headers=SINA_HEADERS) as resp:
                    if resp.status != 200:
                        log.warning(f"获取市场数据失败: HTTP {resp.status}, attempt={attempt}/{max_retries}")
                        if attempt < max_retries:
                            await asyncio.sleep(1 * attempt)
                            continue
                        break
                    text = await resp.text()
                    if not text or not text.strip():
                        log.warning(f"获取市场数据返回空内容, attempt={attempt}/{max_retries}")
                        if attempt < max_retries:
                            await asyncio.sleep(1 * attempt)
                            continue
                        break
                    return self._parse_response(text, codes_to_fetch)
            except asyncio.TimeoutError:
                log.warning(f"获取市场数据超时, attempt={attempt}/{max_retries}")
                last_err = "timeout"
            except Exception as e:
                log.error(f"获取市场数据异常: {type(e).__name__}: {e}, attempt={attempt}/{max_retries}, codes_count={len(codes_to_fetch)}")
                last_err = str(e)

            if attempt < max_retries:
                await asyncio.sleep(1 * attempt)

        # aiohttp 全部失败，fallback 到 requests（同步）
        log.info(f"[GlobalMarketAPI] aiohttp 失败({last_err})，fallback 到 requests")
        try:
            import requests as req
            codes_str = ",".join(codes_to_fetch)
            url = SINA_BASE_URL.format(codes=codes_str)
            resp = req.get(url, headers=SINA_HEADERS, timeout=15)
            if resp.status_code == 200 and resp.text and resp.text.strip():
                return self._parse_response(resp.text, codes_to_fetch)
            else:
                log.warning(f"[GlobalMarketAPI] requests fallback 也失败: HTTP {resp.status_code}")
        except Exception as e:
            log.error(f"[GlobalMarketAPI] requests fallback 异常: {e}")

        return {}

    async def fetch_futures(self) -> Dict[str, MarketData]:
        """获取期货数据"""
        return await self.fetch(list(FUTURES_CODES.keys()))

    async def fetch_us_stocks(self) -> Dict[str, MarketData]:
        """获取美股数据"""
        return await self.fetch(list(_get_us_stock_codes().keys()))

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
