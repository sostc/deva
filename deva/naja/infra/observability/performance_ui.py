"""Naja 性能监控 UI

提供统一的性能监控界面，展示系统各组件的性能表现。
"""

from datetime import datetime
from typing import Dict, List, Any

from .performance_monitor import (
    get_performance_monitor,
    ComponentType,
    SeverityLevel,
    PerformanceReport,
)


TYPE_INFO = {
    ComponentType.STRATEGY: ("📊 策略", "#3b82f6", "策略执行相关组件"),
    ComponentType.TASK: ("⏰ 任务", "#f59e0b", "定时任务执行组件"),
    ComponentType.DATASOURCE: ("📡 数据源", "#8b5cf6", "数据获取处理组件"),
    ComponentType.STORAGE: ("💾 存储", "#10b981", "数据存储操作组件"),
    ComponentType.WEB_REQUEST: ("🌐 Web请求", "#06b6d4", "HTTP 请求处理组件"),
    ComponentType.LOCK_WAIT: ("🔒 锁等待", "#ef4444", "锁竞争等待组件"),
    ComponentType.THREAD_POOL: ("🧵 线程池", "#64748b", "线程池调度组件"),
}


SEVERITY_INFO = {
    SeverityLevel.NORMAL: ("正常", "#059669", "#dcfce7"),
    SeverityLevel.WARNING: ("警告", "#d97706", "#fef3c7"),
    SeverityLevel.CRITICAL: ("严重", "#dc2626", "#fee2e2"),
    SeverityLevel.SEVERE: ("极重", "#991b1b", "#fecaca"),
}


def _render_severity_badge(severity: SeverityLevel) -> str:
    text, color, bg = SEVERITY_INFO.get(severity, SEVERITY_INFO[SeverityLevel.NORMAL])
    return f'<span style="padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;color:{color};background:{bg};">{text}</span>'


async def render_performance_page(ctx: dict):
    """渲染性能监控页面"""
    monitor = get_performance_monitor()
    full_report = monitor.get_full_report()
    slow_summary = monitor.get_slow_components_summary()
    summary = full_report.get("summary", {})
    by_type = full_report.get("by_type", {})
    reports = monitor.generate_performance_reports()

    ctx["put_html"]("""
    <div style="margin: 24px 0;">
        <h2 style="font-size: 20px; font-weight: 700; color: #1e293b; margin-bottom: 16px;">
            📊 性能监控中心
        </h2>
    </div>
    """)

    _render_overview_cards(ctx, summary, slow_summary)
    _render_problem_leaderboard(ctx, reports)
    _render_type_overview(ctx, by_type)
    _render_detailed_metrics(ctx, by_type)


def _render_overview_cards(ctx: dict, summary: dict, slow_summary: dict):
    """渲染概览卡片"""
    total = summary.get("total_components", 0)
    slow_count = slow_summary.get("total_slow", 0)
    severe = slow_summary.get("severe_count", 0)
    critical = slow_summary.get("critical_count", 0)
    warning = slow_summary.get("warning_count", 0)

    thresholds = get_performance_monitor()._thresholds

    cards_html = f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px;">
        <div style="padding: 16px; border-radius: 12px; background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border: 1px solid #bfdbfe;">
            <div style="font-size: 28px; font-weight: 700; color: #1d4ed8;">{total}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">监控组件</div>
        </div>
        <div style="padding: 16px; border-radius: 12px; background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border: 1px solid #fecaca;">
            <div style="font-size: 28px; font-weight: 700; color: #dc2626;">{slow_count}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">性能问题</div>
        </div>
        <div style="padding: 16px; border-radius: 12px; background: linear-gradient(135deg, #fecaca 0%, #fee2e2 100%); border: 1px solid #f87171;">
            <div style="font-size: 28px; font-weight: 700; color: #991b1b;">{severe + critical}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">严重/极重</div>
        </div>
        <div style="padding: 16px; border-radius: 12px; background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 1px solid #fcd34d;">
            <div style="font-size: 28px; font-weight: 700; color: #92400e;">{warning}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">警告</div>
        </div>
    </div>
    <div style="padding: 12px 16px; border-radius: 8px; background: #f8fafc; border: 1px solid #e2e8f0; margin-bottom: 24px;">
        <span style="font-size: 12px; color: #64748b;">告警阈值：</span>
        <span style="font-size: 12px; color: #059669; font-weight: 600;">警告 {thresholds.get('warning', 100)}ms</span>
        <span style="font-size: 12px; color: #94a3b8; margin: 0 8px;">|</span>
        <span style="font-size: 12px; color: #d97706; font-weight: 600;">严重 {thresholds.get('critical', 500)}ms</span>
        <span style="font-size: 12px; color: #94a3b8; margin: 0 8px;">|</span>
        <span style="font-size: 12px; color: #dc2626; font-weight: 600;">极重 {thresholds.get('severe', 1000)}ms</span>
    </div>
    """
    ctx["put_html"](cards_html)


def _render_problem_leaderboard(ctx: dict, reports: List[PerformanceReport]):
    """渲染性能问题排行榜 - 按严重程度排序，一目了然"""
    if not reports:
        ctx["put_html"]("""
        <div style="margin-bottom: 24px; padding: 32px; text-align: center; background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border-radius: 12px; border: 1px solid #86efac;">
            <div style="font-size: 48px; margin-bottom: 8px;">✅</div>
            <div style="font-size: 16px; font-weight: 600; color: #166534;">系统运行良好</div>
            <div style="font-size: 13px; color: #15803d; margin-top: 4px;">暂无性能问题</div>
        </div>
        """)
        return

    rows = []
    for i, report in enumerate(reports):
        severity_text, severity_color, severity_bg = SEVERITY_INFO.get(report.severity, SEVERITY_INFO[SeverityLevel.NORMAL])
        type_icon, type_color, _ = TYPE_INFO.get(report.component_type, ("📦", "#64748b", ""))

        rank_badge = ""
        if i == 0:
            rank_badge = '<span style="background:#dc2626;color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;margin-right:8px;">🔴 TOP1</span>'
        elif i == 1:
            rank_badge = '<span style="background:#d97706;color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;margin-right:8px;">🟠 TOP2</span>'
        elif i == 2:
            rank_badge = '<span style="background:#ca8a04;color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;margin-right:8px;">🟡 TOP3</span>'
        else:
            rank_badge = f'<span style="background:#e5e7eb;color:#6b7280;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;margin-right:8px;">#{i+1}</span>'

        row = f"""
        <div style="display: flex; align-items: center; padding: 14px 16px; border-bottom: 1px solid #f3f4f6; gap: 12px;">
            <div style="min-width: 60px;">{rank_badge}</div>
            <div style="min-width: 32px; font-size: 18px;">{type_icon}</div>
            <div style="flex: 1; min-width: 0;">
                <div style="font-weight: 600; color: #1f2937; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{report.component_name}</div>
                <div style="font-size: 11px; color: #9ca3af; margin-top: 2px;">{report.component_id}</div>
            </div>
            <div style="display: flex; gap: 16px; align-items: center;">
                <div style="text-align: right;">
                    <div style="font-size: 13px; font-weight: 600; color: #dc2626;">{report.avg_time_ms:.1f}ms</div>
                    <div style="font-size: 10px; color: #9ca3af;">平均</div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 13px; font-weight: 600; color: #991b1b;">{report.max_time_ms:.1f}ms</div>
                    <div style="font-size: 10px; color: #9ca3af;">最大</div>
                </div>
                <div style="min-width: 70px; text-align: center;">
                    <span style="padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; color: {severity_color}; background: {severity_bg};">{severity_text}</span>
                </div>
            </div>
        </div>
        """
        rows.append(row)

    leaderboard_html = f"""
    <div style="margin-bottom: 24px; border-radius: 12px; border: 1px solid #e5e7eb; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        <div style="padding: 14px 16px; background: linear-gradient(135deg, #1f2937 0%, #374151 100%); display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 18px;">🚨</span>
            <span style="font-size: 15px; font-weight: 700; color: #ffffff;">性能问题排行榜</span>
            <span style="margin-left: auto; font-size: 12px; color: #9ca3af;">共 {len(reports)} 个问题，按严重程度排序</span>
        </div>
        <div style="max-height: 400px; overflow-y: auto;">
            {''.join(rows)}
        </div>
    </div>
    """
    ctx["put_html"](leaderboard_html)


def _render_type_overview(ctx: dict, by_type: dict):
    """渲染各类型组件概览"""
    ctx["put_html"]("""
    <div style="margin-bottom: 24px;">
        <h3 style="font-size: 16px; font-weight: 600; color: #374151; margin-bottom: 12px;">组件类型分布</h3>
    </div>
    """)

    if not by_type:
        ctx["put_html"]("""
        <div style="padding: 32px; text-align: center; color: #64748b; background: #f8fafc; border-radius: 12px; border: 1px solid #e2e8f0;">
            <div style="font-size: 32px; margin-bottom: 8px;">📭</div>
            <div style="font-size: 14px;">暂无性能数据</div>
            <div style="font-size: 12px; margin-top: 4px; color: #94a3b8;">系统正在收集各组件的性能指标...</div>
        </div>
        """)
        return

    cards = []
    for comp_type, info in TYPE_INFO.items():
        type_key = comp_type.value
        metrics_list = by_type.get(type_key, [])
        count = len(metrics_list)

        icon, color, desc = info
        if count > 0:
            avg_times = [m.get("avg_execution_time_ms", 0) for m in metrics_list]
            max_avg = max(avg_times) if avg_times else 0
            status_color = "#dc2626" if max_avg >= 500 else "#d97706" if max_avg >= 100 else "#059669"
        else:
            status_color = "#94a3b8"

        card = f"""
        <div style="padding: 16px; border-radius: 10px; background: #ffffff; border: 1px solid #e5e7eb; position: relative; overflow: hidden;">
            <div style="position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: {color};"></div>
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                <span style="font-size: 20px;">{icon}</span>
                <span style="font-size: 14px; font-weight: 600; color: #1f2937;">{desc}</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 24px; font-weight: 700; color: {status_color};">{count}</span>
                    <span style="font-size: 12px; color: #6b7280; margin-left: 4px;">个组件</span>
                </div>
            </div>
        </div>
        """
        cards.append(card)

    ctx["put_html"](f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 32px;">
        {''.join(cards)}
    </div>
    """)


def _render_detailed_metrics(ctx: dict, by_type: dict):
    """渲染详细指标"""
    ctx["put_html"]("""
    <div style="margin-bottom: 16px;">
        <h3 style="font-size: 16px; font-weight: 600; color: #374151; margin-bottom: 4px;">详细性能指标</h3>
        <p style="font-size: 12px; color: #6b7280;">按组件类型分组展示所有监控组件的性能数据</p>
    </div>
    """)

    if not by_type:
        return

    for comp_type, info in TYPE_INFO.items():
        type_key = comp_type.value
        metrics_list = by_type.get(type_key, [])

        if not metrics_list:
            continue

        icon, color, desc = info
        sorted_metrics = sorted(metrics_list, key=lambda x: x.get("avg_execution_time_ms", 0), reverse=True)

        table_rows = []
        for m in sorted_metrics:
            name = m.get("component_name", "Unknown")
            comp_id = m.get("component_id", "")
            avg_time = m.get("avg_execution_time_ms", 0)
            max_time = m.get("max_execution_time_ms", 0)
            p95_time = m.get("p95_execution_time_ms", 0)
            calls = m.get("call_count", 0)
            error_rate = m.get("error_rate", 0)
            last_call = m.get("last_call_time", "")

            avg_color = "#dc2626" if avg_time >= 500 else "#d97706" if avg_time >= 100 else "#059669"
            error_display = f'<span style="color:#dc2626;">{error_rate:.1f}%</span>' if error_rate > 5 else f'{error_rate:.1f}%'

            row = f"""
            <tr style="border-bottom: 1px solid #f3f4f6;">
                <td style="padding: 12px 8px;">
                    <div style="font-weight: 500; color: #1f2937;">{name}</div>
                    <div style="font-size: 11px; color: #9ca3af; margin-top: 2px;">{comp_id}</div>
                </td>
                <td style="padding: 12px 8px; text-align: center;">
                    <span style="font-weight: 600; color: {avg_color};">{avg_time:.1f}ms</span>
                </td>
                <td style="padding: 12px 8px; text-align: center; color: #64748b;">{max_time:.1f}ms</td>
                <td style="padding: 12px 8px; text-align: center; color: #64748b;">{p95_time:.1f}ms</td>
                <td style="padding: 12px 8px; text-align: center; color: #64748b;">{calls}</td>
                <td style="padding: 12px 8px; text-align: center;">{error_display}</td>
                <td style="padding: 12px 8px; text-align: center; color: #9ca3af; font-size: 11px;">{last_call[:19] if last_call else '-'}</td>
            </tr>
            """
            table_rows.append(row)

        section = f"""
        <div style="margin-bottom: 24px; border-radius: 12px; border: 1px solid #e5e7eb; overflow: hidden;">
            <div style="padding: 12px 16px; background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%); border-bottom: 1px solid #e5e7eb; display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">{icon}</span>
                <span style="font-weight: 600; color: #1f2937;">{desc}</span>
                <span style="margin-left: auto; font-size: 12px; color: #6b7280;">{len(sorted_metrics)} 个组件</span>
            </div>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead>
                        <tr style="background: #f9fafb;">
                            <th style="padding: 10px 8px; text-align: left; font-weight: 600; color: #6b7280; font-size: 11px; text-transform: uppercase;">组件</th>
                            <th style="padding: 10px 8px; text-align: center; font-weight: 600; color: #6b7280; font-size: 11px; text-transform: uppercase;">平均</th>
                            <th style="padding: 10px 8px; text-align: center; font-weight: 600; color: #6b7280; font-size: 11px; text-transform: uppercase;">最大</th>
                            <th style="padding: 10px 8px; text-align: center; font-weight: 600; color: #6b7280; font-size: 11px; text-transform: uppercase;">P95</th>
                            <th style="padding: 10px 8px; text-align: center; font-weight: 600; color: #6b7280; font-size: 11px; text-transform: uppercase;">调用</th>
                            <th style="padding: 10px 8px; text-align: center; font-weight: 600; color: #6b7280; font-size: 11px; text-transform: uppercase;">错误率</th>
                            <th style="padding: 10px 8px; text-align: center; font-weight: 600; color: #6b7280; font-size: 11px; text-transform: uppercase;">最后调用</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(table_rows)}
                    </tbody>
                </table>
            </div>
        </div>
        """
        ctx["put_html"](section)

    ctx["put_html"]("""
    <div style="margin-top: 32px; padding: 16px; background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0;">
        <div style="font-size: 12px; color: #6b7280;">
            <strong>说明：</strong>
            性能数据由 NajaPerformanceMonitor 统一收集，采样周期内的慢组件（平均响应时间超过阈值）会自动生成告警。
            可以通过 <code style="background: #e5e7eb; padding: 1px 4px; border-radius: 3px;">register_alert_callback()</code> 注册自定义告警处理函数。
        </div>
    </div>
    """)


class PerformanceMonitorUI:
    """兼容性包装类"""

    def __init__(self):
        self.monitor = get_performance_monitor()

    def render(self):
        pass
