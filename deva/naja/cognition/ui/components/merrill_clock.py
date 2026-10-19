"""Merrill Clock 组件 —— 美林时钟入口卡

2026-10-19：原卡片用了 `linear-gradient(135deg, #faf5ff 0%, ...)` 的浅色底，
在深色主题里是一块突兀的白条；改为与全页一致的深色卡片，只保留周期状态与跳转。
"""

from pywebio.output import put_html


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
        confidence = float(summary.get("confidence", 0) or 0)
        emoji = phase_emoji.get(phase, "❓")
        phase_text = f"{emoji} {phase}"
        sub_text = f"置信度 {confidence:.0%}"
        color = "#f59e0b" if phase in ("OVERHEAT", "STAGFLATION") else "#22c55e"
    else:
        phase_text = "🌙 暂无经济数据"
        sub_text = "经济数据未采集"
        color = "#64748b"

    put_html(f"""
    <a href="/merrill_clock" style="text-decoration: none;">
        <div class="cog-card" style="display: flex; align-items: center;
                    justify-content: space-between; gap: 12px;">
            <div>
                <div class="cog-title" style="color: #a855f7;">🕐 美林时钟 · 经济周期</div>
                <div style="font-size: 13px; color: {color}; margin-top: 5px; font-weight: 600;">{phase_text}</div>
                <div style="font-size: 11px; color: #64748b; margin-top: 2px;">{sub_text}</div>
            </div>
            <div style="background: rgba(168,85,247,.15); padding: 6px 12px; border-radius: 8px;
                        font-size: 11px; color: #a855f7; white-space: nowrap;">查看 →</div>
        </div>
    </a>
    """)
