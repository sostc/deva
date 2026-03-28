"""Radar UI - 感知层"""

import re
from datetime import datetime

from pywebio.output import put_html, put_button
from pywebio.session import run_js

from ..common.ui_style import render_empty_state
from .engine import get_radar_engine


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
        "radar_sector_anomaly": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
        "sector_anomaly": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
        "sector_hotspot": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
    }

    icon, color, bg = color_map.get(event_type, ("📌", "#6b7280", "rgba(107,114,128,0.1)"))

    if event_type == "sector_anomaly" or event_type == "radar_sector_anomaly":
        label = "板块联动"
    elif event_type == "sector_hotspot":
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
        self._render_radar_thread()
        self._render_news_fetcher_panel()
        self._render_process_flow()
        self._render_stats_overview()
        self._render_event_timeline()
        self._render_radar_logic()
        self._render_control_panel()
        put_html('</div>')

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
        sector_count = type_counts.get("radar_sector_anomaly", 0) + type_counts.get("sector_anomaly", 0) + type_counts.get("sector_hotspot", 0)

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
                    <span style="font-size: 12px; font-weight: 600; color: #ef4444; margin-left: 4px;">{sector_count}</span>
                </div>
            </div>
        </div>
        """)

    def _render_radar_thread(self):
        """渲染雷达监控脉络图

        显示两类内容：
        1. 雷达监控对象（信号消费者）：新闻获取器、OpenRouter监控
        2. 向雷达发送信号的策略
        """
        from .engine import _get_frequency_label

        consumer_threads = self.engine.get_consumer_threads()
        radar_strategies = self.engine.get_radar_feeding_strategies()

        if not consumer_threads and not radar_strategies:
            return

        def render_consumer_card(t: dict) -> str:
            alert_level = t.get('alert_level', 'normal')
            alert_colors = {
                'normal': ('#22c55e', 'rgba(34, 197, 94, 0.1)'),
                'attention': ('#0ea5e9', 'rgba(14, 165, 233, 0.1)'),
                'warning': ('#f59e0b', 'rgba(245, 158, 11, 0.1)'),
                'critical': ('#ef4444', 'rgba(239, 68, 68, 0.1)'),
            }
            alert_color, alert_bg = alert_colors.get(alert_level, ('#94a3b8', 'rgba(148, 163, 184, 0.1)'))

            freq_color = '#ef4444' if t.get('update_interval_seconds', 0) < 3600 else \
                        '#f59e0b' if t.get('update_interval_seconds', 0) < 86400 else \
                        '#0ea5e9' if t.get('update_interval_seconds', 0) < 604800 else '#94a3b8'

            last_ts = t.get('last_update_ts', 0)
            last_time = datetime.fromtimestamp(last_ts).strftime('%H:%M') if last_ts else '从未'

            freq_label = _get_frequency_label(t.get('update_interval_seconds', 0))

            return f'''
            <div style="background: {alert_bg}; border: 1px solid {alert_color}40; border-radius: 8px; padding: 10px 12px; flex: 1; min-width: 160px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div style="display: flex; align-items: center; gap: 5px;">
                        <span style="font-size: 14px;">{t.get('icon', '📡')}</span>
                        <span style="font-size: 12px; font-weight: 600; color: #f1f5f9;">{t.get('name', '未知')}</span>
                    </div>
                    <span style="font-size: 9px; padding: 1px 4px; border-radius: 3px; background: {alert_color}20; color: {alert_color};">{alert_level}</span>
                </div>
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">{t.get('description', '')}</div>
                <div style="display: flex; justify-content: space-between; font-size: 9px;">
                    <span style="color: #94a3b8;">频率: <span style="color: {freq_color};">{freq_label}</span></span>
                    <span style="color: #94a3b8;">{last_time}</span>
                </div>
            </div>
            '''

        def render_strategy_card(t: dict) -> str:
            signal_types = t.get('signal_types', [])
            signal_labels = {
                'pattern': '📊',
                'drift': '📉',
                'anomaly': '⚡',
                'sector': '🔥',
                'openrouter_trend': '🤖',
            }
            icons = ''.join([signal_labels.get(st, '📌') for st in signal_types if st in signal_labels])

            return f'''
            <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 8px; padding: 8px 10px; flex: 1; min-width: 140px;">
                <div style="display: flex; align-items: center; gap: 5px; margin-bottom: 4px;">
                    <span style="font-size: 12px;">📡</span>
                    <span style="font-size: 11px; font-weight: 600; color: #93c5fd;">{t.get('name', '未知策略')}</span>
                </div>
                <div style="font-size: 9px; color: #64748b;">{icons}</div>
            </div>
            '''

        consumer_html = ''.join([render_consumer_card(t) for t in consumer_threads])
        strategy_html = ''.join([render_strategy_card(t) for t in radar_strategies])

        total_count = len(consumer_threads) + len(radar_strategies)

        put_html(f'''
        <div style="
            margin-bottom: 12px;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border-radius: 14px;
            padding: 16px 20px;
            box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25), inset 0 1px 0 rgba(255,255,255,0.05);
            border: 1px solid #334155;
        ">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 14px;">
                <span style="font-size: 18px;">🕸️</span>
                <span style="font-size: 14px; font-weight: 600; color: #f1f5f9;">雷达监控脉络</span>
                <span style="font-size: 11px; color: #64748b; margin-left: 8px;">{total_count} 个监控项</span>
            </div>

            <div style="margin-bottom: 12px;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 8px;">🔍 监控对象 ({len(consumer_threads)})</div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    {consumer_html if consumer_html else '<span style="font-size: 10px; color: #475569;">无</span>'}
                </div>
            </div>

            <div style="padding-top: 12px; border-top: 1px solid #334155;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 8px;">📡 信号源 ({len(radar_strategies)})</div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    {strategy_html if strategy_html else '<span style="font-size: 10px; color: #475569;">无</span>'}
                </div>
            </div>

            <div style="display: flex; gap: 16px; margin-top: 14px; padding-top: 12px; border-top: 1px solid #334155; font-size: 10px; color: #64748b;">
                <span style="color: #94a3b8;">📊 pattern</span>
                <span style="color: #94a3b8;">📉 drift</span>
                <span style="color: #94a3b8;">⚡ anomaly</span>
                <span style="color: #94a3b8;">🔥 sector</span>
            </div>
        </div>
        ''')

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
            news_section += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">'
            news_section += '<div style="font-size: 11px; font-weight: 500; color: #64748b;">📋 最近新闻（全量）</div>'
            news_section += '<div style="font-size: 9px; color: #475569;">★全在这</div></div>'
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

    def _render_control_panel(self):
        """渲染控制面板 - 底部样式"""
        put_html('''
        <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.08); display: flex; gap: 8px;">
        ''')
        put_button("🔄 刷新", onclick=self._refresh, color="secondary", small=True)
        put_button("🧹 清空事件", onclick=self._clear_events, color="secondary", small=True)
        put_html('</div>')

    def _render_process_flow(self):
        """渲染处理流程说明"""
        put_html('''
        <div style="margin-bottom: 12px; background: rgba(255,255,255,0.02); border-radius: 10px; padding: 12px 14px; border: 1px solid rgba(255,255,255,0.06);">
            <div style="font-size: 11px; font-weight: 500; color: #64748b; margin-bottom: 8px;">⚙️ 处理流程与评分机制</div>
            <div style="display: flex; align-items: center; gap: 4px; font-size: 10px; color: #475569; margin-bottom: 6px;">
                <span style="background: rgba(59,130,246,0.15); color: #60a5fa; padding: 2px 6px; border-radius: 3px;">📰 金十数据</span>
                <span>→</span>
                <span style="background: rgba(34,197,94,0.12); color: #22c55e; padding: 2px 6px; border-radius: 3px;">全部新闻</span>
                <span>→</span>
                <span style="background: rgba(168,85,247,0.12); color: #a855f7; padding: 2px 6px; border-radius: 3px;">主题分类</span>
                <span>→</span>
                <span style="background: rgba(249,115,22,0.12); color: #fb923c; padding: 2px 6px; border-radius: 3px;">注意力评分</span>
                <span>→</span>
                <span style="background: rgba(239,68,68,0.12); color: #f87171; padding: 2px 6px; border-radius: 3px;">★≥0.6事件</span>
            </div>
            <div style="font-size: 9px; color: #64748b; line-height: 1.5;">
                <div style="margin-bottom: 3px; color: #94a3b8;"><span style="color: #fb923c;">注意力评分</span> = 基础0.5 + 标题长度(>20字+0.1, >40字+0.1) + 主题重复(≥3次+0.2, ≥5次+0.1) + 关键词(突发/重磅/暴涨等+0.1)</div>
                <div style="color: #64748b;">低于0.6的新闻只保留在"最近新闻"列表，不产生事件信号</div>
            </div>
        </div>
        ''')

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
                "sector_anomaly": ("🔥", "#fb923c"),
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
        """渲染事件时间线 - 紧凑风格"""
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
                <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 6px;">📌 高关注度事件</div>
                <div style="color: #475569; font-size: 11px;">暂无雷达事件</div>
            </div>
            """)
            return

        event_items = ""
        for event in events:
            event_type = event.get("event_type", "unknown")
            score = float(event.get("score", 0.5))
            message = event.get("message", "-")
            ts = float(event.get("timestamp", 0))
            ts_str = _fmt_time(ts)

            score_color = "#f87171" if score > 0.7 else ("#fb923c" if score > 0.5 else "#60a5fa")

            if event_type == "news_topic":
                topic_match = re.search(r'\[([^\]]+)\]', message)
                topic = topic_match.group(1) if topic_match else ""
                content = message[message.find(']')+1:].strip() if ']' in message else message
                event_items += f'''
                <div style="
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    padding: 6px 8px;
                    background: rgba(255,255,255,0.02);
                    border-radius: 4px;
                    margin-bottom: 4px;
                    font-size: 11px;
                ">
                    <span style="color: #64748b; min-width: 45px;">{ts_str}</span>
                    <span style="
                        background: rgba(59,130,246,0.15);
                        color: #60a5fa;
                        padding: 1px 6px;
                        border-radius: 3px;
                        font-size: 10px;
                        font-weight: 500;
                    ">{topic}</span>
                    <span style="flex: 1; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{content[:40]}</span>
                    <span style="color: {score_color}; font-weight: 600; min-width: 35px; text-align: right;">★{score:.2f}</span>
                </div>'''
            else:
                badge_html = _render_event_badge(event_type, score)
                event_items += f'''
                <div style="
                    display: flex;
                    gap: 10px;
                    padding: 8px;
                    background: rgba(255,255,255,0.02);
                    border-radius: 4px;
                    margin-bottom: 4px;
                ">
                    <div style="font-size: 10px; color: #475569; min-width: 45px; padding-top: 2px;">{ts_str}</div>
                    <div style="flex: 1;">
                        <div style="margin-bottom: 3px;">{badge_html}</div>
                        <div style="font-size: 11px; color: #94a3b8; line-height: 1.3;">{message[:60]}</div>
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
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <div style="font-size: 12px; font-weight: 500; color: #64748b;">📌 高关注度事件（从新闻中筛选）</div>
                <div style="font-size: 9px; color: #475569;">★≥0.6</div>
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
