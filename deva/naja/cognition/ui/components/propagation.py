"""
Propagation 组件
"""


def render_propagation(ui):
    if not ui.engine:
        return

    try:
        newsmind = getattr(ui.engine, '_news_mind', None)
        if not newsmind:
            return
        propagation_engine = getattr(newsmind, 'propagation_engine', None)
        if not propagation_engine:
            return
    except Exception:
        return

    from pywebio.output import put_html

    structure = propagation_engine.get_liquidity_structure()
    if "error" in structure:
        return

    active_markets = structure.get("active_markets", [])
    markets = structure.get("markets", {})
    edges = structure.get("edges", {})

    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #10b981;">
                🌐 全球流动性传播网络
            </div>
            <div style="font-size: 10px; color: #64748b;">
                {len(active_markets)} 个活跃市场 | {len(edges)} 条传播路径
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            节点变化 → 沿边传播 → 验证结果 → 动态调权
        </div>
    """)

    if not active_markets:
        put_html("""
        <div style="text-align: center; padding: 20px; color: #64748b; font-size: 12px;">
            暂无活跃市场变化，等待数据流入...
        </div>
        """)
    else:
        put_html(f"""
        <div style="margin-bottom: 14px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">活跃市场 ({len(active_markets)})</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            """)
        for market_id in active_markets[:8]:
            m_info = markets.get(market_id, {})
            m_name = m_info.get("name", market_id)
            level = m_info.get("attention_level", "unknown")
            score = m_info.get("attention_score", 0)

            level_colors = {
                "critical": "#ef4444",
                "high": "#f97316",
                "medium": "#eab308",
                "low": "#22c55e",
                "dormant": "#64748b",
            }
            color = level_colors.get(level, "#64748b")

            put_html(f"""
            <div style="
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 4px 10px;
                background: {color}20;
                border: 1px solid {color}50;
                border-radius: 6px;
            ">
                <span style="width: 8px; height: 8px; border-radius: 50%; background: {color};"></span>
                <span style="font-size: 11px; color: #cbd5e1;">{m_name}</span>
                <span style="font-size: 10px; color: {color};">{score:.2f}</span>
            </div>
            """)
        put_html("</div></div>")

    if edges:
        put_html("""
        <div style="margin-bottom: 14px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">活跃传播路径</div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
            """)
        for edge_key, e_info in sorted(edges.items(), key=lambda x: -x[1].get("current_weight", 0))[:5]:
            from_m = e_info.get("from_market", "")
            to_m = e_info.get("to_market", "")
            weight = e_info.get("current_weight", 0)
            conf = e_info.get("confidence", 0)
            delay = e_info.get("delay_hours", 0)
            rate = e_info.get("propagation_rate", 0)

            weight_color = "#10b981" if weight > 0.7 else ("#eab308" if weight > 0.4 else "#64748b")

            put_html(f"""
            <div style="
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 6px 10px;
                background: rgba(255,255,255,0.02);
                border-radius: 6px;
                font-size: 11px;
            ">
                <span style="color: #10b981;">{from_m}</span>
                <span style="color: #64748b;">→</span>
                <span style="color: #f97316;">{to_m}</span>
                <span style="color: #475569;">|</span>
                <span style="color: {weight_color};">强度 {weight:.2f}</span>
                <span style="color: #64748b;">置信 {conf:.0%}</span>
                <span style="color: #64748b;">延迟 {delay:.0f}h</span>
            </div>
            """)
        put_html("</div></div>")

    resonance_signals = propagation_engine.get_resonance_signals()
    if resonance_signals:
        put_html("""
        <div>
            <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">共振信号</div>
            <div style="display: flex; flex-direction: column; gap: 4px;">
            """)
        for sig in resonance_signals[:3]:
            name = sig.get("name", "")
            change = sig.get("change", 0)
            attention = sig.get("attention_score", 0)
            change_color = "#10b981" if change > 0 else "#ef4444"

            put_html(f"""
            <div style="
                display: flex;
                justify-content: space-between;
                padding: 4px 8px;
                background: rgba(255,255,255,0.02);
                border-radius: 4px;
                font-size: 11px;
            ">
                <span style="color: #cbd5e1;">{name}</span>
                <span style="color: {change_color};">{change:+.2f}%</span>
                <span style="color: #64748b;">注意力 {attention:.2f}</span>
            </div>
            """)
        put_html("</div></div>")

    put_html('</div>')