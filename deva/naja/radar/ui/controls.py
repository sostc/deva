"""Radar UI — 控制面板 + 刷新/清空"""

from pywebio.output import put_html, put_buttons
from pywebio.session import run_js


def render_control_panel(engine):
    """渲染控制面板"""

    def toggle_scanning(value):
        if engine:
            if value == "pause":
                engine.pause()
            else:
                engine.resume()

    def force_refresh():
        if engine:
            engine.force_scan()

    put_html("""
    <div style="
        background: rgba(107, 114, 128, 0.1);
        border: 1px solid rgba(107, 114, 128, 0.3);
        border-radius: 12px;
        padding: 15px;
        margin-top: 15px;
    ">
        <h4 style="margin: 0 0 15px 0; color: #94a3b8;">⚙️ 控制</h4>
    """)

    put_buttons(
        ["⏸️ 暂停", "▶️ 继续", "🔄 强制扫描"],
        onclick=[
            lambda: toggle_scanning("pause"),
            lambda: toggle_scanning("resume"),
            force_refresh
        ],
        small=True
    )

    put_html("</div>")


def refresh_page():
    """刷新页面"""
    run_js("setTimeout(function() { location.reload(); }, 200)")


def clear_events(engine):
    """清空事件"""
    if engine:
        engine.prune_events(retention_days=0)
    run_js("setTimeout(function() { location.reload(); }, 500)")
