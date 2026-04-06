"""
Storage 组件
"""


def render_storage(ui):
    if not ui.engine:
        return

    from pywebio.output import put_html

    report = ui.engine.get_memory_report()
    memory_layers = report.get('memory_layers', {})

    short = memory_layers.get('short', {})
    mid = memory_layers.get('mid', {})

    short_size = short.get('size', 0)
    short_cap = short.get('capacity', 1000)
    mid_size = mid.get('size', 0)
    mid_cap = mid.get('capacity', 5000)

    short_pct = min(100, int(short_size / short_cap * 100)) if short_cap > 0 else 0
    mid_pct = min(100, int(mid_size / mid_cap * 100)) if mid_cap > 0 else 0

    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #60a5fa; margin-bottom: 4px;">
            🧠 记忆存储
        </div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px;">
            <div style="text-align: center; padding: 10px; background: rgba(96,165,250,0.12); border: 1px solid rgba(96,165,250,0.25); border-radius: 8px;">
                <div style="font-size: 16px; margin-bottom: 2px;">⚡</div>
                <div style="font-size: 11px; font-weight: 600; color: #60a5fa;">短期</div>
                <div style="font-size: 18px; font-weight: 700; color: #93c5fd;">{short_size}</div>
                <div style="font-size: 10px; color: #475569;">/ {short_cap}</div>
            </div>
            <div style="text-align: center; padding: 10px; background: rgba(251,191,36,0.12); border: 1px solid rgba(251,191,36,0.25); border-radius: 8px;">
                <div style="font-size: 16px; margin-bottom: 2px;">📦</div>
                <div style="font-size: 11px; font-weight: 600; color: #fbbf24;">中期</div>
                <div style="font-size: 18px; font-weight: 700; color: #fcd34d;">{mid_size}</div>
                <div style="font-size: 10px; color: #475569;">/ {mid_cap}</div>
            </div>
            <div style="text-align: center; padding: 10px; background: rgba(168,85,247,0.12); border: 1px solid rgba(168,85,247,0.25); border-radius: 8px;">
                <div style="font-size: 16px; margin-bottom: 2px;">🧠</div>
                <div style="font-size: 11px; font-weight: 600; color: #a855f7;">长期</div>
                <div style="font-size: 18px; font-weight: 700; color: #c084fc;">总结</div>
                <div style="font-size: 10px; color: #475569;">定期生成</div>
            </div>
        </div>
        <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #475569; margin-bottom: 4px;">
                <span>短期使用</span><span>{short_size}/{short_cap}</span>
            </div>
            <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                <div style="width: {short_pct}%; height: 100%; background: linear-gradient(90deg,#60a5fa,#93c5fd); border-radius: 3px;"></div>
            </div>
        </div>
        <div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #475569; margin-bottom: 4px;">
                <span>中期使用</span><span>{mid_size}/{mid_cap}</span>
            </div>
            <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                <div style="width: {mid_pct}%; height: 100%; background: linear-gradient(90deg,#fbbf24,#fcd34d); border-radius: 3px;"></div>
            </div>
        </div>
    </div>
    """)