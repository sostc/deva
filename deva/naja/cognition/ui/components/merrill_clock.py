"""
Merrill Clock 组件
"""


def render_merrill_clock(ui):
    try:
        from ....cognition.merrill_clock import get_merrill_clock_engine
        clock = get_merrill_clock_engine()
        summary = clock.get_summary()
        has_data = summary.get("status") == "active"
    except Exception:
        has_data = False
        summary = {}

    phase_emoji = {
        "RECOVERY": "🌱",
        "OVERHEAT": "🔥",
        "STAGFLATION": "⚠️",
        "RECESSION": "🥶",
    }

    if has_data:
        phase = summary.get("phase", "")
        confidence = summary.get("confidence", 0)
        emoji = phase_emoji.get(phase, "❓")
        summary_text = f"{emoji} {phase} | 置信度 {confidence:.0%}"
    else:
        summary_text = "🌙 暂无经济数据"

    from pywebio.output import put_html
    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: linear-gradient(135deg, #faf5ff 0%, rgba(255,255,255,0.05) 100%);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(168,85,247,0.2);
    ">
        <a href="/merrill_clock" style="text-decoration: none;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <div style="font-size: 13px; font-weight: 600; color: #a855f7; margin-bottom: 2px;">
                        🕐 美林时钟 · 经济周期
                    </div>
                    <div style="font-size: 11px; color: #6b7280;">
                        {summary_text}
                    </div>
                </div>
                <div style="
                    background: rgba(168,85,247,0.15);
                    padding: 6px 12px;
                    border-radius: 8px;
                    font-size: 12px;
                    color: #a855f7;
                    font-weight: 500;
                ">
                    查看 →
                </div>
            </div>
        </a>
    </div>
    """)