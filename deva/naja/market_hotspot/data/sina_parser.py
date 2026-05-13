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
from functools import wraps
import time

import pandas as pd

# 提前导入 aiohttp，避免作用域问题
import aiohttp

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 重试装饰器
# ---------------------------------------------------------------------------

def async_retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """异步重试装饰器
    
    Args:
        retries: 最大重试次数
        delay: 初始延迟（秒）
        backoff: 退避因子
        exceptions: 可重试的异常类型
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            _delay = delay
            last_exception = None
            
            for attempt in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == retries:
                        log.warning(f"[async_retry] 达到最大重试次数 {retries}，放弃重试: {e}")
                        break
                    
                    log.warning(f"[async_retry] 尝试 {attempt + 1}/{retries + 1} 失败: {e}，等待 {_delay:.1f}s 后重试...")
                    await asyncio.sleep(_delay)
                    _delay *= backoff
            
            raise last_exception
        
        return wrapper
    return decorator

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
            connector=aiohttp.TCPConnector(
                limit=50,
                limit_per_host=10,
                force_close=True,
                enable_cleanup_closed=True
            ),
            timeout=aiohttp.ClientTimeout(
                total=60,
                connect=10,
                sock_read=30,
                sock_connect=10
            ),
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
    
    # 如果没有提供 session，创建一个临时 session
    if session is None:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=50,
                limit_per_host=10,
                force_close=True,
                enable_cleanup_closed=True
            ),
            timeout=aiohttp.ClientTimeout(
                total=60,
                connect=10,
                sock_read=30,
                sock_connect=10
            ),
        ) as temp_session:
            return await _fetch_sina_batch_with_session(codes, temp_session)
    else:
        return await _fetch_sina_batch_with_session(codes, session)

@async_retry(
    retries=3,
    delay=1.0,
    backoff=2.0,
    exceptions=(
        ConnectionResetError,
        aiohttp.ClientError,
        asyncio.TimeoutError
    )
)
async def _fetch_sina_batch_with_session(codes: List[str], session) -> Dict:
    """使用指定 session 获取一批股票数据（带重试）"""
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
    except (ConnectionResetError, aiohttp.ClientError, asyncio.TimeoutError) as e:
        # 这些异常会被重试装饰器捕获并重试
        log.warning(f"[_fetch_sina_batch_async] 可重试错误: {e}")
        raise  # 重新抛出，让重试装饰器处理
    except Exception as e:
        import traceback
        log.error(f"[_fetch_sina_batch_async] 不可重试错误: {e}")
        log.error(f"[_fetch_sina_batch_async] 堆栈: {traceback.format_exc()}")
        return {}


# ---------------------------------------------------------------------------
# A股代码获取 + 全量异步获取
# ---------------------------------------------------------------------------

def _get_cn_codes_from_registry():
    """从 BlockDictionary 获取 A 股代码列表（仅活跃股票）"""
    try:
        from deva.naja.dictionary.blocks import get_block_dictionary
        bd = get_block_dictionary()
        codes = list(bd.get_active_stocks('CN'))
        if codes:
            log.info(f"[_get_cn_codes_from_registry] 从 BlockDictionary 获取到 {len(codes)} 只活跃A股")
            return codes
    except Exception as e:
        log.warning(f"[_get_cn_codes_from_registry] 获取失败: {e}")
    return None


async def _fetch_all_stocks_async() -> Optional[pd.DataFrame]:
    """异步获取全量股票数据"""
    log.debug(f"[ASYNC] _fetch_all_stocks_async 开始, PID={os.getpid()}")
    log.debug(f"[_fetch_all_stocks_async] 开始获取...")

    codes = _get_cn_codes_from_registry()
    if not codes:
        log.error("[_fetch_all_stocks_async] StockRegistry 为空，无法获取股票代码列表")
        return None

    log.debug(f"[ASYNC] 股票代码总数: {len(codes)}")
    log.debug(f"[_fetch_all_stocks_async] 股票代码总数: {len(codes)}")

    batch_size = 800
    all_data = {}

    log.debug(f"[ASYNC] 创建 ClientSession...")
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(
            limit=50,
            limit_per_host=10,
            force_close=True,
            enable_cleanup_closed=True
        ),
        timeout=aiohttp.ClientTimeout(
            total=60,
            connect=10,
            sock_read=30,
            sock_connect=10
        ),
    ) as session:
        log.debug(f"[ASYNC] ClientSession 创建成功，开始获取批次...")
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            log.debug(f"[ASYNC] 获取批次 {i//batch_size + 1}, 代码数: {len(batch)}")
            batch_data = await _fetch_sina_batch_async(batch, session)
            log.debug(f"[ASYNC] 批次 {i//batch_size + 1} 返回: {len(batch_data)} 条")
            log.debug(f"[_fetch_all_stocks_async] 批次 {i//batch_size + 1} 返回: {len(batch_data)} 条")
            all_data.update(batch_data)
            await asyncio.sleep(0.1)  # 稍微增加延迟，避免请求过快

    log.debug(f"[ASYNC] 所有批次获取完成，总共: {len(all_data)} 条")
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
    log.debug(f"[SINA_SYNC] 开始 PID={os.getpid()}")
    try:
        log.debug("[_fetch_sina_sync] 开始获取 Sina 数据")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        log.debug("[SINA_SYNC] 创建事件循环完成")
        try:
            result = loop.run_until_complete(_fetch_all_stocks_async())
            log.debug(f"[SINA_SYNC] run_until_complete 完成, result={len(result) if result is not None else None}")
            if result is not None:
                log.debug(f"[_fetch_sina_sync] 获取完成: result={type(result)}, len={len(result)}")
            else:
                log.debug("[_fetch_sina_sync] 获取完成: result is None")
            return result
        finally:
            loop.close()
            log.debug("[SINA_SYNC] 事件循环已关闭")
    except Exception as e:
        log.error(f"[SINA_SYNC] 异常: {e}")
        log.error(f"[_fetch_sina_sync] 异常: {e}")
        import traceback
        log.error(traceback.format_exc())
        return None


def _fetch_sina_by_symbols_sync(symbols: List[str]) -> Optional[pd.DataFrame]:
    """同步获取指定 symbols 的 Sina 数据（在子线程中调用）"""
    if not symbols:
        return None
    log.debug(f"[SINA_SYNC_SYMBOLS] 开始 PID={os.getpid()}, symbols数量={len(symbols)}")
    try:
        log.debug(f"[_fetch_sina_by_symbols_sync] 开始获取 {len(symbols)} 只股票")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_fetch_sina_batch_async(symbols))
            log.debug(f"[SINA_SYNC_SYMBOLS] 完成, result={len(result) if result else 0} 条")
            if result:
                df = pd.DataFrame(result).T
                return df
            return None
        finally:
            loop.close()
    except Exception as e:
        log.error(f"[SINA_SYNC_SYMBOLS] 异常: {e}")
        log.error(f"[_fetch_sina_by_symbols_sync] 异常: {e}")
        import traceback
        log.error(traceback.format_exc())
        return None
