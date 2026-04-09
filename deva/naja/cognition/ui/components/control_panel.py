"""
Control Panel 组件
"""

from pywebio.output import put_html
from deva.naja.register import SR


def render_control_panel(ui):
    from ....cognition.insight import get_llm_reflection_engine
    from ....market_hotspot.intelligence.feedback_report import get_feedback_report_generator

    llm_engine = get_llm_reflection_engine()
    pool = SR('insight_pool')
    feedback_reporter = get_feedback_report_generator()

    stats = llm_engine.get_stats()
    pending_signals = stats.get('pending_signals', 0)
    interval = int(stats.get('interval_seconds', 3600))

    signals = pool.get_recent_insights(limit=100) if pool else []
    narratives_data = ui.engine.get_memory_report().get('narratives', {}).get('summary', []) if ui.engine else []

    feedback_data = feedback_reporter.get_summary() if feedback_reporter else {}
    experiment_results = feedback_data.get('experiment_feedback', {})

    put_html("""
    <div style="
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #64748b; margin-bottom: 10px;">
            🎛️ 控制面板
        </div>
    """)
    put_html(f"""
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
        <div style="background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
            <div style="font-size: 11px; color: #60a5fa; font-weight: 600;">待反思</div>
            <div style="font-size: 18px; font-weight: 700; color: #93c5fd;">{pending_signals}</div>
        </div>
        <div style="background: rgba(168,85,247,0.1); border: 1px solid rgba(168,85,247,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
            <div style="font-size: 11px; color: #a855f7; font-weight: 600;">间隔</div>
            <div style="font-size: 18px; font-weight: 700; color: #c084fc;">{interval}s</div>
        </div>
        <div style="background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
            <div style="font-size: 11px; color: #4ade80; font-weight: 600;">反馈实验</div>
            <div style="font-size: 18px; font-weight: 700; color: #6ee7b7;">{len(experiment_results)}</div>
        </div>
    </div>
    """)
    put_html('</div>')