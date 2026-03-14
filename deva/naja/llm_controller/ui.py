"""LLM controller UI."""

from datetime import datetime

from pywebio.output import put_html, put_table, use_scope, set_scope

from deva import NB
from ..common.ui_style import apply_strategy_like_styles, render_empty_state
from ..page_help import render_help_collapse


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


async def render_llm_admin(ctx: dict):
    set_scope("llm_content")
    apply_strategy_like_styles(ctx, scope="llm_content", include_compact_table=True)

    try:
        render_help_collapse("llm_controller")
    except Exception:
        pass

    decisions_db = NB("naja_llm_decisions")
    decisions = []
    try:
        keys = list(decisions_db.keys())
        keys.sort(reverse=True)
        for key in keys[:30]:
            data = decisions_db.get(key)
            if isinstance(data, dict):
                decisions.append(data)
    except Exception:
        pass

    metrics_db = NB("naja_strategy_metrics")
    metric_rows = []
    try:
        keys = list(metrics_db.keys())
        keys.sort(reverse=True)
        for key in keys[:20]:
            data = metrics_db.get(key)
            if isinstance(data, dict):
                metric_rows.append(data)
    except Exception:
        pass

    ctx["put_html"](
        f"""
        <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
            <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#6366f1,#8b5cf6);
                        padding:18px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(99,102,241,0.25);">
                <div style="font-size:12px;opacity:0.9;margin-bottom:4px;">最近决策</div>
                <div style="font-size:28px;font-weight:700;">{len(decisions)}</div>
            </div>
            <div style="flex:2;min-width:220px;background:#fff;padding:16px;border-radius:12px;
                        box-shadow:0 2px 10px rgba(0,0,0,0.06);">
                <div style="font-size:13px;color:#666;margin-bottom:6px;">最近策略指标</div>
                <div style="font-size:12px;color:#333;">{len(metric_rows)} 条</div>
            </div>
        </div>
        """,
        scope="llm_content",
    )

    if not decisions:
        ctx["put_html"](render_empty_state("暂无 LLM 调节记录"), scope="llm_content")
    else:
        decision_table = [["时间", "摘要", "动作数", "原因"]]
        for d in decisions:
            actions = d.get("actions") or []
            decision_table.append(
                [
                    _fmt_ts(float(d.get("timestamp", 0))),
                    d.get("summary", "-"),
                    str(len(actions)),
                    d.get("reason", "-")[:60],
                ]
            )
        ctx["put_table"](decision_table, scope="llm_content")

    if metric_rows:
        metric_table = [["时间", "策略", "成功率", "结果数", "平均耗时"]]
        for m in metric_rows[:20]:
            metric_table.append(
                [
                    _fmt_ts(float(m.get("timestamp", 0))),
                    m.get("strategy_name", "-"),
                    f"{float(m.get('success_rate', 0)) * 100:.1f}%",
                    str(m.get("results_count", 0)),
                    f"{float(m.get('avg_process_time_ms', 0)):.1f}ms",
                ]
            )
        ctx["put_html"]("<div style='margin-top:18px;font-weight:600;'>📈 策略指标快照</div>", scope="llm_content")
        ctx["put_table"](metric_table, scope="llm_content")
