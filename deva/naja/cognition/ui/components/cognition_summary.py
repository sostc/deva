"""
Cognition Summary 组件
"""

from typing import Dict


def render_cognition_summary(ui):
    from ....radar.engine import get_radar_engine
    from ....attention.ui_components.common import get_attention_report
    from ....cognition.insight import get_insight_engine, get_insight_pool
    from pywebio.output import put_html

    radar = get_radar_engine()
    radar_summary = radar.summarize(window_seconds=600) if radar else {}
    radar_events = radar_summary.get("event_count", 0)

    attention_report = get_attention_report() or {}
    global_attention = float(attention_report.get("global_attention", 0))
    activity = float(attention_report.get("activity", 0))

    insight_engine = get_insight_engine()
    insight_pool = get_insight_pool()
    insight_summary = insight_engine.get_summary() if insight_engine else {}
    insight_stats = insight_pool.get_stats() if insight_pool else {"total_insights": 0}

    memory_report = ui.engine.get_memory_report() if ui.engine else {}
    stats = memory_report.get('stats', {})
    total_events = stats.get('total_events', 0)
    filtered_events = stats.get('filtered_events', 0)
    memory_layers = memory_report.get('memory_layers', {})
    short_size = memory_layers.get('short', {}).get('size', 0)
    mid_size = memory_layers.get('mid', {}).get('size', 0)

    attention_icon = "🔥" if global_attention >= 0.6 else ("📊" if global_attention >= 0.3 else "💤")
    attention_color = "#dc2626" if global_attention >= 0.6 else ("#ca8a04" if global_attention >= 0.3 else "#64748b")
    attention_level = "焦点集中" if global_attention >= 0.6 else ("温和" if global_attention >= 0.3 else "低迷")

    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border-radius: 14px;
        padding: 16px 20px;
        box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25), inset 0 1px 0 rgba(255,255,255,0.05);
        border: 1px solid #334155;
        position: relative;
        overflow: hidden;
    ">
        <div style="position: absolute; top: 0; right: 0; width: 200px; height: 100%; background: radial-gradient(ellipse at top right, #14b8a608 0%, transparent 60%); pointer-events: none;"></div>
        <div style="display: flex; justify-content: space-between; align-items: flex-start; position: relative;">
            <div>
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                    <span style="font-size: 24px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">🧠</span>
                    <div>
                        <div style="font-size: 16px; font-weight: 700; color: #f1f5f9;">认知中枢 <span style="font-size: 13px; font-weight: 400; color: #94a3b8;">认知层</span></div>
                        <div style="font-size: 11px; color: #14b8a6; margin-top: 2px;">理解语义、形成记忆、生成洞察</div>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 12px; margin-top: 6px;">
                    <div style="font-size: 12px; color: #64748b;">输入：雷达事件 + 新闻舆情 ｜ 输出：洞察建议 → 注意力调度</div>
                    <a href="/cognition_glossary" target="_blank" style="
                        font-size: 11px;
                        color: #8b5cf6;
                        text-decoration: none;
                        padding: 3px 8px;
                        background: rgba(139, 92, 246, 0.1);
                        border: 1px solid rgba(139, 92, 246, 0.3);
                        border-radius: 4px;
                        display: inline-flex;
                        align-items: center;
                        gap: 4px;
                    ">
                        📖 名词解释
                    </a>
                </div>
            </div>
            <div style="display: flex; gap: 12px; text-align: center;">
                <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">📡 雷达</div>
                    <div style="font-size: 18px; font-weight: 700; color: #f59e0b;">{radar_events}</div>
                    <div style="font-size: 10px; color: #94a3b8;">10分钟事件</div>
                </div>
                <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">👁️ 注意力</div>
                    <div style="font-size: 18px; font-weight: 700; color: {attention_color};">{attention_icon} {global_attention:.2f}</div>
                    <div style="font-size: 10px; color: {attention_color}; opacity: 0.8;">{attention_level}</div>
                </div>
                <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">💡 洞察</div>
                    <div style="font-size: 18px; font-weight: 700; color: #14b8a6;">{insight_stats.get('total_insights', 0)}</div>
                    <div style="font-size: 10px; color: #94a3b8;">活跃主题 {insight_stats.get('active_themes', 0)}</div>
                </div>
                <div style="background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">记忆</div>
                    <div style="font-size: 14px; font-weight: 700; color: #a855f7;">{short_size}/{memory_layers.get('short', {}).get('capacity', 0)}</div>
                    <div style="font-size: 10px; color: #94a3b8;">短/中期 {mid_size}</div>
                </div>
            </div>
        </div>
        <div style="display: flex; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #334155;">
            <div style="flex: 1; padding: 6px 10px; background: rgba(245, 158, 11, 0.15); border-radius: 6px; text-align: center;">
                <span style="font-size: 11px; color: #fcd34d;">📥 接收</span>
                <span style="font-size: 12px; font-weight: 600; color: #f59e0b; margin-left: 4px;">{total_events + filtered_events}</span>
            </div>
            <div style="flex: 1; padding: 6px 10px; background: rgba(239, 68, 68, 0.15); border-radius: 6px; text-align: center;">
                <span style="font-size: 11px; color: #fca5a5;">🚫 过滤</span>
                <span style="font-size: 12px; font-weight: 600; color: #ef4444; margin-left: 4px;">{filtered_events}</span>
            </div>
            <div style="flex: 1; padding: 6px 10px; background: rgba(59, 130, 246, 0.15); border-radius: 6px; text-align: center;">
                <span style="font-size: 11px; color: #93c5fd;">⚡ 短期</span>
                <span style="font-size: 12px; font-weight: 600; color: #3b82f6; margin-left: 4px;">{short_size}</span>
            </div>
            <div style="flex: 1; padding: 6px 10px; background: rgba(16, 185, 129, 0.15); border-radius: 6px; text-align: center;">
                <span style="font-size: 11px; color: #6ee7b7;">📦 中期</span>
                <span style="font-size: 12px; font-weight: 600; color: #10b981; margin-left: 4px;">{mid_size}</span>
            </div>
        </div>
    </div>
    """)

    top_insights = (insight_pool.get_top_insights(limit=3) if insight_pool else []) or []
    recent_radar = (radar_summary.get("events", []) or [])[:3]

    if not top_insights and not recent_radar:
        return

    radar_lines = "".join(
        [f"<li>{e.get('message','-')[:80]}</li>" for e in recent_radar]
    ) or "<li>暂无雷达事件</li>"

    def _format_insight_summary(insight: Dict) -> str:
        summary_raw = insight.get('summary', '')
        if isinstance(summary_raw, dict):
            from ....insight.engine import Insight
            text = Insight._format_dict_for_display(summary_raw, 80)
        elif isinstance(summary_raw, str) and summary_raw.startswith('{') and summary_raw.endswith('}'):
            try:
                import ast
                parsed = ast.literal_eval(summary_raw)
                if isinstance(parsed, dict):
                    from ....insight.engine import Insight
                    text = Insight._format_dict_for_display(parsed, 80)
                else:
                    text = summary_raw[:80]
            except Exception:
                text = summary_raw[:80]
        else:
            text = summary_raw[:80] if summary_raw else '-'
        return text

    insight_lines = "".join(
        [f"<li>{_format_insight_summary(i)}</li>" for i in top_insights]
    ) or "<li>暂无洞察</li>"

    put_html(
        f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-bottom: 16px;">
            <div style="
                background: rgba(255,255,255,0.03);
                border-radius: 12px;
                padding: 14px 18px;
                border: 1px solid rgba(255,255,255,0.08);
            ">
                <div style="font-size: 13px; font-weight: 600; color: #f59e0b; margin-bottom: 8px;">📡 雷达快照</div>
                <div style="font-size: 11px; color: #475569; margin-bottom: 12px;">
                    最近 10 分钟雷达检测到的异常事件
                </div>
                <ol style="padding-left: 16px; margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.6;">{radar_lines}</ol>
            </div>
            <div style="
                background: rgba(255,255,255,0.03);
                border-radius: 12px;
                padding: 14px 18px;
                border: 1px solid rgba(255,255,255,0.08);
            ">
                <div style="font-size: 13px; font-weight: 600; color: #14b8a6; margin-bottom: 8px;">💡 洞察摘要</div>
                <ol style="padding-left: 16px; margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.6;">{insight_lines}</ol>
            </div>
        </div>
        """,
    )