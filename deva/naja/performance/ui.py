"""性能监控 Tab 页面

集成到 Naja 首页的独立性能监控标签页
"""

from pywebio.output import *
from pywebio.input import *
from pywebio.pin import *
from pywebio.session import run_js, set_env
import json
from datetime import datetime

from ..performance.performance_monitor import (
    get_performance_monitor,
    ComponentType,
    SeverityLevel,
)


def create_nav_menu():
    """创建导航菜单 - 使用统一模块"""
    from ..common.ui_theme import get_nav_menu_js
    js_code = get_nav_menu_js()
    run_js(js_code)


def apply_global_styles():
    """应用全局样式 - 使用统一模块"""
    from ..common.ui_theme import get_global_styles
    put_html(get_global_styles())


class PerformanceMonitorUI:
    """性能监控 UI"""
    
    def __init__(self):
        self.monitor = get_performance_monitor()
        self.current_filter = "all"
    
    def render(self):
        """渲染主页面"""
        set_env(title="Naja - 性能监控", output_animation=False)
        apply_global_styles()
        create_nav_menu()
        
        put_html('<div class="container">')
        
        put_html("""
        <div style="margin-bottom: 24px;">
            <h1 style="font-size: 28px; font-weight: 700; color: #1e293b; margin-bottom: 8px;">
                📊 性能监控中心
            </h1>
            <p style="color: #64748b; font-size: 14px;">
                实时监控系统各组件性能表现，识别性能瓶颈
            </p>
        </div>
        """)
        
        self._render_overview()
        self._render_filters()
        self._render_slow_components()
        self._render_component_details()
        
        put_html('</div>')
    
    def _render_overview(self):
        """渲染概览统计"""
        report = self.monitor.get_full_report()
        summary = report.get("summary", {})
        slow_summary = self.monitor.get_slow_components_summary()
        
        put_html('<div class="card">')
        put_html('<div class="card-header">📈 性能概览</div>')
        
        cols = []
        
        total = summary.get("total_components", 0)
        cols.append(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: #3b82f6;">{total}</div>
            <div class="metric-label">监控组件</div>
        </div>
        """)
        
        severe = slow_summary.get("severe_count", 0)
        severe_color = "#dc2626" if severe > 0 else "#059669"
        cols.append(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: {severe_color};">{severe}</div>
            <div class="metric-label">严重问题</div>
        </div>
        """)
        
        critical = slow_summary.get("critical_count", 0)
        critical_color = "#d97706" if critical > 0 else "#059669"
        cols.append(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: {critical_color};">{critical}</div>
            <div class="metric-label">较重问题</div>
        </div>
        """)
        
        warning = slow_summary.get("warning_count", 0)
        warning_color = "#2563eb" if warning > 0 else "#059669"
        cols.append(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: {warning_color};">{warning}</div>
            <div class="metric-label">警告</div>
        </div>
        """)
        
        put_html(f"""
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
            {''.join(cols)}
        </div>
        """)
        
        put_html('</div>')
    
    def _render_filters(self):
        """渲染过滤器"""
        put_html("""
        <div class="filter-tabs">
            <button class="filter-tab active" onclick="filterComponents('all')">全部</button>
            <button class="filter-tab" onclick="filterComponents('strategy')">📊 策略</button>
            <button class="filter-tab" onclick="filterComponents('task')">⏰ 任务</button>
            <button class="filter-tab" onclick="filterComponents('datasource')">📡 数据源</button>
            <button class="filter-tab" onclick="filterComponents('storage')">💾 存储</button>
            <button class="filter-tab" onclick="filterComponents('web_request')">🌐 Web请求</button>
            <button class="filter-tab" onclick="filterComponents('lock_wait')">🔒 锁等待</button>
        </div>
        <script>
            function filterComponents(type) {
                document.querySelectorAll('.filter-tab').forEach(tab => tab.classList.remove('active'));
                event.target.classList.add('active');
            }
        </script>
        """)
    
    def _render_slow_components(self):
        """渲染慢组件列表"""
        reports = self.monitor.generate_performance_reports()
        
        put_html('<div class="card">')
        put_html('<div class="card-header">⚠️ 性能问题组件</div>')
        
        if not reports:
            put_html("""
            <div style="text-align: center; padding: 40px; color: #64748b;">
                <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
                <div style="font-size: 16px;">未发现性能问题</div>
                <div style="font-size: 13px; margin-top: 8px;">所有组件运行正常</div>
            </div>
            """)
        else:
            for report in reports[:20]:
                self._render_component_row(report)
        
        put_html('</div>')
    
    def _render_component_row(self, report):
        """渲染组件行"""
        severity_class = f"severity-{report.severity.value}"
        severity_text = {
            "severe": "严重",
            "critical": "较重",
            "warning": "警告",
            "normal": "正常",
        }.get(report.severity.value, report.severity.value)
        
        type_icons = {
            "strategy": "📊",
            "task": "⏰",
            "datasource": "📡",
            "storage": "💾",
            "web_request": "🌐",
            "lock_wait": "🔒",
        }
        type_icon = type_icons.get(report.component_type.value, "📦")
        
        type_colors = {
            "strategy": "#3b82f6",
            "task": "#f59e0b",
            "datasource": "#8b5cf6",
            "storage": "#10b981",
            "web_request": "#06b6d4",
            "lock_wait": "#ef4444",
        }
        type_color = type_colors.get(report.component_type.value, "#64748b")
        
        put_html(f"""
        <div class="component-row">
            <div class="component-icon" style="background: {type_color}20; color: {type_color};">
                {type_icon}
            </div>
            <div class="component-info">
                <div class="component-name">{report.component_name}</div>
                <div class="component-meta">
                    ID: {report.component_id} | 类型: {report.component_type.value}
                </div>
            </div>
            <div class="component-metrics">
                <div class="component-time" style="color: {'#dc2626' if report.avg_time_ms > 500 else '#d97706' if report.avg_time_ms > 100 else '#059669'};">
                    {report.avg_time_ms:.1f}ms
                </div>
                <div class="component-calls">max: {report.max_time_ms:.1f}ms</div>
            </div>
            <div>
                <span class="severity-badge {severity_class}">{severity_text}</span>
            </div>
        </div>
        """)
        
        if report.recommendation:
            put_html(f"""
            <div style="padding: 0 16px 12px 72px;">
                <div class="recommendation-box">
                    💡 {report.recommendation}
                </div>
            </div>
            """)
    
    def _render_component_details(self):
        """渲染各组件详细性能"""
        report = self.monitor.get_full_report()
        by_type = report.get("by_type", {})
        
        type_names = {
            "strategy": ("📊 策略性能", "#3b82f6"),
            "task": ("⏰ 任务性能", "#f59e0b"),
            "datasource": ("📡 数据源性能", "#8b5cf6"),
            "storage": ("💾 存储性能", "#10b981"),
            "web_request": ("🌐 Web请求性能", "#06b6d4"),
            "lock_wait": ("🔒 锁等待性能", "#ef4444"),
        }
        
        for type_key, metrics_list in by_type.items():
            if not metrics_list:
                continue
            
            title, color = type_names.get(type_key, (f"📦 {type_key}", "#64748b"))
            
            put_html(f'<div class="card">')
            put_html(f'<div class="card-header" style="border-left: 4px solid {color}; padding-left: 12px;">{title}</div>')
            
            sorted_metrics = sorted(metrics_list, key=lambda x: x.get("avg_execution_time_ms", 0), reverse=True)
            
            put_html("""
            <table>
                <thead>
                    <tr>
                        <th>组件名称</th>
                        <th>平均时间</th>
                        <th>最大时间</th>
                        <th>调用次数</th>
                        <th>错误率</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody>
            """)
            
            for m in sorted_metrics[:10]:
                name = m.get("component_name", "Unknown")
                avg_time = m.get("avg_execution_time_ms", 0)
                max_time = m.get("max_execution_time_ms", 0)
                calls = m.get("call_count", 0)
                error_rate = m.get("error_rate", 0)
                
                if avg_time > 1000 or error_rate > 10:
                    status = '<span class="severity-badge severity-severe">严重</span>'
                elif avg_time > 500 or error_rate > 5:
                    status = '<span class="severity-badge severity-critical">较重</span>'
                elif avg_time > 100:
                    status = '<span class="severity-badge severity-warning">警告</span>'
                else:
                    status = '<span class="severity-badge severity-normal">正常</span>'
                
                put_html(f"""
                <tr>
                    <td>{name}</td>
                    <td>{avg_time:.2f}ms</td>
                    <td>{max_time:.2f}ms</td>
                    <td>{calls}</td>
                    <td>{error_rate:.1f}%</td>
                    <td>{status}</td>
                </tr>
                """)
            
            put_html("""
                </tbody>
            </table>
            """)
            
            put_html('</div>')


def main():
    """主入口"""
    ui = PerformanceMonitorUI()
    ui.render()


if __name__ == "__main__":
    main()
