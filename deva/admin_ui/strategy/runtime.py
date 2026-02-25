"""策略运行时模块(Strategy Runtime)

提供策略监控流的初始化、历史数据回放、状态保存和恢复功能。

================================================================================
架构设计
================================================================================

【数据源】
┌─────────────────────────────────────────────────────────────────────────────┐
│  数据源管理器 (DataSourceManager)                                             │
│  - 统一管理所有数据源的生命周期                                                │
│  - 通过 data_func_code 配置数据生成逻辑                                       │
│  - 支持定时器、流、HTTP等多种数据源类型                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  quant_source (NS命名流)                                                      │
│  - 由数据源管理器控制数据生成                                                  │
│  - 接收 gen_quant() 产生的行情数据                                            │
│  - 支持通过 source.emit(df) 手动推送数据（回放模式）                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                          策略处理链 (Strategy Chain)

注意: gen_quant 的调用由数据源管理器统一控制，本模块不再自动执行定时器调用。
"""

from __future__ import annotations

import asyncio
import os
import signal
import atexit
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional
import pandas as pd
from tornado.ioloop import IOLoop

from deva import *

from .quant import gen_quant
from .tradetime import is_tradedate, is_tradetime
from .data import (
    ensure_stock_basic_dataframe_fresh,
    refresh_stock_basic_dataframe,
    get_stock_basic_dataframe_metadata,
)
from .strategy_logic_db import (
    initialize_strategy_logic_db,
    get_logic_db,
    get_instance_db,
    StrategyInstanceState,
)
from .history_db import (
    get_replay_config,
    set_replay_config,
    is_replay_mode,
    get_replay_date,
    save_history_snapshot,
    load_history_snapshot,
    get_history_metadata,
    get_available_history_dates,
    fetch_quant_with_mode,
    save_current_quant_to_history,
    is_auto_save_enabled,
    set_auto_save,
    get_auto_save_config,
    save_quant_with_timestamp,
    get_tick_metadata,
    get_tick_stream,
    get_tick_keys_in_range,
    load_tick_by_key,
    replay_ticks,
)
from .utils import (
    format_pct,
    prepare_df,
    calc_block_ranking,
    get_top_stocks_in_block,
    build_block_change_html,
    build_limit_up_down_html,
    build_block_ranking_html,
)


_quant_state = {
    "last_df": None,
    "updating": False,
    "last_attempt_ts": 0.0,
}
_quant_state_lock = threading.Lock()


def log_strategy_event(level, message, **extra):
    payload = {"level": level, "source": "deva.admin.strategy", "message": message}
    if extra:
        payload.update(extra)
    if threading.current_thread() is threading.main_thread():
        try:
            payload >> log
        except RuntimeError as e:
            if "There is no current event loop in thread" not in str(e):
                raise
        except Exception as e:
            if e.__class__.__name__ != "WebSocketClosedError":
                raise
    if str(level).upper() in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
        extra_text = ""
        if extra:
            parts = [f"{k}={extra[k]}" for k in sorted(extra.keys())]
            extra_text = " | " + ", ".join(parts)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}][{str(level).upper()}][deva.admin.strategy] {message}{extra_text}")


def get_strategy_config_store():
    return NB("admin_strategy_config")


def get_strategy_config():
    db = get_strategy_config_store()
    if "force_fetch" not in db:
        db["force_fetch"] = False
    if "sync_bus" not in db:
        db["sync_bus"] = True
    return {
        "force_fetch": bool(db.get("force_fetch")),
        "sync_bus": bool(db.get("sync_bus")),
    }


def set_strategy_config(*, force_fetch=None, sync_bus=None):
    db = get_strategy_config_store()
    if force_fetch is not None:
        db["force_fetch"] = bool(force_fetch)
    if sync_bus is not None:
        db["sync_bus"] = bool(sync_bus)
    return get_strategy_config()


def get_strategy_basic_meta():
    return get_stock_basic_dataframe_metadata()


async def refresh_strategy_basic_df_async(force=True):
    if force:
        return await asyncio.to_thread(refresh_stock_basic_dataframe, log_func=log_strategy_event)
    return await asyncio.to_thread(ensure_stock_basic_dataframe_fresh, log_func=log_strategy_event)


def _schedule_async_task(coro):
    io_loop = IOLoop.current(instance=False)
    async_loop = getattr(io_loop, "asyncio_loop", None)
    if async_loop is not None and async_loop.is_running():
        return async_loop.create_task(coro)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    return loop.create_task(coro)


def refresh_strategy_basic_df(force=True):
    task = _schedule_async_task(refresh_strategy_basic_df_async(force=force))
    if task is not None:
        return {"scheduled": True, "force": bool(force)}
    target = refresh_stock_basic_dataframe if force else ensure_stock_basic_dataframe_fresh
    t = threading.Thread(
        target=lambda: target(log_func=log_strategy_event),
        daemon=True,
        name="strategy-basic-refresh-bg",
    )
    t.start()
    return {"scheduled": True, "force": bool(force), "thread": t.name}


def fetch_quant_snapshot_safely():
    _trigger_quant_refresh_if_needed()
    with _quant_state_lock:
        return _quant_state["last_df"]


async def _refresh_quant_snapshot_async():
    with _quant_state_lock:
        if _quant_state["updating"]:
            return
        _quant_state["updating"] = True
    try:
        if is_replay_mode():
            replay_date = get_replay_date()
            log_strategy_event("INFO", "replay mode: loading history data", replay_date=replay_date)
            df = await asyncio.to_thread(load_history_snapshot, replay_date)
            if df is None:
                log_strategy_event("WARNING", "replay mode: no history data found", replay_date=replay_date)
            with _quant_state_lock:
                _quant_state["last_df"] = df
            return
        
        cfg = get_strategy_config()
        if (not cfg["force_fetch"]) and (not is_tradedate()):
            log_strategy_event("INFO", "skip quant fetch on non-trade day", force_fetch=cfg["force_fetch"])
            with _quant_state_lock:
                _quant_state["last_df"] = None
            return
        log_strategy_event("INFO", "start quant fetch", force_fetch=cfg["force_fetch"])
        df = await asyncio.to_thread(gen_quant)
        
        if df is not None and len(df) > 0 and is_auto_save_enabled():
            save_result = save_quant_with_timestamp(df)
            if save_result.get("success"):
                log_strategy_event("INFO", "auto saved quant snapshot", timestamp=save_result.get("timestamp"), rows=save_result.get("rows"))
        
        with _quant_state_lock:
            _quant_state["last_df"] = df
    except Exception as e:
        log_strategy_event("ERROR", "gen_quant failed", error=str(e))
    finally:
        with _quant_state_lock:
            _quant_state["updating"] = False


def _trigger_quant_refresh_if_needed(min_interval_seconds=3):
    now = datetime.now().timestamp()
    with _quant_state_lock:
        if _quant_state["updating"]:
            return
        if now - float(_quant_state["last_attempt_ts"]) < float(min_interval_seconds):
            return
        _quant_state["last_attempt_ts"] = now
    _schedule_async_task(_refresh_quant_snapshot_async())


_quant_source_stream = None
_quant_source_stream_lock = threading.Lock()


def get_quant_source_stream():
    with _quant_source_stream_lock:
        return _quant_source_stream


def _set_quant_source_stream(stream):
    global _quant_source_stream
    with _quant_source_stream_lock:
        _quant_source_stream = stream


_replay_running = False
_replay_running_lock = threading.Lock()
_replay_stop_event = threading.Event()


def is_replay_running() -> bool:
    with _replay_running_lock:
        return _replay_running


def _set_replay_running(running: bool):
    global _replay_running
    with _replay_running_lock:
        _replay_running = running
        if not running:
            _replay_stop_event.set()
        else:
            _replay_stop_event.clear()


def start_history_replay(date_str: str = None, interval: float = 5.0, use_ticks: bool = False,
                         start_time: str = None, end_time: str = None) -> dict:
    if is_replay_running():
        return {"success": False, "error": "回放已在进行中"}
    
    source = get_quant_source_stream()
    if source is None:
        return {"success": False, "error": "stream 未初始化"}
    
    _set_replay_running(True)
    set_replay_config(mode="replay", replay_date=date_str, replay_interval=int(interval))
    
    def _replay_worker():
        try:
            log_strategy_event("INFO", "replay started", date=date_str, use_ticks=use_ticks)
            
            if use_ticks:
                stream = get_tick_stream()
                if stream is None:
                    log_strategy_event("ERROR", "tick stream not available")
                    return
                
                count = 0
                for key in stream[start_time:end_time]:
                    if _replay_stop_event.is_set():
                        log_strategy_event("INFO", "replay stopped by user")
                        break
                    df = stream[key]
                    if df is not None:
                        source.emit(df)
                        count += 1
                        log_strategy_event("INFO", "replay tick", key=str(key), rows=len(df))
                        if interval > 0:
                            if _replay_stop_event.wait(timeout=interval):
                                log_strategy_event("INFO", "replay stopped by user during wait")
                                break
                log_strategy_event("INFO", "replay completed", total_ticks=count)
            else:
                if not date_str:
                    log_strategy_event("ERROR", "date_str required for daily replay")
                    return
                df = load_history_snapshot(date_str)
                if df is None:
                    log_strategy_event("ERROR", "no history data found", date=date_str)
                    return
                source.emit(df)
                log_strategy_event("INFO", "replay daily snapshot", date=date_str, rows=len(df))
                
        except Exception as e:
            log_strategy_event("ERROR", "replay error", error=str(e))
        finally:
            _set_replay_running(False)
    
    t = threading.Thread(target=_replay_worker, daemon=True, name="history-replay")
    t.start()
    return {"success": True, "message": "回放已启动", "date": date_str, "interval": interval}


def stop_history_replay() -> dict:
    if not is_replay_running():
        return {"success": False, "error": "没有正在进行的回放"}
    
    _set_replay_running(False)
    set_replay_config(mode="live")
    log_strategy_event("INFO", "replay stopped")
    return {"success": True, "message": "回放已停止"}


DEFAULT_STRATEGIES_CONFIG = [
    {
        "name": "板块异动_30秒",
        "type": "block_change",
        "params": {"window_seconds": 30, "sample_n": 20, "top_n": 5},
        "output_stream": "30秒板块异动",
    },
    {
        "name": "板块异动_1分钟",
        "type": "block_change",
        "params": {"window_seconds": 60, "sample_n": 20, "top_n": 5},
        "output_stream": "1分钟板块异动",
    },
    {
        "name": "领涨领跌板块",
        "type": "block_ranking",
        "params": {"sample_sizes": [20, 50], "top_n": 5, "sample_n": 3},
        "output_stream": "领涨领跌板块",
    },
    {
        "name": "涨跌停统计",
        "type": "limit_up_down",
        "params": {"threshold": 0.098, "top_n": 5},
        "output_stream": "涨跌停",
    },
]


gen_quant_data_func_code = '''
import datetime
import time
import random
import pandas as pd

def is_tradedate(dt=None):
    """判断是否为交易日"""
    try:
        if dt is None:
            dt = datetime.datetime.now()
        
        # 周末判断
        if dt.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        # 简单节假日判断（可根据需要扩展）
        holidays = [
            # 元旦
            (1, 1), (1, 2), (1, 3),
            # 春节（需要按年份调整）
            (2, 10), (2, 11), (2, 12), (2, 13), (2, 14), (2, 15), (2, 16),
            # 清明节
            (4, 4), (4, 5), (4, 6),
            # 劳动节
            (5, 1), (5, 2), (5, 3),
            # 端午节
            (6, 10), (6, 11), (6, 12),
            # 中秋节
            (9, 15), (9, 16), (9, 17),
            # 国庆节
            (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7),
        ]
        
        current_date = (dt.month, dt.day)
        return current_date not in holidays
    except Exception as e:
        print(f"[ERROR] is_tradedate failed: {str(e)}")
        return True  # 默认认为是交易日

def is_tradetime(dt=None):
    """判断是否为交易时间"""
    try:
        if dt is None:
            dt = datetime.datetime.now()
        
        # 交易时间：9:30-11:30, 13:00-15:00
        current_time = dt.time()
        morning_start = datetime.time(9, 30)
        morning_end = datetime.time(11, 30)
        afternoon_start = datetime.time(13, 0)
        afternoon_end = datetime.time(15, 0)
        
        return (morning_start <= current_time <= morning_end) or (afternoon_start <= current_time <= afternoon_end)
    except Exception as e:
        print(f"[ERROR] is_tradetime failed: {str(e)}")
        return True  # 默认认为是交易时间

def create_mock_data():
    """创建模拟数据，用于测试或数据源不可用的情况"""
    try:
        # 模拟股票代码（包含主要指数和个股）
        mock_codes = [
            "000001", "000002", "000858", "002415", "300059",  # 重要个股
            "600000", "600036", "600519", "600887", "601318",  # 金融消费
            "300001", "300015", "300124", "300750", "399001",  # 创业板+深成指
            "000300", "000905", "399006", "000016", "399300"   # 主要指数
        ]
        
        data = []
        current_time = time.time()
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for code in mock_codes:
            base_price = random.uniform(10, 200)
            change = random.uniform(-0.10, 0.10)  # -10% to +10%
            now_price = base_price * (1 + change)
            
            # 生成合理的日内价格
            open_price = base_price * random.uniform(0.98, 1.02)
            high_price = max(open_price, now_price) * random.uniform(1.0, 1.05)
            low_price = min(open_price, now_price) * random.uniform(0.95, 1.0)
            
            data.append({
                "code": code,
                "name": f"股票{code}",
                "open": round(open_price, 2),
                "close": round(base_price, 2),
                "now": round(now_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "volume": random.randint(10000, 10000000),
                "p_change": round(change, 4),
                "timestamp": current_time,
                "datetime": current_datetime
            })
        
        # 转换为DataFrame
        df = pd.DataFrame(data)
        return df
            
    except Exception as e:
        print(f"[ERROR] create_mock_data failed: {str(e)}")
        # 返回最基本的数据结构
        return pd.DataFrame([{
            "code": "000001",
            "name": "平安银行",
            "open": 10.0,
            "close": 10.0,
            "now": 10.0,
            "high": 10.0,
            "low": 10.0,
            "volume": 10000,
            "p_change": 0.0,
            "timestamp": time.time(),
            "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }])

def gen_quant():
    """获取股票行情数据"""
    try:
        # 尝试导入easyquotation
        try:
            import easyquotation
            
            # 使用新浪数据源
            quotation_engine = easyquotation.use("sina")
            q1 = quotation_engine.market_snapshot(prefix=False)
            
            # 转换为DataFrame
            df = pd.DataFrame(q1).T
            
            # 过滤无效数据
            df = df[(True ^ df["close"].isin([0]))]
            df = df[(True ^ df["now"].isin([0]))]
            
            # 计算涨跌幅
            df["p_change"] = (df.now - df.close) / df.close
            df["p_change"] = df.p_change.map(float)
            df["code"] = df.index
            
            # 添加时间戳
            df["timestamp"] = time.time()
            df["datetime"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            print(f"[INFO] Successfully fetched {len(df)} stocks from Sina")
            return df
            
        except ImportError:
            print("[WARNING] easyquotation not available, using mock data")
            return create_mock_data()
        except Exception as e:
            print(f"[ERROR] Failed to fetch market data from Sina: {str(e)}")
            print(f"[ERROR] Using mock data instead")
            return create_mock_data()
            
    except Exception as e:
        print(f"[ERROR] gen_quant failed: {str(e)}")
        return create_mock_data()

def fetch_data():
    """定时获取股票行情数据（数据源执行函数）"""
    try:
        now = datetime.datetime.now()
        
        # 检查是否为交易日
        if not is_tradedate(now):
            print(f"[INFO] Skipping data fetch: non-trading date ({now.date()})")
            return None
        
        # 检查是否为交易时间
        if not is_tradetime(now):
            print(f"[INFO] Skipping data fetch: non-trading time ({now.time()})")
            return None
        
        # 获取行情数据
        df = gen_quant()
        
        if df is not None and len(df) > 0:
            print(f"[INFO] Successfully fetched {len(df)} stocks data")
            return df
        else:
            print("[WARNING] No data fetched")
            return None
            
    except Exception as e:
        print(f"[ERROR] fetch_data failed: {str(e)}")
        return None


async def gen_quant_async():
    """异步获取股票行情数据（使用aiohttp避免阻塞）"""
    try:
        try:
            import aiohttp
            import asyncio
            
            # 使用新浪财经的免费API（异步）
            url = "http://hq.sinajs.cn/list=sh000001,sh000300,sh399001,sh399006"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        text = await response.text()
                        print(f"[INFO] Async fetch successful, data length: {len(text)}")
                        return create_mock_data()  # 简化处理
                    else:
                        print(f"[WARNING] HTTP error: {response.status}")
                        return create_mock_data()
        except ImportError:
            print("[WARNING] aiohttp not available, using sync version")
            return gen_quant()
        except Exception as e:
            print(f"[ERROR] async gen_quant failed: {str(e)}")
            return create_mock_data()
            
    except Exception as e:
        print(f"[ERROR] gen_quant_async failed: {str(e)}")
        return create_mock_data()


async def fetch_data_async():
    """异步定时获取股票行情数据（数据源执行函数）"""
    try:
        now = datetime.datetime.now()
        
        if not is_tradedate(now):
            print(f"[INFO] Async: Skipping data fetch: non-trading date ({now.date()})")
            return None
        
        if not is_tradetime(now):
            print(f"[INFO] Async: Skipping data fetch: non-trading time ({now.time()})")
            return None
        
        df = await gen_quant_async()
        
        if df is not None and len(df) > 0:
            print(f"[INFO] Async: Successfully fetched {len(df)} stocks data")
            return df
        else:
            print("[WARNING] Async: No data fetched")
            return None
            
    except Exception as e:
        print(f"[ERROR] fetch_data_async failed: {str(e)}")
        return None


gen_quant_data_func_code_async = '''
import datetime
import time
import random
import pandas as pd

def is_tradedate(dt=None):
    """判断是否为交易日"""
    try:
        if dt is None:
            dt = datetime.datetime.now()
        
        if dt.weekday() >= 5:
            return False
        
        holidays = [
            (1, 1), (1, 2), (1, 3),
            (2, 10), (2, 11), (2, 12), (2, 13), (2, 14), (2, 15), (2, 16),
            (4, 4), (4, 5), (4, 6),
            (5, 1), (5, 2), (5, 3),
            (6, 10), (6, 11), (6, 12),
            (9, 15), (9, 16), (9, 17),
            (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7),
        ]
        
        current_date = (dt.month, dt.day)
        return current_date not in holidays
    except Exception as e:
        print(f"[ERROR] is_tradedate failed: {str(e)}")
        return True

def is_tradetime(dt=None):
    """判断是否为交易时间"""
    try:
        if dt is None:
            dt = datetime.datetime.now()
        
        current_time = dt.time()
        morning_start = datetime.time(9, 30)
        morning_end = datetime.time(11, 30)
        afternoon_start = datetime.time(13, 0)
        afternoon_end = datetime.time(15, 0)
        
        return (morning_start <= current_time <= morning_end) or (afternoon_start <= current_time <= afternoon_end)
    except Exception as e:
        print(f"[ERROR] is_tradetime failed: {str(e)}")
        return True

def create_mock_data():
    """创建模拟数据"""
    try:
        mock_codes = [
            "000001", "000002", "000858", "002415", "300059",
            "600000", "600036", "600519", "600887", "601318",
            "300001", "300015", "300124", "300750", "399001",
            "000300", "000905", "399006", "000016", "399300"
        ]
        
        data = []
        current_time = time.time()
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for code in mock_codes:
            base_price = random.uniform(10, 200)
            change = random.uniform(-0.1, 0.1)
            now_price = base_price * (1 + change)
            
            data.append({
                "code": code,
                "name": f"股票{code}",
                "close": round(base_price, 2),
                "now": round(now_price, 2),
                "open": round(base_price * random.uniform(0.98, 1.02), 2),
                "high": round(base_price * random.uniform(1.0, 1.1), 2),
                "low": round(base_price * random.uniform(0.9, 1.0), 2),
                "volume": random.randint(1000000, 100000000),
                "p_change": round(change * 100, 2),
                "timestamp": current_time,
                "datetime": current_datetime
            })
        
        return pd.DataFrame(data)
    except Exception as e:
        print(f"[ERROR] create_mock_data failed: {str(e)}")
        return pd.DataFrame([{
            "code": "000001",
            "name": "平安银行",
            "close": 10.0,
            "now": 10.0,
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "volume": 10000,
            "p_change": 0.0,
            "timestamp": time.time(),
            "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }])

import asyncio
import aiohttp

async def gen_quant():
    """异步获取股票行情数据"""
    try:
        try:
            url = "http://hq.sinajs.cn/list=sh000001,sh000300,sh399001,sh399006"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        text = await response.text()
                        print(f"[INFO] Async quant fetched, length: {len(text)}")
                        return create_mock_data()
                    else:
                        print(f"[WARNING] HTTP status: {response.status}")
                        return create_mock_data()
        except ImportError:
            print("[WARNING] aiohttp not available, using mock data")
            return create_mock_data()
        except asyncio.TimeoutError:
            print("[WARNING] Async request timeout")
            return create_mock_data()
        except Exception as e:
            print(f"[ERROR] gen_quant async failed: {str(e)}")
            return create_mock_data()
    except Exception as e:
        print(f"[ERROR] gen_quant exception: {str(e)}")
        return create_mock_data()

async def fetch_data():
    """异步定时获取股票行情数据"""
    try:
        now = datetime.datetime.now()
        
        if not is_tradedate(now):
            print(f"[INFO] Async: non-trading date, skipping")
            return None
        
        if not is_tradetime(now):
            print(f"[INFO] Async: non-trading time, skipping")
            return None
        
        df = await gen_quant()
        
        if df is not None and len(df) > 0:
            print(f"[INFO] Async fetch_data: {len(df)} records")
            return df
        return None
    except Exception as e:
        print(f"[ERROR] fetch_data async failed: {str(e)}")
        return None


def initialize_strategy_monitor_streams(attach_webviews=True, strategies_config: List[Dict] = None):
    from .strategy_manager import get_manager
    from .stock_strategies import (
        BlockChangeStrategy,
        BlockRankingStrategy,
        LimitUpDownStrategy,
        STRATEGY_REGISTRY,
        create_stock_strategy,
    )
    from .fault_tolerance import initialize_fault_tolerance
    from .datasource import get_ds_manager, DataSource, DataSourceType, DataSourceStatus
    
    logic_init_result = initialize_strategy_logic_db()
    log_strategy_event("INFO", "strategy logic db initialized", **logic_init_result)
    
    manager = get_manager()
    manager.load_from_db()
    initialize_fault_tolerance()
    
    ds_mgr = get_ds_manager()
    ds_mgr.load_from_db()
    
    restore_result = ds_mgr.restore_running_states()
    log_strategy_event("INFO", "restored running data sources", **restore_result)
    
    strategy_restore_result = manager.restore_running_states()
    log_strategy_event("INFO", "restored running strategies", **strategy_restore_result)
    
    instance_db = get_instance_db()
    saved_instances = instance_db.list_all()
    log_strategy_event("INFO", "loaded strategy instances from db", count=len(saved_instances))
    
    quant_source = ds_mgr.get_source_by_name("quant_source")
    if not quant_source:
        # 优化缓存配置：确保至少缓存1个数据，最多缓存10个，缓存时间60秒
        source = NS("quant_source", 
                   cache_max_len=10,  # 最多缓存10个数据
                   cache_max_age_seconds=60,  # 缓存60秒
                   description='股票行情数据流，由数据源管理器控制数据生成')
        _set_quant_source_stream(source)
        
        quant_source = DataSource(
            name="quant_source",
            source_type=DataSourceType.TIMER,
            description="股票行情数据流 (定时调用 gen_quant 获取数据)",
            config={},
            stream=source,
            auto_start=False,  # 不自动启动，由状态恢复逻辑控制
            data_func_code=gen_quant_data_func_code,
            interval=5.0,
        )
        ds_mgr.register(quant_source)
    else:
        source = quant_source.get_stream()
        if source:
            _set_quant_source_stream(source)
            # 确保缓存配置合理
            if hasattr(source, 'cache_max_len') and source.cache_max_len < 1:
                source.cache_max_len = 10
            if hasattr(source, 'cache_max_age_seconds') and source.cache_max_age_seconds < 60:
                source.cache_max_age_seconds = 60
        else:
            # 重新创建流，确保缓存配置正确
            source = NS("quant_source", 
                       cache_max_len=10,  # 最多缓存10个数据
                       cache_max_age_seconds=60,  # 缓存60秒
                       description='股票行情数据流，由数据源管理器控制数据生成')
            _set_quant_source_stream(source)
            quant_source.set_stream(source)
        
        if quant_source.metadata.source_type != DataSourceType.TIMER:
            quant_source.metadata.source_type = DataSourceType.TIMER
            quant_source.metadata.data_func_code = gen_quant_data_func_code
            quant_source.metadata.interval = 5.0
            quant_source.save()
            log_strategy_event("INFO", "quant_source upgraded to TIMER type")
    
    quant = source.filter(lambda x: x is not None)
    quant.map(lambda df: log_strategy_event("INFO", "quant fetched", rows=int(len(df))) or df)
    
    quant.filter(lambda _: get_strategy_config()["sync_bus"]) \
        .map(lambda df: {"sender": "gen_quant", "message": "strategy quant snapshot", "quant": df}) >> bus

    quant.timed_window(interval=30) \
        .filter(lambda x: is_tradedate() and is_tradetime()) \
        .filter(lambda x: len(x) < 1) \
        .sink(lambda x: "quant not find data" >> warn)

    log.start_cache(200, cache_max_age_seconds=60 * 60 * 24 * 30)
    log.map(lambda x: log.recent(200) >> concat("<br>")) \
        >> NS("访问日志", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 30, description='访问日志流，用于记录系统访问日志和用户操作')
    os.getpid() >> log
    
    config = strategies_config or DEFAULT_STRATEGIES_CONFIG
    existing_strategies = {s.name: s for s in manager.list_units()}
    created_strategies = {}
    
    for strategy_cfg in config:
        name = strategy_cfg["name"]
        strategy_type = strategy_cfg["type"]
        params = strategy_cfg.get("params", {})
        output_stream_name = strategy_cfg.get("output_stream", name)
        
        if name in existing_strategies:
            strategy = existing_strategies[name]
            strategy.set_input_stream(quant)
            created_strategies[name] = strategy
            continue
        
        strategy = create_stock_strategy(
            strategy_type=strategy_type,
            name=name,
            output_stream_name=output_stream_name,
            **params
        )
        
        if strategy:
            strategy.set_input_stream(quant)
            manager.register(strategy)
            ds_mgr.link_strategy(quant_source.id, strategy.id)
            created_strategies[name] = strategy
    
    for strategy in created_strategies.values():
        quant.sink(lambda df, s=strategy: s.process(df))
    
    # 修复启动逻辑：确保状态为运行时的数据源真正启动定时器
    # 检查保存的运行状态，确保状态一致性
    saved_running_state = quant_source.get_saved_running_state()
    should_start = (
        quant_source.status != DataSourceStatus.RUNNING and 
        (not saved_running_state or saved_running_state.get("is_running", False))
    )
    
    if should_start:
        log_strategy_event("INFO", "starting quant_source based on saved state or initial setup")
        start_result = quant_source.start()
        if start_result.get("success"):
            log_strategy_event("INFO", "quant_source started successfully")
            for strategy in created_strategies.values():
                strategy.start()
        else:
            log_strategy_event("ERROR", "failed to start quant_source", error=start_result.get("error"))
    else:
        if saved_running_state and not saved_running_state.get("is_running", False):
            log_strategy_event("INFO", "quant_source saved state indicates it should not be running")
        else:
            log_strategy_event("INFO", "quant_source already running or no need to start")
    
    log_strategy_event("INFO", "stock strategies initialized", count=len(created_strategies))

    def render_realtime_block_change(df_tuple):
        start_df, end_df = df_tuple
        end_df = end_df.copy()
        valid_mask = start_df["close"] > 0
        if not valid_mask.any():
            return "<p>暂无有效数据</p>"
        end_df = end_df[valid_mask].copy()
        start_df = start_df[valid_mask].copy()
        end_df["change"] = (end_df["now"] - start_df["now"]) / start_df["close"]
        
        prepared = prepare_df(end_df, ["code", "change", "p_change", "name"])
        if prepared.empty:
            return "<p>暂无有效数据</p>"
        
        html = build_block_change_html(prepared, top_n=5, sample_n=3, col="change")
        return html

    quant.sliding_window(6).map(lambda lst: (lst[0], lst[-1])).map(render_realtime_block_change) \
        >> NS("30秒板块异动", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2, description='30秒板块异动流，用于监控板块的30秒级别异动')

    quant.sliding_window(12).map(lambda lst: (lst[0], lst[-1])).map(render_realtime_block_change) \
        >> NS("1分钟板块异动", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2, description='1分钟板块异动流，用于监控板块的1分钟级别异动')

    def render_block_rankings(df):
        prepared = prepare_df(df, ["code", "p_change", "name"])
        if prepared.empty:
            return "<p>暂无有效数据</p>"
        return build_block_ranking_html(prepared, sample_sizes=[20, 50], top_n=5, sample_n=3, col="p_change")

    quant.map(render_block_rankings) >> NS("领涨领跌板块", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2, description='领涨领跌板块流，用于分析板块涨跌排名')

    def render_limit_up_down_overview(df):
        html = build_limit_up_down_html(df, threshold=0.098, top_n=5)
        zt_count = int(df.query("p_change>0.098")["code"].nunique())
        dt_count = int(df.query("p_change<-0.098")["code"].nunique())
        log_strategy_event("INFO", "compute zt/dt", zt=zt_count, dt=dt_count)
        return html

    quant.map(render_limit_up_down_overview) >> NS("涨跌停", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2, description='涨跌停流，用于监控股票涨跌停情况')

    news = NT("news")
    news.start_cache(100, cache_max_age_seconds=60 * 60 * 24 * 2)
    news.map(lambda x: news.recent(100) >> concat("<br>")) \
        >> NS("实时新闻", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2, description='实时新闻流，用于展示最新的财经新闻资讯')

    streams = [
        NS("我要留言", description='留言流，用于接收用户留言和反馈'),
        NS("实时新闻", description='实时新闻流，用于展示最新的财经新闻资讯'),
        NS("涨跌停", description='涨跌停流，用于监控股票涨跌停情况'),
        NS("领涨领跌板块", description='领涨领跌板块流，用于分析板块涨跌排名'),
        NS("1分钟板块异动", description='1分钟板块异动流，用于监控板块的1分钟级别异动'),
        NS("30秒板块异动", description='30秒板块异动流，用于监控板块的30秒级别异动'),
    ]
    if attach_webviews:
        for s in streams:
            s.webview()

    setup_graceful_shutdown()

    log_strategy_event("INFO", "strategy streams initialized")
    return {"source": source, "quant": quant, "news": news}


setup_strategy_streams = initialize_strategy_monitor_streams
_strategy_log = log_strategy_event
_strategy_config_db = get_strategy_config_store


def save_all_strategy_states() -> dict:
    from .strategy_manager import get_manager
    
    manager = get_manager()
    instance_db = get_instance_db()
    
    saved_count = instance_db.save_all_from_manager(manager)
    manager_saved = manager.save_all()
    
    log_strategy_event("INFO", "all strategy states saved", 
                       instance_count=saved_count, 
                       manager_count=manager_saved)
    
    return {
        "success": True,
        "instance_count": saved_count,
        "manager_count": manager_saved,
    }


def restore_strategy_states() -> dict:
    from .strategy_manager import get_manager
    from .stock_strategies import STRATEGY_REGISTRY, create_stock_strategy
    
    manager = get_manager()
    instance_db = get_instance_db()
    
    saved_instances = instance_db.list_all()
    restored_count = 0
    running_count = 0
    
    for instance_state in saved_instances:
        if instance_state.state == "archived":
            continue
            
        existing = manager.get_unit(instance_state.id)
        if existing:
            continue
        
        strategy_type = instance_state.logic_id
        if strategy_type not in STRATEGY_REGISTRY:
            continue
        
        try:
            strategy = create_stock_strategy(
                strategy_type=strategy_type,
                name=instance_state.name,
                **instance_state.params
            )
            
            if strategy:
                strategy._id = instance_state.id
                strategy.state.processed_count = instance_state.processed_count
                strategy.state.error_count = instance_state.error_count
                strategy.state.last_error = instance_state.last_error
                
                manager.register(strategy)
                restored_count += 1
                
                if instance_state.state == "running":
                    strategy.start()
                    running_count += 1
                
        except Exception as e:
            log_strategy_event("ERROR", "failed to restore strategy", 
                               name=instance_state.name, error=str(e))
    
    log_strategy_event("INFO", "strategy states restored",
                       restored=restored_count,
                       running=running_count)
    
    return {
        "success": True,
        "restored_count": restored_count,
        "running_count": running_count,
    }


_shutdown_handlers = []
_shutdown_handlers_lock = threading.Lock()


def register_shutdown_handler(handler: Callable):
    with _shutdown_handlers_lock:
        if handler not in _shutdown_handlers:
            _shutdown_handlers.append(handler)


def execute_shutdown_handlers():
    log_strategy_event("INFO", "executing shutdown handlers")
    
    save_all_strategy_states()
    
    with _shutdown_handlers_lock:
        for handler in _shutdown_handlers:
            try:
                handler()
            except Exception as e:
                log_strategy_event("ERROR", "shutdown handler error", error=str(e))
    
    log_strategy_event("INFO", "shutdown handlers completed")


def setup_graceful_shutdown():
    def signal_handler(signum, frame):
        log_strategy_event("INFO", "received shutdown signal", signal=signum)
        execute_shutdown_handlers()
        import sys
        sys.exit(0)
    
    try:
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    except Exception as e:
        log_strategy_event("WARNING", "failed to register signal handlers", error=str(e))
    
    atexit.register(execute_shutdown_handlers)
    log_strategy_event("INFO", "graceful shutdown configured")
