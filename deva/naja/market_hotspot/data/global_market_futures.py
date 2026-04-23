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
BATCH_SIZE = 50
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

INDEX_CODES = {
    "sh000001": "上证指数",
    "s_sh000300": "沪深300",
    "sz399006": "创业板",
}


def _get_china_codes() -> set:
    """获取A股代码集合（仅活跃股票）"""
    try:
        from deva.naja.dictionary.blocks import get_block_dictionary
        bd = get_block_dictionary()
        return set(bd.get_active_stocks('CN'))
    except Exception:
        return set()


def _get_us_stock_codes() -> Dict[str, str]:
    """从 BlockDictionary 获取美股代码（Sina格式：gb_nvda，仅活跃股票）"""
    try:
        from deva.naja.dictionary.blocks import get_block_dictionary
        bd = get_block_dictionary()
        us_codes = bd.get_active_stocks('US')
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
        us_codes = bd.get_active_stocks('US')
        return {f"gb_{code}": bd.get_stock_info(code).name for code in us_codes if bd.get_stock_info(code)}
    elif market == "a_share":
        cn_codes = bd.get_active_stocks('CN')
        return {code: bd.get_stock_info(code).name for code in cn_codes if bd.get_stock_info(code)}
    else:
        return {}


from deva.naja.bandit.stock_block_map import US_STOCK_BLOCKS

US_INDUSTRY_MAP = {
    code: info.get("industry_code", "other")
    for code, info in US_STOCK_BLOCKS.items()
}

US_INDUSTRY_LIST = list(dict.fromkeys(info.get("industry_code", "other") for info in US_STOCK_BLOCKS.values()))

# 构建只包含活跃美股的映射
_active_us_stocks = _get_us_stock_codes()
# 过滤掉已知无法获取数据的代码
_invalid_codes = {'gb_lucid', 'gb_lam', 'gb_netf', 'gb_googl_class_a', 'gb_ubnt'}
_valid_us_stocks = {code: name for code, name in _active_us_stocks.items() if code not in _invalid_codes}
_active_us_industry_map = {code: US_INDUSTRY_MAP.get(code, "other") for code in _valid_us_stocks}

ALL_CODES = {**FUTURES_CODES, **_active_us_industry_map}
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

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self):
        """关闭 session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            if self._session is not None and self._session.closed:
                self._session = None
            try:
                self._session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(limit=20, limit_per_host=10),
                    timeout=aiohttp.ClientTimeout(total=30),
                )
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    log.warning("[GlobalMarketAPI] 事件循环已关闭，将使用同步 requests fallback")
                    self._session = None
                    return None
                raise
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

    def _parse_index_line(self, line: str, sina_code: str) -> Optional[MarketData]:
        """解析指数数据行

        指数新浪数据格式（与A股不同）：
        - sh000001: name,current,prev_close,high,low,...
        - s_sh000300: name,price,change,change_pct,...
        """
        try:
            prefix, data = line.split('="')
            data = data.rstrip('"')
            if not data:
                return None
            fields = data.split(",")

            if len(fields) < 4:
                return None

            name = INDEX_CODES.get(sina_code, fields[0]) if fields[0] else INDEX_CODES.get(sina_code, sina_code)

            if sina_code == 'sh000001':
                current = float(fields[1]) if fields[1] else 0
                prev_close = float(fields[2]) if fields[2] else 0
                high = float(fields[3]) if fields[3] else 0
                low = float(fields[4]) if fields[4] else 0 if len(fields) > 4 else 0
                change = current - prev_close if current and prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0
                open_price = 0
            elif sina_code == 's_sh000300':
                current = float(fields[1]) if fields[1] else 0
                change = float(fields[2]) if fields[2] else 0
                change_pct = float(fields[3]) if fields[3] else 0
                prev_close = current - change if current and change else 0
                high = 0
                low = 0
                open_price = 0
            elif sina_code == 'sz399006':
                current = float(fields[1]) if fields[1] else 0
                prev_close = float(fields[2]) if fields[2] else 0
                high = float(fields[3]) if fields[3] else 0
                low = float(fields[4]) if len(fields) > 4 and fields[4] else 0
                change = current - prev_close if current and prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0
                open_price = 0
            else:
                return None

            return MarketData(
                code=sina_code,
                market_id=f"index:{sina_code}",
                name=name,
                current=current,
                open=open_price,
                high=high,
                low=low,
                prev_close=prev_close,
                change=change,
                change_pct=change_pct,
                volume=0,
                update_time="",
                update_date="",
                timestamp=datetime.now().timestamp(),
            )
        except Exception as e:
            log.debug(f"解析指数失败: {line[:50]}... error: {e}")
            return None

    def _parse_response(self, text: str, codes: List[str]) -> Dict[str, MarketData]:
        """解析响应"""
        result = {}
        futures_codes = set(FUTURES_CODES.keys())
        us_codes = set(_get_us_stock_codes().keys())
        china_codes = _get_china_codes()
        index_codes = set(INDEX_CODES.keys())
        
        # 构建美股代码映射（带gb_前缀和不带前缀）
        us_code_map = {}
        for code in us_codes:
            if code.startswith('gb_'):
                us_code_map[code] = code.split('_')[1]
                us_code_map[code.split('_')[1]] = code.split('_')[1]

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
                elif full_code in us_codes or code_part in us_code_map:
                    parsed = self._parse_us_stock_line(line)
                    if parsed:
                        result[code_part] = parsed
                elif full_code in index_codes:
                    parsed = self._parse_index_line(line, full_code)
                    if parsed:
                        result[full_code] = parsed
                elif full_code in china_codes:
                    parsed = self._parse_china_stock_line(line, full_code)
                    if parsed:
                        result[full_code] = parsed
            except Exception as e:
                log.debug(f"解析行失败: {line[:50]}... error: {e}")
                continue
        return result

    async def _fetch_batch(self, codes: List[str], session: aiohttp.ClientSession, max_retries: int = 3) -> Dict[str, MarketData]:
        """单批次获取（带重试）"""
        for attempt in range(1, max_retries + 1):
            try:
                codes_str = ",".join(codes)
                url = SINA_BASE_URL.format(codes=codes_str)

                async with session.get(url, headers=SINA_HEADERS) as resp:
                    if resp.status != 200:
                        if attempt < max_retries:
                            await asyncio.sleep(1 * attempt)
                            continue
                        return {}
                    text = await resp.text()
                    if not text or not text.strip():
                        if attempt < max_retries:
                            await asyncio.sleep(1 * attempt)
                            continue
                        return {}
                    return self._parse_response(text, codes)
            except asyncio.TimeoutError:
                if attempt < max_retries:
                    await asyncio.sleep(1 * attempt)
                    continue
                return {}
            except Exception:
                if attempt < max_retries:
                    await asyncio.sleep(1 * attempt)
                    continue
                return {}
        return {}

    async def _fetch_batch_sync(self, codes: List[str], max_retries: int = 3) -> Dict[str, MarketData]:
        """同步方式单批次获取（带重试）"""
        import requests as req
        for attempt in range(1, max_retries + 1):
            try:
                codes_str = ",".join(codes)
                url = SINA_BASE_URL.format(codes=codes_str)
                resp = req.get(url, headers=SINA_HEADERS, timeout=15)
                if resp.status_code == 200 and resp.text and resp.text.strip():
                    return self._parse_response(resp.text, codes)
                if attempt < max_retries:
                    await asyncio.sleep(1 * attempt)
                    continue
                return {}
            except Exception:
                if attempt < max_retries:
                    await asyncio.sleep(1 * attempt)
                    continue
                return {}
        return {}

    async def fetch(self, codes: Optional[List[str]] = None, max_retries: int = 3) -> Dict[str, MarketData]:
        """获取市场数据（分批获取 + 合并结果）"""
        codes_to_fetch = codes or self.codes
        if not codes_to_fetch:
            log.debug("获取市场数据跳过: 代码列表为空")
            return {}
        
        # 过滤掉已知无法获取数据的代码
        _invalid_codes = {'gb_lucid', 'gb_lam', 'gb_netf', 'gb_googl_class_a', 'gb_ubnt'}
        codes_to_fetch = [code for code in codes_to_fetch if code not in _invalid_codes]
        
        if not codes_to_fetch:
            log.debug("获取市场数据跳过: 过滤后代码列表为空")
            return {}

        batches = [codes_to_fetch[i:i + BATCH_SIZE] for i in range(0, len(codes_to_fetch), BATCH_SIZE)]
        if len(batches) > 1:
            log.info(f"[GlobalMarketAPI] 分 {len(batches)} 批获取市场数据, 每批最多 {BATCH_SIZE} 个")

        all_results = {}
        session = await self._get_session()

        for batch_idx, batch in enumerate(batches):
            if len(batches) > 1:
                log.debug(f"[GlobalMarketAPI] 获取第 {batch_idx + 1}/{len(batches)} 批 ({len(batch)} 个)")

            # 先尝试异步获取
            if session is not None:
                result = await self._fetch_batch(batch, session, max_retries)
                if result:
                    log.debug(f"[GlobalMarketAPI] 批次 {batch_idx + 1} 成功获取 {len(result)} 个数据")
                    all_results.update(result)
                else:
                    log.warning(f"[GlobalMarketAPI] 批次 {batch_idx + 1} 异步获取失败，跳过")
            else:
                log.warning(f"[GlobalMarketAPI] 批次 {batch_idx + 1} 无法获取 session，跳过")

            if batch_idx < len(batches) - 1:
                await asyncio.sleep(0.3)

        # 统计失败的代码
        success_codes = set(all_results.keys())
        failed_codes = [code for code in codes_to_fetch if code.split('_')[-1] not in success_codes]
        
        if not all_results:
            log.warning(f"[GlobalMarketAPI] 获取市场数据失败: 0 个结果")
        elif len(all_results) < len(codes_to_fetch):
            log.warning(f"[GlobalMarketAPI] 部分数据获取失败: 获取 {len(all_results)}/{len(codes_to_fetch)} 个, 失败代码: {failed_codes[:10]}...")
        else:
            log.info(f"[GlobalMarketAPI] 全部数据获取成功: {len(all_results)} 个")

        return all_results

    async def fetch_futures(self) -> Dict[str, MarketData]:
        """获取期货数据"""
        return await self.fetch(list(FUTURES_CODES.keys()))

    async def fetch_us_stocks(self) -> Dict[str, MarketData]:
        """获取美股数据"""
        return await self.fetch(list(_get_us_stock_codes().keys()))

    async def fetch_indices(self) -> Dict[str, MarketData]:
        """获取A股指数数据（上证指数、沪深300、创业板）"""
        return await self.fetch(list(INDEX_CODES.keys()))

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
    # 每次调用都重新创建实例，确保使用最新的代码列表
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
