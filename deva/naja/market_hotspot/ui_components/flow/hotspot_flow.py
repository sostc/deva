"""热点系统流式 UI - 热点数据流"""

import logging
from typing import Dict, Any

log = logging.getLogger(__name__)

from ._helpers import _fmt_ts_full, _safe_val


def render_hotspot_flow_ui() -> str:
    """渲染热点系统流式 UI - 返回 HTML 字符串

    整合市场热点系统的核心指标到一个清晰的流式界面
    """
    try:
        from deva.naja.attention.orchestration.trading_center import get_trading_center
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


