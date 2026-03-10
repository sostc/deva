"""
龙虾思想雷达 Web UI Tab
集成到naja首页的独立标签页
风格与其他naja页面保持一致
"""

from pywebio.output import *
from pywebio.input import *
from pywebio.pin import *
from pywebio.session import run_js, set_env
import json
from datetime import datetime, timedelta

# 导入思想雷达策略
import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')
from deva.naja.strategy.plugins.lobster_radar import LobsterRadarStrategy, AttentionScorer


def get_running_radar_strategy():
    """
    获取运行中的龙虾思想雷达策略实例
    从策略管理器中查找
    """
    try:
        from deva.naja.strategy import get_strategy_manager
        
        strategy_mgr = get_strategy_manager()
        
        # 遍历所有策略，找到龙虾思想雷达
        # StrategyManager 使用 _items 存储策略条目
        for strategy_id, strategy_entry in strategy_mgr._items.items():
            if hasattr(strategy_entry, '_metadata'):
                name = strategy_entry._metadata.name
                if name == '龙虾思想雷达':
                    # 尝试从策略代码中获取雷达实例
                    if hasattr(strategy_entry, '_compiled_func'):
                        # 从编译后的函数中获取 _radar 变量
                        func_globals = strategy_entry._compiled_func.__globals__
                        if '_radar' in func_globals:
                            print(f"[LobsterTab] 成功获取运行中的策略实例")
                            return func_globals['_radar']
        
        # 如果没有找到运行的策略，返回一个新的实例（用于测试）
        print(f"[LobsterTab] 未找到运行中的策略，使用新实例")
        return LobsterRadarStrategy()
    except Exception as e:
        print(f"[LobsterTab] 获取运行策略失败: {e}")
        return LobsterRadarStrategy()


def create_nav_menu():
    """创建导航菜单 - 与其他naja页面保持一致"""
    menu_items = [
        {"name": "🏠 首页", "path": "/"},
        {"name": "📡 雷达", "path": "/lobster"},
        {"name": "💰 信号", "path": "/signaladmin"},
        {"name": "🗃️ 数据源", "path": "/dsadmin"},
        {"name": "⏱️ 任务", "path": "/taskadmin"},
        {"name": "🎯 策略", "path": "/strategyadmin"},
        {"name": "📖 字典", "path": "/dictadmin"},
        {"name": "🗄️ 数据表", "path": "/tableadmin"},
        {"name": "🔧 配置", "path": "/configadmin"},
    ]
    
    menu_items_js = ",\n            ".join([
        f"{{name: '{item['name']}', path: '{item['path']}'}}"
        for item in menu_items
    ])
    
    js_code = f"""
    (function() {{
        // 如果已存在导航栏，先移除
        const existingNav = document.querySelector('.navbar');
        if (existingNav) {{
            existingNav.remove();
        }}
        
        const nav = document.createElement('nav');
        nav.className = 'navbar';
        Object.assign(nav.style, {{
            position: 'fixed',
            top: '0',
            left: '0',
            right: '0',
            width: '100%',
            zIndex: '999',
            backgroundColor: '#ffffff',
            borderBottom: '1px solid #e2e8f0',
            padding: '0 24px',
            height: '56px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
        }});
        
        const brand = document.createElement('div');
        const brandLink = document.createElement('a');
        brandLink.href = '/';
        brandLink.innerHTML = '<span style="font-size: 22px;">🚀</span><span style="font-size: 18px; font-weight: 600; color: #1e293b; margin-left: 8px;">Naja</span>';
        brandLink.style.textDecoration = 'none';
        brandLink.style.display = 'flex';
        brandLink.style.alignItems = 'center';
        brand.appendChild(brandLink);

        const menu = document.createElement('div');
        Object.assign(menu.style, {{
            display: 'flex',
            gap: '4px',
            alignItems: 'center'
        }});

        const currentPath = window.location.pathname;
        const menuItems = [
            {menu_items_js}
        ];
        
        menuItems.forEach(item => {{
            const link = document.createElement('a');
            link.href = item.path;
            link.innerText = item.name;
            const isActive = currentPath === item.path;
            Object.assign(link.style, {{
                padding: '8px 14px',
                color: isActive ? '#3b82f6' : '#64748b',
                textDecoration: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: isActive ? '600' : '500',
                backgroundColor: isActive ? '#eff6ff' : 'transparent',
                transition: 'all 0.2s ease'
            }});
            menu.appendChild(link);
        }});

        nav.appendChild(brand);
        nav.appendChild(menu);
        document.body.insertBefore(nav, document.body.firstChild);
        document.body.style.paddingTop = '56px';
    }})();
    """
    
    run_js(js_code)


def apply_global_styles():
    """应用全局样式 - 与其他naja页面保持一致"""
    styles = """
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: #f8fafc;
            margin: 0;
            padding: 0;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        .card-header {
            font-size: 18px;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #e2e8f0;
        }
        .stat-card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 20px;
            text-align: center;
        }
        .stat-value {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .stat-label {
            font-size: 14px;
            color: #64748b;
        }
        .btn {
            padding: 8px 16px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #3b82f6;
            color: white;
        }
        .btn-primary:hover {
            background: #2563eb;
        }
        .btn-success {
            background: #10b981;
            color: white;
        }
        .btn-success:hover {
            background: #059669;
        }
        .btn-warning {
            background: #f59e0b;
            color: white;
        }
        .btn-warning:hover {
            background: #d97706;
        }
        .btn-danger {
            background: #ef4444;
            color: white;
        }
        .btn-danger:hover {
            background: #dc2626;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }
        th {
            font-weight: 600;
            color: #64748b;
            font-size: 12px;
            text-transform: uppercase;
        }
        tr:hover {
            background: #f8fafc;
        }
        .signal-item {
            display: flex;
            align-items: center;
            padding: 12px;
            margin: 8px 0;
            background: #f8fafc;
            border-radius: 8px;
            border-left: 4px solid #3b82f6;
        }
        .signal-time {
            color: #64748b;
            font-size: 12px;
            margin-right: 12px;
            min-width: 80px;
        }
        .signal-content {
            flex: 1;
        }
        .event-card {
            border-left: 4px solid #e74c3c;
            padding: 12px 16px;
            margin: 8px 0;
            background: #fafafa;
            border-radius: 0 8px 8px 0;
        }
        .topic-tag {
            display: inline-block;
            padding: 4px 12px;
            background: #e0e7ff;
            color: #4338ca;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            margin: 4px;
        }
        .memory-layer-card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 16px;
            margin-bottom: 16px;
            border-left: 4px solid;
        }
        .memory-layer-short {
            border-left-color: #3b82f6;
        }
        .memory-layer-mid {
            border-left-color: #f59e0b;
        }
        .memory-layer-long {
            border-left-color: #10b981;
        }
        .memory-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .memory-title {
            font-size: 16px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .memory-badge {
            background: #f1f5f9;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            color: #64748b;
        }
        .memory-item {
            padding: 10px 12px;
            background: #f8fafc;
            border-radius: 8px;
            margin-bottom: 8px;
            font-size: 13px;
        }
        .memory-item-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 4px;
            color: #64748b;
            font-size: 11px;
        }
        .memory-item-content {
            color: #1e293b;
            line-height: 1.4;
        }
        .memory-score {
            font-weight: 600;
        }
        .memory-score-high {
            color: #ef4444;
        }
        .memory-score-mid {
            color: #f59e0b;
        }
        .memory-score-low {
            color: #10b981;
        }
    </style>
    """
    put_html(styles)


class LobsterRadarUI:
    """思想雷达UI"""
    
    def __init__(self):
        self.radar = get_running_radar_strategy()
        self.refresh_interval = 5  # 秒
    
    def render(self):
        """渲染主页面"""
        # 设置页面标题
        set_env(title="Naja - 思想雷达", output_animation=False)
        
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
                🦞 龙虾思想雷达
            </h1>
            <p style="color: #64748b; font-size: 14px;">
                流式学习 + 分层记忆 + 周期性自我反思
            </p>
        </div>
        """)
        
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
            put_button("⚡ 测试事件", onclick=self._test_event, color="warning")
        
        put_html('</div>')
    
    def _render_status_panel(self):
        """渲染状态面板"""
        report = self.radar.get_memory_report()
        stats = report['stats']
        
        put_html('<div class="card">')
        put_html('<div class="card-header">📊 实时状态</div>')
        
        # 统计卡片
        with put_row():
            with put_column():
                put_html(f"""
                <div class="stat-card">
                    <div class="stat-value" style="color: #3b82f6;">{stats['total_events']}</div>
                    <div class="stat-label">总事件数</div>
                </div>
                """)
            
            with put_column():
                put_html(f"""
                <div class="stat-card">
                    <div class="stat-value" style="color: #ef4444;">{stats['high_attention_events']}</div>
                    <div class="stat-label">高注意力事件</div>
                </div>
                """)
            
            with put_column():
                put_html(f"""
                <div class="stat-card">
                    <div class="stat-value" style="color: #10b981;">{stats['topics_created']}</div>
                    <div class="stat-label">主题数</div>
                </div>
                """)
            
            with put_column():
                put_html(f"""
                <div class="stat-card">
                    <div class="stat-value" style="color: #f59e0b;">{stats['drifts_detected']}</div>
                    <div class="stat-label">漂移检测</div>
                </div>
                """)
        
        put_html('</div>')
    
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
        capacity = long_memory.get('capacity', 30)
        interval = long_memory.get('interval_hours', 24)
        data = long_memory.get('data', [])

        put_html(f'''
        <div class="memory-layer-card memory-layer-long">
            <div class="memory-header">
                <div class="memory-title">
                    <span>🏛️</span>
                    <span>长期记忆</span>
                    <span style="font-size: 12px; color: #64748b; font-weight: normal;">周期性总结 (每{interval}小时)</span>
                </div>
                <div class="memory-badge">{size} / {capacity}</div>
            </div>
        ''')

        if not data:
            put_html('<div style="color: #94a3b8; font-size: 13px; text-align: center; padding: 20px;">暂无长期记忆数据</div>')
        else:
            for item in data[:3]:
                summary = item.get('summary', {})
                total_events = summary.get('total_events', 0)
                avg_attention = summary.get('avg_attention', 0)
                top_topics = summary.get('top_topics', [])

                topics_html = ''
                if top_topics:
                    topics_html = '<div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px;">'
                    for topic in top_topics[:3]:
                        topic_name = topic.get('name', f"主题{topic.get('id', '?')}")
                        topics_html += f'<span class="topic-tag">{topic_name}</span>'
                    topics_html += '</div>'

                put_html(f'''
                <div class="memory-item">
                    <div class="memory-item-header">
                        <span>📅 {item.get('period_start', '')[:10]} ~ {item.get('period_end', '')[:10]}</span>
                        <span>{total_events} 事件 | 平均注意力: {avg_attention:.3f}</span>
                    </div>
                    {topics_html}
                </div>
                ''')

        put_html('</div>')

    def _render_topic_cloud(self):
        """渲染主题云图"""
        put_html('<div class="card">')
        put_html('<div class="card-header">🔥 热门主题 TOP10</div>')
        
        report = self.radar.get_memory_report()
        topics = report.get('top_topics', [])
        
        if not topics:
            put_info("暂无主题数据，等待事件流入...")
        else:
            # 主题表格
            topic_data = []
            for t in topics[:10]:
                growth_color = "🟢" if t['growth_rate'] > 0 else "🔴"
                # 使用主题名称，如果没有则显示默认名称
                topic_name = t.get('name', f"主题{t['id']}")
                topic_data.append([
                    topic_name,
                    t['event_count'],
                    f"{t['avg_attention']:.3f}",
                    f"{growth_color} {t['growth_rate']:.3f}",
                    t['created_at'][:16]
                ])
            
            put_table(
                topic_data,
                header=['主题', '事件数', '平均注意力', '增长率', '创建时间']
            )
        
        put_html('</div>')
    
    def _render_attention_timeline(self):
        """渲染注意力时间线"""
        put_html('<div class="card">')
        put_html('<div class="card-header">⚡ 高注意力事件</div>')
        
        report = self.radar.get_memory_report()
        events = report.get('recent_high_attention', [])
        
        if not events:
            put_info("暂无高注意力事件")
        else:
            # 事件列表
            for event in events:
                score_color = "#ef4444" if event['score'] > 0.8 else "#f59e0b"
                put_html(f"""
                <div class="event-card" style="border-left-color: {score_color};">
                    <strong>[{event['type'].upper()}]</strong> 
                    <span style="color: {score_color}; font-weight: bold;">评分: {event['score']}</span>
                    <p style="margin: 5px 0 0 0; color: #64748b; font-size: 13px;">{event['content']}</p>
                </div>
                """)
        
        put_html('</div>')
    
    def _render_signal_stream(self):
        """渲染信号流"""
        put_html('<div class="card">')
        put_html('<div class="card-header">📡 信号流</div>')
        
        # 模拟信号（实际应从策略输出获取）
        signals = [
            {"type": "topic_emerge", "message": "新主题出现: AI算力", "time": "10:23:15", "color": "#10b981"},
            {"type": "high_attention", "message": "高注意力事件: 英伟达涨10%", "time": "10:20:33", "color": "#ef4444"},
            {"type": "topic_grow", "message": "主题快速增长: 量化交易", "time": "10:15:22", "color": "#3b82f6"},
        ]
        
        for signal in signals:
            put_html(f"""
            <div class="signal-item" style="border-left-color: {signal['color']};">
                <span class="signal-time">{signal['time']}</span>
                <span class="signal-content">{signal['message']}</span>
            </div>
            """)
        
        put_html('</div>')
    
    def _render_thought_report(self):
        """渲染思想报告"""
        put_html('<div class="card">')
        put_html('<div class="card-header">🧠 思想报告</div>')
        
        report_text = self.radar.generate_thought_report()
        
        put_textarea(
            label="",
            name="thought_report",
            value=report_text,
            readonly=True,
            rows=20
        )
        
        put_html('</div>')
    
    def _refresh_data(self):
        """刷新数据"""
        run_js("location.reload()")
    
    def _generate_report(self):
        """生成报告"""
        report = self.radar.generate_thought_report()
        popup("思想雷达报告", put_text(report))
    
    def _clear_memory(self):
        """清空记忆"""
        # 清空当前雷达实例的记忆
        if hasattr(self.radar, 'short_term_memory'):
            self.radar.short_term_memory.clear()
        if hasattr(self.radar, 'topics'):
            self.radar.topics.clear()
        if hasattr(self.radar, 'attention_scorer'):
            self.radar.attention_scorer = AttentionScorer()
        toast("记忆已清空", color="success")
        run_js("setTimeout(function() { location.reload(); }, 1000)")
    
    def _test_event(self):
        """测试事件"""
        # 模拟一个测试事件
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
