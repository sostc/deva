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


class LobsterRadarUI:
    """记忆系统 UI"""

    def __init__(self):
        self.radar = get_running_memory_engine()
        self.refresh_interval = 5  # 秒

    def render(self):
        """渲染主页面"""
        # 设置页面标题
        set_env(title="Naja - 记忆", output_animation=False)

        # 应用全局样式
        apply_global_styles()

        # 创建导航菜单
        create_nav_menu()

        # 主容器
        put_html('<div class="container">')

        # 页面标题
        put_html("""
        <div style="margin-bottom: 24px;">
            <h1 style="font-size: 28px; font-weight: 700; color: #1e293b; margin-bottom: 8px;">
                🧠 记忆系统
            </h1>
            <p style="color: #64748b; font-size: 14px;">
                策略结果沉淀为共享记忆，供策略、雷达事件与 AI 大脑共同复用
            </p>
        </div>
        """)

        # 架构概览
        self._render_arch_overview()

        # 记忆与系统关系
        self._render_memory_flow()

        # 控制面板
        self._render_control_panel()

        # 实时状态
        self._render_status_panel()

        # 三层记忆展示
        self._render_memory_layers()

        # 主题云图
        self._render_topic_cloud()

        # 注意力时间线
        self._render_attention_timeline()

        # 信号流
        self._render_signal_stream()

        # 思想报告
        self._render_thought_report()

        put_html('</div>')

    def _render_control_panel(self):
        """渲染控制面板"""
        put_html('<div class="card">')
        put_html('<div class="card-header">⚙️ 控制面板</div>')

        with put_row():
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

        put_html('<div class="card">')
        put_html('<div class="card-header">📊 记忆核心指标</div>')

        # 统计卡片
        with put_row():
            with put_column():
                put_html(f"""
                <div class="stat-card">
                    <div class="stat-value" style="color: #3b82f6;">{stats['total_events']}</div>
                    <div class="stat-label">累计事件</div>
                </div>
                """)

            with put_column():
                put_html(f"""
                <div class="stat-card">
                    <div class="stat-value" style="color: #ef4444;">{stats['high_attention_events']}</div>
                    <div class="stat-label">高注意力</div>
                </div>
                """)

            with put_column():
                put_html(f"""
                <div class="stat-card">
                    <div class="stat-value" style="color: #10b981;">{stats['topics_created']}</div>
                    <div class="stat-label">主题数量</div>
                </div>
                """)

            with put_column():
                put_html(f"""
                <div class="stat-card">
                    <div class="stat-value" style="color: #f59e0b;">{stats['drifts_detected']}</div>
                    <div class="stat-label">漂移次数</div>
                </div>
                """)

        put_html("""
        <div style="display:flex; gap:16px; flex-wrap:wrap; margin-top:16px;">
            <div style="flex:1; min-width:160px; background:#f8fafc; padding:12px 16px; border-radius:10px;">
                <div style="font-size:12px; color:#64748b;">短期记忆</div>
                <div style="font-size:18px; font-weight:600; color:#0f172a;">{}</div>
            </div>
            <div style="flex:1; min-width:160px; background:#f8fafc; padding:12px 16px; border-radius:10px;">
                <div style="font-size:12px; color:#64748b;">中期记忆</div>
                <div style="font-size:18px; font-weight:600; color:#0f172a;">{}</div>
            </div>
            <div style="flex:1; min-width:160px; background:#f8fafc; padding:12px 16px; border-radius:10px;">
                <div style="font-size:12px; color:#64748b;">长期记忆</div>
                <div style="font-size:18px; font-weight:600; color:#0f172a;">{}</div>
            </div>
        </div>
        """.format(short_size, mid_size, long_size))

        put_html('</div>')

    def _render_arch_overview(self):
        """渲染架构概览"""
        put_html("""
        <div class="card">
            <div class="card-header">🧭 记忆系统定位</div>
            <div style="color:#475569; font-size:14px; line-height:1.8;">
                记忆系统是平台级共享能力，不再是单一策略的私有状态。策略结果会沉淀为分层记忆与主题，
                并被策略、雷达事件与 AI 大脑共同读取与复用，形成自调节闭环。
            </div>
        </div>
        """)

    def _render_memory_flow(self):
        """渲染记忆系统关系图"""
        put_html("""
        <div class="card">
            <div class="card-header">🔄 记忆与系统关系</div>
            <div style="display:flex; align-items:center; justify-content:center; flex-wrap:wrap; gap:16px;">
                <div style="width:90px; height:90px; border-radius:14px; background:linear-gradient(135deg,#4facfe,#00f2fe); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:600;">
                    策略结果
                </div>
                <div style="color:#3b82f6; font-size:20px;">→</div>
                <div style="width:90px; height:90px; border-radius:14px; background:linear-gradient(135deg,#6a11cb,#2575fc); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:600;">
                    记忆沉淀
                </div>
                <div style="color:#3b82f6; font-size:20px;">→</div>
                <div style="display:flex; gap:10px; flex-wrap:wrap;">
                    <div style="width:90px; height:90px; border-radius:14px; background:linear-gradient(135deg,#f5576c,#f093fb); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:600;">
                        雷达事件
                    </div>
                    <div style="width:90px; height:90px; border-radius:14px; background:linear-gradient(135deg,#43e97b,#38f9d7); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:600;">
                        AI 大脑
                    </div>
                    <div style="width:90px; height:90px; border-radius:14px; background:linear-gradient(135deg,#fa709a,#fee140); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:600;">
                        策略复用
                    </div>
                </div>
            </div>
            <div style="margin-top:12px; color:#94a3b8; font-size:12px; text-align:center;">
                记忆既是沉淀层，也是调节与复用层
            </div>
        </div>
        """)

    def _render_memory_layers(self):
        """渲染三层记忆"""
        put_html('<div class="card">')
        put_html('<div class="card-header">🧠 三层记忆系统</div>')

        report = self.radar.get_memory_report()
        memory_layers = report.get('memory_layers', {})

        # 短期记忆
        short_memory = memory_layers.get('short', {})
        self._render_short_memory(short_memory)

        # 中期记忆
        mid_memory = memory_layers.get('mid', {})
        self._render_mid_memory(mid_memory)

        # 长期记忆
        long_memory = memory_layers.get('long', {})
        self._render_long_memory(long_memory)

        put_html('</div>')

    def _render_short_memory(self, short_memory):
        """渲染短期记忆"""
        size = short_memory.get('size', 0)
        capacity = short_memory.get('capacity', 1000)
        data = short_memory.get('data', [])

        put_html(f'''
        <div class="memory-layer-card memory-layer-short">
            <div class="memory-header">
                <div class="memory-title">
                    <span>⚡</span>
                    <span>短期记忆</span>
                    <span style="font-size: 12px; color: #64748b; font-weight: normal;">最近的事件流</span>
                </div>
                <div class="memory-badge">{size} / {capacity}</div>
            </div>
        ''')

        if not data:
            put_html('<div style="color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;">暂无短期记忆数据</div>')
        else:
            for item in data[:5]:
                score = item.get('attention_score', 0)
                score_class = 'memory-score-high' if score > 0.7 else ('memory-score-mid' if score > 0.4 else 'memory-score-low')
                put_html(f'''
                <div class="memory-item">
                    <div class="memory-item-header">
                        <span>[{item.get('event_type', 'unknown').upper()}] {item.get('source', 'unknown')}</span>
                        <span class="memory-score {score_class}">注意力: {score}</span>
                    </div>
                    <div class="memory-item-content">{item.get('content', '')}</div>
                </div>
                ''')

        put_html('</div>')

    def _render_mid_memory(self, mid_memory):
        """渲染中期记忆"""
        size = mid_memory.get('size', 0)
        capacity = mid_memory.get('capacity', 5000)
        threshold = mid_memory.get('threshold', 0.7)
        data = mid_memory.get('data', [])

        put_html(f'''
        <div class="memory-layer-card memory-layer-mid">
            <div class="memory-header">
                <div class="memory-title">
                    <span>📦</span>
                    <span>中期记忆</span>
                    <span style="font-size: 12px; color: #64748b; font-weight: normal;">高注意力事件归档 (≥{threshold})</span>
                </div>
                <div class="memory-badge">{size} / {capacity}</div>
            </div>
        ''')

        if not data:
            put_html('<div style="color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;">暂无中期记忆数据</div>')
        else:
            for item in data[:5]:
                score = item.get('attention_score', 0)
                score_class = 'memory-score-high' if score > 0.7 else ('memory-score-mid' if score > 0.4 else 'memory-score-low')
                put_html(f'''
                <div class="memory-item">
                    <div class="memory-item-header">
                        <span>[{item.get('event_type', 'unknown').upper()}] {item.get('source', 'unknown')}</span>
                        <span class="memory-score {score_class}">注意力: {score}</span>
                    </div>
                    <div class="memory-item-content">{item.get('content', '')}</div>
                </div>
                ''')

        put_html('</div>')

    def _render_long_memory(self, long_memory):
        """渲染长期记忆"""
        size = long_memory.get('size', 0)
        data = long_memory.get('data', [])

        put_html(f'''
        <div class="memory-layer-card memory-layer-long">
            <div class="memory-header">
                <div class="memory-title">
                    <span>🧠</span>
                    <span>长期记忆</span>
                    <span style="font-size: 12px; color: #64748b; font-weight: normal;">周期性总结</span>
                </div>
                <div class="memory-badge">{size} / 30</div>
            </div>
        ''')

        if not data:
            put_html('<div style="color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;">暂无长期记忆数据</div>')
        else:
            for item in data[:5]:
                period_start = item.get('period_start', '')
                period_end = item.get('period_end', '')
                summary = item.get('summary', '')
                put_html(f'''
                <div class="memory-item">
                    <div class="memory-item-header">
                        <span>📆 {period_start} ~ {period_end}</span>
                    </div>
                    <div class="memory-item-content">{summary}</div>
                </div>
                ''')

        put_html('</div>')

    def _render_topic_cloud(self):
        """渲染主题云图"""
        put_html('<div class="card">')
        put_html('<div class="card-header">☁️ 主题云图</div>')
        report = self.radar.get_memory_report()
        topics = report.get('top_topics', [])

        if not topics:
            put_html('<div style="color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;">暂无主题数据</div>')
        else:
            put_html('<div style="display: flex; flex-wrap: wrap; gap: 8px;">')
            for topic in topics[:20]:
                size = 12 + min(topic.get('event_count', 1), 20)
                put_html(f'''
                <span style="background: #f1f5f9; color: #334155; padding: 6px 10px; border-radius: 999px; font-size: {size}px;">
                    {topic.get('name', '主题')}
                </span>
                ''')
            put_html('</div>')
        put_html('</div>')

    def _render_attention_timeline(self):
        """渲染注意力时间线"""
        put_html('<div class="card">')
        put_html('<div class="card-header">📈 注意力时间线</div>')
        report = self.radar.get_memory_report()
        events = report.get('recent_high_attention', [])

        if not events:
            put_html('<div style="color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;">暂无高注意力事件</div>')
        else:
            for event in events[:10]:
                put_html(f'''
                <div class="memory-item">
                    <div class="memory-item-header">
                        <span>⏰ {event.get('timestamp', '')}</span>
                        <span class="memory-score memory-score-high">注意力: {event.get('score', 0)}</span>
                    </div>
                    <div class="memory-item-content">{event.get('content', '')}</div>
                </div>
                ''')
        put_html('</div>')

    def _render_signal_stream(self):
        """渲染信号流"""
        put_html('<div class="card">')
        put_html('<div class="card-header">🌊 信号流</div>')
        report = self.radar.get_memory_report()
        signals = report.get('recent_signals', [])

        if not signals:
            put_html('<div style="color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;">暂无信号数据</div>')
        else:
            for signal in signals[:10]:
                put_html(f'''
                <div class="memory-item">
                    <div class="memory-item-header">
                        <span>📡 {signal.get('type', 'signal')}</span>
                        <span>{signal.get('timestamp', '')}</span>
                    </div>
                    <div class="memory-item-content">{signal.get('message', '')}</div>
                </div>
                ''')
        put_html('</div>')

    def _render_thought_report(self):
        """渲染思想报告"""
        put_html('<div class="card">')
        put_html('<div class="card-header">📝 思想报告</div>')
        report_text = self.radar.generate_thought_report()
        put_code(report_text)
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
    ui = LobsterRadarUI()
    ui.render()


if __name__ == "__main__":
    main()
