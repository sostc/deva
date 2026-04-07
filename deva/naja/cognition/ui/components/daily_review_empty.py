"""
Market Replay Empty 组件
"""


def render_daily_review_empty():
    from pywebio.output import put_html
    put_html("""
    <div style="margin-top: 12px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);">
        <div style="font-size: 12px; color: #64748b;">📊 今日市场复盘</div>
        <div style="font-size: 10px; color: #94a3b8; margin-top: 4px;">盘后自动执行，或点击"市场复盘"按钮手动生成</div>
    </div>
    """)