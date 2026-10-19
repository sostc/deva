"""Control Panel 组件 —— 反思调度参数

2026-10-19：合并成一次 put_html（原实现跨调用开/关 div，容器实际不成立）。
"""

from pywebio.output import put_html

from .layout import card


def _get_insight_pool():
    """获取 InsightPool（AppContainer 优先，SR fallback 仅开发用）"""
    from deva.naja.application.container import get_app_container
    container = get_app_container()
    if container is not None:
        ip = getattr(container, 'insight_pool', None)
        if ip is not None:
            return ip
    from deva.naja.register import SR
    return SR('insight_pool')


def render_control_panel(ui):
    from ....cognition.insight import get_llm_reflection_engine
    from ....market_hotspot.intelligence.feedback_report import get_feedback_report_generator

    llm_engine = get_llm_reflection_engine()
    feedback_reporter = get_feedback_report_generator()

    stats = llm_engine.get_stats()
    pending_signals = stats.get('pending_signals', 0)
    interval = int(stats.get('interval_seconds', 3600))

    feedback_data = feedback_reporter.get_summary() if feedback_reporter else {}
    experiment_results = feedback_data.get('experiment_feedback', {})

    cells = "".join(
        f'<div style="background: {color}14; border: 1px solid {color}2e; padding: 7px 12px;'
        f'border-radius: 8px; text-align: center;">'
        f'<div style="font-size: 11px; color: {color};">{label}</div>'
        f'<div style="font-size: 17px; font-weight: 700; color: #e2e8f0;">{value}</div></div>'
        for label, value, color in (
            ("待反思", pending_signals, "#60a5fa"),
            ("反思间隔", f"{interval}s", "#a855f7"),
            ("反馈实验", len(experiment_results), "#22c55e"),
        )
    )

    put_html(card(
        title="控制面板",
        icon="🎛️",
        meta="反思调度",
        body=f'<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">{cells}</div>',
    ))
