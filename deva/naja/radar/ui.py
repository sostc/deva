"""Radar UI - 感知层"""

from datetime import datetime

from pywebio.output import put_html, put_button
from pywebio.session import run_js

from ..common.ui_style import render_empty_state
from .engine import get_radar_engine
from deva.naja.register import SR


def _fmt_time(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _render_event_badge(event_type: str, score: float = 0.5) -> str:
    """渲染事件类型徽章"""
    color_map = {
        "radar_pattern": ("📊", "#2563eb", "rgba(37,99,235,0.1)"),
        "pattern": ("📊", "#2563eb", "rgba(37,99,235,0.1)"),
        "radar_data_distribution_shift": ("📉", "#9333ea", "rgba(147,51,234,0.1)"),
        "drift": ("📉", "#9333ea", "rgba(147,51,234,0.1)"),
        "radar_anomaly": ("⚡", "#dc2626", "rgba(220,38,38,0.1)"),
        "anomaly": ("⚡", "#dc2626", "rgba(220,38,38,0.1)"),
        "radar_block_anomaly": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
        "block_anomaly": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
        "block_hotspot": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
    }

    icon, color, bg = color_map.get(event_type, ("📌", "#6b7280", "rgba(107,114,128,0.1)"))

    if event_type in ("block_anomaly", "radar_block_anomaly"):
        label = "板块联动"
    elif event_type == "block_hotspot":
        label = "板块热点"
    elif event_type == "radar_data_distribution_shift":
        label = "数据漂移"
    elif event_type == "radar_pattern":
        label = "模式"
    elif event_type == "radar_anomaly":
        label = "异常"
    else:
        label = event_type

    score_color = "#f87171" if score > 0.7 else ("#fb923c" if score > 0.5 else "#60a5fa")

    return f'''<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:4px;font-size:12px;font-weight:500;background:{bg};color:{color};">
        {icon} {label}
    </span><span style="font-size:11px;color:{score_color};margin-left:4px;">{score:.2f}</span>'''


class RadarUI:
    """雷达感知层 UI"""

    def __init__(self):
        self.engine = get_radar_engine()

    def render(self):
        """渲染主页面"""
        from pywebio.session import set_env
        from ..common.ui_theme import get_global_styles, get_nav_menu_js

        set_env(title="Naja - 雷达", output_animation=False)
        put_html(get_global_styles())

        nav_js = get_nav_menu_js()
        switch_theme_js = """
            window.switchTheme = function(name) {
                document.cookie = 'naja-theme=' + name + '; path=/; max-age=31536000';
                document.body.style.opacity = '0';
                setTimeout(function() { location.reload(); }, 150);
            };
        """

        run_js("setTimeout(function(){" + nav_js + "}, 50);")
        run_js(switch_theme_js)

        from ..common.ui_theme import get_current_theme

        theme = get_current_theme()
        put_html('<div class="container">')
        self._render_header()
        self._render_news_fetcher_panel()
        self._render_engine_status_panel()
        self._render_stats_overview()
        self._render_event_timeline()
        self._render_radar_logic()
        self._render_liquidity_prediction_panel()
        self._render_control_panel()
        put_html('</div>')

    def _get_cn_trading_status(self) -> tuple:
        """获取A股交易时段状态"""
        try:
            from ..register import ensure_trading_clocks
            ensure_trading_clocks()
            tc = SR('trading_clock')
            phase = tc.current_phase
            phase_map = {
                "trading": ("A股交易中", "#22c55e"),
                "pre_market": ("A股盘前", "#f59e0b"),
                "lunch": ("A股午休", "#64748b"),
                "post_market": ("A股盘后", "#64748b"),
                "closed": ("A股休市", "#dc2626"),
            }
            return phase_map.get(phase, ("A股未知", "#64748b"))
        except:
            return ("A股状态未知", "#64748b")

    def _get_us_trading_status(self) -> tuple:
        """获取美股交易时段状态"""
        try:
            from ..register import ensure_trading_clocks
            ensure_trading_clocks()
            tc = SR('us_trading_clock')
            phase = tc.current_phase
            phase_map = {
                "trading": ("美股交易中", "#22c55e"),
                "pre_market": ("美股盘前", "#f59e0b"),
                "post_market": ("美股盘后", "#64748b"),
                "closed": ("美股休市", "#dc2626"),
            }
            return phase_map.get(phase, ("美股未知", "#64748b"))
        except:
            return ("美股状态未知", "#64748b")

    def _render_header(self):
        """渲染页面标题 - 酷炫深色风格"""
        summary_10m = self.engine.summarize(window_seconds=600) if self.engine else {}
        summary_1h = self.engine.summarize(window_seconds=3600) if self.engine else {}
        summary_24h = self.engine.summarize(window_seconds=86400) if self.engine else {}

        event_10m = summary_10m.get("event_count", 0)
        event_1h = summary_1h.get("event_count", 0)
        event_24h = summary_24h.get("event_count", 0)
        type_counts = summary_10m.get("event_type_counts", {})
        type_count = len(type_counts)

        engine_status = "🟢 运行中" if self.engine else "🔴 已停止"

        pattern_count = type_counts.get("radar_pattern", 0) + type_counts.get("pattern", 0)
        drift_count = type_counts.get("radar_data_distribution_shift", 0) + type_counts.get("drift", 0)
        anomaly_count = type_counts.get("radar_anomaly", 0) + type_counts.get("anomaly", 0)
        block_count = type_counts.get("radar_block_anomaly", 0) + type_counts.get("block_anomaly", 0) + type_counts.get("block_hotspot", 0)

        cn_phase, cn_phase_color = self._get_cn_trading_status()
        us_phase, us_phase_color = self._get_us_trading_status()

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
            <div style="position: absolute; top: 0; right: 0; width: 200px; height: 100%; background: radial-gradient(ellipse at top right, #f59e0b08 0%, transparent 60%); pointer-events: none;"></div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; position: relative;">
                <div>
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                        <span style="font-size: 24px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">📡</span>
                        <div>
                            <div style="font-size: 16px; font-weight: 700; color: #f1f5f9;">雷达 <span style="font-size: 13px; font-weight: 400; color: #94a3b8;">感知层</span></div>
                            <div style="font-size: 11px; color: #f59e0b; margin-top: 2px;">只负责发现行情异常信号，不做调度与结论</div>
                        </div>
                    </div>
                    <div style="font-size: 12px; color: #64748b; margin-top: 6px;">输入：策略执行结果（信号、评分、板块异动）｜ 输出：异常事件 → 认知层</div>
                </div>
                <div style="display: flex; gap: 12px; text-align: center;">
                    <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">10分钟</div>
                        <div style="font-size: 20px; font-weight: 700; color: #f59e0b;">{event_10m}</div>
                        <div style="font-size: 10px; color: #94a3b8;">事件</div>
                    </div>
                    <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">1小时</div>
                        <div style="font-size: 20px; font-weight: 700; color: #0ea5e9;">{event_1h}</div>
                        <div style="font-size: 10px; color: #94a3b8;">事件</div>
                    </div>
                    <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">24小时</div>
                        <div style="font-size: 20px; font-weight: 700; color: #22c55e;">{event_24h}</div>
                        <div style="font-size: 10px; color: #94a3b8;">事件</div>
                    </div>
                    <div style="background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">引擎状态</div>
                        <div style="font-size: 14px; font-weight: 700; color: #22c55e;">{engine_status}</div>
                        <div style="font-size: 10px; color: #94a3b8;">{type_count} 种类型</div>
                    </div>
                    <div style="background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 110px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">交易时段</div>
                        <div style="font-size: 12px; font-weight: 700; color: {cn_phase_color};">{cn_phase}</div>
                        <div style="font-size: 12px; font-weight: 700; color: {us_phase_color};">{us_phase}</div>
                    </div>
                </div>
            </div>
            <div style="display: flex; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #334155;">
                <div style="flex: 1; padding: 6px 10px; background: rgba(37, 99, 235, 0.15); border-radius: 6px; text-align: center;">
                    <span style="font-size: 11px; color: #93c5fd;">📊 Pattern</span>
                    <span style="font-size: 12px; font-weight: 600; color: #3b82f6; margin-left: 4px;">{pattern_count}</span>
                </div>
                <div style="flex: 1; padding: 6px 10px; background: rgba(147, 51, 234, 0.15); border-radius: 6px; text-align: center;">
                    <span style="font-size: 11px; color: #d8b4fe;">📉 Drift</span>
                    <span style="font-size: 12px; font-weight: 600; color: #a855f7; margin-left: 4px;">{drift_count}</span>
                </div>
                <div style="flex: 1; padding: 6px 10px; background: rgba(220, 38, 38, 0.15); border-radius: 6px; text-align: center;">
                    <span style="font-size: 11px; color: #fca5a5;">⚡ Anomaly</span>
                    <span style="font-size: 12px; font-weight: 600; color: #ef4444; margin-left: 4px;">{anomaly_count}</span>
                </div>
                <div style="flex: 1; padding: 6px 10px; background: rgba(239, 68, 68, 0.15); border-radius: 6px; text-align: center;">
                    <span style="font-size: 11px; color: #fca5a5;">🔥 板块</span>
                    <span style="font-size: 12px; font-weight: 600; color: #ef4444; margin-left: 4px;">{block_count}</span>
                </div>
            </div>
        </div>
        """)

    def _render_news_fetcher_panel(self):
        """渲染新闻获取器面板"""
        if not self.engine:
            return

        news_stats = self.engine.get_news_fetcher_stats()

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

        news_events = self.engine.summarize(window_seconds=3600).get("events", [])
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
            '<span>📊 高注意力: ' + str(high_attention) + '</span>'
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

    def _render_engine_status_panel(self):
        """渲染工作引擎状态监控面板"""
        if not self.engine:
            return

        engines = []

        news_stats = self.engine.get_news_fetcher_stats()
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

        global_stats = self.engine.get_global_market_scanner_stats()
        scanner_running = global_stats is not None and global_stats.get('running', False)

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
            from ..radar.openrouter_monitor import get_openrouter_trend, TREND_TABLE
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

    def _render_control_panel(self):
        """渲染控制面板"""
        from pywebio.output import put_buttons, put_button

        def toggle_scanning(value):
            if self.engine:
                if value == "pause":
                    self.engine.pause()
                else:
                    self.engine.resume()

        def force_refresh():
            if self.engine:
                self.engine.force_scan()

        put_html("""
        <div style="
            background: rgba(107, 114, 128, 0.1);
            border: 1px solid rgba(107, 114, 128, 0.3);
            border-radius: 12px;
            padding: 15px;
            margin-top: 15px;
        ">
            <h4 style="margin: 0 0 15px 0; color: #94a3b8;">⚙️ 控制</h4>
        """)

        put_buttons(
            ["⏸️ 暂停", "▶️ 继续", "🔄 强制扫描"],
            onclick=[
                lambda: toggle_scanning("pause"),
                lambda: toggle_scanning("resume"),
                force_refresh
            ],
            small=True
        )

        put_html("</div>")

    def _render_liquidity_prediction_panel(self):
        """渲染跨市场流动性预测面板"""
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            scanner = get_global_market_scanner()
            status = scanner.get_liquidity_status()
        except Exception as e:
            status = {"predictions": {}, "verifications": {}, "resonance": None, "topic_predictions": {}}

        # 获取通知历史
        try:
            from deva.naja.cognition.liquidity import get_notifier
            notifier = get_notifier()
            notifications = notifier.get_recent_notifications(limit=5)
            notifier_stats = notifier.get_stats()
        except Exception as e:
            notifications = []
            notifier_stats = {"total_sent": 0, "total_failed": 0, "history_count": 0}

        predictions = status.get("predictions", {})
        verifications = status.get("verifications", {})
        resonance = status.get("resonance", None)
        topic_predictions = status.get("topic_predictions", {})

        if not predictions and not verifications:
            prediction_html = '<span style="color: #64748b; font-size: 12px;">暂无流动性预测</span>'
        else:
            prediction_html = ""
            for market, pred in predictions.items():
                signal = pred.get("signal", 0.5)
                confidence = pred.get("confidence", 0)
                sources = pred.get("source_signals", [])
                is_valid = pred.get("is_valid", False)

                if signal < 0.4:
                    status_label = "🔴 紧张"
                    bar_color = "#f87171"
                elif signal > 0.7:
                    status_label = "🟢 宽松"
                    bar_color = "#4ade80"
                else:
                    status_label = "🟡 中性"
                    bar_color = "#fbbf24"

                market_display = {
                    "china_a": "A股",
                    "hk": "港股",
                    "us": "美股",
                    "futures": "期货"
                }.get(market, market)

                source_text = ", ".join(sources) if sources else "无"

                validity_icon = "✅" if is_valid else "⏰"

                prediction_html += f"""
                <div style="
                    background: rgba(255,255,255,0.05);
                    border-radius: 8px;
                    padding: 10px;
                    margin-bottom: 8px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 600; color: #e2e8f0;">{market_display}</span>
                        <span style="font-size: 12px;">{status_label}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <div style="flex: 1; background: #334155; border-radius: 4px; height: 8px;">
                            <div style="background: {bar_color}; border-radius: 4px; height: 8px; width: {signal * 100}%;"></div>
                        </div>
                        <span style="font-size: 11px; color: #94a3b8; min-width: 40px;">{signal:.2f}</span>
                    </div>
                    <div style="margin-top: 6px; font-size: 10px; color: #64748b;">
                        信号源: {source_text} | 置信度: {confidence:.0%} | {validity_icon}
                    </div>
                </div>
                """

        if not verifications:
            verification_html = '<span style="color: #64748b; font-size: 12px;">等待验证数据...</span>'
        else:
            verification_html = ""
            for market, ver in verifications.items():
                expected = ver.get("expected", 0.5)
                count = ver.get("verification_count", 0)
                verified = ver.get("verified", False)
                should_relax = ver.get("should_relax", False)

                status_icon = "✅" if verified else ("🔄" if count >= 5 else "⏳")
                relax_text = "解除限制" if should_relax else "保持限制"

                market_display = {
                    "china_a": "A股",
                    "hk": "港股",
                    "us": "美股",
                    "futures": "期货"
                }.get(market, market)

                verification_html += f"""
                <div style="
                    background: rgba(255,255,255,0.05);
                    border-radius: 8px;
                    padding: 10px;
                    margin-bottom: 8px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 600; color: #e2e8f0;">{market_display} 验证</span>
                        <span style="font-size: 12px;">{status_icon} {relax_text}</span>
                    </div>
                    <div style="margin-top: 6px; font-size: 11px; color: #64748b;">
                        预期: {expected:.2f} | 验证次数: {count}/5
                    </div>
                </div>
                """

        if resonance:
            level = resonance.get("level", "none")
            m_signal = resonance.get("market_signal", 0)
            n_signal = resonance.get("narrative_signal", 0)
            alignment = resonance.get("alignment", 0)
            weight = resonance.get("weight", 0)

            level_icons = {
                "high": ("🔴", "#f87171", "高共振"),
                "medium": ("🟡", "#fbbf24", "中共振"),
                "low": ("🔵", "#60a5fa", "低共振"),
                "divergent": ("⚠️", "#9333ea", "背离"),
                "none": ("⚪", "#94a3b8", "无信号"),
            }
            icon, color, label = level_icons.get(level, ("⚪", "#94a3b8", "未知"))

            resonance_html = f"""
            <div style="
                background: rgba(255,255,255,0.05);
                border-radius: 8px;
                padding: 10px;
                margin-bottom: 8px;
            ">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 600; color: #e2e8f0;">信号共振</span>
                    <span style="font-size: 12px;">{icon} {label}</span>
                </div>
                <div style="display: flex; gap: 15px; font-size: 11px; color: #94a3b8;">
                    <span>行情: <b style="color: #f87171;">{m_signal:+.2f}</b></span>
                    <span>舆论: <b style="color: #60a5fa;">{n_signal:+.2f}</b></span>
                    <span>对齐: <b style="color: {color};">{alignment:.0%}</b></span>
                </div>
                <div style="margin-top: 6px; font-size: 10px; color: #64748b;">
                    权重: {weight:.1f} | 最终信号: {m_signal * weight:+.2f}
                </div>
            </div>
            """
        else:
            resonance_html = '<span style="color: #64748b; font-size: 12px;">暂无共振数据</span>'

        if topic_predictions:
            topic_html = ""
            for topic, pred in topic_predictions.items():
                heat = pred.get("heat_score", 0)
                prob = pred.get("spread_probability", 0)
                sectors = pred.get("target_blocks", [])

                heat_bar = min(heat / 10 * 100, 100)
                heat_color = "#f87171" if heat > 5 else ("#fbbf24" if heat > 3 else "#4ade80")

                topic_html += f"""
                <div style="
                    background: rgba(255,255,255,0.05);
                    border-radius: 8px;
                    padding: 10px;
                    margin-bottom: 8px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 600; color: #e2e8f0;">{topic}</span>
                        <span style="font-size: 12px; color: {heat_color};">🔥 {heat:.1f}</span>
                    </div>
                    <div style="background: #334155; border-radius: 4px; height: 6px; margin-bottom: 6px;">
                        <div style="background: {heat_color}; border-radius: 4px; height: 6px; width: {heat_bar}%;"></div>
                    </div>
                    <div style="font-size: 10px; color: #64748b;">
                        传染概率: {prob:.0%} | 目标: {', '.join(sectors[:2]) if sectors else '无'}
                    </div>
                </div>
                """
        else:
            topic_html = '<span style="color: #64748b; font-size: 12px;">暂无主题扩散</span>'

        put_html(f"""
        <div style="
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 12px;
            padding: 15px;
            margin-top: 15px;
            border: 1px solid rgba(99, 102, 241, 0.3);
        ">
            <h4 style="margin: 0 0 15px 0; color: #818cf8;">
                🌊 流动性预测体系
            </h4>
            <div style="font-size: 11px; color: #64748b; margin-bottom: 12px;">
                基于行情+舆论共振检测，主题扩散预测，预判错误时自动解除限制
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                <div>
                    <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">
                        📊 预测
                    </div>
                    {prediction_html}
                </div>
                <div>
                    <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">
                        🔍 验证
                    </div>
                    {verification_html}
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;">
                <div>
                    <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">
                        ⚡ 共振检测
                    </div>
                    {resonance_html}
                </div>
                <div>
                    <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">
                        🔥 主题扩散
                    </div>
                    {topic_html}
                </div>
            </div>

            <div style="margin-top: 15px; padding: 12px; background: rgba(99, 102, 241, 0.1); border-radius: 8px; border: 1px solid rgba(99, 102, 241, 0.2);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div style="font-size: 12px; font-weight: 600; color: #818cf8;">🔔 通知历史</div>
                    <div style="font-size: 10px; color: #64748b;">
                        已发送：{notifier_stats.get('total_sent', 0)} | 失败：{notifier_stats.get('total_failed', 0)}
                    </div>
                </div>
                {self._render_notifications(notifications)}
            </div>

            <div style="margin-top: 12px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">规则说明:</div>
                <div style="font-size: 10px; color: #64748b;">
                    • 共振：行情 + 舆论同向=高权重 (1.0), 背离=低权重 (0.3)<br/>
                    • 主题扩散：热度>3 触发，传染概率×热度因子<br/>
                    • 信号 &lt; 0.4: 紧张调整 | &gt; 0.7: 宽松调整<br/>
                    • 预判错误或预测过期：自动解除限制
                </div>
            </div>
        </div>
        """)

    def _render_notifications(self, notifications):
        """渲染通知历史"""
        if not notifications:
            return '<div style="font-size: 11px; color: #64748b; padding: 8px 0;">暂无通知记录</div>'
        
        html = '<div style="display: flex; flex-direction: column; gap: 6px;">'
        
        for n in notifications:
            time_str = n.get('time_str', '')
            n_type = n.get('type', '')
            severity = n.get('severity', '')
            title = n.get('title', '')
            sent = n.get('sent', False)
            
            # 类型图标
            type_icons = {
                "prediction_created": ("🔔", "#f59e0b"),
                "prediction_confirmed": ("✅", "#22c55e"),
                "prediction_denied": ("❌", "#ef4444"),
                "resonance_detected": ("⚡", "#8b5cf6"),
                "signal_change": ("📊", "#3b82f6"),
            }
            icon, color = type_icons.get(n_type, ("📌", "#64748b"))
            
            # 严重程度标记
            severity_color = {
                "high": "#ef4444",
                "medium": "#f59e0b",
                "low": "#22c55e",
            }.get(severity, "#64748b")
            
            sent_icon = "✓" if sent else "✗"
            sent_color = "#22c55e" if sent else "#ef4444"
            
            # 截断标题
            short_title = title[:50] + "..." if len(title) > 50 else title
            
            html += f'''
            <div style="
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 6px 8px;
                background: rgba(255,255,255,0.03);
                border-radius: 6px;
                border-left: 3px solid {severity_color};
            ">
                <span style="font-size: 14px;">{icon}</span>
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 10px; color: {color}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                        {short_title}
                    </div>
                    <div style="font-size: 9px; color: #64748b;">
                        {time_str} | {severity}
                    </div>
                </div>
                <div style="font-size: 10px; color: {sent_color}; min-width: 20px;">
                    {sent_icon}
                </div>
            </div>
            '''
        
        html += '</div>'
        return html

    def _start_global_scanner(self):
        """启动全球市场扫描器"""
        try:
            self.engine.start_global_market_scanner(
                fetch_interval=60,
                alert_threshold_volatility=2.0,
                alert_threshold_single=3.0,
            )
        except Exception as e:
            pass
        self._refresh()

    def _render_stats_overview(self):
        """渲染事件类型分布 - 淡色风格"""
        if not self.engine:
            return

        summary_10m = self.engine.summarize(window_seconds=600)
        type_counts = summary_10m.get("event_type_counts", {})

        if not type_counts:
            return

        type_bars = ""
        max_count = max(type_counts.values()) if type_counts else 1
        for etype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            width = int(count / max_count * 100)
            icon, color = {
                "pattern": ("📊", "#60a5fa"),
                "drift": ("📉", "#c084fc"),
                "anomaly": ("⚡", "#f87171"),
                "block_anomaly": ("🔥", "#fb923c"),
            }.get(etype, ("📌", "#94a3b8"))

            type_bars += f'''
            <div style="margin-bottom: 10px;">
                <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
                    <span style="color: #94a3b8;">{icon} {etype}</span>
                    <span style="font-weight: 600; color: {color};">{count}</span>
                </div>
                <div style="height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
                    <div style="width: {width}%; height: 100%; background: {color}; border-radius: 2px;"></div>
                </div>
            </div>'''

        put_html(f'''
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 12px;">
                📈 事件类型分布（10分钟）
            </div>
            {type_bars}
        </div>
        ''')

    def _render_event_timeline(self):
        """渲染事件时间线 - 淡色风格"""
        if not self.engine:
            return

        summary = self.engine.summarize(window_seconds=3600)
        events = summary.get("events", [])[:30]

        if not events:
            put_html(f"""
            <div style="
                margin-bottom: 12px;
                background: rgba(255,255,255,0.03);
                border-radius: 12px;
                padding: 14px 18px;
                border: 1px solid rgba(255,255,255,0.08);
                text-align: center;
            ">
                <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 6px;">🕐 最近事件（1小时）</div>
                <div style="color: #475569; font-size: 11px;">暂无雷达事件</div>
            </div>
            """)
            return

        event_items = ""
        for event in events:
            event_type = event.get("event_type", "unknown")
            score = float(event.get("score", 0.5))
            message = event.get("message", "-")
            strategy_name = event.get("strategy_name", "-")
            ts = float(event.get("timestamp", 0))
            ts_str = _fmt_time(ts)

            badge_html = _render_event_badge(event_type, score)
            score_color = "#f87171" if score > 0.7 else ("#fb923c" if score > 0.5 else "#60a5fa")

            event_items += f'''
            <div style="
                display: flex;
                gap: 10px;
                padding: 10px;
                background: rgba(255,255,255,0.02);
                border-radius: 6px;
                margin-bottom: 6px;
                border: 1px solid rgba(255,255,255,0.04);
            ">
                <div style="font-size: 10px; color: #475569; min-width: 45px; padding-top: 2px;">{ts_str}</div>
                <div style="flex: 1;">
                    <div style="margin-bottom: 4px;">{badge_html}</div>
                    <div style="font-size: 11px; color: #94a3b8; line-height: 1.4;">{message[:80]}</div>
                </div>
                <div style="text-align: right; min-width: 40px;">
                    <div style="font-size: 11px; font-weight: 600; color: {score_color};">{score:.2f}</div>
                </div>
            </div>'''

        put_html(f'''
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 12px;">
                🕐 最近事件（1小时）
            </div>
            {event_items}
        </div>
        ''')

    def _render_radar_logic(self):
        """渲染雷达感知逻辑说明 - 详细工作原理"""
        from deva.naja.cognition.system_architecture import get_radar_architecture_doc
        put_html(get_radar_architecture_doc())

    def _refresh(self):
        """刷新页面"""
        run_js("setTimeout(function() { location.reload(); }, 200)")

    def _clear_events(self):
        """清空事件"""
        if self.engine:
            self.engine.prune_events(retention_days=0)
        run_js("setTimeout(function() { location.reload(); }, 500)")


def main():
    """主入口"""
    ui = RadarUI()
    ui.render()


if __name__ == "__main__":
    main()
