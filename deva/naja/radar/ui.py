"""Radar UI - 感知层"""

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
        "pattern": ("📊", "#2563eb", "rgba(37,99,235,0.1)"),
        "drift": ("📉", "#9333ea", "rgba(147,51,234,0.1)"),
        "anomaly": ("⚡", "#dc2626", "rgba(220,38,38,0.1)"),
        "sector_anomaly": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
        "sector_hotspot": ("🔥", "#ef4444", "rgba(239,68,68,0.1)"),
    }

    icon, color, bg = color_map.get(event_type, ("📌", "#6b7280", "rgba(107,114,128,0.1)"))

    if event_type == "sector_anomaly":
        label = "板块联动"
    elif event_type == "sector_hotspot":
        label = "板块热点"
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

        pattern_count = type_counts.get("pattern", 0)
        drift_count = type_counts.get("drift", 0)
        anomaly_count = type_counts.get("anomaly", 0)
        sector_count = type_counts.get("sector_anomaly", 0) + type_counts.get("sector_hotspot", 0)

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

    def _render_control_panel(self):
        """渲染控制面板 - 底部样式"""
        put_html('''
        <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.08); display: flex; gap: 8px;">
        ''')
        put_button("🔄 刷新", onclick=self._refresh, color="secondary", small=True)
        put_button("🧹 清空事件", onclick=self._clear_events, color="secondary", small=True)
        put_html('</div>')

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
        """渲染雷达感知逻辑说明 - 淡色风格"""
        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 10px;">
                🧩 雷达感知逻辑
            </div>
            <div style="font-size: 11px; color: #475569; line-height: 1.7;">
                <div style="margin-bottom: 8px;">
                    <b style="color: #f59e0b;">📊 MarketScanner（市场扫描）</b><br>
                    <span style="color: #64748b;">• Pattern模式：同一信号类型重复出现 → 检测信号强度</span><br>
                    <span style="color: #64748b;">• Drift漂移：概念漂移检测（ADWIN算法）→ 检测市场风格变化</span><br>
                    <span style="color: #64748b;">• Anomaly异常：统计异常检测（z-score）→ 检测极端行情</span><br>
                    <span style="color: #64748b;">• SectorAnomaly板块联动：齐涨齐跌检测 → 发现板块异动</span>
                </div>
                <div style="padding: 8px; background: rgba(14, 165, 233, 0.08); border-radius: 6px; border-left: 2px solid #0ea5e9;">
                    <b style="color: #0ea5e9;">📌 数据流</b><br>
                    <span style="color: #64748b;">策略执行 → RadarEngine.ingest_result() → MarketScanner检测 → 事件存储 → 认知层</span>
                </div>
            </div>
        </div>
        """)

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
