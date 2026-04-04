"""注意力系统 UI 管理页面入口"""

from datetime import datetime
from pywebio.output import put_html, put_row, put_column, put_text, put_button, use_scope
from pywebio.session import run_js, run_async
from pywebio.output import toast

from deva.naja.page_help import render_help_collapse


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


async def render_attention_admin(ctx: dict):
    """渲染注意力系统管理页面"""

    from .common import (
        get_attention_report, get_strategy_stats, is_attention_initialized,
        initialize_attention_system, get_strategy_manager,
    )
    from .cards import (
        render_frequency_distribution, render_strategy_status,
        render_dual_engine_status, render_noise_filter_status, render_hot_sectors_and_stocks,
        render_market_state_panel,
    )
    from .awakening import render_awakening_status
    from .timeline import (
        render_attention_timeline, render_sector_trends, render_attention_shift_report,
        render_multi_threshold_timeline, render_attention_changes, render_recent_signals,
    )
    from .intelligence import render_intelligence_panels
    from .flow import (
        render_attention_flow_ui,
        render_attention_layers_detail,
        # render_data_frequency_panel,  # 已删除
        render_noise_filter_panel,
        render_strategy_status_panel,
        render_dual_engine_panel,
    )

    attention_initialized = is_attention_initialized()

    report = get_attention_report()
    strategy_stats = get_strategy_stats()
    experiment_info = _get_experiment_info()

    global_attention = report.get('global_attention', 0)
    activity = report.get('activity', 0)
    attention_details = report.get('attention_details', {})
    attention_level = attention_details.get('attention_level', '未知') if attention_details else '未知'
    activity_level = attention_details.get('activity_level', '未知') if attention_details else '未知'
    market_timestamp = attention_details.get('timestamp') if attention_details and not attention_details.get('error') else None
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

    attention_icon = "🔥" if global_attention >= 0.6 else ("📊" if global_attention >= 0.3 else "💤")
    activity_icon = "⚡" if activity >= 0.7 else ("🌡️" if activity >= 0.15 else "❄️")
    attention_color = "#dc2626" if global_attention >= 0.6 else ("#ca8a04" if global_attention >= 0.3 else "#64748b")
    activity_color = "#dc2626" if activity >= 0.7 else ("#ca8a04" if activity >= 0.15 else "#64748b")
    market_time_html = f'<div style="font-size: 11px; color: #0ea5e9; margin-top: 6px;">📅 数据时间: {market_time_str}</div>' if market_time_str else ''

    with use_scope("attention_header"):
        put_html(f"""
        <div style="
            margin-bottom: 12px;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
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
                        <span style="font-size: 24px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">👁️</span>
                        <div>
                            <div style="font-size: 16px; font-weight: 700; color: #f1f5f9;">注意力（调度层）</div>
                            <div style="font-size: 11px; color: #0ea5e9; margin-top: 2px;">只负责分配注意力，不输出结论</div>
                        </div>
                    </div>
                    <div style="font-size: 12px; color: #64748b; margin-top: 6px;">输入：雷达事件/洞察提示 ｜ 输出：权重分配/调度决策</div>
                    {market_time_html}
                </div>
                <div style="display: flex; gap: 16px; text-align: center;">
                    <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">注意力</div>
                        <div style="font-size: 18px; font-weight: 700; color: {attention_color};">{attention_icon} {global_attention:.2f}</div>
                        <div style="font-size: 10px; color: {attention_color}; opacity: 0.8;">{attention_level}</div>
                    </div>
                    <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">活跃度</div>
                        <div style="font-size: 18px; font-weight: 700; color: {activity_color};">{activity_icon} {activity:.2f}</div>
                        <div style="font-size: 10px; color: {activity_color}; opacity: 0.8;">{activity_level}</div>
                    </div>
                    <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">系统状态</div>
                        <div style="font-size: 14px; font-weight: 700; color: #22c55e;">{'🟢 运行中' if report.get('status') == 'running' else '🔴 已停止'}</div>
                        <div style="font-size: 10px; color: #94a3b8;">{processed} 快照</div>
                    </div>
                    <div style="background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">策略</div>
                        <div style="font-size: 14px; font-weight: 700; color: #a855f7;">{strategy_stats.get('active_strategies', 0)}/{strategy_stats.get('total_strategies', 0)}</div>
                        <div style="font-size: 10px; color: #94a3b8;">{strategy_stats.get('total_signals_generated', 0)} 信号</div>
                    </div>
                </div>
            </div>
        </div>
        """)

        if not attention_initialized:
            put_html("""
            <div style="margin-bottom:14px;padding:16px;border-radius:10px;background:linear-gradient(135deg,#fef3c7,#fde68a);border:1px solid #f59e0b;color:#92400e;font-size:14px;">
                <strong>⚠️ 注意力系统未启动</strong><br>
                当前 naja 启动时未启用注意力系统。点击下方按钮手动启动。
            </div>
            """)
            put_button("🚀 启动注意力系统", onclick=lambda: initialize_attention_system(), color="warning")
            put_text("")

        if experiment_info.get('active'):
            exp_ds = experiment_info.get('datasource_id', '未知')
            put_html(f"""
            <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;background:linear-gradient(135deg,#dbeafe,#bfdbfe);border:1px solid #93c5fd;color:#1e40af;font-size:13px;">
                <strong>🧪 实验模式运行中</strong><br>
                数据源: {exp_ds} | 策略数: {experiment_info.get('strategy_count', 0)}
            </div>
            """)

        fetcher = report.get('realtime_fetcher')
        if fetcher:
            fetcher_running = fetcher.get('running', False)
            is_force_mode = fetcher.get('is_force_trading_mode', False)

            cn_info = fetcher.get('cn_info', {})
            us_info = fetcher.get('us_info', {})
            cn_active = fetcher.get('cn_active', False)
            us_active = fetcher.get('us_active', False)

            cn_phase = cn_info.get('phase', 'closed')
            us_phase = us_info.get('phase', 'closed')
            cn_phase_name = cn_info.get('phase_name', '休市')
            us_phase_name = us_info.get('phase_name', '休市')
            cn_next = cn_info.get('next_change_time', '')
            us_next = us_info.get('next_change_time', '')
            cn_next_phase = cn_info.get('next_phase_name', '')
            us_next_phase = us_info.get('next_phase_name', '')

            cn_color = '#22c55e' if cn_phase in ('trading', 'pre_market', 'call_auction') else '#f59e0b'
            us_color = '#22c55e' if us_phase in ('trading', 'pre_market') else '#f59e0b'

            if is_force_mode:
                panel_html = f"""
                <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;background:linear-gradient(135deg,#f0fdf4,#dcfce7);border:1px solid #86efac;color:#166534;font-size:13px;">
                    <strong>📡 实盘获取器 🟢</strong> <span style="color:#06b6d4;font-weight:bold;">强制调试中</span><br>
                    <span style="font-size:12px;">
                    🔧 模式: <span style="color:#06b6d4;font-weight:bold;">强制实盘(忽略交易时间)</span>
                    </span><br>
                    <span style="font-size:11px;color:#64748b;">
                    🔄 获取次数: {fetcher.get('fetch_count', 0)} |
                    ❌ 错误: {fetcher.get('error_count', 0)} |
                    📈 档位: HIGH={fetcher.get('high_count', 0)} | MEDIUM={fetcher.get('medium_count', 0)} | LOW={fetcher.get('low_count', 0)}
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
                    cn_level_str = f"A股档位: HIGH={fetcher.get('high_count', 0)} | MEDIUM={fetcher.get('medium_count', 0)} | LOW={fetcher.get('low_count', 0)}" if cn_active else ""
                    us_level_str = f"美股档位: HIGH={fetcher.get('us_high_count', 0)} | MEDIUM={fetcher.get('us_medium_count', 0)} | LOW={fetcher.get('us_low_count', 0)}" if us_active else ""
                    level_str = " | ".join(filter(None, [cn_level_str, us_level_str]))
                    
                    if cn_active and us_active:
                        fetch_info = f"A股🔄{fetcher.get('fetch_count', 0)} | 美股🔄{fetcher.get('us_fetch_count', 0)}"
                    elif cn_active:
                        fetch_info = f"A股 🔄{fetcher.get('fetch_count', 0)} ❌{fetcher.get('error_count', 0)}"
                    elif us_active:
                        fetch_info = f"美股 🔄{fetcher.get('us_fetch_count', 0)} ❌{fetcher.get('us_error_count', 0)}"
                    else:
                        fetch_info = f"🔄{fetcher.get('fetch_count', 0)} ❌{fetcher.get('error_count', 0)}"
                    
                    panel_html = f"""
                    <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;background:linear-gradient(135deg,#f0fdf4,#dcfce7);border:1px solid #86efac;color:#166534;font-size:13px;">
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
                    panel_html = f"""
                    <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;background:linear-gradient(135deg,#fef3c7,#fde68a);border:1px solid #f59e0b;color:#92400e;font-size:13px;">
                        <strong>📡 实盘获取器 🔴</strong> <span style="color:#f59e0b;font-weight:bold;">待机中</span><br>
                        <span style="font-size:12px;">
                        📊 状态: {status_str}
                        </span><br>
                        <span style="font-size:11px;color:#92400e;">
                        ⏰ A股下次开盘: {cn_next} | 美股下次开盘: {us_next}
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

            def _format_market_line(label, info):
                phase_name = info.get('phase_name', '未知')
                next_phase = info.get('next_phase_name', '')
                next_time = info.get('next_change_time', '')
                if info.get('phase') == 'closed' and next_time:
                    return f"{label}{phase_name} →{next_phase} {next_time}"
                return f"{label}{phase_name}"

            cn_line = _format_market_line("A股", cn_info)
            us_line = _format_market_line("美股", us_info)

            put_html(f"""
            <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;background:linear-gradient(135deg,#f1f5f9,#e2e8f0);border:1px solid #cbd5e1;color:#475569;font-size:13px;">
                <strong>📡 实盘获取器</strong> 未启动<br>
                <span style="font-size:12px;">
                🕐 当前时间: {current_weekday} {current_time_str} |
                📊 状态: <span style="color:#f59e0b;font-weight:bold;">{cn_line} | {us_line}</span> |
                模式: <span style="color:#0ea5e9;font-weight:bold;">{mode_ctx.get('mode_label', '实盘模式')}</span>
                </span><br>
                <span style="font-size:11px;color:#64748b;">
                调用 start_realtime_fetcher() 手动启动
                </span>
            </div>
            """)

        try:
            render_help_collapse("attention")
        except Exception:
            pass

    with use_scope("attention_awakening"):
        put_html(render_awakening_status())

    with use_scope("attention_market_state"):
        put_html(render_market_state_panel())

    with use_scope("attention_flow"):
        put_html(render_attention_flow_ui())

    with use_scope("attention_lab_status"):
        put_html(_render_lab_status_panel())

    # 已删除数据获取器面板（2026-04-03）
    # with use_scope("attention_frequency_panel"):
    #     try:
    #         html = render_data_frequency_panel()
    #         print(f"[Admin] render_data_frequency_panel returned: {len(html)} chars")
    #         print(f"[Admin] HTML START: {html[:500]}")
    #         print(f"[Admin] HTML END")
    #         put_html(html)
    #     except Exception as e:
    #         print(f"[Admin] render_data_frequency_panel failed: {e}")
    #         import traceback
    #         traceback.print_exc()

    with use_scope("attention_noise"):
        put_html(render_noise_filter_panel())

    with use_scope("attention_strategy"):
        put_html(render_strategy_status_panel())

    with use_scope("attention_dual_engine"):
        put_html(render_dual_engine_panel())

    with use_scope("attention_shift"):
        shift_report = _get_attention_shift_report_impl()
        put_html(render_attention_shift_report(shift_report))

    with use_scope("attention_signals"):
        manager = get_strategy_manager()
        if manager:
            signals = manager.get_recent_signals(n=20)
            put_html(render_recent_signals(signals))

    with use_scope("attention_intelligence"):
        put_html(render_intelligence_panels())

    put_text("")

    with use_scope("attention_sector_micro"):
        put_html(_render_micro_change_indicator())

    put_text("")

    put_row([
        put_button("🔍 运行诊断", onclick=lambda: _run_diagnostic(), small=True),
        put_button("🔇 噪音过滤管理", onclick=lambda: _manage_noise_filter(), small=True, color="info"),
    ], size="auto")


def _get_attention_shift_report_impl():
    """获取注意力转移报告"""
    tracker = _get_history_tracker()
    if tracker:
        try:
            return tracker.get_attention_shift_report()
        except Exception:
            pass
    return {'has_shift': False}


def _get_attention_changes_impl():
    """获取注意力变化记录"""
    tracker = _get_history_tracker()
    if tracker:
        try:
            return tracker.get_recent_changes(n=20)
        except Exception:
            pass
    return []


def _get_pytorch_patterns_html() -> str:
    """获取 PyTorch 模式识别的 HTML"""
    try:
        from .cards import render_pytorch_patterns
        return render_pytorch_patterns()
    except Exception:
        return "<div style='color: #64748b;'>加载失败</div>"


def _get_attention_changes_html() -> str:
    """获取注意力变化的 HTML"""
    changes = _get_attention_changes_impl()
    try:
        from .timeline import render_attention_changes
        return render_attention_changes(changes)
    except Exception:
        return "<div style='color: #64748b;'>加载失败</div>"


def _render_micro_change_indicator() -> str:
    """渲染细微变化指示器 - 捕获板块和个股的微小波动"""
    tracker = _get_history_tracker()
    if not tracker or len(tracker.snapshots) < 2:
        return ""

    recent_snapshots = list(tracker.snapshots)[-10:]

    micro_sector_changes = []
    micro_symbol_changes = []

    if len(recent_snapshots) >= 2:
        prev_snapshot = recent_snapshots[-2]
        curr_snapshot = recent_snapshots[-1]

        for sector_id, curr_weight in curr_snapshot.sector_weights.items():
            prev_weight = prev_snapshot.sector_weights.get(sector_id, 0)
            if prev_weight > 0:
                change_pct = ((curr_weight - prev_weight) / prev_weight) * 100
                if abs(change_pct) >= 1:
                    sector_name = tracker.get_sector_name(sector_id)
                    micro_sector_changes.append({
                        'name': sector_name,
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

    micro_sector_changes.sort(key=lambda x: abs(x['change']), reverse=True)
    micro_symbol_changes.sort(key=lambda x: abs(x['change']), reverse=True)

    micro_sector_changes = micro_sector_changes[:6]
    micro_symbol_changes = micro_symbol_changes[:8]

    if not micro_sector_changes and not micro_symbol_changes:
        return f"""
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">📊 细微变化监测 · 近{len(recent_snapshots)}个时间点</div>
            <div style="text-align: center; color: #94a3b8; font-size: 12px; padding: 12px;">暂无明显波动</div>
        </div>
        """

    html = f"""
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
        <div style="font-size: 12px; color: #64748b; margin-bottom: 10px;">📊 细微变化监测 · 近{len(recent_snapshots)}个时间点</div>
    """

    if micro_sector_changes:
        html += """<div style="margin-bottom: 10px;"><div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">板块微波动 (≥1%)</div>"""
        for item in micro_sector_changes:
            emoji = "📈" if item['change'] > 0 else "📉"
            color = "#16a34a" if item['change'] > 0 else "#dc2626"
            sign = "+" if item['change'] > 0 else ""
            html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 8px; margin-bottom: 4px; background: white; border-radius: 4px; font-size: 11px;">
                <span>{emoji} {item['name']}</span>
                <span style="color: {color}; font-weight: 600;">{sign}{item['change']:.1f}%</span>
            </div>
            """
        html += "</div>"

    if micro_symbol_changes:
        html += """<div><div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">个股微波动 (≥2%)</div>"""
        for item in micro_symbol_changes:
            emoji = "📈" if item['change'] > 0 else "📉"
            color = "#16a34a" if item['change'] > 0 else "#dc2626"
            sign = "+" if item['change'] > 0 else ""
            html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 8px; margin-bottom: 4px; background: white; border-radius: 4px; font-size: 11px;">
                <span>{emoji} {item['symbol']} {item['name']}</span>
                <span style="color: {color}; font-weight: 600;">{sign}{item['change']:.1f}%</span>
            </div>
            """
        html += "</div>"

    html += "</div>"
    return html


def _get_history_tracker():
    """获取历史追踪器"""
    try:
        from deva.naja.cognition.history_tracker import get_history_tracker
        return get_history_tracker()
    except Exception:
        return None


def _run_diagnostic():
    """运行诊断"""
    from deva.naja.attention.diagnostic import render_attention_diagnostic
    render_attention_diagnostic()


def _manage_noise_filter():
    """管理噪音过滤黑白名单"""
    from pywebio.output import popup, put_html, put_buttons, put_row
    from pywebio.input import input_group, input
    from deva.naja.attention import get_noise_filter

    noise_filter = get_noise_filter()

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


def _render_technical_debug_section(title: str, content: str) -> str:
    """渲染弱化的技术调试折叠区块"""
    return f"""
    <details style="margin-bottom: 8px;">
        <summary style="cursor: pointer; padding: 6px 12px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; font-weight: 500; color: #94a3b8; font-size: 12px; user-select: none;">
            {title}
        </summary>
        <div style="padding: 10px; background: white; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 6px 6px;">
            {content}
        </div>
    </details>
    """


def _do_refresh():
    """手动刷新"""
    toast("正在刷新...", color="info")
    run_js("window.location.reload()")


def _get_lab_activity_logs() -> list:
    """获取 Lab 活动日志"""
    logs = []

    try:
        from deva.naja.attention.trading_center import get_trading_center
        orch = get_trading_center()
        lab_status = orch.get_lab_status()
        processed = lab_status.get('processed_frames', 0)
        if processed > 0:
            logs.append(f"已处理 {processed} 帧数据")
    except:
        pass

    try:
        from deva.naja.bandit.notifier import get_bandit_notifier
        notifier = get_bandit_notifier()
        recent = notifier.get_recent_notifications(limit=5)
        for n in recent:
            logs.append(f"{n.get('type', 'unknown')}: {n.get('title', '')[:40]}")
    except:
        pass

    try:
        from deva.naja.replay import get_replay_scheduler
        scheduler = get_replay_scheduler()
        if scheduler and hasattr(scheduler, '_fetch_count'):
            logs.append(f"回放进度: {scheduler._fetch_count}")
    except:
        pass

    try:
        from deva.naja.bandit.market_observer import get_market_observer
        observer = get_market_observer()
        if observer and hasattr(observer, '_tracked_stocks'):
            logs.append(f"跟踪 {len(observer._tracked_stocks)} 只股票")
    except:
        pass

    return logs[-10:] if logs else []


def _render_lab_status_panel() -> str:
    """渲染 Lab 模式状态面板 - 显示注意力系统关键指标"""
    try:
        from deva.naja.attention.trading_center import get_trading_center
        orch = get_trading_center()
        lab_status = orch.get_lab_status()
    except Exception as e:
        return f"""<div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;background:linear-gradient(135deg,#fef3c7,#fde68a);border:1px solid #f59e0b;color:#92400e;font-size:13px;">
            <strong>🧪 Lab 状态面板</strong> <span style="color:#f59e0b;">(获取失败)</span><br>
            <span style="font-size:11px;">{str(e)}</span>
        </div>"""

    manas = lab_status.get('manas', {})
    awakened = lab_status.get('awakened', {})
    narrative = lab_status.get('narrative', {})
    problem_opp = lab_status.get('problem_opportunity')

    manas_score = manas.get('manas_score', 0)
    ai_compute = manas.get('ai_compute_direction', 'unknown')
    problem_score = manas.get('problem_opportunity_score', 0)
    signal_strength = manas.get('signal_strength', 0)
    should_act = manas.get('should_act', False)
    awakening_level = awakened.get('level', 'unknown')
    insight_count = awakened.get('total_insights', 0)
    narrative_count = narrative.get('event_count', 0)
    latest_event = narrative.get('latest_event', 'N/A')
    supply_demand = narrative.get('supply_demand_signal', 'neutral')

    score_color = '#22c55e' if manas_score > 0.6 else '#f59e0b' if manas_score > 0.3 else '#64748b'
    act_color = '#22c55e' if should_act else '#94a3b8'
    ai_color = '#22c55e' if ai_compute == 'rising' else '#f59e0b' if ai_compute == 'falling' else '#64748b'
    awakening_color = '#22c55e' if awakening_level == 'enlightened' else '#0ea5e9' if awakening_level == 'illuminated' else '#64748b'

    problem_html = ""
    if problem_opp:
        problem_html = f"""<div style="margin-top:8px;padding:8px;background:linear-gradient(135deg,#dbeafe,#bfdbfe);border-radius:6px;font-size:11px;">
            <strong>🎯 问题-机会:</strong> {problem_opp.get('problem', 'N/A')}<br>
            <strong>💡 洞察:</strong> {problem_opp.get('opportunity', 'N/A')}
        </div>"""

    return f"""<div style="margin-bottom:14px;padding:14px 16px;border-radius:12px;background:linear-gradient(135deg,#1e1e2e,#2d2d44);border:1px solid #4ade80;color:#e2e8f0;font-size:13px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <strong style="font-size:15px;">🧪 Lab 注意力监控</strong>
            <span style="font-size:11px;padding:3px 8px;background:#4ade80;color:#1e1e2e;border-radius:12px;font-weight:bold;">
                {lab_status.get('processed_frames', 0)} 帧
            </span>
        </div>

        <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;">
            <div style="padding:10px;background:rgba(255,255,255,0.05);border-radius:8px;">
                <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">Manas Score</div>
                <div style="font-size:24px;font-weight:bold;color:{score_color};">{manas_score:.3f}</div>
            </div>

            <div style="padding:10px;background:rgba(255,255,255,0.05);border-radius:8px;">
                <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">AI算力趋势</div>
                <div style="font-size:18px;font-weight:bold;color:{ai_color};">
                    {'📈 上升' if ai_compute == 'rising' else '📉 下降' if ai_compute == 'falling' else '➡️ 稳定'}
                </div>
            </div>

            <div style="padding:10px;background:rgba(255,255,255,0.05);border-radius:8px;">
                <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">行动信号</div>
                <div style="font-size:18px;font-weight:bold;color:{act_color};">
                    {'✅ 买入' if should_act else '⏸️ 等待'}
                </div>
            </div>

            <div style="padding:10px;background:rgba(255,255,255,0.05);border-radius:8px;">
                <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">觉醒等级</div>
                <div style="font-size:18px;font-weight:bold;color:{awakening_color};">
                    {'🌟 开悟' if awakening_level == 'enlightened' else '💡 照明' if awakening_level == 'illuminated' else '🌱 觉醒' if awakening_level == 'awakening' else '💤 沉睡'}
                </div>
            </div>

            <div style="padding:10px;background:rgba(255,255,255,0.05);border-radius:8px;">
                <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">Signal Strength</div>
                <div style="font-size:18px;font-weight:bold;">{signal_strength:.3f}</div>
            </div>

            <div style="padding:10px;background:rgba(255,255,255,0.05);border-radius:8px;">
                <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">洞察数</div>
                <div style="font-size:18px;font-weight:bold;">{insight_count} 个</div>
            </div>
        </div>

        <div style="margin-top:12px;padding:10px;background:rgba(255,255,255,0.05);border-radius:8px;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px;">
                <span>全局注意力: <strong>{lab_status.get('global_attention', 0):.3f}</strong></span>
                <span>高关注股票: <strong>{lab_status.get('high_attention_count', 0)}</strong></span>
            </div>
            <div style="font-size:11px;color:#94a3b8;">
                热点: {', '.join(lab_status.get('top_symbols', [])[:3]) or '暂无'}
            </div>
        </div>

        <div style="margin-top:12px;padding:10px;background:rgba(255,255,255,0.05);border-radius:8px;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px;">
                <span>📊 叙事事件: <strong>{narrative_count}</strong></span>
                <span style="color:#4ade80;">供需信号: <strong>{supply_demand}</strong></span>
            </div>
            <div style="font-size:11px;color:#94a3b8;">
                最新: {latest_event[:50] if latest_event else 'N/A'}...
            </div>
        </div>

        {problem_html}

        <div style="margin-top:12px;padding:10px;background:rgba(255,255,255,0.05);border-radius:8px;">
            <div style="font-size:11px;color:#94a3b8;margin-bottom:6px;">📜 监控日志</div>
            <div style="max-height:80px;overflow-y:auto;font-size:10px;color:#64748b;">
                {''.join([f"<div style='margin-bottom:3px;'>• {log_item}</div>" for log_item in _get_lab_activity_logs()]) or '<div>暂无活动记录</div>'}
            </div>
        </div>
    </div>"""
