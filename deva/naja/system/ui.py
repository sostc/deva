"""Naja 系统页面 UI"""

from __future__ import annotations

from datetime import datetime


def _format_ts(ts: float) -> str:
    if not ts:
        return "未写入"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


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


def _get_write_level(seconds_since_write: float | None) -> str:
    if seconds_since_write is None:
        return "warning"
    if seconds_since_write > 900:
        return "critical"
    if seconds_since_write > 300:
        return "warning"
    return "ok"


async def render_system_page(ctx: dict):
    """渲染系统页面"""
    from ..strategy.result_store import get_result_store
    from ..market_hotspot.integration import get_market_hotspot_integration
    from ..bootstrap import get_last_boot_report

    await ctx["init_naja_ui"]("系统")

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

    alert = result_store.should_alert_no_writes(stale_seconds=300, cooldown_seconds=300)
    if alert.get("should_alert"):
        gap = alert.get("seconds_since_write")
        msg = f"ResultStore 超过 {int(gap)} 秒未写入，雷达/记忆可能无沉淀"
        try:
            ctx["toast"](msg, color="warn", duration=6)
        except Exception:
            pass
        try:
            from ..log_stream import log_strategy
            log_strategy("WARN", "system", "System", msg)
        except Exception:
            pass

    boot_report = get_last_boot_report()

    status_badge = f"<span style='padding:2px 8px;border-radius:10px;background:{write_color};color:#fff;font-size:12px;'>{_status_label(write_level)}</span>"
    seconds_text = f"{seconds_since_write:.0f}s" if seconds_since_write is not None else "未写入"

    ctx["put_html"](
    """<div style="margin: 10px 0 16px 0; padding: 14px; border-radius: 12px; background: #0f172a; color: #e2e8f0;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="width: 10px; height: 10px; border-radius: 50%; background: """ + write_color + """;"></div>
            <div style="font-size: 15px; font-weight: 600;">系统健康摘要</div>
        </div>
        <div style="margin-top: 10px; font-size: 12px; color: #94a3b8;">
            阈值说明：绿色 ≤ 300s，橙色 300-900s，红色 > 900s
        </div>
    </div>""")

    ctx["put_html"](
    """<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:14px;">
        <div style="padding:12px;border-radius:10px;background:#111827;">
            <div style="font-size:12px;color:#94a3b8;">结果存储</div>
            <div style="margin-top:6px;font-size:14px;">状态: """ + status_badge + """</div>
            <div style="margin-top:6px;font-size:12px;color:#9ca3af;">最近写入: """ + _format_ts(last_write_time) + """</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">间隔: """ + seconds_text + """</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">队列: """ + str(health.get("write_queue_size", 0)) + """ | 失败: """ + str(health.get("failed_writes", 0)) + """</div>
        </div>
        <div style="padding:12px;border-radius:10px;background:#111827;">
            <div style="font-size:12px;color:#94a3b8;">注意力系统</div>
            <div style="margin-top:6px;font-size:14px;">状态: """ + str(attention_report.get("status", "unknown")) + """</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">快照: """ + str(attention_report.get("processed_snapshots", 0)) + """</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">全局注意力: """ + f"{attention_report.get('global_attention', 0):.3f}" + """</div>
        </div>
    </div>""")

    ctx["put_html"](
    """<div style="margin-top: 10px; font-size: 12px; color: #94a3b8;">
        说明：结果存储长期无写入，通常意味着策略未运行或数据源无数据输入。
    </div>""")

    if boot_report:
        ctx["put_markdown"]("### 系统启动报告")
        summary_rows = [
            ["启动成功", "是" if boot_report.get("success") else "否"],
            ["阶段", boot_report.get("stage", "unknown")],
            ["耗时(ms)", f"{boot_report.get('duration_ms', 0):.1f}"],
            ["消息", boot_report.get("message", "")],
        ]
        ctx["put_table"](summary_rows)

        details = boot_report.get("details") or {}
        if details:
            ctx["put_markdown"]("#### 详细信息")
            ctx["put_code"](str(details))

    from ..performance.ui import render_performance_page
    await render_performance_page(ctx)

    from ..loop_audit.ui import render_loop_audit_page
    await render_loop_audit_page(ctx)