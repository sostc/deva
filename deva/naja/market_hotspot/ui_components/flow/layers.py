"""热点系统流式 UI - 层次详情与数据频率"""

import logging
from typing import Dict, Any

log = logging.getLogger(__name__)

from ._helpers import _fmt_ts


def render_hotspot_layers_detail() -> str:
    """渲染热点层次详情 - 题材和个股分布"""
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker

        orchestrator = get_trading_center()
        integration = get_market_hotspot_integration()
        tracker = get_history_tracker()

        if not integration or not integration.hotspot_system:
            return ""

        block_weights = integration.hotspot_system.block_hotspot.get_all_weights(filter_noise=True) or {}
        symbol_weights = integration.hotspot_system.weight_pool.get_all_weights() or {}

        hot_blocks = sorted(block_weights.items(), key=lambda x: x[1], reverse=True)[:10]
        hot_symbols = sorted(symbol_weights.items(), key=lambda x: x[1], reverse=True)[:15]

        total_block_weight = sum(block_weights.values()) if block_weights else 0
        total_symbol_weight = sum(symbol_weights.values()) if symbol_weights else 0

        hotspot_engine = getattr(integration.hotspot_system, 'global_hotspot', None)
        if hotspot_engine:
            history_window = getattr(hotspot_engine, 'history_window', 0)
            history_len = len(getattr(hotspot_engine, '_history_buffer', []))
            history_info = f"{history_len}/{history_window}"
        else:
            history_info = "-"

    except Exception:
        return ""

    block_bars = ""
    for block_id, weight in hot_blocks:
        bar_width = min(100, int(weight * 100))
        pct = (weight / total_block_weight * 100) if total_block_weight > 0 else 0
        name = _get_friendly_name(block_id, 'block', tracker)
        block_bars += f"""
        <div style="margin-bottom: 3px;">
            <div style="display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8;">
                <span style="color: #fb923c;" title="{block_id}">{name[:12]}</span>
                <span>{weight:.4f} <span style="color: #64748b;">({pct:.1f}%)</span></span>
            </div>
            <div style="height: 3px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
                <div style="width: {bar_width}%; height: 100%; background: linear-gradient(90deg, #fb923c, #f97316);"></div>
            </div>
        </div>
        """

    symbol_bars = ""
    for symbol_code, weight in hot_symbols:
        bar_width = min(100, int(weight * 100))
        pct = (weight / total_symbol_weight * 100) if total_symbol_weight > 0 else 0
        name = _get_friendly_name(symbol_code, 'symbol', tracker)
        symbol_bars += f"""
        <div style="margin-bottom: 3px;">
            <div style="display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8;">
                <span style="color: #f87171;" title="{symbol_code}">{name[:14]}</span>
                <span>{weight:.4f} <span style="color: #64748b;">({pct:.1f}%)</span></span>
            </div>
            <div style="height: 3px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
                <div style="width: {bar_width}%; height: 100%; background: linear-gradient(90deg, #f87171, #ef4444);"></div>
            </div>
        </div>
        """

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-size: 13px; font-weight: 600; color: #a855f7;">
                🎯 热点分布
            </div>
            <div style="font-size: 9px; color: #64748b;">
                题材: {len(block_weights)} | 个股: {len(symbol_weights)} | 历史: {history_info}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
            <div>
                <div style="font-size: 10px; font-weight: 600; color: #fb923c; margin-bottom: 6px;">
                    题材热度 (Top10)
                </div>
                {block_bars or '<div style="color: #64748b; font-size: 10px;">暂无数据</div>'}
            </div>
            <div>
                <div style="font-size: 10px; font-weight: 600; color: #f87171; margin-bottom: 6px;">
                    个股热度 (Top15)
                </div>
                {symbol_bars or '<div style="color: #64748b; font-size: 10px;">暂无数据</div>'}
            </div>
        </div>
    </div>
    """


def render_data_frequency_panel() -> str:
    """渲染数据获取频率面板 - 实时数据获取状态"""
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
        from deva.naja.market_hotspot.data.async_fetcher import get_data_fetcher
        from deva.datetime import datetime
        from ..common import get_market_phase_summary, get_ui_mode_context

        orchestrator = get_trading_center()
        fetcher = get_data_fetcher()

        if not fetcher:
            return _render_fetcher_empty_state()

        phase_summary = get_market_phase_summary()
        cn_info = phase_summary.get('cn', {})
        us_info = phase_summary.get('us', {})

        is_cn = cn_info.get('active', False)
        is_us = us_info.get('active', False)
        is_us_only = is_us and not is_cn
        is_cn_only = is_cn and not is_us

        last_fetch = getattr(fetcher, '_last_fetch_time', 0)
        fetch_interval = getattr(fetcher, '_fetch_interval', 0)
        fetcher_stats = getattr(fetcher, '_stats', {})
        is_running = getattr(fetcher, '_running', False)
        is_trading = getattr(fetcher, '_is_trading', False) if hasattr(fetcher, '_is_trading') else False

        last_fetch_str = _fmt_ts(last_fetch) if last_fetch else "-"
        time_since = time.time() - last_fetch if last_fetch else 0

        records_count = fetcher_stats.get('records_processed', 0)
        errors_count = fetcher_stats.get('errors', 0)
        fetch_count = fetcher_stats.get('fetch_count', 0)
        us_stock_count = fetcher_stats.get('us_stock_count', 0)
        us_fetch_count = fetcher_stats.get('us_fetch_count', 0)

        mode_ctx = get_ui_mode_context()
        if mode_ctx.get('is_replay') and mode_ctx.get('market_time_str'):
            current_weekday = "回放"
            current_time_str = mode_ctx.get('market_time_str', '')
        else:
            weekday = datetime.now().weekday()
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            current_weekday = weekday_names[weekday]
            current_time_str = datetime.now().strftime("%H:%M:%S")

        high_count = fetcher_stats.get('high_count', 0)
        medium_count = fetcher_stats.get('medium_count', 0)
        low_count = fetcher_stats.get('low_count', 0)

        status_color = "#4ade80" if is_running else "#f87171"
        status_text = "🟢 运行中" if is_running else "🔴 已停止"

        from deva.naja.market_hotspot.ui_components.styles import format_market_line

        cn_line = format_market_line("🇨🇳 A股", cn_info)
        us_line = format_market_line("🇺🇸 美股", us_info)

        if is_us_only:
            trading_text = us_line
            stock_count = us_stock_count
            market_name = "美股"
            stock_label = "美股"
        elif is_cn_only:
            trading_text = cn_line
            stock_count = low_count
            market_name = "A股"
            stock_label = "A股"
        else:
            trading_text = f"{cn_line} | {us_line}"
            stock_count = low_count + us_stock_count
            market_name = "A股+美股" if (is_cn or is_us) else "休市"
            stock_label = "A股/美股"

        status_color = "#4ade80" if is_running else "#f87171"
        status_text = "🟢 运行中" if is_running else "🔴 已停止"

    except Exception:
        return _render_fetcher_empty_state()

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 13px; font-weight: 600; color: #0ea5e9;">
                📡 数据获取器
            </div>
            <div style="font-size: 9px; color: {status_color};">
                {status_text} | {trading_text} | {mode_ctx.get('mode_label', '实盘模式')}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="text-align: center; padding: 6px; background: rgba(14,165,233,0.1); border-radius: 4px;">
                <div style="font-size: 12px; font-weight: 700; color: #0ea5e9;">{records_count:,}</div>
                <div style="font-size: 8px; color: #64748b;">处理记录</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(248,113,113,0.1); border-radius: 4px;">
                <div style="font-size: 12px; font-weight: 700; color: #f87171;">{errors_count}</div>
                <div style="font-size: 8px; color: #64748b;">错误数</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(74,222,128,0.1); border-radius: 4px;">
                <div style="font-size: 12px; font-weight: 700; color: #4ade80;">{fetch_count:,}</div>
                <div style="font-size: 8px; color: #64748b;">获取次数</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(251,146,60,0.1); border-radius: 4px;">
                <div style="font-size: 12px; font-weight: 700; color: #fb923c;">{last_fetch_str}</div>
                <div style="font-size: 8px; color: #64748b;">最后获取</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(168,85,247,0.1); border-radius: 4px;">
                <div style="font-size: 12px; font-weight: 700; color: #a855f7;">{time_since:.1f}s</div>
                <div style="font-size: 8px; color: #64748b;">间隔</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(96,165,250,0.1); border-radius: 4px;">
                <div style="font-size: 12px; font-weight: 700; color: #60a5fa;">{fetch_interval}s</div>
                <div style="font-size: 8px; color: #64748b;">采集间隔</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 8px;">
            <div style="text-align: center; padding: 4px; background: rgba(239,68,68,0.1); border-radius: 4px;">
                <div style="font-size: 11px; font-weight: 700; color: #ef4444;">{high_count}</div>
                <div style="font-size: 8px; color: #64748b;">高频档位</div>
            </div>
            <div style="text-align: center; padding: 4px; background: rgba(251,146,60,0.1); border-radius: 4px;">
                <div style="font-size: 11px; font-weight: 700; color: #fb923c;">{medium_count}</div>
                <div style="font-size: 8px; color: #64748b;">中频档位</div>
            </div>
            <div style="text-align: center; padding: 4px; background: rgba(34,197,94,0.1); border-radius: 4px;">
                <div style="font-size: 11px; font-weight: 700; color: #22c55e;">{stock_count}</div>
                <div style="font-size: 8px; color: #64748b;">{stock_label}</div>
            </div>
            <div style="text-align: center; padding: 4px; background: rgba(148,163,184,0.1); border-radius: 4px;">
                <div style="font-size: 11px; font-weight: 700; color: #94a3b8;">{current_weekday}</div>
                <div style="font-size: 8px; color: #64748b;">{current_time_str}</div>
            </div>
        </div>

        <div style="font-size: 9px; color: #64748b; text-align: center;">
            实时行情监控 | 异常自动告警
        </div>
    </div>
    """


def _render_fetcher_empty_state() -> str:
    """渲染数据获取器空状态"""
    from datetime import datetime
    from ..common import get_market_phase_summary, get_ui_mode_context
    mode_ctx = get_ui_mode_context()
    if mode_ctx.get('is_replay') and mode_ctx.get('market_time_str'):
        current_time_str = mode_ctx.get('market_time_str', '')
        current_weekday = "回放"
    else:
        current_time_str = datetime.now().strftime("%H:%M:%S")
        weekday = datetime.now().weekday()
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        current_weekday = weekday_names[weekday]

    phase_summary = get_market_phase_summary()
    cn_info = phase_summary.get('cn', {})
    us_info = phase_summary.get('us', {})

    from deva.naja.market_hotspot.ui_components.styles import format_market_line

    cn_line = format_market_line("🇨🇳 A股", cn_info)
    us_line = format_market_line("🇺🇸 美股", us_info)

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 13px; font-weight: 600; color: #0ea5e9;">
                📡 数据获取器
            </div>
            <div style="font-size: 9px; color: #64748b;">
                🔴 未启用 | {mode_ctx.get('mode_label', '实盘模式')}
            </div>
        </div>

        <div style="text-align: center; padding: 20px; color: #64748b;">
            <div style="font-size: 11px; margin-bottom: 8px;">实时数据获取器未启动</div>
            <div style="font-size: 10px;">{current_weekday} {current_time_str} | {cn_line} | {us_line}</div>
            <div style="font-size: 9px; margin-top: 4px; color: #475569;">将在交易时段自动启用</div>
        </div>
    </div>
    """


