"""
记忆系统 Web UI Tab
风格与全局一致，紧凑布局，用户关注内容优先
"""

from datetime import datetime, timedelta

from pywebio.output import *
from pywebio.input import *
from pywebio.pin import *
from pywebio.session import run_js, set_env

from .engine import get_memory_engine
from .core import AttentionScorer
from ..page_help import render_help_collapse


def get_running_memory_engine():
    """获取运行中的记忆引擎实例（单例）"""
    try:
        return get_memory_engine()
    except Exception as e:
        print(f"[MemoryUI] 获取记忆引擎失败: {e}")
        return get_memory_engine()


def create_nav_menu():
    """创建导航菜单 - 使用统一模块"""
    from ..common.ui_theme import get_nav_menu_js
    js_code = get_nav_menu_js()
    run_js(js_code)


def apply_global_styles():
    """应用全局样式 - 使用统一模块"""
    from ..common.ui_theme import get_global_styles
    from pywebio.output import put_html
    put_html(get_global_styles())


class NewsRadarUI:
    """记忆系统 UI - 风格一致版"""

    def __init__(self):
        self.radar = get_running_memory_engine()

    def render(self):
        """渲染主页面"""
        set_env(title="Naja - 记忆", output_animation=False)
        apply_global_styles()
        create_nav_menu()

        put_html('<div class="container">')

        self._render_header()
        self._render_control_panel()
        self._render_stats_overview()
        self._render_hot_topics()
        self._render_recent_events()
        self._render_memory_storage()
        self._render_memory_help()

        put_html('</div>')

    def _render_header(self):
        """渲染页面标题"""
        put_html("""
        <div style="margin-bottom: 20px;">
            <h1 style="font-size: 20px; font-weight: 700; color: #1e293b; margin-bottom: 4px;">
                🧠 智能记忆
            </h1>
            <p style="color: #64748b; font-size: 13px; margin: 0;">
                自动追踪热点，记住重要事件
            </p>
        </div>
        """)

    def _render_control_panel(self):
        """渲染控制面板"""
        put_html("""
        <div style="margin-bottom: 16px; display: flex; gap: 8px; align-items: center;">
        """)
        put_button("🔄 刷新", onclick=self._refresh_data, color="primary")
        put_button("📊 完整报告", onclick=self._generate_report, color="success")
        put_button("🧹 清空", onclick=self._clear_memory, color="danger")
        put_html('</div>')

    def _render_stats_overview(self):
        """渲染统计概览 - 用户最关注的数据"""
        report = self.radar.get_memory_report()
        stats = report['stats']
        topics = report.get('top_topics', [])

        total_events = stats.get('total_events', 0)
        hot_events = stats.get('high_attention_events', 0)
        topic_count = len(topics)

        gradient = "linear-gradient(135deg,#667eea,#764ba2)"

        put_html(f"""
        <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;">
            <div style="flex: 1; min-width: 140px; background: {gradient}; padding: 16px 20px; border-radius: 12px; color: #fff; box-shadow: 0 4px 12px rgba(102,126,234,0.3);">
                <div style="font-size: 12px; opacity: 0.9; margin-bottom: 4px;">📖 记忆总量</div>
                <div style="font-size: 28px; font-weight: 700;">{total_events}</div>
            </div>
            <div style="flex: 1; min-width: 140px; background: linear-gradient(135deg,#ef4444,#dc2626); padding: 16px 20px; border-radius: 12px; color: #fff; box-shadow: 0 4px 12px rgba(239,68,68,0.3);">
                <div style="font-size: 12px; opacity: 0.9; margin-bottom: 4px;">🔥 重要事件</div>
                <div style="font-size: 28px; font-weight: 700;">{hot_events}</div>
            </div>
            <div style="flex: 1; min-width: 140px; background: linear-gradient(135deg,#10b981,#059669); padding: 16px 20px; border-radius: 12px; color: #fff; box-shadow: 0 4px 12px rgba(16,185,129,0.3);">
                <div style="font-size: 12px; opacity: 0.9; margin-bottom: 4px;">📌 热点主题</div>
                <div style="font-size: 28px; font-weight: 700;">{topic_count}</div>
            </div>
        </div>
        """)

        self._render_memory_pipeline()

    def _render_memory_pipeline(self):
        """渲染记忆流水线 - 展示筛选过程"""
        report = self.radar.get_memory_report()
        stats = report['stats']
        memory_layers = report.get('memory_layers', {})

        total_received = stats.get('total_events', 0) + stats.get('filtered_events', 0)
        filtered = stats.get('filtered_events', 0)
        short_size = memory_layers.get('short', {}).get('size', 0)
        mid_size = memory_layers.get('mid', {}).get('size', 0)

        kept_pct = int((short_size / total_received * 100)) if total_received > 0 else 0
        mid_pct = int((mid_size / total_received * 100)) if total_received > 0 else 0

        put_html("""
        <div class="card" style="margin-bottom: 16px;">
            <div style="font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 16px;">
                🔍 记忆流水线
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px; flex-wrap: wrap;">
                <div style="padding: 8px 16px; background: #f1f5f9; border-radius: 8px; text-align: center;">
                    <div style="font-size: 12px; color: #64748b;">📥 接收</div>
                    <div style="font-size: 18px; font-weight: 700; color: #475569;">{total}</div>
                </div>
                <div style="color: #94a3b8; font-size: 18px;">→</div>
                <div style="padding: 8px 16px; background: #fef3c7; border-radius: 8px; text-align: center;">
                    <div style="font-size: 12px; color: #92400e;">🚫 过滤</div>
                    <div style="font-size: 18px; font-weight: 700; color: #d97706;">{filtered}</div>
                </div>
                <div style="color: #94a3b8; font-size: 18px;">→</div>
                <div style="padding: 8px 16px; background: #dbeafe; border-radius: 8px; text-align: center;">
                    <div style="font-size: 12px; color: #1e40af;">⚡ 短期</div>
                    <div style="font-size: 18px; font-weight: 700; color: #2563eb;">{short}</div>
                </div>
                <div style="color: #94a3b8; font-size: 18px;">→</div>
                <div style="padding: 8px 16px; background: #d1fae5; border-radius: 8px; text-align: center;">
                    <div style="font-size: 12px; color: #065f46;">📦 中期</div>
                    <div style="font-size: 18px; font-weight: 700; color: #059669;">{mid}</div>
                </div>
            </div>
            <div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 4px;">
                    <span>📊 留存率</span>
                    <span>{kept_pct}% 进入短期 / {mid_pct}% 进入中期</span>
                </div>
                <div style="height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden;">
                    <div style="float: left; width: {kept_pct}%; height: 100%; background: #3b82f6; border-radius: 4px 0 0 4px;"></div>
                    <div style="float: left; width: {mid_pct}%; height: 100%; background: #10b981; border-radius: 0 4px 4px 0;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-top: 4px;">
                    <span>■ 短期</span>
                    <span>■ 中期</span>
                </div>
            </div>
            <div style="font-size: 11px; color: #94a3b8; line-height: 1.6;">
                💡 <b>筛选逻辑：</b>频率过高→注意力低→被过滤 | 高注意力→进入中期归档
            </div>
        </div>
        """.format(
            total=total_received,
            filtered=filtered,
            short=short_size,
            mid=mid_size,
            kept_pct=kept_pct,
            mid_pct=mid_pct
        ))

    def _render_hot_topics(self):
        """渲染热点主题"""
        report = self.radar.get_memory_report()
        topics = report.get('top_topics', [])

        put_html("""
        <div class="card" style="margin-bottom: 16px;">
            <div style="font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 12px;">
                📈 热点主题
            </div>
        """)

        if not topics:
            put_html(render_empty_state("暂无热点主题"))
        else:
            put_html('<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px;">')
            for topic in topics[:6]:
                name = topic.get('name', '未命名')
                count = topic.get('event_count', 0)
                attention = topic.get('avg_attention', 0)
                growth = topic.get('growth_rate', 0)

                growth_icon = "📈" if growth > 0.2 else ("📉" if growth < -0.2 else "➡️")
                growth_color = "#10b981" if growth > 0.2 else ("#ef4444" if growth < -0.2 else "#64748b")
                heat_level = "🔥🔥🔥" if attention > 0.7 else ("🔥🔥" if attention > 0.5 else "🔥")

                put_html(f'''
                <div style="background: #f8fafc; border-radius: 8px; padding: 12px 14px; border: 1px solid #e2e8f0;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
                        <div style="font-size: 13px; font-weight: 600; color: #1e293b; flex: 1;">{name}</div>
                        <div style="font-size: 11px; color: #94a3b8;">{heat_level}</div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b;">
                        <span>{count} 条</span>
                        <span style="color: {growth_color};">{growth_icon} {growth:+.0%}</span>
                    </div>
                </div>
                ''')
            put_html('</div>')

        put_html('</div>')

    def _render_recent_events(self):
        """渲染最近重要事件"""
        report = self.radar.get_memory_report()
        events = report.get('recent_high_attention', [])

        put_html("""
        <div class="card" style="margin-bottom: 16px;">
            <div style="font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 12px;">
                ⚡ 最近重要事件
            </div>
        """)

        if not events:
            put_html(render_empty_state("暂无重要事件"))
        else:
            put_html('<div style="display: flex; flex-direction: column; gap: 8px;">')
            for event in events[:5]:
                timestamp_str = event.get('timestamp', '')
                if 'T' in timestamp_str:
                    try:
                        ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        timestamp_str = ts.strftime('%m-%d %H:%M')
                    except:
                        pass

                content = event.get('content', '')
                score = event.get('score', 0)
                bar_color = "#ef4444" if score > 0.7 else ("#f59e0b" if score > 0.5 else "#3b82f6")

                put_html(f'''
                <div style="display: flex; align-items: center; gap: 12px; padding: 10px 12px; background: #f8fafc; border-radius: 8px; border-left: 3px solid {bar_color};">
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-size: 13px; color: #1e293b; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{content[:80]}</div>
                        <div style="font-size: 11px; color: #94a3b8;">🕐 {timestamp_str}</div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
                        <div style="width: 50px; height: 5px; background: #e2e8f0; border-radius: 3px; overflow: hidden;">
                            <div style="width: {int(score*100)}%; height: 100%; background: {bar_color}; border-radius: 3px;"></div>
                        </div>
                        <span style="font-size: 11px; color: #64748b; min-width: 32px;">{score:.0%}</span>
                    </div>
                </div>
                ''')
            put_html('</div>')

        put_html('</div>')

    def _render_memory_storage(self):
        """渲染记忆存储"""
        report = self.radar.get_memory_report()
        memory_layers = report.get('memory_layers', {})

        short = memory_layers.get('short', {})
        mid = memory_layers.get('mid', {})

        short_size = short.get('size', 0)
        short_cap = short.get('capacity', 1000)
        mid_size = mid.get('size', 0)
        mid_cap = mid.get('capacity', 5000)

        short_pct = min(100, int(short_size / short_cap * 100)) if short_cap > 0 else 0
        mid_pct = min(100, int(mid_size / mid_cap * 100)) if mid_cap > 0 else 0

        put_html("""
        <div class="card" style="margin-bottom: 16px;">
            <div style="font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 12px;">
                🧠 记忆存储
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px;">
                <div style="text-align: center; padding: 12px; background: linear-gradient(135deg,#dbeafe,#bfdbfe); border-radius: 8px;">
                    <div style="font-size: 20px; margin-bottom: 2px;">⚡</div>
                    <div style="font-size: 12px; font-weight: 600; color: #1e40af;">短期</div>
                    <div style="font-size: 18px; font-weight: 700; color: #1e40af;">{short_size}</div>
                    <div style="font-size: 10px; color: #3b82f6;">/ {short_cap}</div>
                </div>
                <div style="text-align: center; padding: 12px; background: linear-gradient(135deg,#fef3c7,#fde68a); border-radius: 8px;">
                    <div style="font-size: 20px; margin-bottom: 2px;">📦</div>
                    <div style="font-size: 12px; font-weight: 600; color: #92400e;">中期</div>
                    <div style="font-size: 18px; font-weight: 700; color: #92400e;">{mid_size}</div>
                    <div style="font-size: 10px; color: #f59e0b;">/ {mid_cap}</div>
                </div>
                <div style="text-align: center; padding: 12px; background: linear-gradient(135deg,#ede9fe,#ddd6fe); border-radius: 8px;">
                    <div style="font-size: 20px; margin-bottom: 2px;">🧠</div>
                    <div style="font-size: 12px; font-weight: 600; color: #6d28d9;">长期</div>
                    <div style="font-size: 18px; font-weight: 700; color: #6d28d9;">总结</div>
                    <div style="font-size: 10px; color: #8b5cf6;">定期生成</div>
                </div>
            </div>
            <div style="margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 4px;">
                    <span>短期使用</span><span>{short_size}/{short_cap}</span>
                </div>
                <div style="height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden;">
                    <div style="width: {short_pct}%; height: 100%; background: linear-gradient(90deg,#3b82f6,#60a5fa); border-radius: 3px;"></div>
                </div>
            </div>
            <div>
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 4px;">
                    <span>中期使用</span><span>{mid_size}/{mid_cap}</span>
                </div>
                <div style="height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden;">
                    <div style="width: {mid_pct}%; height: 100%; background: linear-gradient(90deg,#f59e0b,#fbbf24); border-radius: 3px;"></div>
                </div>
            </div>
        </div>
        """.format(
            short_size=short_size, short_cap=short_cap, short_pct=short_pct,
            mid_size=mid_size, mid_cap=mid_cap, mid_pct=mid_pct
        ))

    def _render_memory_help(self):
        """渲染帮助说明"""
        render_help_collapse("memory")

    def _refresh_data(self):
        """刷新数据"""
        run_js("setTimeout(function() { location.reload(); }, 200)")

    def _generate_report(self):
        """生成完整报告"""
        report_text = self.radar.generate_thought_report()
        popup("记忆报告", put_text(report_text))

    def _clear_memory(self):
        """清空记忆"""
        if hasattr(self.radar, 'short_memory'):
            self.radar.short_memory.clear()
        if hasattr(self.radar, 'mid_memory'):
            self.radar.mid_memory.clear()
        if hasattr(self.radar, 'long_memory'):
            self.radar.long_memory.clear()
        if hasattr(self.radar, 'topics'):
            self.radar.topics.clear()
        if hasattr(self.radar, 'attention_scorer'):
            self.radar.attention_scorer = AttentionScorer()
        toast("记忆已清空", color="success")
        run_js("setTimeout(function() { location.reload(); }, 1000)")


def render_empty_state(message: str) -> str:
    """渲染空状态"""
    return f'<div style="padding: 24px; text-align: center; color: #94a3b8; font-size: 13px; background: #f8fafc; border-radius: 8px;">{message}</div>'


def main():
    """主入口"""
    ui = NewsRadarUI()
    ui.render()


if __name__ == "__main__":
    main()
