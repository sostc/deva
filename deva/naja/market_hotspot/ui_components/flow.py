"""市场热点流式 UI - 展示市场热点数据流和层次

一切皆流，无物永驻
"""

import logging
from typing import Dict, List, Any, Optional
import time

log = logging.getLogger(__name__)

from ...common.ui_style import format_timestamp


def _fmt_ts(ts: float) -> str:
    """格式化时间戳（短格式：HH:MM:SS）"""
    return format_timestamp(ts, fmt="%H:%M:%S")


def _fmt_ts_full(ts: float) -> str:
    """格式化完整时间戳（微秒精度）"""
    if not ts:
        return "-"
    try:
        from datetime import datetime
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%H:%M:%S.%f")[:-3]
    except Exception:
        return str(ts)


def _safe_val(val, default="-"):
    """安全获取值"""
    if val is None:
        return default
    return val


def render_hotspot_flow_ui() -> str:
    """渲染热点系统流式 UI - 返回 HTML 字符串

    整合市场热点系统的核心指标到一个清晰的流式界面
    """
    try:
        from deva.naja.attention.trading_center import get_trading_center
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        from deva.naja.radar.trading_clock import is_trading_time as is_cn_trading, is_us_trading_time

        orchestrator = get_trading_center()
        integration = get_market_hotspot_integration()

        stats = orchestrator.get_stats()
        context = orchestrator.get_attention_context()

        is_cn = is_cn_trading()
        is_us = is_us_trading_time()

        us_data = None
        if integration and integration.hotspot_system:
            try:
                us_data = integration.hotspot_system.get_us_hotspot_state()
                log.debug(f"[Flow-UI] us_data global_hotspot={us_data.get('global_hotspot', 0) if us_data else 'None'}")
            except Exception as e:
                log.warning(f"[Flow-UI] get_us_hotspot_state failed: {e}")
                us_data = None

        log.debug(f"[Flow-UI] stats processed_frames={stats.get('processed_frames', 0)}, is_cn={is_cn}, is_us={is_us}")

    except Exception as e:
        log.error(f"[Flow-UI] render_hotspot_flow_ui failed: {e}")
        import traceback
        traceback.print_exc()
        return _render_empty_state()

    return _build_hotspot_flow_html(stats, context, integration, is_cn, is_us, us_data)


def _render_empty_state() -> str:
    """渲染空状态"""
    return """
    <div style="
        padding: 20px;
        text-align: center;
        color: #64748b;
        background: rgba(255,255,255,0.02);
        border-radius: 8px;
    ">
        <div style="font-size: 14px; margin-bottom: 8px;">⚠️ 市场热点监测未初始化</div>
        <div style="font-size: 11px;">请先启动市场数据接入</div>
    </div>
    """


def _build_hotspot_flow_html(stats: Dict, context: Dict, integration, is_cn: bool, is_us: bool, us_data: Dict) -> str:
    """构建市场热点流 HTML"""

    processed_frames = stats.get('processed_frames', 0)
    filtered_frames = stats.get('filtered_frames', 0)
    filter_ratio = stats.get('filter_ratio', 0)
    registered_strategies = stats.get('registered_strategies', 0)
    registered_datasources = stats.get('registered_datasources', 0)
    global_hotspot = stats.get('global_hotspot', 0)
    high_hotspot_count = stats.get('high_hotspot_count', 0)
    noise_stats = stats.get('noise_filter', {})

    active_blocks = context.get('active_blocks', set())
    high_hotspot_symbols = context.get('high_hotspot_symbols', set())

    if isinstance(active_blocks, set):
        active_block_count = len(active_blocks)
    else:
        active_block_count = len(active_blocks) if active_blocks else 0

    if isinstance(high_hotspot_symbols, set):
        high_hotspot_symbol_count = len(high_hotspot_symbols)
    else:
        high_hotspot_symbol_count = len(high_hotspot_symbols) if high_hotspot_symbols else 0

    has_us_data = us_data and us_data.get('global_hotspot', 0) > 0

    if is_us and not is_cn:
        show_us_only = True
        show_cn_only = False
    elif is_cn and not is_us:
        show_us_only = False
        show_cn_only = True
    else:
        show_us_only = False
        show_cn_only = False

    if show_us_only and has_us_data:
        global_hotspot = us_data.get('global_hotspot', 0)
        us_blocks = us_data.get('block_hotspot', {})
        us_symbols = us_data.get('symbol_weights', {})
        active_block_count = len(us_blocks)
        high_hotspot_symbol_count = len([s for s, w in us_symbols.items() if w > 3])
        processed_frames = us_data.get('stock_count', 0)
        filtered_frames = 0
        filter_ratio = 0

    hotspot_color = "#4ade80" if global_hotspot > 0.6 else ("#fb923c" if global_hotspot > 0.3 else "#f87171")
    filter_pct = int(filter_ratio * 100) if filter_ratio else 0

    history_info = ""
    last_update = ""
    if integration and integration.hotspot_system:
        try:
            attn_engine = integration.hotspot_system.global_hotspot
            history_window = getattr(attn_engine, 'history_window', 0)
            history_len = len(getattr(attn_engine, '_history_buffer', []))
            last_update_ts = getattr(attn_engine, '_last_update', 0)
            last_update = _fmt_ts_full(last_update_ts) if last_update_ts else "-"
            history_info = f"{history_len}/{history_window}"
        except Exception:
            history_info = "-"
            last_update = "-"
    else:
        history_info = "-"
        last_update = "-"

    noise_stats_html = ""
    if noise_stats:
        noise_filtered = noise_stats.get('filtered_count', 0)
        noise_whitelist = noise_stats.get('whitelist_count', 0)
        noise_blacklist = noise_stats.get('blacklist_count', 0)
        noise_stats_html = f"""
        <div style="display: flex; gap: 8px; font-size: 9px; margin-top: 4px;">
            <span style="color: #64748b;">过滤: {noise_filtered:,}</span>
            <span style="color: #4ade80;">白: {noise_whitelist}</span>
            <span style="color: #f87171;">黑: {noise_blacklist}</span>
        </div>
        """

    frame_stats_html = f"""
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px;">
        <div style="background: rgba(96,165,250,0.1); padding: 6px; border-radius: 4px; text-align: center;">
            <div style="font-size: 14px; font-weight: 700; color: #60a5fa;">{processed_frames:,}</div>
            <div style="font-size: 8px; color: #64748b;">处理帧</div>
        </div>
        <div style="background: rgba(251,146,60,0.1); padding: 6px; border-radius: 4px; text-align: center;">
            <div style="font-size: 14px; font-weight: 700; color: #fb923c;">{filtered_frames:,}</div>
            <div style="font-size: 8px; color: #64748b;">过滤帧</div>
        </div>
        <div style="background: rgba(74,222,128,0.1); padding: 6px; border-radius: 4px; text-align: center;">
            <div style="font-size: 14px; font-weight: 700; color: #4ade80;">{filter_pct}%</div>
            <div style="font-size: 8px; color: #64748b;">过滤率</div>
        </div>
    </div>
    """

    hotspot_hierarchy_html = f"""
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-bottom: 6px;">
        <div style="background: rgba(74,222,128,0.1); padding: 6px; border-radius: 4px; text-align: center;">
            <div style="font-size: 14px; font-weight: 700; color: #4ade80;">{global_hotspot:.3f}</div>
            <div style="font-size: 8px; color: #64748b;">热点强度</div>
        </div>
        <div style="background: rgba(251,146,60,0.1); padding: 6px; border-radius: 4px; text-align: center;">
            <div style="font-size: 14px; font-weight: 700; color: #fb923c;">{active_block_count}</div>
            <div style="font-size: 8px; color: #64748b;">活跃题材</div>
        </div>
        <div style="background: rgba(248,113,113,0.1); padding: 6px; border-radius: 4px; text-align: center;">
            <div style="font-size: 14px; font-weight: 700; color: #f87171;">{high_hotspot_symbol_count}</div>
            <div style="font-size: 8px; color: #64748b;">高热点股</div>
        </div>
    </div>
    <div style="padding: 4px 6px; background: rgba(74,222,128,0.05); border-radius: 4px; border-left: 2px solid {hotspot_color};">
        <div style="font-size: 9px; color: {hotspot_color}; font-weight: 600;">
            {'🔥 活跃' if global_hotspot > 0.6 else ('📊 一般' if global_hotspot > 0.3 else '💤 冷清')}
        </div>
    </div>
    """

    system_stats_html = f"""
    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px; font-size: 9px;">
        <div style="display: flex; align-items: center; gap: 4px;">
            <span style="color: #60a5fa;">📡</span>
            <span style="color: #94a3b8;">策略: {registered_strategies}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 4px;">
            <span style="color: #a855f7;">🔗</span>
            <span style="color: #94a3b8;">数据源: {registered_datasources}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 4px;">
            <span style="color: #fb923c;">📊</span>
            <span style="color: #94a3b8;">历史: {history_info}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 4px;">
            <span style="color: #4ade80;">🕐</span>
            <span style="color: #94a3b8;">更新: {last_update}</span>
        </div>
    </div>
    {noise_stats_html}
    """

    flow_diagram_html = _render_flow_diagram(global_hotspot, active_block_count, high_hotspot_symbol_count)

    flow_title = "🇺🇸 美股热点流" if show_us_only else ("🇨🇳 A股热点流" if show_cn_only else "🌊 市场热点流")
    flow_subtitle = "一切皆流，无物永驻 — 美股行情 → 热点计算 → 策略调度" if show_us_only else ("一切皆流，无物永驻 — A股行情 → 过滤 → 热点 → 策略调度" if show_cn_only else "一切皆流，无物永驻 — 行情数据 → 过滤 → 热点 → 策略调度")

    html = f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #14b8a6;">
                {flow_title}
            </div>
            <div style="font-size: 10px; color: #475569;">
                {processed_frames} 条 | 过滤 {filter_pct}%
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 12px;">
            {flow_subtitle}
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
            <div>
                <div style="font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 6px;">
                    📊 数据统计
                </div>
                {frame_stats_html}
            </div>
            <div>
                <div style="font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 6px;">
                    👁️ 热点层次
                </div>
                {hotspot_hierarchy_html}
            </div>
            <div>
                <div style="font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 6px;">
                    ⚙️ 系统状态
                </div>
                {system_stats_html}
                <div style="margin-top: 6px;">
                    {flow_diagram_html}
                </div>
            </div>
        </div>
    </div>
    """
    return html


def _render_flow_diagram(global_hotspot: float, active_blocks: int, high_hotspot: int) -> str:
    """渲染市场热点流图"""
    items = [
        ("📥 行情输入", "#60a5fa", True),
        ("🔊 噪音过滤", "#fb923c", True),
        ("👁️ 热点计算", "#14b8a6", True),
        ("📡 策略调度", "#a855f7", high_hotspot > 0),
        ("🤖 策略执行", "#0ea5e9", global_hotspot > 0.5),
        ("📤 信号输出", "#4ade80", active_blocks > 0),
    ]

    items_html = ""
    for name, color, active in items:
        opacity = "1" if active else "0.4"
        items_html += f"""
        <div style="display: flex; align-items: center; gap: 6px; padding: 3px 0; opacity: {opacity};">
            <div style="width: 6px; height: 6px; border-radius: 50%; background: {color};"></div>
            <span style="font-size: 9px; color: #94a3b8;">{name}</span>
        </div>
        """

    return f"""
    <div style="background: rgba(255,255,255,0.02); border-radius: 4px; padding: 5px;">
        <div style="font-size: 8px; color: #64748b; margin-bottom: 3px;">处理流程</div>
        {items_html}
    </div>
    """


def _get_friendly_name(item_id: str, item_type: str, tracker) -> str:
    """获取友好的名称

    Args:
        item_id: 题材ID或股票代码
        item_type: 'block' 或 'symbol'
        tracker: 历史追踪器实例
    """
    if item_type == 'block':
        name = tracker.get_block_name(item_id) if tracker else item_id
        if name != item_id:
            return f"{name}"
        return f"{item_id}"
    else:
        name = tracker.get_symbol_name(item_id) if tracker else item_id
        if name != item_id:
            return f"{item_id} {name}"
        return f"{item_id}"


def render_hotspot_layers_detail() -> str:
    """渲染热点层次详情 - 题材和个股分布"""
    try:
        from deva.naja.attention.trading_center import get_trading_center
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        from deva.naja.market_hotspot.market_hotspot_history_tracker import get_history_tracker

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

        attention_engine = getattr(integration.hotspot_system, 'global_hotspot', None)
        if attention_engine:
            history_window = getattr(attention_engine, 'history_window', 0)
            history_len = len(getattr(attention_engine, '_history_buffer', []))
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
        from deva.naja.attention.trading_center import get_trading_center
        from deva.naja.market_hotspot.realtime_data_fetcher import get_data_fetcher
        from deva.datetime import datetime
        from .common import get_market_phase_summary, get_ui_mode_context

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

        def _format_market_line(label: str, info: Dict[str, Any]) -> str:
            phase_name = info.get('phase_name', '未知')
            next_phase = info.get('next_phase_name', '')
            next_time = info.get('next_change_time', '')
            if info.get('phase') == 'closed' and next_time:
                return f"{label}{phase_name} →{next_phase} {next_time}"
            return f"{label}{phase_name}"

        cn_line = _format_market_line("🇨🇳 A股", cn_info)
        us_line = _format_market_line("🇺🇸 美股", us_info)

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
    from .common import get_market_phase_summary, get_ui_mode_context
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

    def _format_market_line(label: str, info: Dict[str, Any]) -> str:
        phase_name = info.get('phase_name', '未知')
        next_phase = info.get('next_phase_name', '')
        next_time = info.get('next_change_time', '')
        if info.get('phase') == 'closed' and next_time:
            return f"{label}{phase_name} →{next_phase} {next_time}"
        return f"{label}{phase_name}"

    cn_line = _format_market_line("🇨🇳 A股", cn_info)
    us_line = _format_market_line("🇺🇸 美股", us_info)

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


def render_noise_filter_panel() -> str:
    """渲染噪音过滤面板"""
    try:
        from deva.naja.attention.trading_center import get_trading_center
        from deva.naja.market_hotspot.market_hotspot_history_tracker import get_history_tracker
        from deva.naja.market_hotspot.processing import get_block_noise_detector, get_noise_manager

        orchestrator = get_trading_center()
        tracker = get_history_tracker()
        stats = orchestrator.get_stats()
        noise_stats = stats.get('noise_filter', {})

        noise_detector = get_block_noise_detector()
        noise_manager = get_noise_manager()

        blacklist_patterns = []
        if noise_detector and noise_detector.config:
            blacklist_patterns = noise_detector.config.blacklist_patterns or []

        auto_blacklist = set()
        manual_blacklist = set()
        if noise_manager:
            auto_blacklist = noise_manager._auto_blacklist if hasattr(noise_manager, '_auto_blacklist') else set()
            manual_blacklist = noise_manager._manual_blacklist if hasattr(noise_manager, '_manual_blacklist') else set()

        if not noise_stats and not blacklist_patterns:
            return _render_noise_empty_state()

        filtered = noise_stats.get('filtered_count', 0)
        whitelist = noise_stats.get('whitelist_count', 0)
        blacklist = noise_stats.get('blacklist_count', 0)
        total = noise_stats.get('total_processed', 1)

        filter_rate = (filtered / max(total, 1)) * 100 if total else 0

        whitelist_stocks = noise_stats.get('whitelist_stocks', [])
        blacklist_stocks = noise_stats.get('blacklist_stocks', [])

        def format_stock_list(stocks, max_display=5):
            if not stocks:
                return "-"
            formatted = []
            for code in stocks[:max_display]:
                name = tracker.get_symbol_name(code) if tracker else code
                if name != code:
                    formatted.append(f"{code} {name[:4]}")
                else:
                    formatted.append(code)
            result = ", ".join(formatted)
            if len(stocks) > max_display:
                result += f" +{len(stocks) - max_display}"
            return result

        whitelist_display = format_stock_list(whitelist_stocks)
        blacklist_display = format_stock_list(blacklist_stocks)

        pattern_tags = ""
        for pattern in blacklist_patterns[:12]:
            pattern_tags += f'<span style="display: inline-block; padding: 1px 4px; background: rgba(251,146,60,0.15); color: #fb923c; border-radius: 3px; font-size: 8px; margin: 1px;">{pattern}</span>'
        if len(blacklist_patterns) > 12:
            pattern_tags += f'<span style="font-size: 8px; color: #64748b;">+{len(blacklist_patterns) - 12}</span>'

        noise_blocks = sorted(list(auto_blacklist | manual_blacklist))[:8]
        noise_block_tags = ""
        for block_id in noise_blocks:
            block_display = tracker.get_block_name(block_id) if tracker else block_id
            if block_display != block_id:
                noise_block_tags += f'<span style="display: inline-block; padding: 1px 4px; background: rgba(248,113,113,0.15); color: #f87171; border-radius: 3px; font-size: 8px; margin: 1px;" title="{block_id}">{block_display[:8]}</span>'
            else:
                noise_block_tags += f'<span style="display: inline-block; padding: 1px 4px; background: rgba(248,113,113,0.15); color: #f87171; border-radius: 3px; font-size: 8px; margin: 1px;">{block_id[:10]}</span>'
        if len(auto_blacklist | manual_blacklist) > 8:
            noise_block_tags += f'<span style="font-size: 8px; color: #64748b;">+{len(auto_blacklist | manual_blacklist) - 8}</span>'

    except Exception:
        return _render_noise_empty_state()

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 13px; font-weight: 600; color: #fb923c;">
                🔇 噪音过滤
            </div>
            <div style="font-size: 9px; color: #64748b;">
                总处理: {total:,}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="text-align: center; padding: 8px; background: rgba(248,113,113,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #f87171;">{filtered:,}</div>
                <div style="font-size: 8px; color: #64748b;">过滤数量</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(74,222,128,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #4ade80;">{whitelist}</div>
                <div style="font-size: 8px; color: #64748b;">白名单</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(251,146,60,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #fb923c;">{blacklist}</div>
                <div style="font-size: 8px; color: #64748b;">黑名单</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(168,85,247,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #a855f7;">{filter_rate:.1f}%</div>
                <div style="font-size: 8px; color: #64748b;">过滤率</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
            <div style="padding: 6px; background: rgba(74,222,128,0.05); border-radius: 4px;">
                <div style="font-size: 8px; color: #4ade80; margin-bottom: 2px;">✅ 白名单</div>
                <div style="font-size: 8px; color: #94a3b8; word-break: break-all;">{whitelist_display}</div>
            </div>
            <div style="padding: 6px; background: rgba(251,146,60,0.05); border-radius: 4px;">
                <div style="font-size: 8px; color: #fb923c; margin-bottom: 2px;">🚫 黑名单</div>
                <div style="font-size: 8px; color: #94a3b8; word-break: break-all;">{blacklist_display}</div>
            </div>
        </div>

        <div style="margin-bottom: 8px;">
            <div style="font-size: 8px; color: #a855f7; margin-bottom: 4px;">🔍 过滤模式 (题材名含以下关键词即被过滤)</div>
            <div style="padding: 4px; background: rgba(168,85,247,0.05); border-radius: 4px;">{pattern_tags or '<span style="color: #64748b; font-size: 8px;">暂无</span>'}</div>
        </div>

        <div>
            <div style="font-size: 8px; color: #f87171; margin-bottom: 4px;">🚫 噪音题材 (自动/手动)</div>
            <div style="padding: 4px; background: rgba(248,113,113,0.05); border-radius: 4px;">{noise_block_tags or '<span style="color: #64748b; font-size: 8px;">暂无</span>'}</div>
        </div>

        <div style="padding: 4px; background: rgba(255,255,255,0.02); border-radius: 4px; margin-top: 8px;">
            <div style="height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden;">
                <div style="width: {min(100, filter_rate)}%; height: 100%; background: linear-gradient(90deg, #fb923c, #f97316);"></div>
            </div>
        </div>
    </div>
    """


def _render_noise_empty_state() -> str:
    """渲染噪音过滤空状态"""
    return """
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #fb923c; margin-bottom: 10px;">
            🔇 噪音过滤
        </div>
        <div style="text-align: center; padding: 15px; color: #64748b; font-size: 11px;">
            噪音过滤系统未初始化
        </div>
    </div>
    """


def render_strategy_status_panel() -> str:
    """渲染策略状态面板"""
    try:
        from deva.naja.market_hotspot.strategies import get_strategy_manager
        from .common import get_market_phase_summary, get_ui_mode_context

        manager = get_strategy_manager()
        if not manager:
            return ""

        mode_ctx = get_ui_mode_context()
        phase_summary = get_market_phase_summary()
        cn_active = phase_summary.get('cn', {}).get('active', False)
        us_active = phase_summary.get('us', {}).get('active', False)
        if mode_ctx.get('is_replay'):
            current_market = "REPLAY"
        elif cn_active and us_active:
            current_market = "ALL"
        elif us_active:
            current_market = "US"
        elif cn_active:
            current_market = "CN"
        else:
            current_market = "CN"

        all_stats = manager.get_all_stats() if hasattr(manager, 'get_all_stats') else {}
        strategies = manager.strategies if hasattr(manager, 'strategies') else {}
        configs = manager.configs if hasattr(manager, 'configs') else {}

        total_strategies = len(strategies)
        if configs:
            active_strategies = sum(1 for c in configs.values() if getattr(c, 'enabled', False))
        else:
            active_strategies = sum(1 for s in strategies.values() if getattr(s, 'is_active', False))

        if current_market == "ALL":
            matched_strategies = total_strategies
        elif current_market == "REPLAY":
            matched_strategies = total_strategies
        else:
            matched_strategies = sum(
                1 for s in strategies.values()
                if getattr(s, 'market_scope', 'ALL') in ("ALL", current_market)
            )
        total_signals = all_stats.get('total_signals_generated', 0)
        recent_signals = all_stats.get('recent_signals_count', 0)
        is_running = getattr(manager, 'is_running', False)

        strategy_list = []
        for name, strategy in list(strategies.items())[:6]:
            config = configs.get(name)
            if config is not None:
                is_active = getattr(config, 'enabled', False)
            else:
                is_active = getattr(strategy, 'is_active', False)
            signal_count = getattr(strategy, 'signal_count', 0)
            last_signal = getattr(strategy, 'last_signal_time', 0)
            last_signal_str = _fmt_ts(last_signal) if last_signal else "-"

            status_color = "#4ade80" if is_active else "#64748b"
            strategy_list.append({
                'name': name[:12],
                'status': status_color,
                'signals': signal_count,
                'last': last_signal_str,
                'active': is_active
            })

    except Exception:
        return ""

    strategy_items = ""
    for s in strategy_list:
        strategy_items += f"""
        <div style="display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
            <div style="width: 6px; height: 6px; border-radius: 50%; background: {s['status']};"></div>
            <span style="font-size: 9px; color: #94a3b8; flex: 1;">{s['name']}</span>
            <span style="font-size: 8px; color: #64748b;">{s['signals']} 信号</span>
            <span style="font-size: 8px; color: #64748b;">{s['last']}</span>
        </div>
        """

    if not strategy_items:
        strategy_items = '<div style="color: #64748b; font-size: 10px; text-align: center; padding: 10px;">暂无策略</div>'

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 13px; font-weight: 600; color: #a855f7;">
                🎯 策略状态
            </div>
            <div style="font-size: 9px; color: #64748b;">
                活跃: {active_strategies}/{total_strategies} | 总信号: {total_signals:,}
                | 状态: <span style="color:{'#4ade80' if is_running else '#f87171'};">{'运行中' if is_running else '未运行'}</span>
                | 匹配: {matched_strategies} | 市场: {current_market}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="text-align: center; padding: 6px; background: rgba(168,85,247,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #a855f7;">{total_strategies}</div>
                <div style="font-size: 8px; color: #64748b;">总策略</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(74,222,128,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #4ade80;">{active_strategies}</div>
                <div style="font-size: 8px; color: #64748b;">活跃</div>
            </div>
            <div style="text-align: center; padding: 6px; background: rgba(14,165,233,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #0ea5e9;">{recent_signals}</div>
                <div style="font-size: 8px; color: #64748b;">最近信号</div>
            </div>
        </div>

        <div style="font-size: 8px; color: #64748b; margin-bottom: 4px; display: flex; justify-content: space-between; padding: 0 3px;">
            <span>策略</span>
            <span>信号</span>
            <span>最近</span>
        </div>
        {strategy_items}
    </div>
    """


def render_dual_engine_panel() -> str:
    """渲染双引擎状态面板"""
    try:
        from deva.naja.attention.trading_center import get_trading_center
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration

        orchestrator = get_trading_center()
        integration = get_market_hotspot_integration()

        if not integration or not integration.hotspot_system:
            return ""

        dual_engine = integration.hotspot_system.dual_engine
        if not dual_engine:
            return ""

        river_stats = getattr(dual_engine, 'river_stats', {}) or {}
        pytorch_stats = getattr(dual_engine, 'pytorch_stats', {}) or {}

        river_processed = river_stats.get('processed_count', 0)
        river_anomalies = river_stats.get('anomaly_count', 0)
        river_active = river_stats.get('active_symbols', 0)

        pytorch_inferences = pytorch_stats.get('inference_count', 0)
        pytorch_patterns = pytorch_stats.get('pattern_count', 0)

    except Exception:
        return ""

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #6366f1; margin-bottom: 10px;">
            ⚡ 双引擎状态
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
            <div style="padding: 10px; background: rgba(34,197,94,0.1); border-radius: 6px; border-left: 3px solid #22c55e;">
                <div style="font-size: 10px; font-weight: 600; color: #22c55e; margin-bottom: 6px;">🌊 River 引擎</div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px;">
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #4ade80;">{river_processed:,}</div>
                        <div style="font-size: 8px; color: #64748b;">处理数</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #fb923c;">{river_anomalies:,}</div>
                        <div style="font-size: 8px; color: #64748b;">异常数</div>
                    </div>
                    <div style="grid-column: span 2;">
                        <div style="font-size: 12px; font-weight: 700; color: #60a5fa;">{river_active:,}</div>
                        <div style="font-size: 8px; color: #64748b;">活跃标的</div>
                    </div>
                </div>
            </div>

            <div style="padding: 10px; background: rgba(168,85,247,0.1); border-radius: 6px; border-left: 3px solid #a855f7;">
                <div style="font-size: 10px; font-weight: 600; color: #a855f7; margin-bottom: 6px;">🧠 PyTorch 引擎</div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px;">
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #a855f7;">{pytorch_inferences:,}</div>
                        <div style="font-size: 8px; color: #64748b;">推理数</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; font-weight: 700; color: #c084fc;">{pytorch_patterns:,}</div>
                        <div style="font-size: 8px; color: #64748b;">模式数</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
