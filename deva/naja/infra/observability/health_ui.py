"""统一系统健康监控 UI

将系统健康、性能监控、循环审计、调优监控等功能整合到一个统一的页面中。
"""

from typing import Dict, Any
from .health import get_health_check_manager, HealthStatus
from .system_monitor_ui import render_monitor_panel
from .performance_ui import render_performance_page
from .loop_audit_ui import render_loop_audit_page


def _render_health_check_panel(ctx: dict):
    """渲染健康检查面板"""
    try:
        manager = get_health_check_manager()
        overall = manager.get_overall_status()
        reports = manager.check_all()
        
        status_icon = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.DEGRADED: "⚠️",
            HealthStatus.UNHEALTHY: "❌",
            HealthStatus.UNKNOWN: "❓"
        }.get(overall.status, "❓")
        
        status_color = {
            HealthStatus.HEALTHY: "#16a34a",
            HealthStatus.DEGRADED: "#f59e0b",
            HealthStatus.UNHEALTHY: "#dc2626",
            HealthStatus.UNKNOWN: "#64748b"
        }.get(overall.status, "#64748b")
        
        ctx["put_html"](f"""
        <div style="margin: 24px 0;">
            <h2 style="font-size: 20px; font-weight: 700; color: #1e293b; margin-bottom: 16px;">
                🩺 健康检查中心
            </h2>
        </div>
        """)
        
        # 总体状态卡片
        ctx["put_html"](f"""
        <div style="padding: 20px; border-radius: 12px; background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); border: 1px solid #cbd5e1; margin-bottom: 24px;">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                <span style="font-size: 24px;">{status_icon}</span>
                <div>
                    <div style="font-size: 16px; font-weight: 600; color: {status_color};">{overall.status.value.upper()}</div>
                    <div style="font-size: 13px; color: #64748b;">{overall.message}</div>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px;">
                <div style="text-align: center; padding: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #16a34a;">{overall.details.get('healthy', 0)}</div>
                    <div style="font-size: 11px; color: #64748b;">健康</div>
                </div>
                <div style="text-align: center; padding: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #f59e0b;">{overall.details.get('degraded', 0)}</div>
                    <div style="font-size: 11px; color: #64748b;">降级</div>
                </div>
                <div style="text-align: center; padding: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #dc2626;">{overall.details.get('unhealthy', 0)}</div>
                    <div style="font-size: 11px; color: #64748b;">不健康</div>
                </div>
                <div style="text-align: center; padding: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #3b82f6;">{overall.details.get('total', 0)}</div>
                    <div style="font-size: 11px; color: #64748b;">总组件</div>
                </div>
            </div>
        </div>
        """)
        
        # 组件健康状态列表
        if reports:
            ctx["put_html"]("""
            <div style="margin-bottom: 24px;">
                <h3 style="font-size: 16px; font-weight: 600; color: #374151; margin-bottom: 12px;">组件健康状态</h3>
            </div>
            """)
            
            rows = []
            for component, report in reports.items():
                icon = status_icon = {
                    HealthStatus.HEALTHY: "✅",
                    HealthStatus.DEGRADED: "⚠️",
                    HealthStatus.UNHEALTHY: "❌",
                    HealthStatus.UNKNOWN: "❓"
                }.get(report.status, "❓")
                
                color = status_color = {
                    HealthStatus.HEALTHY: "#16a34a",
                    HealthStatus.DEGRADED: "#f59e0b",
                    HealthStatus.UNHEALTHY: "#dc2626",
                    HealthStatus.UNKNOWN: "#64748b"
                }.get(report.status, "#64748b")
                
                row = f"""
                <div style="display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid #f3f4f6; gap: 12px;">
                    <div style="font-size: 18px;">{icon}</div>
                    <div style="flex: 1;">
                        <div style="font-weight: 600; color: #1f2937;">{component}</div>
                        <div style="font-size: 12px; color: #64748b; margin-top: 2px;">{report.message}</div>
                    </div>
                    <div style="font-size: 13px; font-weight: 600; color: {color};">{report.status.value}</div>
                </div>
                """
                rows.append(row)
            
            ctx["put_html"](f"""
            <div style="border-radius: 12px; border: 1px solid #e5e7eb; overflow: hidden;">
                <div style="padding: 12px 16px; background: #f9fafb; border-bottom: 1px solid #e5e7eb;">
                    <span style="font-weight: 600; color: #374151;">组件状态</span>
                </div>
                <div style="max-height: 300px; overflow-y: auto;">
                    {''.join(rows)}
                </div>
            </div>
            """)
    except Exception as e:
        ctx["put_html"](f"""
        <div style="padding: 20px; border-radius: 12px; background: #fef2f2; border: 1px solid #fecaca; margin-bottom: 24px;">
            <div style="color: #dc2626; font-size: 14px;">⚠️ 健康检查加载失败: {str(e)[:100]}</div>
        </div>
        """)


async def render_health_dashboard(ctx: dict):
    """渲染统一健康监控仪表盘"""
    await ctx["init_naja_ui"]("系统健康")
    
    # 顶部导航标签
    ctx["put_html"]("""
    <div style="margin-bottom: 24px;">
        <div style="display: flex; gap: 4px; background: #f1f5f9; padding: 4px; border-radius: 8px;">
            <button onclick="showTab('overview', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #ffffff; font-weight: 600; color: #374151; cursor: pointer;">总览</button>
            <button onclick="showTab('system', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #f1f5f9; color: #64748b; cursor: pointer;">系统监控</button>
            <button onclick="showTab('performance', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #f1f5f9; color: #64748b; cursor: pointer;">性能监控</button>
            <button onclick="showTab('loop', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #f1f5f9; color: #64748b; cursor: pointer;">循环审计</button>
            <button onclick="showTab('tuning', event)" style="flex: 1; padding: 8px 16px; border: none; border-radius: 6px; background: #f1f5f9; color: #64748b; cursor: pointer;">调优监控</button>
        </div>
    </div>
    
    <div id="tab-content">
        <div id="overview" style="display: block;">
    """)
    
    # 总览标签内容
    _render_health_check_panel(ctx)
    
    # 系统健康摘要（从原 system_page 复制）
    from datetime import datetime as _dt
    from deva.naja.strategy.result_store import get_result_store
    from deva.naja.market_hotspot.integration import get_market_hotspot_integration
    from deva.naja.application.container import get_last_boot_report
    
    def _format_ts(ts: float) -> str:
        if not ts:
            return "未写入"
        return _dt.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    
    def _status_color(level: str) -> str:
        if level == "critical":
            return "#dc2626"
        if level == "warning":
            return "#f59e0b"
        return "#16a34a"
    
    def _status_label(level: str) -> str:
        if level == "critical":
            return "严重"
        if level == "warning":
            return "告警"
        return "正常"
    
    def _get_write_level(seconds_since_write) -> str:
        if seconds_since_write is None:
            return "warning"
        if seconds_since_write > 900:
            return "critical"
        if seconds_since_write > 300:
            return "warning"
        return "ok"
    
    result_store = get_result_store()
    health = result_store.get_health_summary()
    
    last_write_time = health.get("last_write_time", 0) or 0
    seconds_since_write = health.get("seconds_since_write")
    write_level = _get_write_level(seconds_since_write)
    write_color = _status_color(write_level)
    
    attention_report = {"status": "not_initialized"}
    try:
        attention_report = get_market_hotspot_integration().get_hotspot_report()
    except Exception:
        pass
    
    status_badge = f"<span style='padding:2px 8px;border-radius:10px;background:{write_color};color:#fff;font-size:12px;'>{_status_label(write_level)}</span>"
    seconds_text = f"{seconds_since_write:.0f}s" if seconds_since_write is not None else "未写入"
    
    ctx["put_html"](f"""
    <div style="margin: 10px 0 16px 0; padding: 14px; border-radius: 12px; background: #0f172a; color: #e2e8f0;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="width: 10px; height: 10px; border-radius: 50%; background: {write_color};"></div>
            <div style="font-size: 15px; font-weight: 600;">系统健康摘要</div>
        </div>
        <div style="margin-top: 10px; font-size: 12px; color: #94a3b8;">
            阈值说明：绿色 ≤ 300s，橙色 300-900s，红色 &gt; 900s
        </div>
    </div>
    """)
    
    ctx["put_html"](f"""
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:14px;">
        <div style="padding:12px;border-radius:10px;background:#111827;">
            <div style="font-size:12px;color:#94a3b8;">结果存储</div>
            <div style="margin-top:6px;font-size:14px;">状态: {status_badge}</div>
            <div style="margin-top:6px;font-size:12px;color:#9ca3af;">最近写入: {_format_ts(last_write_time)}</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">间隔: {seconds_text}</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">队列: {health.get('write_queue_size', 0)} | 失败: {health.get('failed_writes', 0)}</div>
        </div>
        <div style="padding:12px;border-radius:10px;background:#111827;">
            <div style="font-size:12px;color:#94a3b8;">注意力系统</div>
            <div style="margin-top:6px;font-size:14px;">状态: {attention_report.get('status', 'unknown')}</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">快照: {attention_report.get('processed_snapshots', 0)}</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">全局注意力: {attention_report.get('global_attention', 0):.3f}</div>
        </div>
    </div>
    """)
    
    boot_report = get_last_boot_report()
    if boot_report:
        ctx["put_markdown"]("### 系统启动报告")
        summary_rows = [
            ["启动成功", "是" if boot_report.get("success") else "否"],
            ["阶段", boot_report.get("stage", "unknown")],
            ["耗时(ms)", f"{boot_report.get('duration_ms', 0):.1f}"],
            ["消息", boot_report.get("message", "")],
        ]
        ctx["put_table"](summary_rows)
    
    ctx["put_html"]("""
        </div>
        <div id="system" style="display: none;">
    """)
    
    # 系统监控标签内容
    ctx["put_html"](render_monitor_panel())
    
    ctx["put_html"]("""
        </div>
        <div id="performance" style="display: none;">
    """)
    
    # 性能监控标签内容
    await render_performance_page(ctx)
    
    ctx["put_html"]("""
        </div>
        <div id="loop" style="display: none;">
    """)
    
    # 循环审计标签内容
    await render_loop_audit_page(ctx)
    
    ctx["put_html"]("""
        </div>
        <div id="tuning" style="display: none;">
    """)
    
    # 调优监控标签内容
    try:
        from deva.naja.attention.ui.auto_tuning_monitor import (
            render_tuning_monitor_panel,
            render_frequency_monitor_panel,
            render_datasource_tuning_panel,
        )
        ctx["put_html"](render_tuning_monitor_panel())
        ctx["put_html"](render_frequency_monitor_panel())
        ctx["put_html"](render_datasource_tuning_panel())
    except Exception as e:
        ctx["put_html"](f"""
        <div style="padding: 20px; border-radius: 12px; background: #fef2f2; border: 1px solid #fecaca; margin: 24px;">
            <div style="color: #dc2626; font-size: 14px;">⚠️ 调优监控加载失败: {str(e)[:100]}</div>
        </div>
        """)
    
    ctx["put_html"]("""
        </div>
    </div>
    
    <script>
        function showTab(tabId, event) {
            // 隐藏所有标签内容
            document.querySelectorAll('#tab-content > div').forEach(div => {
                div.style.display = 'none';
            });
            
            // 显示选中的标签内容
            document.getElementById(tabId).style.display = 'block';
            
            // 更新按钮样式
            document.querySelectorAll('button').forEach(btn => {
                btn.style.background = '#f1f5f9';
                btn.style.color = '#64748b';
            });
            
            // 设置当前按钮样式
            if (event && event.target) {
                event.target.style.background = '#ffffff';
                event.target.style.color = '#374151';
            }
        }
    </script>
    """)


async def health_dashboard_page():
    """健康监控仪表盘页面"""
    from deva.naja.web_ui.ui_base import _ctx
    ctx = _ctx()
    await render_health_dashboard(ctx)
