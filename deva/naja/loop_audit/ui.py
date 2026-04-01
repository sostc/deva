"""Naja 闭环状态审计 UI

提供闭环执行状态的实时监控界面。
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any

from deva import NB

LOOP_AUDIT_TABLE = "naja_loop_audit"
DB_PATH = None

try:
    from pathlib import Path
    DB_PATH = Path.home() / ".deva" / "nb.sqlite"
except:
    pass


LOOP_TYPE_INFO = {
    "dataflow": ("📦 数据流", "#3b82f6", "策略执行 → 分发下游"),
    "decision": ("🧠 决策", "#8b5cf6", "Attention → Manas → 反馈"),
    "bandit": ("🎰 Bandit", "#f59e0b", "策略选择 → 参数调节"),
    "alaya": ("✨ Alaya", "#10b981", "模式归档 → 跨市场迁移"),
    "global_market": ("🌍 全球市场", "#06b6d4", "市场扫描 → 流动性预测"),
    "senses": ("🔮 预感知", "#ec4899", "动量/情绪/资金流预兆"),
}


def _get_connection():
    import sqlite3
    if DB_PATH is None:
        return None
    return sqlite3.connect(str(DB_PATH))


def _get_stats(since_hours: int = 24) -> Dict[str, Any]:
    since = datetime.now() - timedelta(hours=since_hours)
    since_ts = since.timestamp()

    conn = _get_connection()
    if conn is None:
        return {}

    cur = conn.cursor()
    stats = {}

    try:
        cur.execute(f"""
            SELECT
                loop_type,
                COUNT(*) as total_count,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped,
                AVG(duration_ms) as avg_duration_ms,
                MAX(timestamp) as last_run
            FROM {LOOP_AUDIT_TABLE}
            WHERE timestamp >= ?
            GROUP BY loop_type
        """, (since_ts,))

        for row in cur.fetchall():
            loop_type, total, completed, failed, running, skipped, avg_dur, last_run = row
            stats[loop_type] = {
                "total": total or 0,
                "completed": completed or 0,
                "failed": failed or 0,
                "running": running or 0,
                "skipped": skipped or 0,
                "avg_duration_ms": avg_dur or 0,
                "last_run": last_run,
            }
    except Exception as e:
        pass

    conn.close()
    return stats


def _get_recent_records(limit: int = 20, since_hours: int = 24) -> List[Dict]:
    since = datetime.now() - timedelta(hours=since_hours)
    since_ts = since.timestamp()

    conn = _get_connection()
    if conn is None:
        return []

    cur = conn.cursor()
    records = []

    try:
        cur.execute(f"""
            SELECT * FROM {LOOP_AUDIT_TABLE}
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (since_ts, limit))

        columns = [desc[0] for desc in cur.description]
        for row in cur.fetchall():
            d = dict(zip(columns, row))
            records.append(d)
    except Exception:
        pass

    conn.close()
    return records


def _check_table_exists() -> bool:
    conn = _get_connection()
    if conn is None:
        return False

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (LOOP_AUDIT_TABLE,))
        exists = cur.fetchone() is not None
        conn.close()
        return exists
    except:
        conn.close()
        return False


def _format_duration(ms: float) -> str:
    if ms < 1:
        return f"{ms*1000:.0f}μs"
    elif ms < 1000:
        return f"{ms:.1f}ms"
    else:
        return f"{ms/1000:.1f}s"


def _format_time(ts: float) -> str:
    if ts is None:
        return "N/A"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


async def render_loop_audit_page(ctx: dict):
    """渲染闭环审计页面"""
    ctx["put_html"]("""
    <div style="margin: 24px 0;">
        <h2 style="font-size: 20px; font-weight: 700; color: #1e293b; margin-bottom: 16px;">
            🔄 闭环状态审计
        </h2>
        <p style="font-size: 13px; color: #64748b; margin-bottom: 16px;">
            追踪系统中各闭环的执行状态、数据流转路径和性能表现。
        </p>
    </div>
    """)

    if not _check_table_exists():
        ctx["put_html"]("""
        <div style="padding: 24px; border-radius: 12px; background: #f8fafc; border: 1px solid #e2e8f0; text-align: center;">
            <p style="color: #64748b; font-size: 14px;">审计系统正在初始化，请先启动 Naja 系统</p>
        </div>
        """)
        return

    stats = _get_stats(24)
    recent = _get_recent_records(30, 24)

    _render_overview_cards(ctx, stats)
    _render_loop_type_grid(ctx, stats)
    _render_recent_records(ctx, recent)


def _render_overview_cards(ctx: dict, stats: Dict):
    total_runs = sum(s.get("total", 0) for s in stats.values())
    total_failed = sum(s.get("failed", 0) for s in stats.values())
    total_completed = sum(s.get("completed", 0) for s in stats.values())
    active_loops = sum(s.get("running", 0) for s in stats.values())

    ctx["put_html"](f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 24px;">
        <div style="padding: 16px; border-radius: 12px; background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border: 1px solid #bfdbfe;">
            <div style="font-size: 28px; font-weight: 700; color: #1d4ed8;">{total_runs}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">总执行次数</div>
        </div>
        <div style="padding: 16px; border-radius: 12px; background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 1px solid #bbf7d0;">
            <div style="font-size: 28px; font-weight: 700; color: #16a34a;">{total_completed}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">已完成</div>
        </div>
        <div style="padding: 16px; border-radius: 12px; background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border: 1px solid #fecaca;">
            <div style="font-size: 28px; font-weight: 700; color: #dc2626;">{total_failed}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">失败</div>
        </div>
        <div style="padding: 16px; border-radius: 12px; background: linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%); border: 1px solid #e9d5ff;">
            <div style="font-size: 28px; font-weight: 700; color: #9333ea;">{active_loops}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">进行中</div>
        </div>
    </div>
    """)


def _render_loop_type_grid(ctx: dict, stats: Dict):
    ctx["put_html"]("""
    <div style="margin-bottom: 24px;">
        <h3 style="font-size: 16px; font-weight: 600; color: #374151; margin-bottom: 12px;">各闭环状态</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px;">
    """)

    for loop_type, (name, color, desc) in LOOP_TYPE_INFO.items():
        s = stats.get(loop_type, {})
        total = s.get("total", 0)
        completed = s.get("completed", 0)
        failed = s.get("failed", 0)
        avg_dur = s.get("avg_duration_ms", 0)
        last_run = s.get("last_run", 0)

        status_color = "#16a34a" if failed == 0 else "#dc2626" if failed > 0 else "#94a3b8"
        status_text = "🟢 正常" if failed == 0 and total > 0 else "🔴 有失败" if failed > 0 else "⚪ 未执行"

        ctx["put_html"](f"""
        <div style="padding: 16px; border-radius: 10px; background: #fff; border: 1px solid #e5e7eb; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                <span style="font-size: 18px; color: {color};">{name}</span>
                <span style="font-size: 12px; color: {status_color}; font-weight: 600;">{status_text}</span>
            </div>
            <div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">{desc}</div>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; font-size: 12px;">
                <div>执行: <span style="font-weight: 600;">{total}</span></div>
                <div>完成: <span style="font-weight: 600; color: #16a34a;">{completed}</span></div>
                <div>失败: <span style="font-weight: 600; color: #dc2626;">{failed}</span></div>
                <div>平均: <span style="font-weight: 600;">{_format_duration(avg_dur)}</span></div>
            </div>
            <div style="font-size: 11px; color: #9ca3af; margin-top: 8px;">最后: {_format_time(last_run)}</div>
        </div>
        """)

    ctx["put_html"]("</div></div>")


def _render_recent_records(ctx: dict, records: List):
    ctx["put_html"]("""
    <div style="margin-bottom: 24px;">
        <h3 style="font-size: 16px; font-weight: 600; color: #374151; margin-bottom: 12px;">最近执行记录</h3>
    """)

    if not records:
        ctx["put_html"]("""
        <div style="padding: 24px; border-radius: 10px; background: #f9fafb; border: 1px solid #e5e7eb; text-align: center;">
            <p style="color: #9ca3af; font-size: 14px;">暂无执行记录</p>
        </div>
        """)
    else:
        ctx["put_html"]("""
        <div style="border-radius: 10px; overflow: hidden; border: 1px solid #e5e7eb;">
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <thead>
                    <tr style="background: #f9fafb;">
                        <th style="padding: 10px 12px; text-align: left; color: #6b7280; font-weight: 500;">时间</th>
                        <th style="padding: 10px 12px; text-align: left; color: #6b7280; font-weight: 500;">闭环</th>
                        <th style="padding: 10px 12px; text-align: left; color: #6b7280; font-weight: 500;">阶段</th>
                        <th style="padding: 10px 12px; text-align: left; color: #6b7280; font-weight: 500;">状态</th>
                        <th style="padding: 10px 12px; text-align: right; color: #6b7280; font-weight: 500;">耗时</th>
                    </tr>
                </thead>
                <tbody>
        """)

        for r in records:
            ts = _format_time(r.get("timestamp", 0))
            loop_type = r.get("loop_type", "")
            stage = r.get("stage", "")
            status = r.get("status", "")
            duration = r.get("duration_ms", 0)

            info = LOOP_TYPE_INFO.get(loop_type, ("📦", "#6b7280", ""))
            name = info[0]

            status_color = {"completed": "#16a34a", "failed": "#dc2626", "running": "#9333ea", "skipped": "#f59e0b"}.get(status, "#6b7280")
            status_icon = {"completed": "✓", "failed": "✗", "running": "⟳", "skipped": "⊘"}.get(status, "?")

            ctx["put_html"](f"""
                <tr style="border-top: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; color: #374151;">{ts}</td>
                    <td style="padding: 10px 12px; color: #374151;">{name} {loop_type}</td>
                    <td style="padding: 10px 12px; color: #6b7280;">{stage}</td>
                    <td style="padding: 10px 12px;">
                        <span style="color: {status_color}; font-weight: 600;">{status_icon} {status}</span>
                    </td>
                    <td style="padding: 10px 12px; text-align: right; color: #6b7280;">{_format_duration(duration)}</td>
                </tr>
            """)

        ctx["put_html"]("</tbody></table></div>")

    ctx["put_html"]("</div>")