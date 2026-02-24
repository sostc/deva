"""History stock data storage and replay for admin runtime."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, List

import pandas as pd
from walrus import Database

from deva import NB, DBStream

_db = Database()
_history_cache = _db.cache(name="stock_history_data")

_history_meta_db = NB("stock_history_meta")
_history_data_db = NB("stock_history_data")

_quant_tick_stream = None
_quant_tick_stream_lock = threading.Lock()


def _get_quant_tick_stream():
    """获取行情时间戳数据流（延迟初始化）"""
    global _quant_tick_stream
    if _quant_tick_stream is None:
        with _quant_tick_stream_lock:
            if _quant_tick_stream is None:
                _quant_tick_stream = DBStream(
                    name="stock_quant_ticks",
                    key_mode="time",
                    time_dict_policy="append",
                )
    return _quant_tick_stream


def _date_key(date_str: str) -> str:
    return f"hist:{date_str}"


def get_available_history_dates() -> List[str]:
    """获取所有可用的历史数据日期列表"""
    meta = _history_meta_db.get("available_dates", [])
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except Exception:
            return []
    return meta if isinstance(meta, list) else []


def _save_available_dates(dates: List[str]):
    _history_meta_db["available_dates"] = json.dumps(sorted(set(dates)))


def save_history_snapshot(df: pd.DataFrame, date_str: Optional[str] = None) -> dict:
    """
    保存历史行情快照到数据库
    
    参数:
        df: 行情 DataFrame (来自 gen_quant)
        date_str: 日期字符串 YYYY-MM-DD 格式，默认使用今天
    
    返回:
        保存结果信息
    """
    if df is None or len(df) == 0:
        return {"success": False, "error": "DataFrame is empty"}
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    try:
        key = _date_key(date_str)
        _history_data_db[key] = df
        
        dates = get_available_history_dates()
        if date_str not in dates:
            dates.append(date_str)
            _save_available_dates(dates)
        
        return {
            "success": True,
            "date": date_str,
            "rows": len(df),
            "columns": list(df.columns),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def load_history_snapshot(date_str: str) -> Optional[pd.DataFrame]:
    """
    从数据库加载指定日期的历史行情
    
    参数:
        date_str: 日期字符串 YYYY-MM-DD 格式
    
    返回:
        DataFrame 或 None
    """
    try:
        key = _date_key(date_str)
        df = _history_data_db.get(key)
        if df is None:
            return None
        if isinstance(df, bytes):
            import pickle
            df = pickle.loads(df)
        return df
    except Exception as e:
        print(f"[stock_history] load_history_snapshot error: {e}")
        return None


def delete_history_snapshot(date_str: str) -> dict:
    """删除指定日期的历史数据"""
    try:
        key = _date_key(date_str)
        if key in _history_data_db:
            del _history_data_db[key]
        
        dates = get_available_history_dates()
        if date_str in dates:
            dates.remove(date_str)
            _save_available_dates(dates)
        
        return {"success": True, "date": date_str}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_history_metadata() -> dict:
    """获取历史数据库元信息（不遍历数据，避免阻塞）"""
    dates = get_available_history_dates()
    return {
        "total_dates": len(dates),
        "dates": sorted(dates, reverse=True),
        "details": [],
    }


_replay_state = {
    "mode": "live",
    "replay_date": None,
    "replay_interval": 5,
    "replay_start": None,
    "replay_end": None,
}
_replay_state_lock = threading.Lock()

_auto_save_state = {
    "enabled": False,
    "last_save_ts": None,
}
_auto_save_state_lock = threading.Lock()


def is_auto_save_enabled() -> bool:
    """检查是否开启自动保存"""
    with _auto_save_state_lock:
        return _auto_save_state["enabled"]


def set_auto_save(enabled: bool) -> dict:
    """设置自动保存开关"""
    with _auto_save_state_lock:
        _auto_save_state["enabled"] = bool(enabled)
        return {"auto_save": _auto_save_state["enabled"]}


def get_auto_save_config() -> dict:
    """获取自动保存配置"""
    with _auto_save_state_lock:
        return {
            "enabled": _auto_save_state["enabled"],
            "last_save_ts": _auto_save_state["last_save_ts"],
        }


def save_quant_with_timestamp(df: pd.DataFrame) -> dict:
    """
    按时间戳保存行情快照到 DBStream，支持回放
    
    参数:
        df: 行情 DataFrame (来自 gen_quant)
    
    返回:
        保存结果信息
    """
    if df is None or len(df) == 0:
        return {"success": False, "error": "DataFrame is empty"}
    
    now = datetime.now()
    timestamp_key = now.strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        stream = _get_quant_tick_stream()
        store_key = stream.append(df)
        
        with _auto_save_state_lock:
            _auto_save_state["last_save_ts"] = timestamp_key
        
        return {
            "success": True,
            "timestamp": timestamp_key,
            "store_key": store_key,
            "rows": len(df),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_tick_stream():
    """获取行情时间戳数据流"""
    return _get_quant_tick_stream()


def get_tick_keys_in_range(start: str, end: str = None) -> List:
    """
    获取时间范围内的所有 key
    
    参数:
        start: 开始时间 'YYYY-MM-DD HH:MM:SS'
        end: 结束时间 'YYYY-MM-DD HH:MM:SS'，默认为当前时间
    
    返回:
        key 列表
    """
    stream = _get_quant_tick_stream()
    return list(stream[start:end])


def load_tick_by_key(key) -> Optional[pd.DataFrame]:
    """
    根据 key 加载行情快照
    
    参数:
        key: DBStream 中的 key（时间戳）
    
    返回:
        DataFrame 或 None
    """
    try:
        stream = _get_quant_tick_stream()
        df = stream[key]
        if df is None:
            return None
        return df
    except Exception as e:
        print(f"[stock_history] load_tick_by_key error: {e}")
        return None


def get_tick_metadata() -> dict:
    """获取按时间戳保存的数据元信息（仅返回基本信息，避免阻塞）"""
    stream = _get_quant_tick_stream()
    try:
        total_ticks = len(stream)
    except Exception:
        total_ticks = 0
    
    return {
        "total_dates": 0,
        "total_ticks": total_ticks,
        "dates": [],
        "details": [],
    }


def replay_ticks(start: str, end: str = None, interval: float = None, stop_event: threading.Event = None):
    """
    回放指定时间范围内的行情数据
    
    参数:
        start: 开始时间 'YYYY-MM-DD HH:MM:SS'
        end: 结束时间 'YYYY-MM-DD HH:MM:SS'，默认为当前时间
        interval: 回放间隔（秒），默认使用配置的 replay_interval
        stop_event: 可选的停止事件，用于中断回放
    
    Yields:
        (key, DataFrame) 元组
    """
    stream = _get_quant_tick_stream()
    if interval is None:
        interval = get_replay_config().get("replay_interval", 5)
    
    for key in stream[start:end]:
        if stop_event is not None and stop_event.is_set():
            break
        df = stream[key]
        if df is not None:
            yield (key, df)
            if interval > 0:
                if stop_event is not None:
                    if stop_event.wait(timeout=interval):
                        break
                else:
                    time.sleep(interval)


def get_replay_config() -> dict:
    """获取回放配置"""
    with _replay_state_lock:
        return {
            "mode": _replay_state["mode"],
            "replay_date": _replay_state["replay_date"],
            "replay_interval": _replay_state["replay_interval"],
            "replay_start": _replay_state["replay_start"],
            "replay_end": _replay_state["replay_end"],
        }


def set_replay_config(*, mode: str = None, replay_date: str = None, 
                      replay_interval: int = None, replay_start: str = None,
                      replay_end: str = None) -> dict:
    """
    设置回放配置
    
    参数:
        mode: "live" 实盘模式 或 "replay" 回放模式
        replay_date: 回放日期 YYYY-MM-DD
        replay_interval: 回放间隔(秒)
        replay_start: 回放开始时间 'YYYY-MM-DD HH:MM:SS'
        replay_end: 回放结束时间 'YYYY-MM-DD HH:MM:SS'
    """
    with _replay_state_lock:
        if mode is not None:
            if mode not in ("live", "replay"):
                raise ValueError("mode must be 'live' or 'replay'")
            _replay_state["mode"] = mode
        if replay_date is not None:
            _replay_state["replay_date"] = replay_date
        if replay_interval is not None:
            _replay_state["replay_interval"] = max(1, int(replay_interval))
        if replay_start is not None:
            _replay_state["replay_start"] = replay_start
        if replay_end is not None:
            _replay_state["replay_end"] = replay_end
        return get_replay_config()


def is_replay_mode() -> bool:
    """检查是否处于回放模式"""
    with _replay_state_lock:
        return _replay_state["mode"] == "replay"


def get_replay_date() -> Optional[str]:
    """获取当前回放日期"""
    with _replay_state_lock:
        return _replay_state["replay_date"]


def save_current_quant_to_history() -> dict:
    """
    保存当前实盘数据到历史数据库
    用于在交易时段保存快照
    """
    from .quant import gen_quant
    try:
        df = gen_quant()
        if df is None or len(df) == 0:
            return {"success": False, "error": "No data from gen_quant"}
        return save_history_snapshot(df)
    except Exception as e:
        return {"success": False, "error": str(e)}


def fetch_quant_with_mode():
    """
    根据当前模式获取行情数据:
    - live 模式: 调用 gen_quant 获取实盘数据
    - replay 模式: 从历史数据库加载指定日期的数据
    """
    if is_replay_mode():
        replay_date = get_replay_date()
        if replay_date:
            df = load_history_snapshot(replay_date)
            if df is not None:
                return df
            print(f"[stock_history] No history data for {replay_date}, fallback to live")
    from .quant import gen_quant
    return gen_quant()
