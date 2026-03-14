"""Radar UI."""

from datetime import datetime

from pywebio.output import put_html, put_table, use_scope, set_scope, put_collapse

from ..common.ui_style import apply_strategy_like_styles, render_empty_state
from .engine import get_radar_engine


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _render_radar_help():
    """渲染雷达帮助说明"""
    return put_collapse(
        "📖 帮助说明",
        put_html("""
        <div style="font-size:13px;line-height:1.6;color:#374151;">
            <p><strong>雷达系统</strong>专注检测市场<strong>技术层面</strong>的变化，包括量价突破、波动率变化、模式切换等可交易的技术信号。</p>
            
            <h4 style="margin:12px 0 8px;color:#1f2937;">🎯 与记忆系统的区别</h4>
            <table style="width:100%;border-collapse:collapse;font-size:12px;">
                <tr style="background:#fef2f2;">
                    <td style="padding:8px;border:1px solid #fecaca;"><strong>雷达 (技术)</strong></td>
                    <td style="padding:8px;border:1px solid #fecaca;"><strong>记忆 (叙事)</strong></td>
                </tr>
                <tr>
                    <td style="padding:8px;border:1px solid #e5e7eb;">量价突破、波动率变化</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;">热点主题、叙事变化</td>
                </tr>
                <tr style="background:#f9fafb;">
                    <td style="padding:8px;border:1px solid #e5e7eb;">技术模式切换</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;">市场注意力焦点</td>
                </tr>
                <tr>
                    <td style="padding:8px;border:1px solid #e5e7eb;">可交易的信号</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;">市场共识/情绪</td>
                </tr>
            </table>
            
            <h4 style="margin:12px 0 8px;color:#1f2937;">📊 字段说明</h4>
            <table style="width:100%;border-collapse:collapse;font-size:12px;">
                <tr style="background:#f3f4f6;">
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>时间</strong></td>
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;">事件发生时间</td>
                </tr>
                <tr>
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>事件</strong></td>
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;">事件类型：pattern(模式)、drift(漂移)、anomaly(异常)</td>
                </tr>
                <tr style="background:#f3f4f6;">
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>分数</strong></td>
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;">事件严重程度/置信度 (0-10)</td>
                </tr>
                <tr>
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>策略</strong></td>
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;">触发该事件的策略名称</td>
                </tr>
                <tr style="background:#f3f4f6;">
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>信号类型</strong></td>
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;">检测到的具体信号类型</td>
                </tr>
                <tr>
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;"><strong>说明</strong></td>
                    <td style="padding:6px 10px;border:1px solid #e5e7eb;">事件的详细描述</td>
                </tr>
            </table>
            
            <h4 style="margin:12px 0 8px;color:#1f2937;">📈 技术信号类型</h4>
            <table style="width:100%;border-collapse:collapse;font-size:12px;">
                <tr style="background:#fef2f2;">
                    <td style="padding:6px 10px;border:1px solid #fecaca;color:#dc2626;"><strong>fast_anomaly</strong></td>
                    <td style="padding:6px 10px;border:1px solid #fecaca;">快速异常 - 短时间内数据分布剧烈变化</td>
                </tr>
                <tr style="background:#fffbeb;">
                    <td style="padding:6px 10px;border:1px solid #fde68a;color:#d97706;"><strong>volume_breakout</strong></td>
                    <td style="padding:6px 10px;border:1px solid #fde68a;">成交量突破 - 成交量模式突变，可能预示突破</td>
                </tr>
                <tr style="background:#eff6ff;">
                    <td style="padding:6px 10px;border:1px solid #bfdbfe;color:#2563eb;"><strong>block_rotation</strong></td>
                    <td style="padding:6px 10px;border:1px solid #bfdbfe;">板块轮动 - 资金在板块间流动</td>
                </tr>
                <tr style="background:#f0fdf4;">
                    <td style="padding:6px 10px;border:1px solid #bbf7d0;color:#16a34a;"><strong>trend_analysis</strong></td>
                    <td style="padding:6px 10px;border:1px solid #bbf7d0;">趋势分析 - 市场趋势模式漂移</td>
                </tr>
                <tr style="background:#f3e8ff;">
                    <td style="padding:6px 10px;border:1px solid #e9d5ff;color:#9333ea;"><strong>tick_drift_adwin</strong></td>
                    <td style="padding:6px 10px;border:1px solid #e9d5ff;">ADWIN漂移 - 基于ADWIN算法的价格漂移</td>
                </tr>
            </table>
        </div>
        """)
    )


async def render_radar_admin(ctx: dict):
    set_scope("radar_content")
    apply_strategy_like_styles(ctx, scope="radar_content", include_compact_table=True)

    radar = get_radar_engine()
    summary = radar.summarize(window_seconds=600)
    events = summary.get("events", []) or []

    ctx["put_html"](
        f"""
        <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
            <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#0ea5e9,#38bdf8);
                        padding:18px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(14,165,233,0.25);">
                <div style="font-size:12px;opacity:0.9;margin-bottom:4px;">最近 10 分钟事件</div>
                <div style="font-size:28px;font-weight:700;">{summary.get("event_count", 0)}</div>
            </div>
            <div style="flex:2;min-width:220px;background:#fff;padding:16px;border-radius:12px;
                        box-shadow:0 2px 10px rgba(0,0,0,0.06);">
                <div style="font-size:13px;color:#666;margin-bottom:6px;">事件分布</div>
                <div style="font-size:12px;color:#333;">
                    {", ".join([f"{k}:{v}" for k, v in (summary.get("event_type_counts") or {}).items()]) or "暂无"}
                </div>
            </div>
        </div>
        """,
        scope="radar_content",
    )

    _render_radar_help()

    if not events:
        ctx["put_html"](render_empty_state("暂无雷达事件"), scope="radar_content")
        return

    table_data = [["时间", "事件", "分数", "策略", "信号类型", "说明"]]
    for e in events[:50]:
        table_data.append(
            [
                _fmt_ts(float(e.get("timestamp", 0))),
                e.get("event_type", "-"),
                f"{float(e.get('score', 0)):.2f}" if e.get("score") is not None else "-",
                e.get("strategy_name", "-"),
                e.get("signal_type", "-"),
                e.get("message", "-"),
            ]
        )

    ctx["put_table"](table_data, scope="radar_content")
