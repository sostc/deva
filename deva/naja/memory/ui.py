"""
记忆系统 Web UI Tab
集成到 naja 首页的独立标签页
风格与其他 naja 页面保持一致
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
    """记忆系统 UI"""

    def __init__(self):
        self.radar = get_running_memory_engine()
        self.refresh_interval = 5  # 秒

    def render(self):
        """渲染主页面"""
        set_env(title="Naja - 记忆", output_animation=False)
        apply_global_styles()
        create_nav_menu()

        put_html('<div class="container" style="max-width:1400px;margin:0 auto;padding:16px;">')

        put_html("""
        <div style="margin-bottom: 20px;">
            <h1 style="font-size: 22px; font-weight: 700; color: #1e293b; margin-bottom: 6px;">
                🧠 记忆系统
            </h1>
            <p style="color: #64748b; font-size: 13px;">
                策略结果沉淀为共享记忆，供策略、雷达事件与 AI 大脑共同复用
            </p>
        </div>
        """)

        self._render_status_panel()

        self._render_control_panel()

        put_html('<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">')
        self._render_signal_stream()
        self._render_attention_timeline()
        put_html('</div>')

        self._render_memory_layers()

        self._render_topic_cloud()

        self._render_thought_report()

        self._render_memory_help()

        put_html('</div>')

    def _render_control_panel(self):
        """渲染控制面板"""
        put_html('<div style="margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">')
        put_button("🔄 刷新数据", onclick=self._refresh_data, color="primary")
        put_button("📊 生成报告", onclick=self._generate_report, color="success")
        put_button("🧹 清空记忆", onclick=self._clear_memory, color="danger")
        put_button("⚡ 注入测试事件", onclick=self._test_event, color="warning")
        put_html('</div>')

    def _render_status_panel(self):
        """渲染状态面板"""
        report = self.radar.get_memory_report()
        stats = report['stats']
        memory_layers = report.get('memory_layers', {})
        short_size = memory_layers.get('short', {}).get('size', 0)
        mid_size = memory_layers.get('mid', {}).get('size', 0)
        long_size = memory_layers.get('long', {}).get('size', 0)

        put_html("""
        <div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px;">
            <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#3b82f6,#1d4ed8);padding:16px 20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(59,130,246,0.3);">
                <div style="font-size:12px;opacity:0.9;margin-bottom:4px;">累计事件</div>
                <div style="font-size:28px;font-weight:700;">{}</div>
            </div>
            <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#ef4444,#dc2626);padding:16px 20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(239,68,68,0.3);">
                <div style="font-size:12px;opacity:0.9;margin-bottom:4px;">高注意力</div>
                <div style="font-size:28px;font-weight:700;">{}</div>
            </div>
            <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#10b981,#059669);padding:16px 20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(16,185,129,0.3);">
                <div style="font-size:12px;opacity:0.9;margin-bottom:4px;">主题数量</div>
                <div style="font-size:28px;font-weight:700;">{}</div>
            </div>
            <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#f59e0b,#d97706);padding:16px 20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(245,158,11,0.3);">
                <div style="font-size:12px;opacity:0.9;margin-bottom:4px;">漂移次数</div>
                <div style="font-size:28px;font-weight:700;">{}</div>
            </div>
        </div>
        <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
            <div style="flex:1;min-width:120px;background:#f8fafc;padding:12px 16px;border-radius:10px;border:1px solid #e2e8f0;">
                <div style="font-size:11px;color:#64748b;margin-bottom:2px;">⚡ 短期记忆</div>
                <div style="font-size:18px;font-weight:600;color:#0f172a;">{}</div>
            </div>
            <div style="flex:1;min-width:120px;background:#f8fafc;padding:12px 16px;border-radius:10px;border:1px solid #e2e8f0;">
                <div style="font-size:11px;color:#64748b;margin-bottom:2px;">📦 中期记忆</div>
                <div style="font-size:18px;font-weight:600;color:#0f172a;">{}</div>
            </div>
            <div style="flex:1;min-width:120px;background:#f8fafc;padding:12px 16px;border-radius:10px;border:1px solid #e2e8f0;">
                <div style="font-size:11px;color:#64748b;margin-bottom:2px;">🧠 长期记忆</div>
                <div style="font-size:18px;font-weight:600;color:#0f172a;">{}</div>
            </div>
        </div>
        """.format(
            stats['total_events'],
            stats['high_attention_events'],
            stats['topics_created'],
            stats['drifts_detected'],
            f"{short_size} / {memory_layers.get('short', {}).get('capacity', 1000)}",
            f"{mid_size} / {memory_layers.get('mid', {}).get('capacity', 5000)}",
            f"{long_size} / 30"
        ))

    def _render_memory_help(self):
        """渲染记忆系统帮助说明"""
        render_help_collapse("memory")

    def _render_memory_layers(self):
        """渲染三层记忆"""
        put_html('<div style="margin-bottom:16px;">')
        put_html('<div style="font-size:15px;font-weight:600;color:#333;margin-bottom:12px;">🧠 三层记忆系统</div>')

        report = self.radar.get_memory_report()
        memory_layers = report.get('memory_layers', {})

        put_html('<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">')

        short_memory = memory_layers.get('short', {})
        self._render_short_memory(short_memory)

        mid_memory = memory_layers.get('mid', {})
        self._render_mid_memory(mid_memory)

        long_memory = memory_layers.get('long', {})
        self._render_long_memory(long_memory)

        put_html('</div>')
        put_html('</div>')

    def _render_short_memory(self, short_memory):
        """渲染短期记忆"""
        size = short_memory.get('size', 0)
        capacity = short_memory.get('capacity', 1000)
        data = short_memory.get('data', [])

        put_html(f'''
        <div style="background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.06);overflow:hidden;border:1px solid #e0e7ff;">
            <div style="background:linear-gradient(135deg,#3b82f6,#1d4ed8);padding:10px 12px;color:#fff;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span style="font-size:14px;">⚡</span>
                        <span style="font-weight:600;font-size:13px;">短期记忆</span>
                    </div>
                    <span style="background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:10px;font-size:11px;">{size}/{capacity}</span>
                </div>
                <div style="font-size:11px;opacity:0.8;margin-top:2px;">最近的事件流</div>
            </div>
        ''')

        if not data:
            put_html('<div style="color: #94a3b8; font-size: 12px; text-align: center; padding: 16px;">暂无数据</div>')
        else:
            put_html('<div style="padding:8px;max-height:180px;overflow-y:auto;">')
            for item in data[:4]:
                score = item.get('attention_score', 0)
                score_class = '#ef4444' if score > 0.7 else ('#f59e0b' if score > 0.4 else '#64748b')
                timestamp_str = item.get('timestamp', '')
                if 'T' in timestamp_str:
                    try:
                        from datetime import datetime
                        ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        timestamp_str = ts.strftime('%m-%d %H:%M')
                    except:
                        pass
                source = item.get('source', 'unknown')
                put_html(f'''
                <div style="padding:8px;margin-bottom:6px;background:#f8fafc;border-radius:6px;border-left:3px solid {score_class};">
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;margin-bottom:4px;">
                        <span style="color:#475569;font-weight:500;">[{item.get('event_type', 'unknown').upper()}] {source}</span>
                        <span style="color:{score_class};font-weight:600;">{score:.2f}</span>
                    </div>
                    <div style="font-size:10px;color:#94a3b8;margin-bottom:4px;">⏰ {timestamp_str}</div>
                    <div style="font-size:11px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{item.get('content', '')}</div>
                </div>
                ''')
            put_html('</div>')

        put_html('</div>')

    def _render_mid_memory(self, mid_memory):
        """渲染中期记忆"""
        size = mid_memory.get('size', 0)
        capacity = mid_memory.get('capacity', 5000)
        threshold = mid_memory.get('threshold', 0.7)
        data = mid_memory.get('data', [])

        put_html(f'''
        <div style="background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.06);overflow:hidden;border:1px solid #fef3c7;">
            <div style="background:linear-gradient(135deg,#f59e0b,#d97706);padding:10px 12px;color:#fff;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span style="font-size:14px;">📦</span>
                        <span style="font-weight:600;font-size:13px;">中期记忆</span>
                    </div>
                    <span style="background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:10px;font-size:11px;">{size}/{capacity}</span>
                </div>
                <div style="font-size:11px;opacity:0.8;margin-top:2px;">高注意力事件归档 (≥{threshold})</div>
            </div>
        ''')

        if not data:
            put_html('<div style="color: #94a3b8; font-size: 12px; text-align: center; padding: 16px;">暂无数据</div>')
        else:
            put_html('<div style="padding:8px;max-height:180px;overflow-y:auto;">')
            for item in data[:4]:
                score = item.get('attention_score', 0)
                score_class = '#ef4444' if score > 0.7 else ('#f59e0b' if score > 0.4 else '#64748b')
                timestamp_str = item.get('timestamp', '')
                if 'T' in timestamp_str:
                    try:
                        from datetime import datetime
                        ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        timestamp_str = ts.strftime('%m-%d %H:%M')
                    except:
                        pass
                source = item.get('source', 'unknown')
                put_html(f'''
                <div style="padding:8px;margin-bottom:6px;background:#f8fafc;border-radius:6px;border-left:3px solid {score_class};">
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;margin-bottom:4px;">
                        <span style="color:#475569;font-weight:500;">[{item.get('event_type', 'unknown').upper()}] {source}</span>
                        <span style="color:{score_class};font-weight:600;">{score:.2f}</span>
                    </div>
                    <div style="font-size:10px;color:#94a3b8;margin-bottom:4px;">⏰ {timestamp_str}</div>
                    <div style="font-size:11px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{item.get('content', '')}</div>
                </div>
                ''')
            put_html('</div>')

        put_html('</div>')

    def _render_long_memory(self, long_memory):
        """渲染长期记忆"""
        size = long_memory.get('size', 0)
        data = long_memory.get('data', [])

        put_html(f'''
        <div style="background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.06);overflow:hidden;border:1px solid #ede9fe;">
            <div style="background:linear-gradient(135deg,#8b5cf6,#7c3aed);padding:10px 12px;color:#fff;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span style="font-size:14px;">🧠</span>
                        <span style="font-weight:600;font-size:13px;">长期记忆</span>
                    </div>
                    <span style="background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:10px;font-size:11px;">{size}/30</span>
                </div>
                <div style="font-size:11px;opacity:0.8;margin-top:2px;">周期性总结</div>
            </div>
        ''')

        if not data:
            put_html('<div style="color: #94a3b8; font-size: 12px; text-align: center; padding: 16px;">暂无数据</div>')
        else:
            put_html('<div style="padding:8px;max-height:180px;overflow-y:auto;">')
            for item in data[:4]:
                period_start = item.get('period_start', '')
                period_end = item.get('period_end', '')
                if 'T' in period_start:
                    try:
                        from datetime import datetime
                        ps = datetime.fromisoformat(period_start.replace('Z', '+00:00'))
                        period_start = ps.strftime('%m-%d %H:%M')
                    except:
                        pass
                if 'T' in period_end:
                    try:
                        from datetime import datetime
                        pe = datetime.fromisoformat(period_end.replace('Z', '+00:00'))
                        period_end = pe.strftime('%m-%d %H:%M')
                    except:
                        pass
                summary = item.get('summary', '')
                put_html(f'''
                <div style="padding:8px;margin-bottom:6px;background:#f8fafc;border-radius:6px;border-left:3px solid #8b5cf6;">
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;margin-bottom:4px;">
                        <span style="color:#8b5cf6;font-weight:500;">📆 {period_start} → {period_end}</span>
                    </div>
                    <div style="font-size:11px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{summary}</div>
                </div>
                ''')
            put_html('</div>')

        put_html('</div>')

    def _render_topic_cloud(self):
        """渲染主题云图"""
        put_html('<div style="margin-bottom:16px;">')
        put_html('<div style="font-size:15px;font-weight:600;color:#333;margin-bottom:12px;">☁️ 主题云图</div>')
        report = self.radar.get_memory_report()
        topics = report.get('top_topics', [])

        if not topics:
            put_html('<div style="color: #94a3b8; font-size: 12px; text-align: center; padding: 20px;background:#f8fafc;border-radius:10px;">暂无主题数据</div>')
        else:
            put_html('<div style="display: flex; flex-wrap: wrap; gap: 8px;padding:12px;background:#f8fafc;border-radius:10px;">')
            for topic in topics[:20]:
                size = 12 + min(topic.get('event_count', 1), 16)
                color_idx = hash(topic.get('name', '')) % 5
                colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']
                bg_color = colors[color_idx]
                put_html(f'''
                <span style="background:{bg_color}15;color:{bg_color};padding:6px 10px;border-radius:999px;font-size:{size}px;font-weight:500;border:1px solid {bg_color}30;">
                    {topic.get('name', '主题')} ({topic.get('event_count', 0)})
                </span>
                ''')
            put_html('</div>')
        put_html('</div>')

    def _render_attention_timeline(self):
        """渲染注意力时间线"""
        put_html('<div style="background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.06);overflow:hidden;border:1px solid #e2e8f0;">')
        put_html('<div style="background:linear-gradient(135deg,#6366f1,#4f46e5);padding:10px 12px;color:#fff;"><span style="font-weight:600;font-size:13px;">📈 注意力时间线</span></div>')
        report = self.radar.get_memory_report()
        events = report.get('recent_high_attention', [])

        if not events:
            put_html('<div style="color: #94a3b8; font-size: 12px; text-align: center; padding: 20px;">暂无高注意力事件</div>')
        else:
            put_html('<div style="padding:10px;max-height:240px;overflow-y:auto;">')
            for event in events[:8]:
                timestamp_str = event.get('timestamp', '')
                if 'T' in timestamp_str:
                    try:
                        from datetime import datetime
                        ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        timestamp_str = ts.strftime('%m-%d %H:%M')
                    except:
                        pass
                source = event.get('source', '')
                event_type = event.get('type', '')
                put_html(f'''
                <div style="padding:8px;margin-bottom:6px;background:#f8fafc;border-radius:6px;border-left:3px solid #ef4444;">
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;margin-bottom:4px;">
                        <span style="color:#6366f1;font-weight:500;">[{event_type.upper()}] {source}</span>
                        <span style="color:#ef4444;font-weight:600;">{event.get('score', 0):.2f}</span>
                    </div>
                    <div style="font-size:10px;color:#94a3b8;margin-bottom:4px;">⏰ {timestamp_str}</div>
                    <div style="font-size:12px;color:#334155;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{event.get('content', '')}</div>
                </div>
                ''')
            put_html('</div>')
        put_html('</div>')

    def _render_signal_stream(self):
        """渲染信号流"""
        put_html('<div style="background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.06);overflow:hidden;border:1px solid #e2e8f0;">')
        put_html('<div style="background:linear-gradient(135deg,#06b6d4,#0891b2);padding:10px 12px;color:#fff;"><span style="font-weight:600;font-size:13px;">🌊 信号流</span></div>')
        report = self.radar.get_memory_report()
        signals = report.get('recent_signals', [])

        if not signals:
            put_html('<div style="color: #94a3b8; font-size: 12px; text-align: center; padding: 20px;">暂无信号数据</div>')
        else:
            put_html('<div style="padding:10px;max-height:240px;overflow-y:auto;">')
            for signal in signals[:8]:
                signal_type = signal.get('type', 'signal')
                type_colors = {
                    'radar': '#f59e0b',
                    'memory': '#8b5cf6',
                    'trade': '#ef4444',
                    'alert': '#dc2626'
                }
                color = type_colors.get(signal_type, '#64748b')
                put_html(f'''
                <div style="padding:8px;margin-bottom:6px;background:#f8fafc;border-radius:6px;border-left:3px solid {color};">
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;margin-bottom:4px;">
                        <span style="color:{color};font-weight:500;">📡 {signal.get('type', 'signal')}</span>
                        <span style="color:#64748b;">{signal.get('timestamp', '')}</span>
                    </div>
                    <div style="font-size:12px;color:#334155;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{signal.get('message', '')}</div>
                </div>
                ''')
            put_html('</div>')
        put_html('</div>')

    def _render_thought_report(self):
        """渲染思想报告"""
        put_html('<div style="margin-bottom:16px;">')
        put_html('<div style="font-size:15px;font-weight:600;color:#333;margin-bottom:12px;">📝 思想报告</div>')
        report_text = self.radar.generate_thought_report()
        put_html(f'<div style="background:#f8fafc;padding:12px;border-radius:10px;border:1px solid #e2e8f0;"><pre style="white-space:pre-wrap;word-break:break-word;font-size:12px;line-height:1.6;color:#334155;margin:0;">{report_text}</pre></div>')
        put_html('</div>')

    def _refresh_data(self):
        """刷新数据"""
        run_js("setTimeout(function() { location.reload(); }, 200)")

    def _generate_report(self):
        """生成报告"""
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

    def _test_event(self):
        """测试事件"""
        test_record = {
            "timestamp": datetime.now(),
            "source": "test",
            "data": {
                "title": "测试新闻",
                "content": "AI算力突破！英伟达发布新一代GPU，性能提升100%",
            }
        }

        signals = self.radar.process_record(test_record)
        toast(f"测试事件已处理，生成 {len(signals)} 个信号", color="info")

        for signal in signals:
            put_html(f"<p>📡 {signal['type']}: {signal['message']}</p>")


def main():
    """主入口"""
    ui = NewsRadarUI()
    ui.render()


if __name__ == "__main__":
    main()
