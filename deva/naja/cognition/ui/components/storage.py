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
    """)

    # === 衰减参数 & 强化保护 升级区域 ===
    try:
        from deva.naja.cognition.memory_manager import MemoryManager
        mm = MemoryManager()

        short_hl = getattr(mm, 'short_term_half_life', 300)
        mid_hl = getattr(mm, 'mid_term_half_life', 3600)
        topic_hl = getattr(mm, 'topic_half_life', 1800)
        mid_threshold = getattr(mm, 'mid_memory_threshold', 0.7)
        long_interval = getattr(mm, 'long_memory_interval', 86400)
        shield_time = getattr(mm, 'reinforcement_shield', 60)

        def _fmt_duration(seconds):
            if seconds >= 3600:
                return f"{seconds / 3600:.1f}h"
            elif seconds >= 60:
                return f"{int(seconds / 60)}m"
            else:
                return f"{int(seconds)}s"

        put_html(f"""
        <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.06);">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 8px; font-weight: 500;">
                ⏳ 衰减参数 & 强化保护
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px;">
                <div style="background: rgba(96,165,250,0.08); border: 1px solid rgba(96,165,250,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 13px; color: #60a5fa; font-weight: 700;">{_fmt_duration(short_hl)}</div>
                    <div style="font-size: 9px; color: #94a3b8;">短期半衰期</div>
                </div>
                <div style="background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 13px; color: #fbbf24; font-weight: 700;">{_fmt_duration(mid_hl)}</div>
                    <div style="font-size: 9px; color: #94a3b8;">中期半衰期</div>
                </div>
                <div style="background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 13px; color: #a855f7; font-weight: 700;">{_fmt_duration(topic_hl)}</div>
                    <div style="font-size: 9px; color: #94a3b8;">主题半衰期</div>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px;">
                <div style="background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 13px; color: #f59e0b; font-weight: 700;">{mid_threshold:.0%}</div>
                    <div style="font-size: 9px; color: #94a3b8;">中期阈值</div>
                    <div style="font-size: 8px; color: #64748b;">动态调整</div>
                </div>
                <div style="background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 13px; color: #22c55e; font-weight: 700;">{_fmt_duration(shield_time)}</div>
                    <div style="font-size: 9px; color: #94a3b8;">强化保护</div>
                    <div style="font-size: 8px; color: #64748b;">shield</div>
                </div>
                <div style="background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 13px; color: #a855f7; font-weight: 700;">{_fmt_duration(long_interval)}</div>
                    <div style="font-size: 9px; color: #94a3b8;">归档间隔</div>
                    <div style="font-size: 8px; color: #64748b;">长期总结</div>
                </div>
            </div>
        </div>
        """)
    except Exception:
        pass

    # 长期记忆总结摘要
    try:
        long_summary = report.get('long_term_summary', '')
        if long_summary:
            put_html(f"""
        <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.06);">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px; font-weight: 500;">📝 长期记忆摘要</div>
            <div style="
                background: rgba(168,85,247,0.04);
                border-left: 3px solid rgba(168,85,247,0.3);
                padding: 6px 10px;
                border-radius: 0 6px 6px 0;
                font-size: 10px;
                color: #c4b5fd;
                line-height: 1.5;
            ">{long_summary[:200]}{'...' if len(long_summary) > 200 else ''}</div>
        </div>
            """)
    except Exception:
        pass

    put_html("</div>")