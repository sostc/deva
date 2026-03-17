"""LLM controller UI - 自调优系统统一展示"""

from datetime import datetime

from pywebio.output import put_html, put_table, use_scope, set_scope, put_collapse
from pywebio.input import textarea
from pywebio.session import run_async

from deva import NB
from ..common.ui_style import apply_strategy_like_styles, render_empty_state
from ..page_help import render_help_collapse


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_ts_short(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _fmt_duration(seconds: float) -> str:
    if not seconds:
        return "-"
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        return f"{int(seconds/60)}分钟"
    else:
        return f"{int(seconds/3600)}小时"


async def render_llm_admin(ctx: dict):
    set_scope("llm_content")
    apply_strategy_like_styles(ctx, scope="llm_content", include_compact_table=True)

    try:
        render_help_collapse("llm_controller")
    except Exception:
        pass

    try:
        from deva.naja.common.auto_tuner import get_auto_tuner
        tuner = get_auto_tuner()
        tune_status = tuner.get_status()
        tune_events = tuner.get_recent_events(limit=20)
        conditions_status = tuner.get_conditions_status()
    except Exception as e:
        tune_status = {}
        tune_events = []
        conditions_status = []

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

    total_llm_decisions = len(decisions)
    total_auto_events = tune_status.get("events_count", 0)
    last_llm_ts = decisions[0].get("timestamp", 0) if decisions else 0
    last_auto_ts = tune_events[0].get("ts", 0) if tune_events else 0

    is_running = tune_status.get("running", False)
    active_conditions = sum(1 for c in conditions_status if c.get("trigger_count", 0) > 0)

    ctx["put_html"](
        """
        <div style="background:linear-gradient(135deg,#1e1e2f,#2d2d44);padding:20px;border-radius:14px;margin-bottom:20px;">
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
                <div>
                    <h2 style="margin:0 0 4px 0;color:#fff;font-size:20px;font-weight:600;">🤖 自调优系统</h2>
                    <p style="margin:0;color:#a0a0b0;font-size:13px;">策略调优 + 系统调优 统一控制台</p>
                </div>
                <div style="display:flex;align-items:center;gap:16px;">
                    <div style="display:flex;align-items:center;gap:8px;padding:8px 16px;background:rgba(255,255,255,0.1);border-radius:20px;">
                        <span style="width:10px;height:10px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;"></span>
                        <span style="color:#fff;font-size:13px;">自动调优</span>
                        <span style="color:#a0a0b0;font-size:12px;">""" + ("运行中" if is_running else "已停止") + """</span>
                    </div>
                </div>
            </div>
        </div>
        """,
        scope="llm_content",
    )

    ctx["put_html"](
        f"""
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px;">
            <div style="background:#fff;padding:16px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.06);border-left:4px solid #6366f1;">
                <div style="font-size:12px;color:#6b7280;margin-bottom:4px;">🎯 LLM 策略调节</div>
                <div style="font-size:24px;font-weight:700;color:#6366f1;">{total_llm_decisions}</div>
                <div style="font-size:11px;color:#9ca3af;">最近: {_fmt_ts_short(last_llm_ts)}</div>
            </div>
            <div style="background:#fff;padding:16px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.06);border-left:4px solid #3b82f6;">
                <div style="font-size:12px;color:#6b7280;margin-bottom:4px;">⚙️ 系统自动调节</div>
                <div style="font-size:24px;font-weight:700;color:#3b82f6;">{total_auto_events}</div>
                <div style="font-size:11px;color:#9ca3af;">活跃条件: {active_conditions}/{len(conditions_status)}</div>
            </div>
            <div style="background:#fff;padding:16px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.06);border-left:4px solid #10b981;">
                <div style="font-size:12px;color:#6b7280;margin-bottom:4px;">📊 策略指标</div>
                <div style="font-size:24px;font-weight:700;color:#10b981;">{len(metric_rows)}</div>
                <div style="font-size:11px;color:#9ca3af;">监控中</div>
            </div>
            <div style="background:#fff;padding:16px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.06);border-left:4px solid #f59e0b;">
                <div style="font-size:12px;color:#6b7280;margin-bottom:4px;">🔔 调优条件</div>
                <div style="font-size:24px;font-weight:700;color:#f59e0b;">{len(conditions_status)}</div>
                <div style="font-size:11px;color:#9ca3af;">监控项</div>
            </div>
        </div>
        """,
        scope="llm_content",
    )

    async def handle_manual_tune():
        try:
            from deva.naja.common.auto_tuner import manual_llm_tune
            result = manual_llm_tune(requirement)
            ctx["toast"](result.get('status', '调优已提交'), color="success")
        except Exception as e:
            ctx["toast"](f"调优失败: {str(e)}", color="error")

    async def do_manual_tune(requirement: str):
        try:
            from deva.naja.common.auto_tuner import manual_llm_tune
            result = manual_llm_tune(requirement)
            ctx["toast"](result.get('status', '调优已提交'), color="success")
        except Exception as e:
            ctx["toast"](f"调优失败: {str(e)}", color="error")

    async def show_tune_dialog():
        form = await ctx["input_group"]("手动 LLM 调优", [
            ctx["textarea"]("调优要求", name="requirement", 
                placeholder="例如：优化策略延迟、降低内存占用、提高数据源稳定性...",
                rows=3, required=True),
            ctx["actions"]("操作", [
                {"label": "🚀 立即调优", "value": "tune", "color": "primary"},
                {"label": "取消", "value": "cancel", "color": "default"},
            ], name="action"),
        ])
        
        if form and form.get("action") == "tune":
            await do_manual_tune(form.get("requirement", ""))

    ctx["put_html"](
        """
        <div style="background:linear-gradient(135deg,#f0f9ff,#e0f2fe);padding:20px;border-radius:12px;margin-bottom:20px;border:2px solid #0ea5e9;">
            <div style="display:flex;align-items:center;justify-content:space-between;">
                <div style="display:flex;align-items:center;">
                    <span style="font-size:24px;margin-right:8px;">🎯</span>
                    <div>
                        <h3 style="margin:0;color:#0369a1;font-size:16px;font-weight:600;">手动触发 LLM 调优</h3>
                        <p style="margin:0;color:#0c4a6e;font-size:12px;">点击按钮输入调优要求，LLM 将结合当前配置进行智能调优</p>
                    </div>
                </div>
            </div>
        </div>
        """,
        scope="llm_content",
    )

    ctx["put_buttons"](
        [{"label": "� 输入调优要求", "value": "tune", "color": "primary"}],
        onclick=lambda v: run_async(show_tune_dialog()),
        scope="llm_content"
    )

    ctx["put_html"]("<div style='margin:20px 0 12px 0;font-size:15px;font-weight:600;color:#374151;'>📜 调节历史记录 <span style='font-weight:400;font-size:12px;color:#9ca3af;'>(点击查看详情)</span></div>", scope="llm_content")

    all_events = []

    for idx, d in enumerate(decisions):
        actions = d.get("actions", [])
        detail_json = ""
        if actions:
            import json
            detail_json = json.dumps(actions, ensure_ascii=False, indent=2)
        
        all_events.append({
            "id": f"llm_{idx}",
            "ts": d.get("timestamp", 0),
            "type": "llm",
            "category": "strategy",
            "title": d.get("summary", "-")[:40],
            "actions": len(actions),
            "status": "success" if actions else "no_action",
            "detail": d.get("reason", "-")[:50],
            "full_detail": detail_json or d.get("reason", "-"),
        })

    for idx, e in enumerate(tune_events):
        before = e.get("before")
        after = e.get("after")
        param = e.get("param", "")
        reason = e.get("reason", "")
        action_type = e.get("action", "")
        
        change_info = ""
        if before is not None and after is not None:
            change_info = f"{param}: {before} → {after}"
        
        category_labels = {
            "system_overload": "🔴 系统过载",
            "performance_degradation": "🟡 性能下降",
            "low_utilization": "🟢 资源低效",
            "business_change": "🔵 业务变化",
            "manual": "🎯 手动调优",
        }
        
        all_events.append({
            "id": f"auto_{idx}",
            "ts": e.get("timestamp", 0),
            "type": "auto",
            "category": e.get("category", ""),
            "title": param[:40] if param else "自动调优",
            "actions": 1,
            "status": "auto",
            "detail": e.get("explanation", "")[:100] or reason[:100],
            "full_detail": f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 调节详情
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【参数名称】{param}
【触发类别】{category_labels.get(e.get('category', ''), e.get('category', ''))}
【动作类型】{action_type or '系统自动调节'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 调整原因
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{reason or '系统检测到异常，自动执行调节'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ 参数变化
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【调整前】{before if before is not None else '-'}
【调整后】{after if after is not None else '-'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 影响说明
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{e.get('impact', '-')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 LLM 建议
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{e.get('llm_suggestion', '-')}""",
            "change_info": change_info,
            "reason": reason,
            "action_type": action_type,
        })

    all_events.sort(key=lambda x: x["ts"], reverse=True)

    if not all_events:
        ctx["put_html"](
            "<div style='padding:30px;background:#f9fafb;border-radius:10px;text-align:center;color:#6b7280;'>"
            "暂无调节记录，系统正在监控中..."
            "</div>",
            scope="llm_content",
        )
    else:
        for event in all_events[:15]:
            type_icons = {"llm": "🤖", "auto": "⚙️"}
            type_labels = {"llm": "LLM策略调节", "auto": "系统自动调节"}

            category_icons = {
                "strategy": "🎯",
                "system_overload": "🔴",
                "performance_degradation": "🟡",
                "low_utilization": "🟢",
                "business_change": "🔵",
            }

            if event["type"] == "llm":
                category_icon = category_icons.get("strategy", "📌")
                bg_color = "rgba(99,102,241,0.08)"
                border_color = "#6366f1"
            else:
                cat = event.get("category", "")
                category_icon = category_icons.get(cat, "⚙️")
                bg_color = "rgba(59,130,246,0.08)"
                border_color = "#3b82f6"

            detail_id = f"detail_{event['id']}"
            
            change_info = event.get("change_info", "")
            change_display = ""
            if change_info:
                change_display = f'<span style="display:inline-block;padding:2px 8px;background:#dbeafe;color:#2563eb;border-radius:10px;font-size:10px;margin-left:6px;">{change_info}</span>'
            
            row_html = f"""
            <div style="margin-bottom:8px;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
                <div onclick="document.getElementById('{detail_id}').style.display=document.getElementById('{detail_id}').style.display==='none'?'':'none'" 
                     style="display:grid;grid-template-columns:80px 90px 1fr 60px 140px;gap:8px;padding:12px;cursor:pointer;background:{bg_color};border-bottom:1px solid #e5e7eb;font-size:12px;align-items:center;">
                    <div style="color:#6b7280;">{_fmt_ts_short(event['ts'])}</div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span>{type_icons.get(event['type'], '•')}</span>
                        <span style="color:#6b7280;font-size:11px;">{type_labels.get(event['type'], '-')}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;overflow:hidden;">
                        <span>{category_icon}</span>
                        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{event['title']}">{event['title']}</span>
                    </div>
                    <div style="text-align:center;">
                        <span style="display:inline-block;padding:2px 8px;background:{border_color};color:#fff;border-radius:10px;font-size:11px;">
                            {event['actions']}
                        </span>
                    </div>
                    <div style="display:flex;align-items:center;">
                        <span style="color:#9ca3af;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{event.get('detail', '-')}">
                            {event.get('detail', '-')}
                        </span>
                        {change_display}
                    </div>
                </div>
                <div id="{detail_id}" style="display:none;padding:12px;background:#fafafa;border-bottom:1px solid #e5e7eb;font-size:12px;">
                    <div style="font-weight:600;color:#374151;margin-bottom:8px;">📋 详细信息</div>
                    <pre style="margin:0;padding:10px;background:#fff;border-radius:6px;border:1px solid #e5e7eb;overflow-x:auto;font-size:11px;color:#4b5563;white-space:pre-wrap;word-break:break-all;">{event.get('full_detail', '-')}</pre>
                </div>
            </div>
            """
            ctx["put_html"](row_html, scope="llm_content")

    if metric_rows:
        ctx["put_html"]("<div style='margin:24px 0 12px 0;font-size:15px;font-weight:600;color:#374151;'>📊 策略指标快照</div>", scope="llm_content")

        ctx["put_html"](
            """
            <div style="display:grid;grid-template-columns:1fr 80px 80px 70px 70px 90px;gap:0;padding:0;
                        background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
                <div style="padding:12px 16px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;">策略名称</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">状态</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">成功率</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">结果数</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">平均耗时</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">最近执行</div>
            </div>
            """,
            scope="llm_content",
        )

        for m in metric_rows[:10]:
            success_rate = float(m.get('success_rate', 0))
            results_count = m.get("results_count", 0)
            avg_time = float(m.get('avg_process_time_ms', 0))
            last_ts = m.get("timestamp", 0)

            if success_rate >= 0.9:
                status_color, status_bg, status_icon, status_label = "#10b981", "rgba(16,185,129,0.15)", "✅", "优秀"
            elif success_rate >= 0.7:
                status_color, status_bg, status_icon, status_label = "#f59e0b", "rgba(245,158,11,0.15)", "⚠️", "良好"
            elif success_rate >= 0.5:
                status_color, status_bg, status_icon, status_label = "#d97706", "rgba(217,119,6,0.15)", "📊", "一般"
            else:
                status_color, status_bg, status_icon, status_label = "#dc2626", "rgba(220,38,38,0.15)", "❌", "差"

            strategy_name = m.get("strategy_name", "-")[:20]

            metric_row = f"""
            <div style="display:grid;grid-template-columns:1fr 80px 80px 70px 70px 90px;gap:0;padding:0;
                        background:#fff;border-bottom:1px solid #f3f4f6;font-size:12px;">
                <div style="padding:12px 16px;color:#374151;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{m.get('strategy_name', '-')}">
                    {strategy_name}
                </div>
                <div style="padding:12px;text-align:center;">
                    <span style="display:inline-flex;align-items:center;gap:3px;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:500;background:{status_bg};color:{status_color};">
                        {status_icon} {status_label}
                    </span>
                </div>
                <div style="padding:12px;text-align:center;color:#374151;font-weight:500;">
                    {success_rate * 100:.1f}%
                </div>
                <div style="padding:12px;text-align:center;color:#6b7280;">
                    {results_count}
                </div>
                <div style="padding:12px;text-align:center;color:#6b7280;">
                    {avg_time:.1f}ms
                </div>
                <div style="padding:12px;text-align:center;color:#9ca3af;font-size:11px;">
                    {_fmt_ts_short(last_ts)}
                </div>
            </div>
            """
            ctx["put_html"](metric_row, scope="llm_content")

    ctx["put_html"]("<div style='margin:24px 0 12px 0;font-size:15px;font-weight:600;color:#374151;'>⚙️ 调优条件状态</div>", scope="llm_content")

    if not conditions_status:
        ctx["put_html"](
            "<div style='padding:20px;background:#f9fafb;border-radius:10px;text-align:center;color:#6b7280;'>"
            "暂无调优条件"
            "</div>",
            scope="llm_content",
        )
    else:
        ctx["put_html"](
            """
            <div style="display:grid;grid-template-columns:1.5fr 80px 60px 60px 80px 80px;gap:0;padding:0;
                        background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
                <div style="padding:12px 16px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;">条件名称</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">类别</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">阈值</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">操作符</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">触发</div>
                <div style="padding:12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:12px;font-weight:600;color:#6b7280;text-align:center;">冷却</div>
            </div>
            """,
            scope="llm_content",
        )

        for c in conditions_status:
            category_icons = {
                "system_overload": "🔴",
                "performance_degradation": "🟡",
                "low_utilization": "🟢",
                "business_change": "🔵",
            }
            cat = c.get("category", "")
            icon = category_icons.get(cat, "⚪")

            trigger_count = c.get("trigger_count", 0)
            trigger_bg = "rgba(239,68,68,0.15)" if trigger_count > 0 else "rgba(107,114,128,0.15)"
            trigger_color = "#dc2626" if trigger_count > 0 else "#6b7280"

            cond_row = f"""
            <div style="display:grid;grid-template-columns:1.5fr 80px 60px 60px 80px 80px;gap:0;padding:0;
                        background:#fff;border-bottom:1px solid #f3f4f6;font-size:12px;align-items:center;">
                <div style="padding:12px 16px;font-weight:500;color:#374151;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{c.get('name', '-')}">
                    {c.get('name', '-')[:35]}
                </div>
                <div style="padding:12px;text-align:center;">
                    <span style="display:inline-flex;align-items:center;gap:3px;font-size:11px;">
                        <span>{icon}</span>
                        <span style="color:#6b7280;">{cat[:8]}</span>
                    </span>
                </div>
                <div style="padding:12px;text-align:center;color:#374151;font-weight:500;">
                    {c.get('threshold', '')}
                </div>
                <div style="padding:12px;text-align:center;color:#6b7280;font-family:monospace;">
                    {c.get('operator', '')}
                </div>
                <div style="padding:12px;text-align:center;">
                    <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:500;background:{trigger_bg};color:{trigger_color};">
                        {trigger_count}
                    </span>
                </div>
                <div style="padding:12px;text-align:center;color:#9ca3af;">
                    {c.get('cooldown', 0)}s
                </div>
            </div>
            """
            ctx["put_html"](cond_row, scope="llm_content")
