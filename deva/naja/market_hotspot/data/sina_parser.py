"""
Sina 行情数据解析与获取

提供新浪行情源的底层 HTTP 能力：
- Session 管理（aiohttp 连接池）
- 响应解析（新浪特有文本格式 → dict）
- 异步批量获取
- A股全量获取（从 BlockDictionary 拿代码列表）
- 同步包装器（供子线程调用）
"""

import asyncio
import os
import logging
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session 管理
# ---------------------------------------------------------------------------

_session = None


def _get_sina_session():
    """获取全局 aiohttp session"""
    global _session
    if _session is None or _session.closed:
        import aiohttp
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=50, limit_per_host=20),
            timeout=aiohttp.ClientTimeout(total=30),
        )
    return _session


def _close_sina_session():
    """关闭全局 aiohttp session"""
    global _session
    if _session is not None and not _session.closed:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_session.close())
            else:
                loop.run_until_complete(_session.close())
        except Exception as e:
            log.warning(f"关闭 Sina session 失败: {e}")
        finally:
            _session = None


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def _parse_sina_response(text: str) -> Dict:
    """解析新浪返回的数据"""
    result = {}
    for line in text.strip().split("\n"):
        if not line or '="' not in line:
            continue
        try:
            prefix, data = line.split('="')
            code = prefix.split("_")[-1]
            data = data.rstrip('"')
            if not data:
                continue
            fields = data.split(",")
            if len(fields) < 33:
                continue
            result[code] = {
                "name": fields[0],
                "open": float(fields[1]),
                "close": float(fields[2]),
                "now": float(fields[3]),
                "high": float(fields[4]),
                "low": float(fields[5]),
                "volume": int(fields[8]),
                "amount": float(fields[9]) if len(fields) > 9 and fields[9] else 0.0,
            }
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
# 异步批量获取
# ---------------------------------------------------------------------------

async def _fetch_sina_batch_async(codes: List[str], session=None) -> Dict:
    """异步获取一批股票数据"""
    if not codes:
        return {}
    if session is None:
        session = _get_sina_session()
    codes_str = ",".join(codes)
    url = f"https://hq.sinajs.cn/list={codes_str}"
    headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    try:
        log.debug(f"[_fetch_sina_batch_async] 请求 Sina API: codes数量={len(codes)}")
        async with session.get(url, headers=headers) as resp:
            log.debug(f"[_fetch_sina_batch_async] 响应状态: status={resp.status}")
            if resp.status != 200:
                return {}
            text = await resp.text()
            log.debug(f"[_fetch_sina_batch_async] 响应长度: {len(text)}")
            return _parse_sina_response(text)
    except Exception as e:
        log.error(f"[_fetch_sina_batch_async] 请求失败: {e}")
        return {}


# ---------------------------------------------------------------------------
# A股代码获取 + 全量异步获取
# ---------------------------------------------------------------------------

def _get_cn_codes_from_registry():
    """从 BlockDictionary 获取 A 股代码列表"""
    try:
        from deva.naja.dictionary.blocks import get_block_dictionary
        bd = get_block_dictionary()
        codes = list(bd.get_all_stocks('CN'))
        if codes:
            log.info(f"[_get_cn_codes_from_registry] 从 BlockDictionary 获取到 {len(codes)} 只 A 股")
            return codes
    except Exception as e:
        log.warning(f"[_get_cn_codes_from_registry] 获取失败: {e}")
    return None


async def _fetch_all_stocks_async() -> Optional[pd.DataFrame]:
    """异步获取全量股票数据"""
    import aiohttp

    print(f"[ASYNC] _fetch_all_stocks_async 开始, PID={os.getpid()}", flush=True)
    log.debug(f"[_fetch_all_stocks_async] 开始获取...")

    codes = _get_cn_codes_from_registry()
    if not codes:
        log.error("[_fetch_all_stocks_async] StockRegistry 为空，无法获取股票代码列表")
        return None

    print(f"[ASYNC] 股票代码总数: {len(codes)}", flush=True)
    log.debug(f"[_fetch_all_stocks_async] 股票代码总数: {len(codes)}")

    batch_size = 800
    all_data = {}

    print(f"[ASYNC] 创建 ClientSession...", flush=True)
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=50, limit_per_host=20),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        print(f"[ASYNC] ClientSession 创建成功，开始获取批次...", flush=True)
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            print(f"[ASYNC] 获取批次 {i//batch_size + 1}, 代码数: {len(batch)}", flush=True)
            batch_data = await _fetch_sina_batch_async(batch, session)
            print(f"[ASYNC] 批次 {i//batch_size + 1} 返回: {len(batch_data)} 条", flush=True)
            log.debug(f"[_fetch_all_stocks_async] 批次 {i//batch_size + 1} 返回: {len(batch_data)} 条")
            all_data.update(batch_data)
            await asyncio.sleep(0.05)

    print(f"[ASYNC] 所有批次获取完成，总共: {len(all_data)} 条", flush=True)
    log.debug(f"[_fetch_all_stocks_async] 总共获取: {len(all_data)} 条数据")

    if not all_data:
        log.debug("[_fetch_all_stocks_async] 无数据返回")
        return None

    df = pd.DataFrame(all_data).T
    return df


# ---------------------------------------------------------------------------
# 同步包装器
# ---------------------------------------------------------------------------

def _fetch_sina_sync(force_trading: bool = False) -> Optional[pd.DataFrame]:
    """同步获取 Sina 全量数据（在子线程中调用）"""
    print(f"[SINA_SYNC] 开始 PID={os.getpid()}", flush=True)
    try:
        log.debug("[_fetch_sina_sync] 开始获取 Sina 数据")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print(f"[SINA_SYNC] 创建事件循环完成", flush=True)
        try:
            result = loop.run_until_complete(_fetch_all_stocks_async())
            print(f"[SINA_SYNC] run_until_complete 完成, result={len(result) if result is not None else None}", flush=True)
            if result is not None:
                log.debug(f"[_fetch_sina_sync] 获取完成: result={type(result)}, len={len(result)}")
            else:
                log.debug("[_fetch_sina_sync] 获取完成: result is None")
            return result
        finally:
            loop.close()
            print(f"[SINA_SYNC] 事件循环已关闭", flush=True)
    except Exception as e:
        print(f"[SINA_SYNC] 异常: {e}", flush=True)
        log.error(f"[_fetch_sina_sync] 异常: {e}")
        import traceback
        log.error(traceback.format_exc())
        return None


def _fetch_sina_by_symbols_sync(symbols: List[str]) -> Optional[pd.DataFrame]:
    """同步获取指定 symbols 的 Sina 数据（在子线程中调用）"""
    if not symbols:
        return None
    print(f"[SINA_SYNC_SYMBOLS] 开始 PID={os.getpid()}, symbols数量={len(symbols)}", flush=True)
    try:
        log.debug(f"[_fetch_sina_by_symbols_sync] 开始获取 {len(symbols)} 只股票")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_fetch_sina_batch_async(symbols))
            print(f"[SINA_SYNC_SYMBOLS] 完成, result={len(result) if result else 0} 条", flush=True)
            if result:
                df = pd.DataFrame(result).T
                return df
            return None
        finally:
            loop.close()
    except Exception as e:
        print(f"[SINA_SYNC_SYMBOLS] 异常: {e}", flush=True)
        log.error(f"[_fetch_sina_by_symbols_sync] 异常: {e}")
        import traceback
        log.error(traceback.format_exc())
        return None
