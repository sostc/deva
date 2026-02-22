"""Stock monitor pipelines integrated into admin runtime."""

from __future__ import annotations

import asyncio
import os
import threading
from datetime import datetime
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


_quant_state = {
    "last_df": None,
    "updating": False,
    "last_attempt_ts": 0.0,
}
_quant_state_lock = threading.Lock()


def log_stock_event(level, message, **extra):
    payload = {"level": level, "source": "deva.admin.stock", "message": message}
    if extra:
        payload.update(extra)
    # Only emit to deva log stream on main thread (IOLoop thread).
    # Worker threads (e.g. asyncio.to_thread) must not touch stream pipelines.
    if threading.current_thread() is threading.main_thread():
        try:
            payload >> log
        except RuntimeError as e:
            if "There is no current event loop in thread" not in str(e):
                raise
        except Exception as e:
            if e.__class__.__name__ != "WebSocketClosedError":
                raise
    # Mirror key stock logs to stdout so they remain visible even when DEVA_LOG_LEVEL is strict.
    if str(level).upper() in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
        extra_text = ""
        if extra:
            parts = [f"{k}={extra[k]}" for k in sorted(extra.keys())]
            extra_text = " | " + ", ".join(parts)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}][{str(level).upper()}][deva.admin.stock] {message}{extra_text}")


def get_stock_config_store():
    return NB("admin_stock_config")


def get_stock_config():
    db = get_stock_config_store()
    if "force_fetch" not in db:
        db["force_fetch"] = False
    if "sync_bus" not in db:
        db["sync_bus"] = True
    return {
        "force_fetch": bool(db.get("force_fetch")),
        "sync_bus": bool(db.get("sync_bus")),
    }


def set_stock_config(*, force_fetch=None, sync_bus=None):
    db = get_stock_config_store()
    if force_fetch is not None:
        db["force_fetch"] = bool(force_fetch)
    if sync_bus is not None:
        db["sync_bus"] = bool(sync_bus)
    return get_stock_config()


def get_stock_basic_meta():
    return get_stock_basic_dataframe_metadata()


async def refresh_stock_basic_df_async(force=True):
    if force:
        return await asyncio.to_thread(refresh_stock_basic_dataframe, log_func=log_stock_event)
    return await asyncio.to_thread(ensure_stock_basic_dataframe_fresh, log_func=log_stock_event)


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


def refresh_stock_basic_df(force=True):
    """Always non-blocking: schedule in loop; if no loop, run in daemon thread."""
    task = _schedule_async_task(refresh_stock_basic_df_async(force=force))
    if task is not None:
        return {"scheduled": True, "force": bool(force)}
    target = refresh_stock_basic_dataframe if force else ensure_stock_basic_dataframe_fresh
    t = threading.Thread(
        target=lambda: target(log_func=log_stock_event),
        daemon=True,
        name="stock-basic-refresh-bg",
    )
    t.start()
    return {"scheduled": True, "force": bool(force), "thread": t.name}


def enrich_with_stock_metadata(df):
    try:
        from .data import Stock
        return Stock.render(df)
    except Exception:
        return df


def ensure_required_stock_columns(df):
    """Ensure downstream aggregations always have required columns."""
    out = df.copy()
    if "blockname" not in out.columns:
        out["blockname"] = "unknown"
    if "name" not in out.columns:
        out["name"] = out["code"].astype(str) if "code" in out.columns else "unknown"
    return out


def expand_blockname_rows(df, block_col="blockname", target_col="blockname_item"):
    """
    Expand pipe-separated block names into one row per concrete block.
    Example: "军工|国家安防" -> two rows.
    """
    if df is None:
        return pd.DataFrame(columns=[block_col, target_col])
    if len(df) == 0:
        out = df.copy()
        if target_col not in out.columns:
            out[target_col] = []
        return out

    out = df.copy()
    if block_col not in out.columns:
        out[block_col] = "unknown"

    out[block_col] = out[block_col].fillna("unknown").astype(str)
    out[target_col] = out[block_col].map(
        lambda x: [item.strip() for item in x.split("|") if item and item.strip()] or ["unknown"]
    )
    out = out.explode(target_col, ignore_index=True)
    return out


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
        cfg = get_stock_config()
        if (not cfg["force_fetch"]) and (not is_tradedate()):
            log_stock_event("INFO", "skip quant fetch on non-trade day", force_fetch=cfg["force_fetch"])
            with _quant_state_lock:
                _quant_state["last_df"] = None
            return
        log_stock_event("INFO", "start quant fetch", force_fetch=cfg["force_fetch"])
        df = await asyncio.to_thread(gen_quant)
        with _quant_state_lock:
            _quant_state["last_df"] = df
    except Exception as e:
        log_stock_event("ERROR", "gen_quant failed", error=str(e))
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


def initialize_stock_monitor_streams(attach_webviews=True):
    # Startup check moved to async scheduling to avoid blocking admin startup.
    refresh_stock_basic_df(force=False)

    # Daily refresh task for blockname/basic mapping (e.g. THS concept boards).
    blockname_timer = Stream.timer(
        func=lambda: refresh_stock_basic_df(force=True),
        interval=24 * 60 * 60,
        thread=False,
        start=True,
        name="stock_blockname_daily_refresh",
    )

    # Keep execution on the main IOLoop thread; downstream bus/sources require an active loop context.
    source = Stream.timer(func=fetch_quant_snapshot_safely, interval=5, thread=False, start=True, name="quant_source")
    quant = source.filter(lambda x: x is not None)
    quant.map(lambda df: log_stock_event("INFO", "quant fetched", rows=int(len(df)), columns=list(df.columns)) or df)
    quant.start_cache(1)

    quant.filter(lambda _: get_stock_config()["sync_bus"]) \
        .map(lambda df: {"sender": "gen_quant", "message": "stock quant snapshot", "quant": df}) >> bus
    quant.map(lambda df: log_stock_event("INFO", "quant bus sync",
                                    enabled=get_stock_config()["sync_bus"],
                                    rows=int(len(df))) or df)

    quant.timed_window(interval=30) \
        .filter(lambda x: is_tradedate() and is_tradetime()) \
        .filter(lambda x: len(x) < 1) \
        .sink(lambda x: "quant not find data" >> Dtalk())

    log.start_cache(200, cache_max_age_seconds=60 * 60 * 24 * 30)
    log.map(lambda x: log.recent(200) >> concat("<br>")) \
        >> NS("访问日志", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 30)
    os.getpid() >> log

    def render_realtime_block_change(df_tuple):
        start_df, end_df = df_tuple
        end_df = end_df.copy()
        end_df.loc[:, "change"] = (end_df.now - start_df.now) / start_df.close
        df = ensure_required_stock_columns(enrich_with_stock_metadata(end_df[["code", "change", "p_change"]]))
        df = expand_blockname_rows(df)
        df.loc[:, "change"] = pd.to_numeric(df["change"], errors="coerce").fillna(0.0)
        log_stock_event("DEBUG", "compute realtime_change", rows=int(len(df)))
        max_group = (
            df.sort_values(["change"], ascending=False)
            .groupby("blockname_item").head(3)
            .groupby("blockname_item")["change"].mean()
            .to_frame("change")
            .sort_values("change", ascending=False).head(10)
        )
        min_group = (
            df.sort_values(["change"], ascending=True)
            .groupby("blockname_item").head(3)
            .groupby("blockname_item")["change"].mean()
            .to_frame("change")
            .sort_values("change", ascending=True).head(10)
        )
        _max = max_group.to_html() if not max_group.empty else "<p>暂无板块异动数据</p>"
        _min = min_group.to_html() if not min_group.empty else "<p>暂无板块异动数据</p>"
        return _max + "<br>" + _min

    quant.sliding_window(6).map(lambda lst: (lst[0], lst[-1])).map(render_realtime_block_change) \
        >> NS("30秒板块异动", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2)

    quant.sliding_window(12).map(lambda lst: (lst[0], lst[-1])).map(render_realtime_block_change) \
        >> NS("1分钟板块异动", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2)

    def render_block_rankings(df):
        df = ensure_required_stock_columns(enrich_with_stock_metadata(df[["code", "p_change"]]))
        df = expand_blockname_rows(df)
        df.loc[:, "p_change"] = pd.to_numeric(df["p_change"], errors="coerce").fillna(0.0)
        log_stock_event("DEBUG", "compute block ranking", rows=int(len(df)))

        def _get_max_n(n):
            max_group = (
                df.sort_values(["p_change"], ascending=False)
                .groupby("blockname_item").head(n)
                .groupby("blockname_item")["p_change"].mean()
                .to_frame("p_change")
                .sort_values("p_change", ascending=False).head(10)
            )
            return _get_max_n.__doc__ % n + "<br>" + \
                (max_group.to_html() if not max_group.empty else "<p>暂无领涨板块数据</p>")

        def _get_min_n(n):
            min_group = (
                df.sort_values(["p_change"])
                .groupby("blockname_item").head(n)
                .groupby("blockname_item")["p_change"].mean()
                .to_frame("p_change")
                .sort_values("p_change").head(10)
            )
            return _get_min_n.__doc__ % n + "<br>" + \
                (min_group.to_html() if not min_group.empty else "<p>暂无领跌板块数据</p>")

        _get_max_n.__doc__ = "按照板块分别取%s只涨幅最高的股票作为样本,按照平均值排序top10"
        _get_min_n.__doc__ = "按照板块分别取%s只跌幅最大的股票作为样本,按照平均值排序top10"
        return _get_max_n(20) + "<br>" + _get_max_n(50) + "<br>" + _get_min_n(20) + "<br>" + _get_min_n(50) + "<br>"

    quant.map(render_block_rankings) >> NS("领涨领跌板块", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2)

    def render_limit_up_down_overview(df):
        zt_df = df[["code", "p_change", "ask1_volume"]].query("p_change>0.098")
        dt_df = df[["code", "p_change", "bid1_volume"]].query("p_change<-0.098")
        zt_df = ensure_required_stock_columns(enrich_with_stock_metadata(zt_df))
        dt_df = ensure_required_stock_columns(enrich_with_stock_metadata(dt_df))
        log_stock_event("INFO", "compute zt/dt summary", zt_count=int(len(zt_df)), dt_count=int(len(dt_df)))
        # Use detail tables directly; pivot_table defaults to mean and may fail on object columns like `code`.
        zt_detail = (
            zt_df[["blockname", "name", "code", "p_change", "ask1_volume"]]
            .sort_values(["p_change"], ascending=False)
            .to_html(index=False)
        )
        dt_detail = (
            dt_df[["blockname", "name", "code", "p_change", "bid1_volume"]]
            .sort_values(["p_change"], ascending=True)
            .to_html(index=False)
        )
        zt_count = str(int(df.query("p_change>0.098")["code"].nunique()))
        dt_count = str(int(df.query("p_change<-0.098")["code"].nunique()))
        return "涨停%s,跌停%s(包含150开头的基金)</br>%s</br>%s" % (zt_count, dt_count, zt_detail, dt_detail)

    quant.map(render_limit_up_down_overview) >> NS("涨跌停", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2)

    news = NT("news")
    news.start_cache(100, cache_max_age_seconds=60 * 60 * 24 * 2)
    news.map(lambda x: news.recent(100) >> concat("<br>")) \
        >> NS("实时新闻", cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 2)

    streams = [
        NS("我要留言"),
        NS("实时新闻"),
        NS("涨跌停"),
        NS("领涨领跌板块"),
        NS("1分钟板块异动"),
        NS("30秒板块异动"),
    ]
    if attach_webviews:
        for s in streams:
            s.webview()

    log_stock_event("INFO", "stock streams initialized", attach_webviews=attach_webviews)
    return {"source": source, "quant": quant, "news": news, "blockname_timer": blockname_timer}


# Compatibility aliases
setup_stock_streams = initialize_stock_monitor_streams
_stock_log = log_stock_event
_stock_config_db = get_stock_config_store
_render_with_stock = enrich_with_stock_metadata
_normalize_stock_df = ensure_required_stock_columns
_safe_gen_quant = fetch_quant_snapshot_safely
