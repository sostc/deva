"""Radar UI — 新闻获取器面板 + 工作引擎状态面板"""

from pywebio.output import put_html


def render_news_fetcher_panel(engine):
    """渲染新闻获取器面板"""
    if not engine:
        return

    news_stats = engine.get_news_fetcher_stats()

    if news_stats is None:
        put_html("""
        <div style="margin-bottom: 12px; background: rgba(255,255,255,0.03); border-radius: 12px; padding: 14px 18px; border: 1px solid rgba(255,255,255,0.08);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-size: 12px; font-weight: 500; color: #64748b;">📰 雷达内置新闻获取器</div>
                <div style="font-size: 11px; color: #dc2626;">● 未启动</div>
            </div>
        </div>
        """)
        return

    running = news_stats.get('running', False)
    trading_phase = news_stats.get('trading_phase', 'closed')
    fetch_count = news_stats.get('fetch_count', 0)
    fetch_interval = news_stats.get('fetch_interval', 0)
    llm_override = news_stats.get('llm_override')
    base_interval = news_stats.get('base_interval', 0)

    processor_stats = news_stats.get('processor_stats', {})
    stats = processor_stats.get('stats', {})
    total_processed = stats.get('total_processed', 0)
    high_attention = stats.get('high_attention', 0)
    signals_generated = stats.get('signals_generated', 0)
    topics_identified = stats.get('topics_identified', 0)

    status_icon = "🟢" if running else "🔴"
    status_color = "#22c55e" if running else "#dc2626"

    phase_map = {
        "trading": ("交易中", "#22c55e"),
        "pre_market": ("盘前", "#f59e0b"),
        "lunch": ("午间休市", "#64748b"),
        "post_market": ("盘后", "#64748b"),
        "closed": ("休市", "#dc2626"),
    }
    phase_name, phase_color = phase_map.get(trading_phase, ("未知", "#64748b"))

    news_events = engine.summarize(window_seconds=3600).get("events", [])
    news_event_count = len([e for e in news_events if e.get("event_type") == "news_topic"])

    recent_news = processor_stats.get('recent_news', [])

    panel_html = (
        '<div style="margin-bottom: 12px; background: rgba(255,255,255,0.03); border-radius: 12px; padding: 14px 18px; border: 1px solid rgba(255,255,255,0.08);">'
        '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">'
        '<div style="font-size: 12px; font-weight: 500; color: #64748b;">📰 雷达内置新闻获取器</div>'
        '<div style="display: flex; gap: 8px; align-items: center;">'
        '<span style="font-size: 11px; color: ' + status_color + ';">' + status_icon + ' ' + ('运行中' if running else '已停止') + '</span>'
        '<span style="font-size: 11px; color: #94a3b8;">|</span>'
        '<span style="font-size: 11px; color: ' + phase_color + ';">● ' + phase_name + '</span>'
        '</div></div>'
        '<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px;">'
        '<div style="background: rgba(37,99,235,0.1); border-radius: 6px; padding: 8px; text-align: center;">'
        '<div style="font-size: 16px; font-weight: 700; color: #3b82f6;">' + str(fetch_count) + '</div>'
        '<div style="font-size: 10px; color: #64748b;">获取批次</div></div>'
        '<div style="background: rgba(34,197,94,0.1); border-radius: 6px; padding: 8px; text-align: center;">'
        '<div style="font-size: 16px; font-weight: 700; color: #22c55e;">' + str(total_processed) + '</div>'
        '<div style="font-size: 10px; color: #64748b;">处理新闻</div></div>'
        '<div style="background: rgba(168,85,247,0.1); border-radius: 6px; padding: 8px; text-align: center;">'
        '<div style="font-size: 16px; font-weight: 700; color: #a855f7;">' + str(signals_generated) + '</div>'
        '<div style="font-size: 10px; color: #64748b;">产生信号</div></div>'
        '<div style="background: rgba(245,158,11,0.1); border-radius: 6px; padding: 8px; text-align: center;">'
        '<div style="font-size: 16px; font-weight: 700; color: #f59e0b;">' + str(topics_identified) + '</div>'
        '<div style="font-size: 10px; color: #64748b;">识别主题</div></div></div>'
        '<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">'
        '<div style="padding: 6px 8px; background: rgba(255,255,255,0.03); border-radius: 4px;">'
        '<div style="font-size: 10px; color: #64748b;">获取间隔</div>'
        '<div style="font-size: 12px; font-weight: 600; color: #e2e8f0;">' + '{:.1f}s'.format(fetch_interval) + '</div></div>'
        '<div style="padding: 6px 8px; background: rgba(255,255,255,0.03); border-radius: 4px;">'
        '<div style="font-size: 10px; color: #64748b;">基础间隔</div>'
        '<div style="font-size: 12px; font-weight: 600; color: #e2e8f0;">' + '{:.1f}s'.format(base_interval) + '</div></div>'
        '<div style="padding: 6px 8px; background: rgba(255,255,255,0.03); border-radius: 4px;">'
        '<div style="font-size: 10px; color: #64748b;">LLM覆盖</div>'
        '<div style="font-size: 12px; font-weight: 600; color: #e2e8f0;">' + ('{:.1f}s'.format(llm_override) if llm_override else '无') + '</div></div></div>'
        '<div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; font-size: 10px; color: #64748b;">'
        '<span>📊 高热度: ' + str(high_attention) + '</span>'
        '<span>🆕 新闻事件: ' + str(news_event_count) + '</span></div>'
    )
    put_html(panel_html)

    if recent_news:
        news_section = '<div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.08);">'
        news_section += '<div style="font-size: 11px; font-weight: 500; color: #64748b; margin-bottom: 8px;">📋 最近新闻</div>'
        for item in recent_news[:5]:
            score = item.get('attention_score', 0)
            score_color = "#f87171" if score > 0.7 else ("#fb923c" if score > 0.5 else "#60a5fa")
            ts = item.get('timestamp', '')[:-8] if item.get('timestamp') else ''
            news_section += (
                '<div style="padding: 6px 8px; margin-bottom: 4px; background: rgba(255,255,255,0.02); border-radius: 4px; border-left: 3px solid ' + score_color + ';">'
                '<div style="font-size: 11px; color: #e2e8f0; margin-bottom: 2px;">' + item.get('title', '') + '</div>'
                '<div style="font-size: 10px; color: #64748b;">'
                '<span style="color: #a855f7;">' + item.get('topic_name', '') + '</span>'
                '<span style="margin-left: 8px;">⏱ ' + ts + '</span>'
                '<span style="margin-left: 8px; color: ' + score_color + ';">★ ' + '{:.2f}'.format(score) + '</span>'
                '</div></div>'
            )
        news_section += '</div>'
        put_html(news_section)
    else:
        put_html('<div style="margin-top: 12px; padding: 12px; text-align: center; font-size: 11px; color: #475569;">暂无新闻数据</div>')

    put_html('</div>')


def render_engine_status_panel(engine):
    """渲染工作引擎状态监控面板"""
    if not engine:
        return

    engines = []

    news_stats = engine.get_news_fetcher_stats()
    if news_stats is not None:
        running = news_stats.get('running', False)
        fetch_interval = news_stats.get('fetch_interval', 0)
        fetch_count = news_stats.get('fetch_count', 0)
        trading_phase = news_stats.get('trading_phase', 'closed')
        phase_display = {
            "trading": ("交易中", "#22c55e"),
            "pre_market": ("盘前", "#f59e0b"),
            "lunch": ("午间休市", "#64748b"),
            "post_market": ("盘后", "#64748b"),
            "closed": ("休市", "#dc2626"),
        }.get(trading_phase, ("未知", "#64748b"))

        engines.append({
            "name": "📰 新闻获取器",
            "status": "🟢 运行中" if running else "🔴 已停止",
            "status_color": "#22c55e" if running else "#dc2626",
            "interval": f"{fetch_interval:.0f}秒",
            "count": f"获取 {fetch_count} 次",
            "phase": phase_display[0],
            "phase_color": phase_display[1],
            "icon": "📰",
        })

    global_stats = engine.get_global_market_scanner_stats()

    if global_stats is not None:
        running = global_stats.get('running', False)
        current_interval = global_stats.get('current_interval', 0)
        fetch_count = global_stats.get('fetch_count', 0)
        alert_count = global_stats.get('alert_count', 0)
        us_phase = global_stats.get('us_trading_phase', 'unknown')
        success_rate = global_stats.get('success_rate', 0)

        phase_display = {
            "trading": ("交易中", "#22c55e"),
            "pre_market": ("盘前", "#f59e0b"),
            "post_market": ("盘后", "#64748b"),
            "closed": ("休市", "#dc2626"),
        }.get(us_phase, ("未知", "#64748b"))

        engines.append({
            "name": "🌐 全球市场扫描器",
            "status": "🟢 运行中" if running else "🔴 已停止",
            "status_color": "#22c55e" if running else "#dc2626",
            "interval": f"{current_interval:.0f}秒",
            "count": f"扫描 {fetch_count} 次 | 告警 {alert_count} 次",
            "phase": phase_display[0],
            "phase_color": phase_display[1],
            "success_rate": f"{success_rate:.1%}",
            "icon": "🌐",
        })
    else:
        engines.append({
            "name": "🌐 全球市场扫描器",
            "status": "🔴 未启动",
            "status_color": "#dc2626",
            "interval": "需手动启动",
            "count": "点击下方按钮启动",
            "phase": "",
            "phase_color": "#64748b",
            "icon": "🌐",
        })

    try:
        from deva.naja.cognition.openrouter_monitor import get_openrouter_trend
        trend_data = get_openrouter_trend()
        if trend_data:
            direction = trend_data.get('direction', 'unknown')
            direction_emoji = {
                "strong_up": "🚀",
                "up": "📈",
                "down": "📉",
                "strong_down": "⚠️",
                "unknown": "❓",
            }.get(direction, "➡️")

            alert_level = trend_data.get('alert_level', 'normal')
            alert_color = {
                "normal": "#22c55e",
                "attention": "#f59e0b",
                "warning": "#f97316",
                "critical": "#dc2626",
            }.get(alert_level, "#64748b")

            engines.append({
                "name": "💰 OpenRouter TOKEN",
                "status": f"{direction_emoji} {alert_level.upper()}",
                "status_color": alert_color,
                "interval": "每周更新",
                "count": trend_data.get('latest_total_formatted', 'N/A'),
                "phase": f"周环比 {trend_data.get('latest_change', 0):+.1f}%",
                "phase_color": alert_color,
                "icon": "🤖",
            })
    except ImportError:
        pass

    if not engines:
        return

    engine_cards = ""
    for eng in engines:
        phase_html = f'''<span style="font-size: 10px; color: {eng.get('phase_color', '#64748b')};">● {eng.get('phase', '')}</span>''' if eng.get('phase') else ""
        success_rate_html = f'''<span style="font-size: 10px; color: #22c55e;">成功率 {eng.get('success_rate', 'N/A')}</span>''' if eng.get('success_rate') else ""

        engine_cards += f'''
        <div style="flex: 1; min-width: 200px; background: rgba(255,255,255,0.03); border-radius: 8px; padding: 12px; border: 1px solid rgba(255,255,255,0.08);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-size: 13px; font-weight: 600; color: #e2e8f0;">{eng['icon']} {eng['name'].replace(eng['icon'], '').strip()}</div>
                <div style="font-size: 11px; color: {eng['status_color']};">{eng['status']}</div>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                <div style="padding: 4px 6px; background: rgba(255,255,255,0.03); border-radius: 4px;">
                    <div style="font-size: 9px; color: #64748b; margin-bottom: 2px;">扫描间隔</div>
                    <div style="font-size: 12px; font-weight: 600; color: #60a5fa;">{eng['interval']}</div>
                </div>
                <div style="padding: 4px 6px; background: rgba(255,255,255,0.03); border-radius: 4px;">
                    <div style="font-size: 9px; color: #64748b; margin-bottom: 2px;">运行时长</div>
                    <div style="font-size: 12px; font-weight: 600; color: #e2e8f0;">{eng['count']}</div>
                </div>
            </div>
            <div style="display: flex; gap: 8px; margin-top: 8px; align-items: center;">
                {phase_html}
                {success_rate_html}
            </div>
        </div>'''

    put_html(f'''
    <div style="margin-bottom: 12px;">
        <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 10px;">⚙️ 工作引擎状态</div>
        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            {engine_cards}
        </div>
    </div>
    ''')
