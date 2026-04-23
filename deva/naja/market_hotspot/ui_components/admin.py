"""市场热点系统 UI 管理页面入口"""

import logging
from datetime import datetime
from pywebio.output import put_html, put_row, put_button, use_scope
from pywebio.session import run_async

from deva.naja.infra.ui.page_help import render_help_collapse
from deva.naja.register import SR
from deva.naja.market_hotspot.ui_components.styles import (
    GRADIENT_DARK_REVERSE, GRADIENT_WARNING, GRADIENT_INFO, GRADIENT_SUCCESS,
    GRADIENT_NEUTRAL,
    info_panel_style,
    COLOR_BORDER_WARNING, COLOR_BORDER_INFO, COLOR_BORDER_SUCCESS,
    COLOR_WARNING_TEXT, COLOR_INFO_DEEPER, COLOR_SUCCESS_DEEPER,
)

log = logging.getLogger(__name__)


def _get_experiment_info():
    """获取实验模式信息"""
    from .common import get_strategy_manager
    try:
        manager = get_strategy_manager()
        if manager:
            return manager.get_experiment_info()
    except Exception:
        pass
    return {"active": False}





async def render_market_hotspot_admin(ctx: dict):
    """渲染市场热点监测管理页面"""
    from .common import (
        get_hotspot_report, get_strategy_stats, is_hotspot_system_initialized,
        initialize_hotspot_system, get_strategy_manager,
    )
    from .cards import (
        render_frequency_distribution, render_pytorch_patterns,
        render_market_state_panel,
    )
    from .cards.signal_tuner_panel import render_signal_tuner_panel
    from .cards.strategy_allocator_panel import render_strategy_allocator_panel
    from .cards.liquidity_rescue_panel import render_liquidity_rescue_panel
    from .cards.feedback_report_panel import render_feedback_report_panel
    from .timeline import (
        render_hotspot_timeline, render_block_trends, render_hotspot_shift_report,
        render_multi_threshold_timeline, render_hotspot_changes, render_recent_signals,
        render_block_hotspot_timeline, render_block_trading_timeline,
    )
    from .intelligence import render_intelligence_panels, render_propagation_panel
    from .flow import (
        render_hotspot_flow_ui,
        render_hotspot_layers_detail,
        render_noise_filter_panel,
        render_strategy_status_panel,
        render_dual_engine_panel,
    )
    from .us_market import render_cross_market_predictions

    hotspot_initialized = is_hotspot_system_initialized()
    report = get_hotspot_report()
    strategy_stats = get_strategy_stats()
    experiment_info = _get_experiment_info()

    global_hotspot = report.get('global_hotspot', 0)
    activity = report.get('activity', 0)
    hotspot_details = report.get('hotspot_details', {})
    hotspot_level = hotspot_details.get('hotspot_level', '未知') if hotspot_details else '未知'
    activity_level = hotspot_details.get('activity_level', '未知') if hotspot_details else '未知'
    market_timestamp = hotspot_details.get('timestamp') if hotspot_details and not hotspot_details.get('error') else None
    if market_timestamp:
        dt = datetime.fromtimestamp(market_timestamp)
        market_time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
    else:
        market_time_str = None
    freq_summary = report.get('frequency_summary', {})
    dual_summary = report.get('dual_engine_summary', {})
    processed = report.get('processed_snapshots', 0)
    avg_latency = report.get('avg_latency_ms', 0)

    river_processed = dual_summary.get('river_stats', {}).get('processed_count', 0)
    river_anomalies = dual_summary.get('river_stats', {}).get('anomaly_count', 0)
    pytorch_inferences = dual_summary.get('pytorch_stats', {}).get('inference_count', 0)
    noise_filtered = dual_summary.get('noise_filter_stats', {}).get('total_filtered', 0)

    hotspot_icon = "🔥" if global_hotspot >= 0.6 else ("📊" if global_hotspot >= 0.3 else "💤")
    activity_icon = "⚡" if activity >= 0.7 else ("🌡️" if activity >= 0.15 else "❄️")
    hotspot_color = "#dc2626" if global_hotspot >= 0.6 else ("#ca8a04" if global_hotspot >= 0.3 else "#64748b")
    activity_color = "#dc2626" if activity >= 0.7 else ("#ca8a04" if activity >= 0.15 else "#64748b")
    market_time_html = f'<div style="font-size: 11px; color: #0ea5e9; margin-top: 6px;">📅 数据时间: {market_time_str}</div>' if market_time_str else ''

    with use_scope("hotspot_header"):
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        put_html(f"""
        <div style="
            margin-bottom: 12px;
            background: {GRADIENT_DARK_REVERSE};
            border-radius: 14px;
            padding: 16px 20px;
            box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25), inset 0 1px 0 rgba(255,255,255,0.05);
            border: 1px solid #334155;
            position: relative;
            overflow: hidden;
        ">
            <div style="position: absolute; top: 0; right: 0; width: 200px; height: 100%; background: radial-gradient(ellipse at top right, #0ea5e908 0%, transparent 60%); pointer-events: none;"></div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; position: relative;">
                <div>
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                        <span style="font-size: 24px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">📡</span>
                        <div>
                            <div style="font-size: 16px; font-weight: 700; color: #f1f5f9;">市场热点监测</div>
                            <div style="font-size: 11px; color: #0ea5e9; margin-top: 2px;">实时追踪题材与个股热度</div>
                        </div>
                    </div>
                    <div style="font-size: 12px; color: #64748b; margin-top: 6px;">输入：市场行情数据 ｜ 输出：热点排序与聚焦度</div>
                    {market_time_html}
                </div>
                <div style="display: flex; gap: 16px; text-align: center;">
                    <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">⏱️ 实时时间</div>
                        <div style="font-size: 13px; font-weight: 600; color: #0ea5e9;" id="live_time" data-ts="{current_timestamp}">{current_timestamp}</div>
                        <div style="font-size: 10px; color: #22c55e; margin-top: 4px;">● <span id="live_indicator" style="animation: pulse 1.5s infinite;">LIVE</span></div>
                    </div>
                    <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">市场聚焦度</div>
                        <div style="font-size: 18px; font-weight: 700; color: {hotspot_color};">{hotspot_icon} {global_hotspot:.2f}</div>
                        <div style="font-size: 10px; color: {hotspot_color}; opacity: 0.8;">{hotspot_level}</div>
                    </div>
                    <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">市场活跃度</div>
                        <div style="font-size: 18px; font-weight: 700; color: {activity_color};">{activity_icon} {activity:.2f}</div>
                        <div style="font-size: 10px; color: {activity_color}; opacity: 0.8;">{activity_level}</div>
                    </div>
                    <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">数据状态</div>
                        <div style="font-size: 14px; font-weight: 700; color: #22c55e;">{'🟢 正常' if report.get('status') == 'running' else '🔴 异常'}</div>
                        <div style="font-size: 10px; color: #94a3b8;">{processed} 条记录</div>
                    </div>
                    <div style="background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">热点题材</div>
                        <div style="font-size: 14px; font-weight: 700; color: #a855f7;">{strategy_stats.get('active_strategies', 0)} 个</div>
                        <div style="font-size: 10px; color: #94a3b8;">{strategy_stats.get('total_signals_generated', 0)} 股票</div>
                    </div>
                </div>
            </div>
        </div>
        <script>
        (function() {{
            function updateTime() {{
                const now = new Date();
                const ts = now.getFullYear() + '-' + 
                    String(now.getMonth() + 1).padStart(2, '0') + '-' +
                    String(now.getDate()).padStart(2, '0') + ' ' +
                    String(now.getHours()).padStart(2, '0') + ':' +
                    String(now.getMinutes()).padStart(2, '0') + ':' +
                    String(now.getSeconds()).padStart(2, '0');
                const el = document.getElementById('live_time');
                if (el) el.textContent = ts;
            }}
            setInterval(updateTime, 1000);
        }})();
        </script>
        <style>
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}
        </style>
        """)

        if not hotspot_initialized:
            put_html(f"""
            <div style="{info_panel_style(GRADIENT_WARNING, COLOR_BORDER_WARNING, COLOR_WARNING_TEXT, padding='16px', font_size='14px')}">
                <strong>⚠️ 市场热点监测未启动</strong><br>
                当前未接入市场数据，无法进行热点监测。
            </div>
            """)

        if experiment_info.get('active'):
            exp_ds = experiment_info.get('datasource_id', '未知')
            put_html(f"""
            <div style="{info_panel_style(GRADIENT_INFO, COLOR_BORDER_INFO, COLOR_INFO_DEEPER)}">
                <strong>🧪 实验模式运行中</strong><br>
                数据源: {exp_ds} | 策略数: {experiment_info.get('strategy_count', 0)}
            </div>
            """)

        from deva.naja.market_hotspot.data.async_fetcher import get_data_fetcher
        fetcher_instance = get_data_fetcher()

        cn_freq = report.get('cn_frequency', {'high': 0, 'medium': 0, 'low': 0})
        stats = fetcher_instance.get_stats() if fetcher_instance and hasattr(fetcher_instance, 'get_stats') else None

        if stats:
            us_high = stats.get('us_high_count', 0)
            us_med = stats.get('us_medium_count', 0)
            us_low = stats.get('us_low_count', 0)
            is_force_mode = stats.get('is_force_trading_mode', False)

            cn_info = stats.get('cn_info', {})
            us_info = stats.get('us_info', {})
            cn_active = stats.get('cn_active', False)
            us_active = stats.get('us_active', False)

            cn_phase = cn_info.get('phase', 'closed')
            us_phase = us_info.get('phase', 'closed')
            cn_phase_name = cn_info.get('phase_name') if cn_info.get('phase_name') not in (None, '未知') else '休市'
            us_phase_name = us_info.get('phase_name') if us_info.get('phase_name') not in (None, '未知') else '休市'
            cn_next = cn_info.get('next_change_time') or ''
            us_next = us_info.get('next_change_time') or ''
            cn_next_phase = cn_info.get('next_phase_name') or ''
            us_next_phase = us_info.get('next_phase_name') or ''

            cn_color = '#22c55e' if cn_phase in ('trading', 'pre_market', 'call_auction') else '#f59e0b'
            us_color = '#22c55e' if us_phase in ('trading', 'pre_market') else '#f59e0b'

            if is_force_mode:
                panel_html = f"""
                <div style="{info_panel_style(GRADIENT_SUCCESS, COLOR_BORDER_SUCCESS, COLOR_SUCCESS_DEEPER)}">
                    <strong>📡 实盘获取器 🟢</strong> <span style="color:#06b6d4;font-weight:bold;">强制调试中</span><br>
                    <span style="font-size:12px;">
                    🔧 模式: <span style="color:#06b6d4;font-weight:bold;">强制实盘(忽略交易时间)</span>
                    </span><br>
                    <span style="font-size:11px;color:#64748b;">
                    🔄 获取次数: {stats.get('fetch_count', 0)} |
                    ❌ 错误: {stats.get('error_count', 0)} |
                    📈 档位: HIGH={cn_freq.get('high', 0)} | MEDIUM={cn_freq.get('medium', 0)} | LOW={cn_freq.get('low', 0)}
                    </span>
                </div>
                """
            else:
                status_parts = []
                if cn_active:
                    status_parts.append(f'<span style="color:{cn_color};font-weight:bold;">A股<span style="font-size:11px;">({cn_phase_name})</span></span>')
                else:
                    next_info = f'→{cn_next_phase} {cn_next}' if cn_next else ''
                    status_parts.append(f'<span style="color:{cn_color};font-weight:bold;">A股<span style="font-size:11px;">(休市 {next_info})</span></span>')

                if us_active:
                    status_parts.append(f'<span style="color:{us_color};font-weight:bold;">美股<span style="font-size:11px;">({us_phase_name})</span></span>')
                else:
                    next_info = f'→{us_next_phase} {us_next}' if us_next else ''
                    status_parts.append(f'<span style="color:{us_color};font-weight:bold;">美股<span style="font-size:11px;">(休市 {next_info})</span></span>')

                status_str = " | ".join(status_parts)

                if cn_active or us_active:
                    cn_level_str = f"A股档位: HIGH={cn_freq.get('high', 0)} | MEDIUM={cn_freq.get('medium', 0)} | LOW={cn_freq.get('low', 0)}" if cn_active else ""
                    us_level_str = f"美股档位: HIGH={us_high} | MEDIUM={us_med} | LOW={us_low}"
                    level_str = " | ".join(filter(None, [cn_level_str, us_level_str]))

                    if cn_active and us_active:
                        fetch_info = f"A股🔄{stats.get('fetch_count', 0)} | 美股🔄{stats.get('us_fetch_count', 0)}"
                    elif cn_active:
                        fetch_info = f"A股 🔄{stats.get('fetch_count', 0)} ❌{stats.get('error_count', 0)}"
                    elif us_active:
                        fetch_info = f"美股 🔄{stats.get('us_fetch_count', 0)} ❌{stats.get('us_error_count', 0)}"
                    else:
                        fetch_info = f"🔄{stats.get('fetch_count', 0)} ❌{stats.get('error_count', 0)}"

                    panel_html = f"""
                    <div style="{info_panel_style(GRADIENT_SUCCESS, COLOR_BORDER_SUCCESS, COLOR_SUCCESS_DEEPER)}">
                        <strong>📡 实盘获取器 🟢</strong> <span style="color:#22c55e;font-weight:bold;">运行中</span><br>
                        <span style="font-size:12px;">
                        📊 状态: {status_str}
                        </span><br>
                        <span style="font-size:11px;color:#64748b;">
                        {fetch_info} | {level_str}
                        </span>
                    </div>
                    """
                else:
                    cn_level_str = f"A股档位: HIGH={cn_freq.get('high', 0)} | MEDIUM={cn_freq.get('medium', 0)} | LOW={cn_freq.get('low', 0)}"
                    us_level_str = f"美股档位: HIGH={us_high} | MEDIUM={us_med} | LOW={us_low}"
                    level_str = " | ".join(filter(None, [cn_level_str, us_level_str]))
                    panel_html = f"""
                    <div style="{info_panel_style(GRADIENT_WARNING, COLOR_BORDER_WARNING, COLOR_WARNING_TEXT)}">
                        <strong>📡 实盘获取器 🔴</strong> <span style="color:#f59e0b;font-weight:bold;">待机中</span><br>
                        <span style="font-size:12px;">
                        📊 状态: {status_str}
                        </span><br>
                        <span style="font-size:11px;color:#92400e;">
                        {level_str}
                        </span>
                    </div>
                    """
            put_html(panel_html)
        else:
            from .common import get_market_phase_summary, get_ui_mode_context
            mode_ctx = get_ui_mode_context()
            if mode_ctx.get('is_replay') and mode_ctx.get('market_time_str'):
                current_time_str = mode_ctx.get('market_time_str', '')
                current_weekday = "回放"
            else:
                current_time_str = datetime.now().strftime("%H:%M")
                weekday = datetime.now().weekday()
                weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                current_weekday = weekday_names[weekday]

            phase_summary = get_market_phase_summary()
            cn_info = phase_summary.get('cn', {})
            us_info = phase_summary.get('us', {})

            from deva.naja.market_hotspot.ui_components.styles import format_market_line

            market_line = ' | '.join([
                format_market_line('A股', cn_info, html=True),
                format_market_line('美股', us_info, html=True)
            ])

            panel_html = f"""
            <div style="{info_panel_style(GRADIENT_NEUTRAL, '#cbd5e1', '#475569')}">
                <strong>📡 数据获取器</strong> <span style="color:#94a3b8;">(未运行)</span><br>
                <span style="font-size:12px;">
                🕐 {current_time_str} {current_weekday}
                </span><br>
                <span style="font-size:11px;color:#64748b;">
                {market_line}
                </span>
            </div>
            """
            put_html(panel_html)

    # ========== 平铺布局：各题材依次渲染 ==========

    def _section_header(icon: str, title: str, subtitle: str = "") -> str:
        sub_html = f'<span style="font-size:11px;color:#64748b;margin-left:8px;">{subtitle}</span>' if subtitle else ''
        return f"""
        <div style="margin: 20px 0 10px 0; padding: 10px 16px;
                    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                    border-radius: 10px; border-left: 4px solid #0ea5e9;
                    display: flex; align-items: center;">
            <span style="font-size:18px; margin-right:8px;">{icon}</span>
            <span style="font-size:14px; font-weight:700; color:#f1f5f9;">{title}</span>
            {sub_html}
        </div>"""

    # ---  热点追踪（实时更新）---
    put_html(_section_header("🔥", "热点追踪", "题材轮动与热点变化"))

    # 市场状态 + 热点流向 合并为一个实时区块
    put_html('<div id="realtime-market-flow"></div>')
    put_html(_generate_realtime_market_flow_js())

    # 热点变化 + 热点转移报告（实时更新）
    put_html('<div id="realtime-hotspot-changes"></div>')
    put_html(_generate_realtime_changes_js())

    put_html(render_block_hotspot_timeline())
    put_html(render_block_trading_timeline())

    # --- 🧠 智能系统（实时更新部分）---
    put_html(_section_header("🧠", "智能系统", "策略引擎与信号分析"))

    # 策略状态（实时更新）
    put_html('<div id="realtime-strategy-status"></div>')
    put_html(_generate_realtime_strategy_status_js())

    put_html(render_dual_engine_panel())
    put_html(render_pytorch_patterns())
    put_html(render_frequency_distribution(freq_summary))
    put_html(render_signal_tuner_panel())
    put_html(render_strategy_allocator_panel())
    put_html(render_intelligence_panels())
    put_html(render_propagation_panel())
    manager = get_strategy_manager()
    if manager:
        signals = manager.get_recent_signals(n=20)
        put_html(render_recent_signals(signals))

    # --- 🛡️ 风险监控 ---
    put_html(_section_header("🛡️", "风险监控", "噪声过滤与流动性预警"))
    put_html(render_noise_filter_panel())
    put_html(render_liquidity_rescue_panel())
    put_html(_render_micro_change_indicator())
    put_html(render_feedback_report_panel())

    # --- ⚙️ 系统运维 ---
    put_html(_section_header("⚙️", "系统运维", "诊断与管理工具"))
    try:
        render_help_collapse("hotspot")
    except Exception:
        pass
    put_row([
        put_button("🔍 运行诊断", onclick=lambda: _run_diagnostic(), small=True),
        put_button("🔇 噪音过滤管理", onclick=lambda: _manage_noise_filter(), small=True, color="info"),
    ], size="auto")


def _get_hotspot_shift_report_impl():
    """获取热点转移报告"""
    tracker = _get_history_tracker()
    if tracker:
        try:
            return tracker.get_hotspot_shift_report()
        except Exception:
            pass
    return {'has_shift': False}


def _get_hotspot_changes_impl():
    """获取热点变化记录"""
    tracker = _get_history_tracker()
    if tracker:
        try:
            return tracker.get_recent_changes(n=20)
        except Exception:
            pass
    return []





def _render_micro_change_indicator() -> str:
    """渲染细微变化指示器 - 捕获题材和个股的微小波动"""
    tracker = _get_history_tracker()
    if not tracker or len(tracker.snapshots) < 2:
        return ""

    recent_snapshots = list(tracker.snapshots)[-10:]

    micro_block_changes = []
    micro_symbol_changes = []

    if len(recent_snapshots) >= 2:
        prev_snapshot = recent_snapshots[-2]
        curr_snapshot = recent_snapshots[-1]

        for block_id, curr_weight in curr_snapshot.block_weights.items():
            prev_weight = prev_snapshot.block_weights.get(block_id, 0)
            if prev_weight > 0:
                change_pct = ((curr_weight - prev_weight) / prev_weight) * 100
                if abs(change_pct) >= 1:
                    block_name = tracker.get_block_name(block_id)
                    micro_block_changes.append({
                        'name': block_name,
                        'change': change_pct,
                        'old': prev_weight,
                        'new': curr_weight,
                    })

        for symbol, curr_weight in curr_snapshot.symbol_weights.items():
            prev_weight = prev_snapshot.symbol_weights.get(symbol, 0)
            if prev_weight > 0:
                change_pct = ((curr_weight - prev_weight) / prev_weight) * 100
                if abs(change_pct) >= 2:
                    symbol_name = tracker.get_symbol_name(symbol)
                    micro_symbol_changes.append({
                        'symbol': symbol,
                        'name': symbol_name,
                        'change': change_pct,
                        'old': prev_weight,
                        'new': curr_weight,
                    })

    micro_block_changes.sort(key=lambda x: abs(x['change']), reverse=True)
    micro_symbol_changes.sort(key=lambda x: abs(x['change']), reverse=True)

    micro_block_changes = micro_block_changes[:6]
    micro_symbol_changes = micro_symbol_changes[:8]

    if not micro_block_changes and not micro_symbol_changes:
        return f"""
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <div style="font-size: 12px; font-weight: 600; color: #1e293b; margin-bottom: 4px;">📊 细微变化监测</div>
            <div style="font-size: 10px; color: #64748b; margin-bottom: 8px;">监测近 {len(recent_snapshots)} 个时间点内权重发生突变的题材和个股</div>
            <div style="text-align: center; color: #94a3b8; font-size: 12px; padding: 12px;">暂无明显波动</div>
        </div>
        """

    html = f"""
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
        <div style="font-size: 12px; font-weight: 600; color: #1e293b; margin-bottom: 4px;">📊 细微变化监测</div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 10px;">监测近 {len(recent_snapshots)} 个时间点内权重发生突变的题材（≥1%）和个股（≥2%）</div>
    """

    if micro_block_changes:
        html += """<div style="margin-bottom: 10px;"><div style="font-size: 11px; color: #1e40af; margin-bottom: 6px;">📱 题材微波动 (≥1%)</div>"""
        for item in micro_block_changes:
            emoji = "📈" if item['change'] > 0 else "📉"
            color = "#16a34a" if item['change'] > 0 else "#dc2626"
            sign = "+" if item['change'] > 0 else ""
            html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 8px; margin-bottom: 4px; background: white; border-radius: 4px; font-size: 11px;">
                <span style="display: flex; align-items: center; gap: 4px;">
                    <span>{emoji}</span>
                    <span style="font-weight: 500;">{item['name']}</span>
                </span>
                <span style="display: flex; flex-direction: column; align-items: flex-end;">
                    <span style="color: {color}; font-weight: 600;">{sign}{item['change']:.1f}%</span>
                    <span style="font-size: 9px; color: #94a3b8;">({item['old']:.3f} → {item['new']:.3f})</span>
                </span>
            </div>
            """
        html += "</div>"

    if micro_symbol_changes:
        html += """<div><div style="font-size: 11px; color: #7c3aed; margin-bottom: 6px;">📈 个股微波动 (≥2%)</div>"""
        for item in micro_symbol_changes:
            emoji = "📈" if item['change'] > 0 else "📉"
            color = "#16a34a" if item['change'] > 0 else "#dc2626"
            sign = "+" if item['change'] > 0 else ""
            html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 8px; margin-bottom: 4px; background: white; border-radius: 4px; font-size: 11px;">
                <span style="display: flex; align-items: center; gap: 4px;">
                    <span>{emoji}</span>
                    <span style="font-weight: 500;">{item['symbol']}</span>
                    <span style="color: #64748b; font-size: 10px;">{item['name']}</span>
                </span>
                <span style="display: flex; flex-direction: column; align-items: flex-end;">
                    <span style="color: {color}; font-weight: 600;">{sign}{item['change']:.1f}%</span>
                    <span style="font-size: 9px; color: #94a3b8;">({item['old']:.4f} → {item['new']:.4f})</span>
                </span>
            </div>
            """
        html += "</div>"

    html += "</div>"
    return html


def _generate_realtime_market_flow_js() -> str:
    """生成市场状态的实时 JS - 使用原有完整样式"""
    return '''
    <script>
    (function() {
        const POLL_INTERVAL = 10000;

        function fmtIdx(pct) {
            if (pct === null || pct === undefined) return "--";
            return (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
        }

        function idxColor(pct) {
            if (pct === null || pct === undefined) return "#64748b";
            return pct >= 0 ? "#16a34a" : "#dc2626";
        }

        function updateMarketFlow() {
            fetch('/api/market/hotspot')
                .then(r => r.json())
                .then(data => {
                    const cn = data.cn || {};
                    const us = data.us || {};
                    const ms = data.market_state || {};
                    const stats = data.stats || {};

                    const state = ms.state || "unknown";
                    const stateConfig = {
                        'active': {color: '#dc2626', bg: '#fef2f2', emoji: '🔥', label: '焦点集中'},
                        'moderate': {color: '#ca8a04', bg: '#fefce8', emoji: '⚡', label: '焦点较集中'},
                        'quiet': {color: '#0284c7', bg: '#f0f9ff', emoji: '👁️', label: '焦点分散'},
                        'very_quiet': {color: '#16a34a', bg: '#f0fdf4', emoji: '💤', label: '焦点涣散'},
                        'unknown': {color: '#64748b', bg: '#f8fafc', emoji: '❓', label: '未知状态'}
                    };
                    const cfg = stateConfig[state] || stateConfig['unknown'];
                    const globalHotspot = ms.global_hotspot || cn.market_hotspot || 0;
                    const activity = cn.market_activity || 0;

                    const cnBlocks = cn.hot_blocks || [];
                    const cnStocks = cn.hot_stocks || [];
                    const usBlocks = us.hot_blocks || [];
                    const usStocks = us.hot_stocks || [];

                    const cnIndices = cn.indices || {};
                    const usFutures = us.futures || {};
                    const usSummary = us.market_summary || {};

                    const hasUsData = usBlocks.length > 0 || usStocks.length > 0;
                    const hasCnData = cnBlocks.length > 0 || cnStocks.length > 0;
                    const showUsOnly = hasUsData && !hasCnData;
                    const showCnOnly = hasCnData && !hasUsData;
                    const showBoth = hasCnData && hasUsData;

                    let panelTitle = "👁️ 市场热点";
                    if (showUsOnly) panelTitle = "🇺🇸 美股市场热点";
                    else if (showCnOnly) panelTitle = "🇨🇳 A股市场热点";
                    else if (showBoth) panelTitle = "🌐 双市场热点";

                    let html = `<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <div style="font-weight: 600; color: #1e293b;">${panelTitle}</div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <div style="font-size: 12px; color: #64748b;">实时更新</div>
                                <div style="background: ${cfg.bg}; color: ${cfg.color}; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">${cfg.emoji} ${cfg.label}</div>
                            </div>
                        </div>`;

                    // 美股数据（当 showUsOnly 或 showBoth 时显示）
                    if (hasUsData && hasCnData) {
                        // 双市场：美股数据显示在美股区块
                        const usUpPct = usSummary.stock_count > 0 ? (usSummary.up_count / usSummary.stock_count * 100) : 0;
                        const usDownPct = usSummary.stock_count > 0 ? (usSummary.down_count / usSummary.stock_count * 100) : 0;
                        const usFlatPct = usSummary.stock_count > 0 ? (usSummary.flat_count / usSummary.stock_count * 100) : 0;

                        html += `<div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="color: #f8fafc; font-size: 13px; font-weight: 600;">🇺🇸 美股市场</div>
                                <div style="display: flex; gap: 16px; align-items: center;">
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <span style="color: #94a3b8; font-size: 10px;">纳指</span>
                                        <span style="color: ${idxColor(usFutures.NQ)}; font-size: 11px; font-weight: 600;">${fmtIdx(usFutures.NQ)}</span>
                                        <span style="color: #94a3b8; font-size: 10px;">标普</span>
                                        <span style="color: ${idxColor(usFutures.ES)}; font-size: 11px; font-weight: 600;">${fmtIdx(usFutures.ES)}</span>
                                        <span style="color: #94a3b8; font-size: 10px;">道指</span>
                                        <span style="color: ${idxColor(usFutures.YM)}; font-size: 11px; font-weight: 600;">${fmtIdx(usFutures.YM)}</span>
                                    </div>
                                    <div style="display: flex; gap: 12px; border-left: 1px solid #334155; padding-left: 12px;">
                                        <div style="text-align: center;">
                                            <div style="color: #94a3b8; font-size: 9px;">热点度</div>
                                            <div style="color: #22c55e; font-size: 14px; font-weight: 700;">${(us.market_hotspot || 0).toFixed(3)}</div>
                                        </div>
                                        <div style="text-align: center;">
                                            <div style="color: #94a3b8; font-size: 9px;">活跃度</div>
                                            <div style="color: #3b82f6; font-size: 14px; font-weight: 700;">${(us.market_activity || 0).toFixed(3)}</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>`;

                        if (usBlocks.length > 0) {
                            html += `<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #7c3aed; margin-bottom: 8px;">🇺🇸 美股热门题材</div><div style="display: flex; flex-wrap: wrap; gap: 8px;">`;
                            usBlocks.slice(0, 5).forEach(b => {
                                const w = b.weight || 0;
                                const barWidth = Math.min(w * 20, 100);
                                const color = w > 0.5 ? "#dc2626" : (w > 0.3 ? "#ca8a04" : "#16a34a");
                                html += `<div style="background: #f1f5f9; border-radius: 8px; padding: 10px 14px; min-width: 140px;">
                                    <div style="font-size: 14px; font-weight: 600; color: #1e293b;">${b.block_id}</div>
                                    <div style="display: flex; align-items: center; gap: 8px; margin-top: 6px;">
                                        <div style="background: ${color}; height: 6px; border-radius: 3px; width: ${barWidth}px; min-width: 6px;"></div>
                                        <span style="font-size: 13px; font-weight: 600; color: #1e293b;">${w.toFixed(2)}</span>
                                    </div>
                                </div>`;
                            });
                            html += `</div></div>`;
                        }

                        if (usStocks.length > 0) {
                            html += `<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #2563eb; margin-bottom: 8px;">🇺🇸 美股热门股票</div><div style="display: flex; flex-wrap: wrap; gap: 6px;">`;
                            usStocks.slice(0, 10).forEach(s => {
                                const w = s.weight || 0;
                                const changePct = s.change_pct || 0;
                                const color = w > 5 ? "#dc2626" : (w > 3 ? "#ea580c" : (w > 2 ? "#ca8a04" : "#16a34a"));
                                const bgColor = w > 5 ? "#fef2f2" : (w > 3 ? "#fff7ed" : (w > 2 ? "#fef3c7" : "#f0fdf4"));
                                const changeColor = changePct > 0 ? "#16a34a" : (changePct < 0 ? "#dc2626" : "#64748b");
                                const changeStr = changePct !== 0 ? (changePct > 0 ? "+" : "") + changePct.toFixed(2) + "%" : "";
                                html += `<div style="background: ${bgColor}; border-radius: 6px; padding: 6px 10px; font-size: 11px; display: flex; align-items: center; gap: 4px;">
                                    <span style="color: #1e293b; font-weight: 600;">${s.symbol.toUpperCase()}</span>
                                    ${changeStr ? `<span style="font-size: 10px; color: ${changeColor}; font-weight: 600;">${changeStr}</span>` : ""}
                                    <span style="color: ${color}; font-weight: 600;">${w.toFixed(1)}</span>
                                </div>`;
                            });
                            html += `</div></div>`;
                        }

                        if (usSummary.stock_count > 0) {
                            html += `<div style="background: #f1f5f9; border-radius: 6px; padding: 8px 12px; margin-bottom: 16px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-size: 11px; color: #64748b;">🇺🇸 美股涨跌分布 (${usSummary.stock_count}只)</span>
                                    <span style="font-size: 10px; color: #64748b;">🔼${usSummary.up_count} 🔽${usSummary.down_count} ➡️${usSummary.flat_count}</span>
                                </div>
                                <div style="display: flex; gap: 2px; height: 18px; border-radius: 4px; overflow: hidden;">
                                    <div style="background: #22c55e; width: ${usUpPct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 9px; font-weight: 600;">${usUpPct > 5 ? usUpPct.toFixed(0) + "%" : ""}</div>
                                    <div style="background: #94a3b8; width: ${usFlatPct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 9px; font-weight: 600;">${usFlatPct > 5 ? usFlatPct.toFixed(0) + "%" : ""}</div>
                                    <div style="background: #ef4444; width: ${usDownPct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 9px; font-weight: 600;">${usDownPct > 5 ? usDownPct.toFixed(0) + "%" : ""}</div>
                                </div>
                            </div>`;
                        }
                    } else if (showUsOnly) {
                        // 仅美股：完整显示美股区块
                        const usUpPct = usSummary.stock_count > 0 ? (usSummary.up_count / usSummary.stock_count * 100) : 0;
                        const usDownPct = usSummary.stock_count > 0 ? (usSummary.down_count / usSummary.stock_count * 100) : 0;
                        const usFlatPct = usSummary.stock_count > 0 ? (usSummary.flat_count / usSummary.stock_count * 100) : 0;

                        html += `<div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="color: #f8fafc; font-size: 13px; font-weight: 600;">🇺🇸 美股市场</div>
                                <div style="display: flex; gap: 16px; align-items: center;">
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <span style="color: #94a3b8; font-size: 10px;">纳指</span>
                                        <span style="color: ${idxColor(usFutures.NQ)}; font-size: 11px; font-weight: 600;">${fmtIdx(usFutures.NQ)}</span>
                                        <span style="color: #94a3b8; font-size: 10px;">标普</span>
                                        <span style="color: ${idxColor(usFutures.ES)}; font-size: 11px; font-weight: 600;">${fmtIdx(usFutures.ES)}</span>
                                        <span style="color: #94a3b8; font-size: 10px;">道指</span>
                                        <span style="color: ${idxColor(usFutures.YM)}; font-size: 11px; font-weight: 600;">${fmtIdx(usFutures.YM)}</span>
                                    </div>
                                    <div style="display: flex; gap: 12px; border-left: 1px solid #334155; padding-left: 12px;">
                                        <div style="text-align: center;">
                                            <div style="color: #94a3b8; font-size: 9px;">热点度</div>
                                            <div style="color: #22c55e; font-size: 14px; font-weight: 700;">${(us.market_hotspot || 0).toFixed(3)}</div>
                                        </div>
                                        <div style="text-align: center;">
                                            <div style="color: #94a3b8; font-size: 9px;">活跃度</div>
                                            <div style="color: #3b82f6; font-size: 14px; font-weight: 700;">${(us.market_activity || 0).toFixed(3)}</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>`;

                        if (usBlocks.length > 0) {
                            html += `<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #7c3aed; margin-bottom: 8px;">🇺🇸 美股热门题材</div><div style="display: flex; flex-wrap: wrap; gap: 8px;">`;
                            usBlocks.slice(0, 5).forEach(b => {
                                const w = b.weight || 0;
                                const barWidth = Math.min(w * 20, 100);
                                const color = w > 0.5 ? "#dc2626" : (w > 0.3 ? "#ca8a04" : "#16a34a");
                                html += `<div style="background: #f1f5f9; border-radius: 8px; padding: 10px 14px; min-width: 140px;">
                                    <div style="font-size: 14px; font-weight: 600; color: #1e293b;">${b.block_id}</div>
                                    <div style="display: flex; align-items: center; gap: 8px; margin-top: 6px;">
                                        <div style="background: ${color}; height: 6px; border-radius: 3px; width: ${barWidth}px; min-width: 6px;"></div>
                                        <span style="font-size: 13px; font-weight: 600; color: #1e293b;">${w.toFixed(2)}</span>
                                    </div>
                                </div>`;
                            });
                            html += `</div></div>`;
                        }

                        if (usStocks.length > 0) {
                            html += `<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #2563eb; margin-bottom: 8px;">🇺🇸 美股热门股票</div><div style="display: flex; flex-wrap: wrap; gap: 6px;">`;
                            usStocks.slice(0, 10).forEach(s => {
                                const w = s.weight || 0;
                                const changePct = s.change_pct || 0;
                                const color = w > 5 ? "#dc2626" : (w > 3 ? "#ea580c" : (w > 2 ? "#ca8a04" : "#16a34a"));
                                const bgColor = w > 5 ? "#fef2f2" : (w > 3 ? "#fff7ed" : (w > 2 ? "#fef3c7" : "#f0fdf4"));
                                const changeColor = changePct > 0 ? "#16a34a" : (changePct < 0 ? "#dc2626" : "#64748b");
                                const changeStr = changePct !== 0 ? (changePct > 0 ? "+" : "") + changePct.toFixed(2) + "%" : "";
                                html += `<div style="background: ${bgColor}; border-radius: 6px; padding: 6px 10px; font-size: 11px; display: flex; align-items: center; gap: 4px;">
                                    <span style="color: #1e293b; font-weight: 600;">${s.symbol.toUpperCase()}</span>
                                    ${changeStr ? `<span style="font-size: 10px; color: ${changeColor}; font-weight: 600;">${changeStr}</span>` : ""}
                                    <span style="color: ${color}; font-weight: 600;">${w.toFixed(1)}</span>
                                </div>`;
                            });
                            html += `</div></div>`;
                        }

                        if (usSummary.stock_count > 0) {
                            html += `<div style="background: #f1f5f9; border-radius: 6px; padding: 8px 12px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-size: 11px; color: #64748b;">🇺🇸 美股涨跌分布 (${usSummary.stock_count}只)</span>
                                    <span style="font-size: 10px; color: #64748b;">🔼${usSummary.up_count} 🔽${usSummary.down_count} ➡️${usSummary.flat_count}</span>
                                </div>
                                <div style="display: flex; gap: 2px; height: 18px; border-radius: 4px; overflow: hidden;">
                                    <div style="background: #22c55e; width: ${usUpPct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 9px; font-weight: 600;">${usUpPct > 5 ? usUpPct.toFixed(0) + "%" : ""}</div>
                                    <div style="background: #94a3b8; width: ${usFlatPct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 9px; font-weight: 600;">${usFlatPct > 5 ? usFlatPct.toFixed(0) + "%" : ""}</div>
                                    <div style="background: #ef4444; width: ${usDownPct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 9px; font-weight: 600;">${usDownPct > 5 ? usDownPct.toFixed(0) + "%" : ""}</div>
                                </div>
                            </div>`;
                        }
                    }

                    // A股数据（当 showCnOnly 或 showBoth 时显示）
                    if (hasCnData) {
                        const cnDesc = ms.description || "等待数据...";
                        html += `<div style="background: ${cfg.bg}; border-left: 4px solid ${cfg.color}; padding: 12px 16px; margin-bottom: 16px; border-radius: 0 8px 8px 0;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="font-size: 13px; color: #1e293b; line-height: 1.5;"><strong>📊 ${cnDesc}</strong></div>
                                <div style="display: flex; gap: 10px; align-items: center;">
                                    <span style="color: #64748b; font-size: 10px;">上证</span>
                                    <span style="color: ${idxColor(cnIndices.SH)}; font-size: 11px; font-weight: 600;">${fmtIdx(cnIndices.SH)}</span>
                                    <span style="color: #64748b; font-size: 10px;">沪深300</span>
                                    <span style="color: ${idxColor(cnIndices.HS300)}; font-size: 11px; font-weight: 600;">${fmtIdx(cnIndices.HS300)}</span>
                                    <span style="color: #64748b; font-size: 10px;">创业板</span>
                                    <span style="color: ${idxColor(cnIndices.CHINEXT)}; font-size: 11px; font-weight: 600;">${fmtIdx(cnIndices.CHINEXT)}</span>
                                </div>
                            </div>
                            <div style="font-size: 12px; color: #64748b; margin-top: 6px;">A股市场热点指数: <strong>${globalHotspot.toFixed(3)}</strong></div>
                        </div>`;

                        // A股题材
                        if (cnBlocks.length > 0) {
                            html += `<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #7c3aed; margin-bottom: 8px;">📈 A股交易热点题材 Top5</div><div style="display: flex; flex-wrap: wrap; gap: 8px;">`;
                            cnBlocks.slice(0, 5).forEach(b => {
                                const w = b.weight || 0;
                                const barWidth = Math.min(w * 20, 100);
                                const color = w > 0.5 ? "#dc2626" : (w > 0.3 ? "#ca8a04" : "#16a34a");
                                html += `<div style="background: #f1f5f9; border-radius: 8px; padding: 10px 14px; min-width: 140px;">
                                    <div style="font-size: 14px; font-weight: 600; color: #1e293b;">${b.name || b.block_id}</div>
                                    <div style="display: flex; align-items: center; gap: 8px; margin-top: 6px;">
                                        <div style="background: ${color}; height: 6px; border-radius: 3px; width: ${barWidth}px; min-width: 6px;"></div>
                                        <span style="font-size: 13px; font-weight: 600; color: #1e293b;">${w.toFixed(4)}</span>
                                    </div>
                                </div>`;
                            });
                            html += `</div></div>`;
                        }

                        // A股股票
                        if (cnStocks.length > 0) {
                            html += `<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #2563eb; margin-bottom: 8px;">🔥 A股交易热点个股 Top10</div><div style="display: flex; flex-wrap: wrap; gap: 6px;">`;
                            cnStocks.slice(0, 10).forEach(s => {
                                const w = s.weight || 0;
                                const color = w > 5 ? "#dc2626" : (w > 3 ? "#ea580c" : (w > 2 ? "#ca8a04" : "#16a34a"));
                                const bgColor = w > 5 ? "#fef2f2" : (w > 3 ? "#fff7ed" : (w > 2 ? "#fef3c7" : "#f0fdf4"));
                                html += `<div style="background: ${bgColor}; border-radius: 6px; padding: 6px 10px; font-size: 11px; display: flex; align-items: center; gap: 4px; min-width: 0;">
                                    <span style="color: #1e293b; font-weight: 600;">${s.symbol}</span>
                                    <span style="color: #1e293b; max-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${s.name || ""}</span>
                                    <span style="color: ${color}; font-weight: 600;">${w.toFixed(1)}</span>
                                </div>`;
                            });
                            html += `</div></div>`;
                        }
                    }

                    if (cnBlocks.length === 0 && cnStocks.length === 0 && !hasUsData) {
                        html += `<div style="background: #f8fafc; border-radius: 8px; padding: 24px; text-align: center; color: #64748b;">
                            <div style="font-size: 24px; margin-bottom: 8px;">📊</div>
                            <div>暂无市场热点数据</div>
                            <div style="font-size: 12px; margin-top: 4px;">等待市场数据输入...</div>
                        </div>`;
                    }

                    html += `</div>`;
                    document.getElementById('realtime-market-flow').innerHTML = html;
                })
                .catch(e => console.error('Update market flow failed:', e));
        }

        updateMarketFlow();
        setInterval(updateMarketFlow, POLL_INTERVAL);
    })();
    </script>
    '''


def _generate_realtime_changes_js() -> str:
    """生成热点变化的实时 JS"""
    return '''
    <script>
    (function() {
        const POLL_INTERVAL = 10000;

        function formatVolume(vol) {
            if (!vol) return "";
            if (vol >= 1e8) return "量: " + (vol/1e8).toFixed(1) + "亿";
            if (vol >= 1e4) return "量: " + (vol/1e4).toFixed(1) + "万";
            return "量: " + vol.toFixed(0);
        }

        function renderChange(change) {
            const typeConfig = {
                'new_hot': {icon: '🔥', color: '#dc2626', bg: '#fef2f2', label: '新热门'},
                'cooled': {icon: '❄️', color: '#3b82f6', bg: '#eff6ff', label: '冷却'},
                'strengthen': {icon: '📈', color: '#16a34a', bg: '#f0fdf4', label: '加强'},
                'weaken': {icon: '📉', color: '#f59e0b', bg: '#fffbeb', label: '减弱'}
            };
            const cfg = typeConfig[change.change_type] || {icon: '•', color: '#64748b', bg: '#f8fafc', label: '变化'};

            let marketInfo = [];
            if (change.price) marketInfo.push("¥" + change.price.toFixed(2));
            if (change.price_change) marketInfo.push((change.price_change >= 0 ? "+" : "") + change.price_change.toFixed(2) + "%");
            if (change.block) marketInfo.push("[" + change.block + "]");

            let volumeStr = formatVolume(change.volume);

            return `<div style="padding: 10px 12px; margin-bottom: 6px; background: ${cfg.bg}; border-radius: 8px; border-left: 3px solid ${cfg.color}; font-size: 13px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                            <span style="font-size: 11px; color: #64748b; font-family: monospace;">${change.time || ''}</span>
                            <span style="font-size: 16px;">${cfg.icon}</span>
                            <span style="font-weight: 600; color: #1e293b;">${change.item_name || change.item_id || ''}</span>
                            <span style="font-size: 10px; color: ${cfg.color}; background: rgba(255,255,255,0.6); padding: 1px 6px; border-radius: 4px;">${cfg.label}</span>
                        </div>
                        <div style="font-size: 11px; color: #64748b; margin-left: 46px;">
                            权重: ${(change.old_weight || 0).toFixed(2)} → ${(change.new_weight || 0).toFixed(2)} (${(change.change_percent >= 0 ? '+' : '') + (change.change_percent || 0).toFixed(1)}%)
                            ${marketInfo.length ? ' | ' + marketInfo.join(' | ') : ''}
                            ${volumeStr ? ' | ' + volumeStr : ''}
                        </div>
                    </div>
                </div>
            </div>`;
        }

        function renderShiftReport(shift) {
            if (!shift || !shift.has_shift) {
                return `<div style="color: #64748b; text-align: center; padding: 10px;">暂无热点切换<br><span style="font-size: 12px;">Top 3 题材和 Top 5 个股未发生变化</span></div>`;
            }

            let html = '';

            if (shift.block_shift) {
                const removed = shift.old_top_blocks.filter(b => !shift.new_top_blocks.find(n => n[0] === b[0]));
                const added = shift.new_top_blocks.filter(n => !shift.old_top_blocks.find(o => o[0] === n[0]));
                const kept = shift.new_top_blocks.filter(n => shift.old_top_blocks.find(o => o[0] === n[0]));

                if (removed.length || added.length) {
                    html += `<div style="margin-bottom: 14px;">`;
                    if (removed.length) {
                        html += `<div style="font-weight: 500; color: #dc2626; margin-bottom: 6px;">📤 退出 Top3:</div>`;
                        html += `<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;">`;
                        removed.forEach(b => {
                            html += `<span style="background: #fee2e2; color: #dc2626; padding: 3px 10px; border-radius: 6px; font-size: 12px;">${b[1] || b[0]} <span style="opacity: 0.7;">${(b[2] || 0).toFixed(2)}</span></span>`;
                        });
                        html += `</div>`;
                    }
                    if (added.length) {
                        html += `<div style="font-weight: 500; color: #16a34a; margin-bottom: 6px;">📥 新进入 Top3:</div>`;
                        html += `<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;">`;
                        added.forEach(b => {
                            html += `<span style="background: #dcfce7; color: #16a34a; padding: 3px 10px; border-radius: 6px; font-size: 12px;">${b[1] || b[0]} <span style="opacity: 0.7;">${(b[2] || 0).toFixed(2)}</span></span>`;
                        });
                        html += `</div>`;
                    }
                    html += `</div>`;
                }
            }

            if (shift.symbol_shift) {
                const removedSym = shift.old_top_symbols.filter(s => !shift.new_top_symbols.find(n => n[0] === s[0]));
                const addedSym = shift.new_top_symbols.filter(n => !shift.old_top_symbols.find(o => o[0] === n[0]));

                if (removedSym.length || addedSym.length) {
                    html += `<div style="margin-top: 8px;">`;
                    if (removedSym.length) {
                        html += `<div style="font-weight: 500; color: #dc2626; margin-bottom: 6px;">📤 退出 Top5:</div>`;
                        html += `<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;">`;
                        removedSym.forEach(s => {
                            html += `<span style="background: #fee2e2; color: #dc2626; padding: 2px 8px; border-radius: 4px; font-size: 11px;">${s[0]}${s[1] !== s[0] ? ' ' + s[1] : ''} <span style="opacity: 0.7;">${(s[2] || 0).toFixed(1)}</span></span>`;
                        });
                        html += `</div>`;
                    }
                    if (addedSym.length) {
                        html += `<div style="font-weight: 500; color: #16a34a; margin-bottom: 6px;">📥 新进入 Top5:</div>`;
                        html += `<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;">`;
                        addedSym.forEach(s => {
                            html += `<span style="background: #dcfce7; color: #16a34a; padding: 2px 8px; border-radius: 4px; font-size: 11px;">${s[0]}${s[1] !== s[0] ? ' ' + s[1] : ''} <span style="opacity: 0.7;">${(s[2] || 0).toFixed(1)}</span></span>`;
                        });
                        html += `</div>`;
                    }
                    html += `</div>`;
                }
            }

            return html;
        }

        function updateChanges() {
            fetch('/api/market/hotspot')
                .then(r => r.json())
                .then(data => {
                    const changes = data.recent_changes || [];
                    const shift = data.shift_report || {has_shift: false};
                    const timestamp = new Date().toLocaleTimeString();

                    let changesHtml = '';
                    if (changes.length === 0) {
                        changesHtml = `<div style="color: #64748b; text-align: center; padding: 20px;">暂无变化记录<br><span style="font-size: 12px;">等待数据更新...</span></div>`;
                    } else {
                        changes.slice(0, 10).forEach(change => {
                            changesHtml += renderChange(change);
                        });
                    }

                    let shiftHtml = renderShiftReport(shift);
                    if (shift.has_shift) {
                        shiftHtml = `<div style="background: linear-gradient(135deg, #fef3c7, #fde68a); border: 1px solid #f59e0b; border-radius: 8px; padding: 16px; margin-top: 12px;">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                                <span style="font-size: 16px;">🚨</span>
                                <span style="font-weight: 700; color: #92400e; font-size: 13px;">热点转移 detected</span>
                            </div>
                            ${shiftHtml}
                        </div>`;
                    } else {
                        shiftHtml = `<div style="background: linear-gradient(135deg, #f0f9ff, #e0f2fe); border: 1px solid #7dd3fc; border-radius: 8px; padding: 16px; margin-top: 12px;">
                            <div style="font-weight: 600; margin-bottom: 8px; color: #0369a1;">🔄 热点切换监测</div>
                            ${shiftHtml}
                        </div>`;
                    }

                    const html = `
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                            <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                    <div style="font-weight: 600; color: #1e293b;">📈 个股重大变化记录</div>
                                    <div style="font-size: 11px; color: #64748b;">${timestamp}</div>
                                </div>
                                <div style="max-height: 300px; overflow-y: auto;">
                                    ${changesHtml}
                                </div>
                            </div>
                            <div>
                                ${shiftHtml}
                            </div>
                        </div>
                    `;

                    document.getElementById('realtime-hotspot-changes').innerHTML = html;
                })
                .catch(e => console.error('Update changes failed:', e));
        }

        updateChanges();
        setInterval(updateChanges, POLL_INTERVAL);
    })();
    </script>
    '''


def _generate_realtime_strategy_status_js() -> str:
    """生成策略状态的实时 JS"""
    return '''
    <script>
    (function() {
        const POLL_INTERVAL = 15000;

        async function updateStrategyStatus() {
            try {
                const resp = await fetch('/api/market/hotspot');
                const data = await resp.json();
                const cn = data.cn || {};
                const processed = cn.processed_snapshots || 0;
                const dualSummary = cn.dual_engine_summary || {};
                const riverStats = dualSummary.river_stats || {};
                const pytorchStats = dualSummary.pytorch_stats || {};
                const timestamp = new Date().toLocaleTimeString();

                const html = `
                    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-top: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <div style="font-weight: 600; color: #1e293b;">🧠 策略状态</div>
                            <div style="font-size: 11px; color: #64748b;">${timestamp}</div>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;">
                            <div style="background: #f8fafc; padding: 10px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 10px; color: #64748b;">已处理</div>
                                <div style="font-size: 16px; font-weight: bold; color: #3b82f6;">${processed}</div>
                            </div>
                            <div style="background: #f8fafc; padding: 10px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 10px; color: #64748b;">River</div>
                                <div style="font-size: 16px; font-weight: bold; color: #10b981;">${riverStats.processed_count || 0}</div>
                            </div>
                            <div style="background: #f8fafc; padding: 10px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 10px; color: #64748b;">异常检测</div>
                                <div style="font-size: 16px; font-weight: bold; color: #f59e0b;">${riverStats.anomaly_count || 0}</div>
                            </div>
                            <div style="background: #f8fafc; padding: 10px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 10px; color: #64748b;">PyTorch</div>
                                <div style="font-size: 16px; font-weight: bold; color: #8b5cf6;">${pytorchStats.inference_count || 0}</div>
                            </div>
                        </div>
                    </div>
                `;

                document.getElementById('realtime-strategy-status').innerHTML = html;
            } catch (e) {
                console.error('Update strategy status failed:', e);
            }
        }

        updateStrategyStatus();
        setInterval(updateStrategyStatus, POLL_INTERVAL);
    })();
    </script>
    '''


def _get_history_tracker():
    """获取历史追踪器"""
    try:
        from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
        return get_history_tracker()
    except Exception:
        return None


def _run_diagnostic():
    """运行诊断"""
    from deva.naja.market_hotspot.ui_components.diagnostic import render_hotspot_diagnostic
    render_hotspot_diagnostic()


def _manage_noise_filter():
    """管理噪音过滤黑白名单"""
    from pywebio.output import popup, put_html, put_buttons, put_row
    from pywebio.input import input_group, input

    hotspot_system = SR('hotspot_system')
    noise_filter = hotspot_system.noise_filter

    def refresh_popup():
        """刷新弹窗内容"""
        blacklist = list(noise_filter.config.blacklist)
        whitelist = list(noise_filter.config.whitelist)

        html = f"""
        <div style="padding: 16px;">
            <div style="margin-bottom: 20px;">
                <div style="font-weight: 600; color: #dc2626; margin-bottom: 8px;">⚫ 黑名单 ({len(blacklist)})</div>
                <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">强制过滤的股票</div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px; max-height: 100px; overflow-y: auto;">
                    {''.join([f'<span style="font-size: 11px; padding: 4px 8px; background: #fee2e2; color: #dc2626; border-radius: 4px;">{s}</span>' for s in blacklist]) if blacklist else '<span style="color: #94a3b8;">暂无</span>'}
                </div>
            </div>

            <div style="margin-bottom: 20px;">
                <div style="font-weight: 600; color: #16a34a; margin-bottom: 8px;">⚪ 白名单 ({len(whitelist)})</div>
                <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">保护不被过滤的股票</div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px; max-height: 100px; overflow-y: auto;">
                    {''.join([f'<span style="font-size: 11px; padding: 4px 8px; background: #dcfce7; color: #16a34a; border-radius: 4px;">{s}</span>' for s in whitelist]) if whitelist else '<span style="color: #94a3b8;">暂无</span>'}
                </div>
            </div>

            <div style="background: #f8fafc; padding: 12px; border-radius: 8px; font-size: 12px; color: #64748b;">
                <strong>当前过滤配置:</strong><br>
                • 最小金额: {noise_filter.config.min_amount:,.0f} 元<br>
                • 最小成交量: {noise_filter.config.min_volume:,.0f} 股<br>
                • 动态阈值: {'启用' if noise_filter.config.dynamic_threshold else '禁用'}<br>
                • B股过滤: {'启用' if noise_filter.config.filter_b_shares else '禁用'}
            </div>
        </div>
        """
        return html

    popup_ctx = popup("🔇 噪音过滤管理")

    async def _do_add_to_blacklist():
        """添加到黑名单"""
        async def handle_input(form_data):
            symbol = form_data.get("symbol", "").strip()
            if symbol:
                noise_filter.add_to_blacklist(symbol, "手动添加")
                from pywebio.output import toast
                toast(f"已添加 {symbol} 到黑名单", color="success")
                popup_ctx.close()
                _manage_noise_filter()

        form = await input_group("添加黑名单", [
            input("股票代码", name="symbol", placeholder="如: 200012", required=True),
        ])
        if form:
            await handle_input(form)

    async def _do_add_to_whitelist():
        """添加到白名单"""
        async def handle_input(form_data):
            symbol = form_data.get("symbol", "").strip()
            if symbol:
                noise_filter.add_to_whitelist(symbol, "手动添加")
                from pywebio.output import toast
                toast(f"已添加 {symbol} 到白名单", color="success")
                popup_ctx.close()
                _manage_noise_filter()

        form = await input_group("添加白名单", [
            input("股票代码", name="symbol", placeholder="如: 000001", required=True),
        ])
        if form:
            await handle_input(form)

    async def _do_remove_from_blacklist():
        """从黑名单移除"""
        async def handle_input(form_data):
            symbol = form_data.get("symbol", "").strip()
            if symbol:
                noise_filter.remove_from_blacklist(symbol)
                from pywebio.output import toast
                toast(f"已从黑名单移除 {symbol}", color="success")
                popup_ctx.close()
                _manage_noise_filter()

        form = await input_group("从黑名单移除", [
            input("股票代码", name="symbol", placeholder="如: 200012", required=True),
        ])
        if form:
            await handle_input(form)

    async def _do_remove_from_whitelist():
        """从白名单移除"""
        async def handle_input(form_data):
            symbol = form_data.get("symbol", "").strip()
            if symbol:
                noise_filter.remove_from_whitelist(symbol)
                from pywebio.output import toast
                toast(f"已从白名单移除 {symbol}", color="success")
                popup_ctx.close()
                _manage_noise_filter()

        form = await input_group("从白名单移除", [
            input("股票代码", name="symbol", placeholder="如: 000001", required=True),
        ])
        if form:
            await handle_input(form)

    async def reset_stats():
        """重置统计"""
        noise_filter.reset_stats()
        from pywebio.output import toast
        toast("统计已重置", color="success")
        popup_ctx.close()
        _manage_noise_filter()

    with popup_ctx:
        put_html(refresh_popup())

        put_row([
            put_buttons([
                {'label': '⚫ 添加黑名单', 'value': 'add_black', 'color': 'danger'},
                {'label': '⚪ 添加白名单', 'value': 'add_white', 'color': 'success'},
            ], onclick=lambda v: run_async(_do_add_to_blacklist()) if v == 'add_black' else run_async(_do_add_to_whitelist())),
        ])

        put_row([
            put_buttons([
                {'label': '移除黑名单', 'value': 'remove_black', 'color': 'secondary'},
                {'label': '移除白名单', 'value': 'remove_white', 'color': 'secondary'},
            ], onclick=lambda v: run_async(_do_remove_from_blacklist()) if v == 'remove_black' else run_async(_do_remove_from_whitelist())),
        ])

        put_buttons([
            {'label': '🔄 重置统计', 'value': 'reset', 'color': 'warning'},
            {'label': '❌ 关闭', 'value': 'close', 'color': 'secondary'},
        ], onclick=lambda v: run_async(reset_stats()) if v == 'reset' else popup_ctx.close())



