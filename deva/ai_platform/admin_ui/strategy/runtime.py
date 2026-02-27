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
        cfg = get_strategy_config()
        if (not cfg["force_fetch"]) and (not is_tradedate()):
            log_strategy_event("INFO", "skip quant fetch on non-trade day",
                               force_fetch=cfg["force_fetch"])
            with _quant_state_lock:
                _quant_state["last_df"] = None
            return
        log_strategy_event("INFO", "start quant fetch", force_fetch=cfg["force_fetch"])
        df = await asyncio.to_thread(gen_quant)

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
    from ..datasource.datasource import get_ds_manager, DataSource, DataSourceType, DataSourceStatus, create_timer_source

    logic_init_result = initialize_strategy_logic_db()
    log_strategy_event("INFO", "strategy logic db initialized", **logic_init_result)

    manager = get_manager()
    manager.load_from_db()
    initialize_fault_tolerance()

    ds_mgr = get_ds_manager()
    ds_mgr.load_from_db()

    # 确保quant_source存在
    global quant, quant_source
    from ..datasource.datasource import quant, quant_source

    restore_result = ds_mgr.restore_running_states()
    log_strategy_event("INFO", "restored running data sources", **restore_result)

    instance_db = get_instance_db()
    saved_instances = instance_db.list_all()
    log_strategy_event("INFO", "loaded strategy instances from db", count=len(saved_instances))

    # 只处理数据库里的老策略，不处理新策略
    existing_strategies = {s.name: s for s in manager.list_units()}
    processed_strategies = {}

    # 遍历数据库中的现有策略
    for strategy in existing_strategies.values():
        # Use the stream from the strategy's bound datasource if available
        if strategy.metadata.bound_datasource_id:
            bound_source = ds_mgr.get_source(strategy.metadata.bound_datasource_id)
            if bound_source:
                bound_stream = bound_source.get_stream()
                if bound_stream:
                    strategy.set_input_stream(bound_stream.filter(lambda x: x is not None))
        else:
            strategy.set_input_stream(quant)
            # 无绑定数据流的策略，运行状态需要设置成已暂停
            if strategy.state.status == "running":
                strategy.pause()
                log_strategy_event("INFO", f"Paused strategy without bound datasource: {strategy.name}")
        
        processed_strategies[strategy.name] = strategy

    # 修复启动逻辑：确保状态为运行时的数据源真正启动定时器
    # 检查保存的运行状态，确保状态一致性
    if quant_source:
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
            else:
                log_strategy_event("ERROR", "failed to start quant_source",
                                   error=start_result.get("error"))
        else:
            if saved_running_state and not saved_running_state.get("is_running", False):
                log_strategy_event(
                    "INFO", "quant_source saved state indicates it should not be running")
            else:
                log_strategy_event("INFO", "quant_source already running or no need to start")

    # 最后才恢复策略的运行状态
    strategy_restore_result = manager.restore_running_states()
    log_strategy_event("INFO", "restored running strategies", **strategy_restore_result)

    log_strategy_event("INFO", "stock strategies initialized", count=len(processed_strategies))

    setup_graceful_shutdown()

    log_strategy_event("INFO", "strategy streams initialized")


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
