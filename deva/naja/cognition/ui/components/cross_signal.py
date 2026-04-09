"""
Cross Signal 组件
"""

from ....common.ui_style import format_timestamp


def render_cross_signal(ui):
    try:
        from .cross_signal_analyzer import get_cross_signal_analyzer, ResonanceType, SignalSource
        analyzer = get_cross_signal_analyzer()
        if not analyzer:
            return
    except Exception:
        return

    from pywebio.output import put_html

    stats = analyzer.get_stats()
    recent_resonances = analyzer.get_recent_resonances(n=8)
    high_resonance_blocks = analyzer.get_high_resonance_blocks(threshold=0.7, n=5)
    market_resonance_summary = analyzer.get_market_resonance_summary()

    news_buffer_size = stats.get('news_buffer_size', 0)
    attention_buffer_size = stats.get('attention_buffer_size', 0)
    market_buffer_size = stats.get('market_buffer_size', 0)
    resonance_history_size = stats.get('resonance_history_size', 0)
    market_resonance_history_size = stats.get('market_resonance_history_size', 0)
    recent_resonance_count = stats.get('recent_resonance_count', 0)
    recent_market_resonance_count = stats.get('recent_market_resonance_count', 0)
    llm_cooldown_remaining = stats.get('llm_cooldown_remaining', 0)

    should_trigger_llm = analyzer.should_trigger_llm()
    llm_ready = "🔥 就绪" if should_trigger_llm else f"💤 冷却 ({int(llm_cooldown_remaining)}s)"

    resonance_type_colors = {
        "temporal": "#60a5fa",
        "intensity": "#f97316",
        "narrative": "#a855f7",
        "correlation": "#14b8a6",
    }

    market_resonance_type_colors = {
        "intensity": "#f97316",
        "macro": "#a855f7",
        "cross_market": "#14b8a6",
    }

    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #f97316;">
                🔄 跨信号分析（共振检测）
            </div>
            <div style="font-size: 10px; color: #475569;">
                LLM层: {llm_ready}
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            新闻 × 注意力 / 新闻 × 宏观叙事 / 市场 × 市场 → 三层共振
        </div>
    """)

    put_html(f"""
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px;">
        <div style="background: rgba(249,115,22,0.1); border: 1px solid rgba(249,115,22,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
            <div style="font-size: 11px; color: #fb923c; font-weight: 600;">📰 新闻缓冲</div>
            <div style="font-size: 9px; color: #94a3b8;">{news_buffer_size} 条</div>
        </div>
        <div style="background: rgba(168,85,247,0.1); border: 1px solid rgba(168,85,247,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
            <div style="font-size: 11px; color: #a855f7; font-weight: 600;">👁️ 注意力缓冲</div>
            <div style="font-size: 9px; color: #94a3b8;">{attention_buffer_size} 条</div>
        </div>
        <div style="background: rgba(20,184,166,0.1); border: 1px solid rgba(20,184,166,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
            <div style="font-size: 11px; color: #14b8a6; font-weight: 600;">📊 市场缓冲</div>
            <div style="font-size: 9px; color: #94a3b8;">{market_buffer_size} 条</div>
        </div>
    </div>
    """)

    put_html(f"""
    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 14px;">
        <div style="background: rgba(96,165,250,0.12); border: 1px solid rgba(96,165,250,0.25); padding: 10px 14px; border-radius: 8px; text-align: center;">
            <div style="font-size: 10px; color: #64748b; margin-bottom: 2px;">⚡ 板块共振历史</div>
            <div style="font-size: 18px; font-weight: 700; color: #60a5fa;">{resonance_history_size}</div>
            <div style="font-size: 9px; color: #94a3b8;">近1分钟: {recent_resonance_count}</div>
        </div>
        <div style="background: rgba(249,115,22,0.12); border: 1px solid rgba(249,115,22,0.25); padding: 10px 14px; border-radius: 8px; text-align: center;">
            <div style="font-size: 10px; color: #64748b; margin-bottom: 2px;">🌐 市场共振历史</div>
            <div style="font-size: 18px; font-weight: 700; color: #fb923c;">{market_resonance_history_size}</div>
            <div style="font-size: 9px; color: #94a3b8;">近1分钟: {recent_market_resonance_count}</div>
        </div>
    </div>
    """)

    put_html("""
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px;">
        <div style="background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
            <div style="font-size: 11px; color: #60a5fa; font-weight: 600;">板块共振</div>
            <div style="font-size: 10px; color: #94a3b8;">新闻 × 注意力</div>
            <div style="font-size: 9px; color: #64748b; margin-top: 2px;">AI/芯片/新能源</div>
        </div>
        <div style="background: rgba(168,85,247,0.1); border: 1px solid rgba(168,85,247,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
            <div style="font-size: 11px; color: #a855f7; font-weight: 600;">宏观共振</div>
            <div style="font-size: 10px; color: #94a3b8;">新闻 × 宏观叙事</div>
            <div style="font-size: 9px; color: #64748b; margin-top: 2px;">流动性/全球宏观</div>
        </div>
        <div style="background: rgba(20,184,166,0.1); border: 1px solid rgba(20,184,166,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
            <div style="font-size: 11px; color: #14b8a6; font-weight: 600;">市场共振</div>
            <div style="font-size: 10px; color: #94a3b8;">市场 × 市场</div>
            <div style="font-size: 9px; color: #64748b; margin-top: 2px;">纳斯达克×标普</div>
        </div>
    </div>
    """)

    if high_resonance_blocks:
        block_bars = ""
        for block_id, avg_score in high_resonance_blocks[:5]:
            bar_width = min(100, int(avg_score * 100))
            score_color = '#f87171' if avg_score >= 0.85 else ('#fb923c' if avg_score >= 0.7 else '#60a5fa')
            block_bars += f'''
            <div style="margin-bottom: 6px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; margin-bottom: 2px;">
                    <span style="color: #cbd5e1;">{block_id}</span>
                    <span style="color: {score_color}; font-weight: 600;">{avg_score:.2f}</span>
                </div>
                <div style="height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
                    <div style="width: {bar_width}%; height: 100%; background: linear-gradient(90deg, {score_color}, {score_color}cc); border-radius: 2px;"></div>
                </div>
            </div>
            '''

        put_html(f"""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            padding: 12px;
        ">
            <div style="font-size: 11px; font-weight: 600; color: #f97316; margin-bottom: 8px;">
                🔥 高共振板块
            </div>
            {block_bars}
        </div>
        """)

    if recent_resonances:
        resonance_items = ""
        for res in recent_resonances[-6:]:
            res_type_color = resonance_type_colors.get(res.resonance_type.value, '#60a5fa')
            sentiment_icon = "📈" if res.news_sentiment > 0.2 else "📉" if res.news_sentiment < -0.2 else "📊"
            attention_icon = "🔥" if res.attention_weight > 0.6 else "⚡" if res.attention_weight > 0.3 else "💤"
            ts_str = format_timestamp(res.timestamp) if res.timestamp else "-"

            resonance_items += f"""
            <div style="display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: rgba(255,255,255,0.02); border-radius: 6px; margin-bottom: 4px; border-left: 2px solid {res_type_color};">
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 11px; font-weight: 600; color: #cbd5e1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{res.block_name or res.block_id}</div>
                    <div style="font-size: 9px; color: #64748b;">{sentiment_icon} {res.news_sentiment:+.2f} {attention_icon} {res.attention_weight:.2f}</div>
                </div>
                <div style="text-align: right; flex-shrink: 0;">
                    <div style="font-size: 11px; font-weight: 600; color: {res_type_color};">{res.resonance_score:.2f}</div>
                    <div style="font-size: 9px; color: #475569;">{ts_str[-8:]}</div>
                </div>
            </div>
            """

        put_html(f"""
        <div style="
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            padding: 12px;
        ">
            <div style="font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 8px;">
                📋 最近共振信号
            </div>
            {resonance_items}
        </div>
        """)

    resonance_list = market_resonance_summary.get('共振列表', [])
    if resonance_list:
        market_resonance_items = ""
        for res in resonance_list[:6]:
            res_type_color = market_resonance_type_colors.get('intensity', '#f97316')
            change_str = f"{res['market_change']:+.1f}%" if isinstance(res['market_change'], (int, float)) else res.get('market_change', 'N/A')
            market_resonance_items += f"""
            <div style="display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: rgba(255,255,255,0.02); border-radius: 6px; margin-bottom: 4px; border-left: 2px solid {res_type_color};">
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 11px; font-weight: 600; color: #cbd5e1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{res['market_name'] or res['market_index']}</div>
                    <div style="font-size: 9px; color: #64748b;">{res['narrative']} {change_str}</div>
                </div>
                <div style="text-align: right; flex-shrink: 0;">
                    <div style="font-size: 11px; font-weight: 600; color: {res_type_color};">{res['resonance_score']:.2f}</div>
                    <div style="font-size: 9px; color: #475569;">{res.get('stage', 'N/A')}</div>
                </div>
            </div>
            """

        put_html(f"""
        <div style="
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            padding: 12px;
        ">
            <div style="font-size: 11px; font-weight: 600; color: #f97316; margin-bottom: 8px;">
                🌐 市场共振信号
            </div>
            {market_resonance_items}
        </div>
        """)

    put_html("</div>")
